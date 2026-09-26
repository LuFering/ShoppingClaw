<template>
  <div ref="rootEl" class="graph-canvas">
    <div ref="containerEl" class="graph-canvas__inner" />
    <p v-if="!hasData" class="graph-canvas__empty">暂无图谱数据</p>
  </div>
</template>

<script setup>
/**
 * 通用力导向图谱容器（G6 v5）。
 *
 * 刻意做成「不含业务」的一层：节点/边的样式全部由外部通过 resolver 传入，
 * 本组件只负责 G6 实例生命周期、尺寸、布局、事件与数据映射。
 * 业务语义（类型取色、状态降透明、关系线型）放在 PurchaseDecisionGraph 一类的领域组件里。
 *
 * 实现参照 Yuxi web/src/components/GraphCanvas.vue（同为 G6 v5），
 * 保留其已验证的布局参数与事件写法，去掉本项目不需要的 Chunk 过滤与统计面板。
 */
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { Graph } from '@antv/g6'
import { themeColor } from '@/utils/themeColors'

const props = defineProps({
  graphData: { type: Object, default: () => ({ nodes: [], edges: [] }) },
  labelField: { type: String, default: 'name' },
  autoFit: { type: Boolean, default: true },
  autoResize: { type: Boolean, default: true },
  /** 无显式 resolver 时，按连接度决定节点大小 */
  sizeByDegree: { type: Boolean, default: true },
  sizeRange: { type: Array, default: () => [16, 46] },
  layoutOptions: { type: Object, default: () => ({}) },
  /** (nodeData) => { size, fill, stroke, lineWidth, opacity, labelFill, labelText } */
  resolveNode: { type: Function, default: null },
  /** (edgeData) => { stroke, lineDash, opacity, labelFill } */
  resolveEdge: { type: Function, default: null },
  /**
   * 「以哪个节点为核心」。
   *
   * 用途只有一个：radial 布局的 `focusNode`，决定同心环按到谁的距离来排。
   * **不参与相机定位** —— 相机一律按内容包围盒居中，否则左重右轻的图
   * 会被推偏（详见 centerOnFocus 的说明）。
   */
  focusId: { type: [String, Number], default: '' }
})

const emit = defineEmits(['ready', 'data-rendered', 'node-click', 'edge-click', 'canvas-click'])

const rootEl = ref(null)
const containerEl = ref(null)

let graph = null
let resizeObserver = null
let resizeTimer = null
let centerTimer = null
let syncing = false
let syncPending = false
/**
 * 「代」计数器：每次重建 G6 实例自增一次。
 *
 * ⚠️ 这是修「多点几次辐射/力导向，图就消失」的关键。
 * `syncing` 是一把**跨实例**的锁，但 `syncData` 的 `await graph.render()`
 * 绑在**某一代实例**上。切换布局会 `initGraph()` 重建实例，而上一代那次
 * `syncData` 还卡在它的 `render()` 里（实测永不返回）—— 锁因此永不释放。
 * 之后每一代 `syncData` 进来都只把 `syncPending` 置 true 就返回，
 * 而负责排空它的那个循环已经随旧实例一起死了 → 新实例一次都没渲染过，
 * 画布上一个 canvas 都不剩，看起来就是「图消失了」（实测 canvasEls 0）。
 *
 * 有了代号：旧的那次醒来发现代号变了就自己退出，且**不碰锁**；
 * `initGraph` 负责把锁重置给新一代。
 */
let syncGen = 0
let renderRetries = 0
const MAX_RETRIES = 8

const hasData = computed(() => {
  const d = props.graphData || {}
  return (d.nodes?.length || 0) > 0 || (d.edges?.length || 0) > 0
})

/** 与 Yuxi 一致的 d3-force 参数：charge 拉开、link 收拢、collide 防重叠 */
const BASE_LAYOUT = {
  type: 'd3-force',
  preventOverlap: true,
  alphaDecay: 0.1,
  alphaMin: 0.01,
  velocityDecay: 0.6,
  iterations: 150,
  force: {
    center: { x: 0.5, y: 0.5, strength: 0.1 },
    charge: { strength: -420, distanceMax: 720 },
    link: { distance: 104, strength: 0.8 }
  },
  collide: { radius: 46, strength: 0.8, iterations: 3 }
}

