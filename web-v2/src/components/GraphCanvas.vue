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
   * 需要置于视口正中的节点 id。
   * fitView 居中的是整图包围盒，而「以某节点为核心」的图（如决策图的核心任务）
   * 需要焦点节点本身居中，所以 fitView 之后再补一次平移。
   */
  focusId: { type: [String, Number], default: '' }
})

const emit = defineEmits(['ready', 'data-rendered', 'node-click', 'edge-click', 'canvas-click'])

const rootEl = ref(null)
const containerEl = ref(null)

let graph = null
let resizeObserver = null
let resizeTimer = null
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

  const edges = (src.edges || []).map((e, i) => ({
    id: e.id ? String(e.id) : `e-${i}`,
    source: String(e.source_id),
    target: String(e.target_id),
    data: {
      label: e.type ?? e.label ?? '',
      original: e
    }
  }))

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
    autoFit: props.autoFit,
    autoResize: props.autoResize,
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
        labelText: (d) => edgeStyleFn('labelText', d) ?? d.data.label,
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

  emit('ready', graph)
  syncData()
}

/**
 * 把焦点节点尽量推向视口中心。
 *
 * 为什么不是「推到正中心」：fitView 之后内容包围盒已居中，
 * 若内容相对焦点严重不对称（决策图里左侧分支远多于右侧），
 * 强行把焦点移到正中心必须大幅缩小，整张图会变得很小、反而更难读。
 *
 * 所以采用有界折中：允许最多损失 ZOOM_BUDGET 的缩放，
 * 在这个约束下求出能推多远（k ∈ [0,1]），按 k 做部分平移。
 * 任何一步取不到值就放弃，保留 fitView 结果。
 */
const centerOnFocus = async () => {
  if (!graph || !props.focusId) return
  try {
    const nodes = props.graphData?.nodes || []
    if (!nodes.length) return

    const at = (id) => {
      const p = graph.getElementPosition(id)
      const x = Array.isArray(p) ? p[0] : p?.x
      const y = Array.isArray(p) ? p[1] : p?.y
      return Number.isFinite(x) && Number.isFinite(y) ? [x, y] : null
    }

    const focus = at(props.focusId)
    if (!focus) return
    const [px, py] = focus

    let minX = Infinity
    let maxX = -Infinity
    let minY = Infinity
    let maxY = -Infinity
    for (const n of nodes) {
      const p = at(String(n.id))
      if (!p) continue
      minX = Math.min(minX, p[0]); maxX = Math.max(maxX, p[0])
      minY = Math.min(minY, p[1]); maxY = Math.max(maxY, p[1])
    }
    if (!Number.isFinite(minX)) return

    const w = containerEl.value?.offsetWidth || 0
    const h = containerEl.value?.offsetHeight || 0
    if (!w || !h) return

    const PAD = 34
    const MARGIN = 26 // 节点半径 + 下方标签的余量
    const ZOOM_BUDGET = 0.86 // 允许的最大缩放损失
    const cx = w / 2
    const cy = h / 2
    const halfW = Math.max(1, cx - PAD)
    const halfH = Math.max(1, cy - PAD)

    const z = Number(graph.getZoom?.()) || 1
    const bcx = (minX + maxX) / 2
    const bcy = (minY + maxY) / 2

    // 完全居中所需的屏幕位移
    const dx = -(px - bcx) * z
    const dy = -(py - bcy) * z

    // 内容半宽/半高（屏幕像素，含节点与标签余量）
    const ax = ((maxX - minX) / 2 + MARGIN) * z
    const ay = ((maxY - minY) / 2 + MARGIN) * z

    // 位移 |d|×k 后需要缩放 s ≤ half/(k|d| + a)；令 s ≥ ZOOM_BUDGET 反解 k
    const kOf = (half, a, d) => {
      if (Math.abs(d) < 0.5) return 1
      const k = (half / ZOOM_BUDGET - a) / Math.abs(d)
      return Math.max(0, Math.min(1, k))
    }
    const k = Math.min(kOf(halfW, ax, dx), kOf(halfH, ay, dy))
    if (!Number.isFinite(k) || k <= 0.01) return

    // 这个 k 下必须的缩放（≤1）。少了这一步，位移后的内容会被画布裁掉。
    const needW = k * Math.abs(dx) + ax
    const needH = k * Math.abs(dy) + ay
    const s = Math.min(1, needW > 0 ? halfW / needW : 1, needH > 0 ? halfH / needH : 1)
    const z2 = z * s
    if (!Number.isFinite(z2) || z2 <= 0) return

    if (Math.abs(s - 1) > 0.005) {
      try {
        await graph.zoomTo?.(z2)
      } catch {
        /* 缩放不可用时退回纯平移，宁可少移一点也不裁内容 */
        return
      }
    }

    // 焦点应落到「视口中心再往回退 (1-k)·s·|d|」的位置
    const targetFx = cx - (1 - k) * dx * s
    const targetFy = cy - (1 - k) * dy * s
    graph.translateTo([targetFx - px * z2, targetFy - py * z2])
  } catch {
    /* API 形状不符时保持 fitView 结果 */
  }
}

const syncData = async () => {
  if (!graph) return
  graph.setData(toG6Data())
  await graph.render()
  if (props.autoFit && typeof graph.fitView === 'function') {
    try {
      // 留出内边距：fitView 的包围盒不含节点下方的标签，不留边会被画布裁掉
      await graph.fitView({ direction: 'both', padding: 34 })
    } catch {
      /* 空图或参数不支持时忽略 */
    }
  }
  // 力导向布局要等模拟收敛后再定位，否则拿到的是中途坐标
  if (props.focusId) {
    setTimeout(() => { centerOnFocus() }, props.layoutOptions?.type === 'radial' ? 120 : 700)
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
      }, 120)
    })
    resizeObserver.observe(rootEl.value)
  }
})

onBeforeUnmount(() => {
  clearTimeout(resizeTimer)
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
    try {
      await graph?.fitView?.({ direction: 'both', padding: 34 })
    } catch {
      /* ignore */
    }
    centerOnFocus()
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