const cssVar = (name, fallback) => themeColor(name, fallback)

/** 连接度：节点的连线条数，作为「重要程度」的缺省代理 */
const buildDegreeMap = (edges) => {
  const m = new Map()
  for (const e of edges || []) {
    const s = String(e.source_id)
    const t = String(e.target_id)
    m.set(s, (m.get(s) || 0) + 1)
    m.set(t, (m.get(t) || 0) + 1)
  }
  return m
}

const toG6Data = () => {
  const src = props.graphData || { nodes: [], edges: [] }
  const degrees = buildDegreeMap(src.edges)
  const maxDeg = Math.max(1, ...degrees.values())

  const nodes = (src.nodes || []).map((n) => {
    const degree = degrees.get(String(n.id)) || 0
    return {
      id: String(n.id),
      data: {
        label: n[props.labelField] ?? n.name ?? String(n.id),
        degree,
        maxDeg,
        original: n
      }
    }
  })

  // 同一对起止点之间可能有多条边，再加同源的兄弟边 —— 序号用来错开曲率，
  // 否则它们会画成同一条线（见 buildConfig 里 curveOffset 的说明）
  const pairSeen = new Map()
  const edges = (src.edges || []).map((e, i) => {
    const key = `${e.source_id}->${e.target_id}`
    const dup = pairSeen.get(key) || 0
    pairSeen.set(key, dup + 1)
    return {
      id: e.id ? String(e.id) : `e-${i}`,
      source: String(e.source_id),
      target: String(e.target_id),
      data: {
        label: e.type ?? e.label ?? '',
        original: e,
        // 第几条同名边 —— 曲率按它递增，让平行边分得开
        dupIndex: dup
      }
    }
  })

  return { nodes, edges }
}

const defaultNodeStyle = (d) => {
  const [min, max] = props.sizeRange
  const deg = d.data.degree || 0
  const size = props.sizeByDegree
    ? Math.min(max, min + Math.round((deg / (d.data.maxDeg || 1)) * (max - min)))
    : Math.round((min + max) / 2)
  return { size, opacity: 0.92 }
}

const nodeStyleFn = (key, d) => {
  const resolved = props.resolveNode ? props.resolveNode(d.data.original, d.data) || {} : {}
  if (resolved[key] !== undefined) return resolved[key]
  return defaultNodeStyle(d)[key]
}

const edgeStyleFn = (key, d) => {
  const resolved = props.resolveEdge ? props.resolveEdge(d.data.original, d.data) || {} : {}
  return resolved[key]
}

const buildConfig = (width, height) => {
  // 画布底色在 canvas 里有一个妙用：节点用它描边，重叠时自然分层，不需要阴影
  const canvasBg = () => cssVar('--bg-surface', '#ffffff')

  // 传入带 type 的完整布局对象时直接采用（如 radial 需要 focusNode，与力导向参数完全不同）；
  // 否则把参数合进默认的力导向配置
  const layout = props.layoutOptions?.type
    ? props.layoutOptions
    : { ...BASE_LAYOUT, ...props.layoutOptions }

  return {
    container: containerEl.value,
    width,
    height,
    // ⚠️ 关掉 G6 的内置自适应。它的 fitView 读 `canvas.getBounds()`（绘制后
    // 的包围盒），而 render() 里 fitView 与 postLayout 并发，会拿到尚未布局
    // 完的范围，算出随机且离谱的 zoom。自适应改由 centerOnFocus 自己做。
    autoFit: false,
    autoResize: props.autoResize,
    // padding 仍要留着：G6 的 paddingOffset 参与其它变换
    padding: 34,
    layout,
    node: {
      type: 'circle',
      style: {
        size: (d) => nodeStyleFn('size', d),
        fill: (d) => nodeStyleFn('fill', d) ?? canvasBg(),
        stroke: (d) => nodeStyleFn('stroke', d) ?? canvasBg(),
        lineWidth: (d) => nodeStyleFn('lineWidth', d) ?? 1.5,
        opacity: (d) => nodeStyleFn('opacity', d) ?? 0.92,
        labelText: (d) => nodeStyleFn('labelText', d) ?? d.data.label,
        labelFill: (d) => nodeStyleFn('labelFill', d) ?? cssVar('--text', '#2b3034'),
        labelFontSize: 11,
        labelPlacement: 'bottom',
        labelOffsetY: 4,
        labelWordWrap: true,
        labelMaxWidth: '320%',
        cursor: 'pointer'
      }
    },
    edge: {
      type: 'quadratic',
      style: {
        // ⚠️ 曲率按「第几条同名边」错开。原先所有边曲率相同，从同一个
        // 品类节点射向多件候选时，几条线会**画成同一条**，看上去就是
        // 「很多线重重叠在一起」（用户截图里的观感问题）。
        curveOffset: (d) => 18 + (d.data.dupIndex || 0) * 26,
        labelText: (d) => {
          const forced = edgeStyleFn('labelText', d)
          if (forced !== undefined) return forced
          // 关系标签只有「很多条边共用同一个词」时才是噪音 ——
          // 实测几十条「候选」叠在一起，字都糊成一团。
          // 领域层用 labelText:'' 明确要求不显示时也照办（见 resolveEdge）。
          return d.data.label
        },
        labelFill: (d) => edgeStyleFn('labelFill', d) ?? cssVar('--text-muted', '#6b727a'),
        labelFontSize: 10,
        labelBackground: true,
        labelBackgroundFill: () => canvasBg(),
        labelBackgroundRadius: 3,
        labelPadding: [1, 4],
        stroke: (d) => edgeStyleFn('stroke', d) ?? cssVar('--border-strong', '#d2d5cf'),
        lineDash: (d) => edgeStyleFn('lineDash', d) ?? undefined,
        opacity: (d) => edgeStyleFn('opacity', d) ?? 0.75,
        lineWidth: 1.3,
        endArrow: true,
        endArrowType: 'vee',
        endArrowSize: 7
      }
    },
    behaviors: ['drag-element', 'zoom-canvas', 'drag-canvas', 'hover-activate']
  }
}

const destroyGraph = () => {
  if (!graph) return
  // 重建实例前取消待执行的居中：那个定时器捕获的是**旧实例**，
  // 让它跑完会对着已经销毁的图调 API（静默失败，但会掩盖真正的居中）
  if (centerTimer) { clearTimeout(centerTimer); centerTimer = null }
  try {
    graph.destroy()
  } catch {
    /* 销毁失败不阻塞后续重建 */
  }
  graph = null
}

const initGraph = () => {
  if (!containerEl.value) return
  const width = containerEl.value.offsetWidth
  const height = containerEl.value.offsetHeight

  // 容器尚未布局完成时尺寸为 0，G6 会画错，等下一帧重试
  if (width === 0 || height === 0) {
    if (renderRetries < MAX_RETRIES) {
      renderRetries += 1
      requestAnimationFrame(initGraph)
    }
    return
  }
  renderRetries = 0

  destroyGraph()
  // ⚠️ 重建实例 = 换一代。上一代可能还卡在 render() 里握着锁，
  // 必须在这里作废它并把锁交还给新一代（见 syncGen 的说明）。
  syncGen += 1
  syncing = false
  syncPending = false
  graph = new Graph(buildConfig(width, height))

  graph.on('node:click', (evt) => {
    const id = evt?.target?.id
    if (id) emit('node-click', graph.getNodeData(id))
  })
  graph.on('edge:click', (evt) => {
    const id = evt?.target?.id
    if (id) emit('edge-click', graph.getEdgeData(id))
  })
  graph.on('canvas:click', (evt) => {
    if (!evt?.target) emit('canvas-click')
  })

  // 布局真正跑完的时点。力导向在此之前取到的都是中途坐标，
  // 据此居中必然偏 —— 这是主路径，syncData 里的定时器只是兜底。
  graph.on('afterlayout', () => scheduleCenter())

  emit('ready', graph)
  syncData()
}

/**
 * 自适应：把整张图缩放并居中到视口。
 *
 * ═══════════════════════════════════════════════════════════════════
 * 2026-09-25 重写：不再用 G6 的 fitView，也不再自己混坐标系
 * ═══════════════════════════════════════════════════════════════════
 *
 * 症状是「图老是偏左 / 偏右，一边被裁、另一边一大片空白」。
 * 实测（真实 Chrome + CDP 量 G6 实例）抓到两个独立的原因：
 *
 * **原因一：G6 的 fitView 在 zoom 上不可靠。**
 * 同一个 run 反复加载，zoom 会在 1.46 / 4.24 / 7.63 之间跳。原因是
 * `fitView` 读的是 `canvas.getBounds()` —— 那是**绘制后**的包围盒，
 * 而 `render()` 里 `fitView` 与 `postLayout()` 是并发的
 * （`Promise.all([draw(), postLayout()])` 之后才 autoFit）。
 * 拿到尚未布局完的包围盒（实测只有 67×68 世界单位），就会算出 7.5 倍
 * 这种离谱的放大，整张图被放大到画布外，看起来就是「偏了、被裁了」。
 *
 * **原因二：原来的 centerOnFocus 在世界/视口坐标之间混用。**
 * `translateTo` 收的是视口位移（G6 内部按 `delta = -translate / zoom`
 * 作用到相机），旧代码却传 `targetFx - px * z2`，把世界坐标乘个 zoom
 * 当屏幕坐标用，偏差恰好是 `w/2 × (z2 - 1)`。
 *
 * 所以整段重写为**自己算、只用两个稳定原语**：
 *   · `zoomTo(z)`      —— 只改缩放，不动相机位置
 *   · `translateBy(t)` —— 只平移，t 就是视口位移
 * 内容范围用**节点位置**（`getElementPosition`，布局产物，稳定）而不是
 * 绘制包围盒；缩放系数一次算准，再在视口坐标里做一次居中平移。
 * 全程不依赖任何「绘制完没有」的时序，因此可复现。
 *
 * 居中的是**内容包围盒**，不是 focusId 那个节点 —— 后者只决定 radial
 * 布局怎么排环。这一点单独踩过坑，见下面注释。
 */
const centerOnFocus = async () => {
  if (!graph) return
  try {
    const nodes = props.graphData?.nodes || []
    if (!nodes.length) return

    const w = containerEl.value?.offsetWidth || 0
    const h = containerEl.value?.offsetHeight || 0
    if (!w || !h) return

    const PAD = 34
    // 节点下方的标签、节点半径不在节点坐标里，按最大节点尺寸留余量
    const EXTRA_W = 92
    const EXTRA_H = 104

    // ── 1. 世界坐标下的内容范围（节点位置，布局产物） ──
    const posOf = (id) => {
      try {
        const p = graph.getElementPosition(String(id))
        const x = Array.isArray(p) ? p[0] : p?.x
        const y = Array.isArray(p) ? p[1] : p?.y
        return Number.isFinite(x) && Number.isFinite(y) ? [x, y] : null
      } catch {
        return null
      }
    }

    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
    for (const n of nodes) {
      const p = posOf(n.id)
      if (!p) continue
      minX = Math.min(minX, p[0]); maxX = Math.max(maxX, p[0])
      minY = Math.min(minY, p[1]); maxY = Math.max(maxY, p[1])
    }
    if (!Number.isFinite(minX)) return

    const worldW = Math.max(1, maxX - minX) + EXTRA_W
    const worldH = Math.max(1, maxY - minY) + EXTRA_H

    // ── 2. 一次算准缩放：整图要装进 (w-2PAD, h-2PAD) ──
    // 上限 1：不放大超过原始尺寸（放大只会让图更糊，信息量不变）
    const fitZoom = Math.min(1, (w - 2 * PAD) / worldW, (h - 2 * PAD) / worldH)
    if (!Number.isFinite(fitZoom) || fitZoom <= 0) return

    // zoomTo 只改缩放，不动相机位置 —— 此时内容的视口坐标可以直接读出来
    await graph.zoomTo(fitZoom)

    // ── 3. 在视口坐标里居中 ──
    // 优先让 focus 节点居中；若那样会把内容推出画布，则退到「内容居中」。
    const toVp = (p) => {
      try {
        const v = graph.getViewportByCanvas(p)
        const x = Array.isArray(v) ? v[0] : v?.x
        const y = Array.isArray(v) ? v[1] : v?.y
        return Number.isFinite(x) && Number.isFinite(y) ? [x, y] : null
      } catch {
        return null
      }
    }

    let vminX = Infinity, vmaxX = -Infinity, vminY = Infinity, vmaxY = -Infinity
    for (const n of nodes) {
      const p = posOf(n.id)
      if (!p) continue
      const v = toVp(p)
      if (!v) continue
      vminX = Math.min(vminX, v[0]); vmaxX = Math.max(vmaxX, v[0])
      vminY = Math.min(vminY, v[1]); vmaxY = Math.max(vmaxY, v[1])
    }
    if (!Number.isFinite(vminX)) return

    const cx = w / 2
    const cy = h / 2
    const contentCx = (vminX + vmaxX) / 2
    const contentCy = (vminY + vmaxY) / 2

    // ═══════════════════════════════════════════════════════════════
    // 居中「内容」，不是居中「焦点节点」
    // ═══════════════════════════════════════════════════════════════
    //
    // 原先这里会让 focusId 优先居中，只要内容还能塞进画布就这么做。
    // 结果就是用户反复说的「图老是偏左」：决策图天然左重右轻
    // （左边挂着一串候选商品，右边只有几条依据），把中间那个核心任务
    // 摆到正中央，整张图必然被推向左 —— 实测左留白 146px、右留白 328px。
    //
    // 用户要的是**整张图看着居中**，不是「核心节点在正中」。所以改成
    // 一律按内容包围盒居中。focusId 仍然有用 —— 它是 radial 布局的
    // focusNode（决定同心环怎么排），只是不再参与相机定位。
    let tx = cx - contentCx
    let ty = cy - contentCy

    // 兜底夹取：内容必须完整可见。极端情况下（内容仍比画布大）取中点，
    // 让两侧超出量均等，而不是硬贴一边。
    const clamp = (t, lo, hi) => (lo > hi ? (lo + hi) / 2 : Math.max(lo, Math.min(hi, t)))
    tx = clamp(tx, PAD - vminX, (w - PAD) - vmaxX)
    ty = clamp(ty, PAD - vminY, (h - PAD) - vmaxY)

    if (Math.abs(tx) < 0.5 && Math.abs(ty) < 0.5) return   // 已经到位，别白动一次

    await graph.translateBy([tx, ty])
  } catch {
    /* API 形状不符时保持当前视口，不做任何事 —— 宁可不动，也不要乱动 */
  }
}

/**
 * 安排一次居中（防抖）。
 *
 * 时机是这里最容易出错的地方：布局是**异步**的，`await graph.render()`
 * 返回时力导向还在跑，此刻取到的节点坐标是中途值，据此算出的平移必然偏。
 * 所以居中不能只做一次，要在布局收敛之后再补一次。
 *
 * 两条触发路径，都汇进同一个防抖定时器，只有最后一次生效：
 *   · `afterlayout` —— G6 布局真正跑完时发的事件（主路径）
 *   · syncData 里的兜底调用 —— 万一某布局不发该事件
 */
const CENTER_DEBOUNCE = 80
const scheduleCenter = (delay = CENTER_DEBOUNCE) => {
  if (!props.autoFit) return
  if (centerTimer) clearTimeout(centerTimer)
  centerTimer = setTimeout(() => {
    centerTimer = null
    centerOnFocus()
  }, delay)
}

/**
 * 把最新数据同步到图上。
 *
 * ═══════════════════════════════════════════════════════════════════
 * 2026-09-25 修正：并发调用会丢节点
 * ═══════════════════════════════════════════════════════════════════
 *
 * 症状：17 个节点的数据，画布上只画出前 6 个（第一批 intake 的），
 * 后面 SSE 推来的全都不见了。
 *
 * 原因：`render()` 是异步的，而 deep watcher 每收到一次 graphData 变化就
 * 调一次 syncData。工作台在推演期间会连续推 7 次图变更，于是多个
 * `setData()` + `render()` **重叠执行** —— 前一次的渲染还没走完，数据就被
 * 下一次 `setData` 换掉了。G6 的更新流程在动画回调里按 id 取元素
 * （`elementMap[id].onUpdate`），元素已被后一次操作销毁 → 抛
 * `TypeError: Cannot read properties of undefined (reading 'onUpdate')`，
 * 那批元素就此丢失。
 *
 * 修法：**串行化**。同一时刻只允许一次同步在跑；期间到达的新数据只记一个
 * 「有待办」标记，等当前这次跑完再补一次（latest-wins）。这样既不会重叠，
 * 也不会因为节流而漏掉最后一次数据。
 *
 * `syncing` / `syncPending` 声明在文件顶部，与其它实例级状态放一起。
 */
const syncData = async () => {
  if (!graph) return
  const myGen = syncGen
  if (syncing) {
    // 正在渲染：记下「有新数据」，等它跑完再同步一次（只保留最后一次）
    syncPending = true
    return
  }
  syncing = true
  try {
    do {
      syncPending = false
      // 循环期间实例可能被销毁，或已被新一代取代 —— 这一代就此作废
      if (!graph || myGen !== syncGen) return
      graph.setData(toG6Data())
      await graph.render()
      // render 期间可能已经切过布局：那时这次的结果属于旧实例，直接作废
      if (!graph || myGen !== syncGen) return
      // 自适应统一交给 centerOnFocus（自己算缩放 + 居中，可复现）。
      // 不再调 graph.fitView()：它读的是**绘制后**的包围盒，而 render() 里
      // fitView 与 postLayout 是并发的，会拿到尚未布局完的范围，算出离谱的
      // zoom（实测 1.46 / 4.24 / 7.63 随机跳）。详见 centerOnFocus 的说明。
      // 兜底：radial 布局很快收敛，力导向要多等一会儿
      scheduleCenter(props.layoutOptions?.type === 'radial' ? 160 : 700)
    } while (syncPending)
  } finally {
    // ⚠️ 只有仍是当前代才释放锁。旧代若在这里无条件释放，
    // 会把新一代刚拿到的锁清掉，导致两个循环并发（正是丢节点的老毛病）。
    if (myGen === syncGen) syncing = false
  }
  emit('data-rendered', props.graphData)
}

onMounted(async () => {
  await nextTick()
  initGraph()

  if (props.autoResize && typeof ResizeObserver !== 'undefined' && rootEl.value) {
    resizeObserver = new ResizeObserver(() => {
      if (!graph) return
      clearTimeout(resizeTimer)
      resizeTimer = setTimeout(() => {
        const w = containerEl.value?.offsetWidth
        const h = containerEl.value?.offsetHeight
        if (!w || !h) return
        graph.setSize(w, h)
        // 画布尺寸变了，之前算的缩放/居中就不再适用 —— 重新适配一次
        scheduleCenter()
      }, 120)
    })
    resizeObserver.observe(rootEl.value)
  }
})

onBeforeUnmount(() => {
  clearTimeout(resizeTimer)
  if (centerTimer) { clearTimeout(centerTimer); centerTimer = null }
  resizeObserver?.disconnect()
  resizeObserver = null
  destroyGraph()
})

watch(
  () => props.graphData,
  () => {
    if (!graph) initGraph()
    else syncData()
  },
  { deep: true }
)

// 切换布局算法（辐射 ↔ 力导向）必须重建实例：只改配置不足以换算法
watch(
  () => props.layoutOptions,
  () => { initGraph() },
  { deep: true }
)

defineExpose({
  /** 供外部（如「跟随执行」开关）在数据变化后重新居中 */
  fitView: async () => {
    // 不再走 G6 的 fitView（原因见 buildConfig 的 autoFit 说明），
    // 直接走自己的调度：布局可能还在收敛，等它结束再算
    scheduleCenter()
  },
  getGraph: () => graph
})
</script>

<style lang="less" scoped>
.graph-canvas {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 240px;

  &__inner {
    width: 100%;
    height: 100%;
  }

  &__empty {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0;
    font-size: 0.76rem;
    color: var(--text-faint);
  }
}
</style>
