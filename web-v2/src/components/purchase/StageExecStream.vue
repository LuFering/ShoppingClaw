<template>
  <div class="xs">
    <header class="xs-head">
      <span class="xs-title">执行流</span>
      <span class="xs-prog mono">{{ totalCalls }} 次调用</span>
      <span v-if="live" class="xs-live">
        <i class="xs-live-dot" />{{ live.text }}
      </span>
      <span v-else-if="totalMs" class="xs-total mono">{{ fmtMs(totalMs) }}</span>
      <button v-if="!atBottom" class="xs-jump" type="button" @click="scrollToBottom">
        回到最新 ↓
      </button>
    </header>

    <div ref="scrollEl" class="xs-scroll" @scroll="onScroll">
      <!-- 开头锚点：让它「有始」 -->
      <p v-if="startLine" class="xs-start">{{ startLine }}</p>

      <section
        v-for="g in groups"
        :key="g.key"
        class="xg"
        :class="[`is-${g.state}`, { 'is-open': isOpen(g) }]"
      >
        <!--
          阶段头 = 结构。一行回答三件事：
            ① 这阶段在做什么（名字）
            ② 做完了吗、结果如何（统计徽章：排除 12/26、5 项维度…）
            ③ 花了多久
          已完成的阶段默认**收起**，只留这一行 —— 这就是「思路清晰」的来源：
          整条流程是 5 行，而不是 30 行。
        -->
        <!--
          「继续执行」不是阶段，是**一次中断的边界** —— 用户拍板后 agent
          从中断处接着走。它不该占一个阶段行（那会让人以为有个叫「继续执行」
          的步骤），做成一条淡分隔线：既标出「这里断过一次」，又不冒充步骤。
        -->
        <p v-if="g.separator" class="xg-sep">
          <span class="xg-sep-line" />
          <span class="xg-sep-text">{{ g.title }}</span>
          <span class="xg-sep-line" />
        </p>

        <button v-else class="xg-head" type="button" @click="toggle(g)">
          <span class="xg-dot" :class="`is-${g.state}`">
            <i v-if="g.state === 'running'" class="xg-dot-pulse" />
          </span>
          <span class="xg-name">{{ g.title }}</span>

          <!-- 实时：当前阶段显示正在做的那件事 -->
          <span v-if="g.state === 'running' && g.current" class="xg-now">
            {{ g.current.title || g.current.detail }}<i class="xs-caret" />
          </span>
          <!-- 已完成：结果统计徽章 -->
          <span v-else-if="g.badge" class="xg-badge mono">{{ g.badge }}</span>

          <span class="xg-ms mono">
            {{ g.state === 'running' ? elapsedOf(g) : fmtMs(g.ms) }}
          </span>
          <span v-if="g.rows.length" class="xg-chev" :class="{ open: isOpen(g) }">›</span>
        </button>

        <!-- 展开：这个阶段里具体做了什么（仍是状态行，不是日志） -->
        <div v-if="!g.separator && isOpen(g)" class="xg-body">
          <div v-for="r in g.rows" :key="r.uid" class="xs-row">
            <span class="xs-dot" :class="`is-${r.state}`" />
            <span v-if="r.grouped?.length" class="xs-mul mono">×{{ r.grouped.length }}</span>
            <span v-if="r.by && r.by !== 'llm'" class="xs-by" :class="`by-${r.by}`">
              {{ BY_LABEL[r.by] || r.by }}
            </span>
            <span class="xs-text">{{ r.title }}</span>
            <span v-if="briefOf(r)" class="xs-brief">· {{ briefOf(r) }}</span>
            <!-- 合并掉的那几次：列出来才是「不失信息」 -->
            <ul v-if="r.grouped?.length" class="xs-sub">
              <li v-for="(s, k) in r.grouped" :key="k">
                <span class="xs-sub-t">{{ s.title }}</span>
                <span v-if="briefOf(s)" class="xs-sub-b">{{ briefOf(s) }}</span>
              </li>
            </ul>
          </div>
          <p v-if="!g.rows.length" class="xs-none">（这一步没有留下明细）</p>
        </div>
      </section>

      <!--
        「正在思考」行 —— 模型思考期间界面不能毫无动静。
        ⚠️ 实测数据：建 run 之后有 **13.6 秒**没有任何事件（模型冷启动），
        一次 run 内还有 5 段 ≥5s 的静默。那段时间左栏完全静止，用户以为
        卡死了 —— 这正是「没有主智能体那样的缓冲等待体验」的来源。
        主智能体的做法是三点动画 + 文案 + 秒数，这里沿用同一套。
      -->
      <div v-if="waiting" class="xs-wait">
        <span class="xs-wait-dots"><i /><i /><i /></span>
        <span class="xs-wait-text">{{ waitText }}</span>
        <span class="xs-wait-sec mono">{{ waitSeconds }}s</span>
      </div>

      <!-- 收尾总结：让它「有终」 -->
      <div v-if="summary" class="xs-sum" :class="`is-${summary.state}`">
        <span class="xs-sum-mark">{{ summary.mark }}</span>
        <span class="xs-sum-text">{{ summary.text }}</span>
      </div>

      <p v-if="!groups.length && !summary" class="xs-empty">还没有开始执行。</p>
    </div>
  </div>
</template>

<script setup>
/**
 * 左栏 · 阶段化的执行流。
 *
 * ═══════════════════════════════════════════════════════════════════
 * 2026-09-27：从「时间序流水账」改成「阶段分组 + 收尾总结」
 * ═══════════════════════════════════════════════════════════════════
 * 用户反馈：「执行流还是达不到思路清晰、执行逻辑明确、状态实时、有始有终
 * 的效果」。
 *
 * 前三轮我都在做**减法**（压扁、合并、去详情），但那治不了根：
 * **时间序的流水账天然表达不出结构**。「先搜了床、又搜了沙发、中间插了
 * 一次风险查询」——这是发生顺序，不是任务逻辑。用户要的是「理解需求 →
 * 逐类搜筛 → 排风险 → 收敛交付」这个**结构**，以及「现在在哪一步、
 * 还剩几步」这个**方位**。
 *
 * 所以这一版换的是表达方式，不是密度：
 *   · **按阶段分组**：同阶段的调用收在一个可折叠块里。已完成的默认收起，
 *     整条流程从 30 行变成 5 行 —— 结构一眼可见。
 *   · **阶段头带结果统计**：「排除 12/26」「5 项维度」「定 5 件」。
 *     光说「筛选硬约束 ✓」没用；要说出它**筛出了什么结果**。
 *   · **当前阶段展开**：正在做的那件事带呼吸点与实时秒数 —— 实时性不丢。
 *   · **收尾总结行**：『✓ 已完成 · 54.3s · 5 个品类 · ¥10,418』。
 *     回答「到底跑完没有、结果是什么」——这就是「有终」。
 *
 * ⚠️ 一处反直觉但重要的取舍：**「思考」行默认全部隐藏**，连统计都不给。
 * 模型一次运行吐 30 段自言自语，它是过程噪音而非执行状态；把它们塞进
 * 阶段里会让每个阶段都膨胀回流水账。要读推理过程的话，它属于「模型
 * 在想什么」，不是「任务执行到哪了」——两者混在一起正是前几版的问题。
 */
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'

const props = defineProps({
  items: { type: Array, default: () => [] },
  /** 收尾总结的素材：由工作台按 run 状态传入 */
  finish: { type: Object, default: null }
})

const BY_LABEL = { llm: '模型', kb: '知识库', rule: '规则' }

/** 工作台在用户拍板后续跑处插入的标记阶段名（见 PurchaseWorkbenchView） */
const RESUME_PHASE = '__resume__' 

const scrollEl = ref(null)
const atBottom = ref(true)

/** 阶段序：按**首次出现**的顺序排，不写死 —— 走法由模型定 */
const groups = computed(() => {
  const src = props.items
  const out = []
  const byPhase = new Map()      // phase 名 → 聚合块（同名阶段合并展示）
  let cur = null

  for (const it of src) {
    if (it.kind === 'phase') {
      // ⚠️ 同名阶段会被**反复进入**（模型搜一轮、筛一轮、又回头搜 —— 实测
      // 「搜索候选」出现 3 次）。它们合并成**一个块**展示，因为从用户视角
      // 它们就是同一件事；分成三个「搜索候选」反而看不出主次。
      //
      // 但**耗时不能简单相加**：那样只是把零碎的时间堆起来，读者无法据此
      // 判断「哪一步慢」。取**最长的那一次**（模型回头重搜通常是补搜，
      // 第一次才是主搜索），并在徽章里注明进入了几轮。
      // 「继续执行」不是阶段，是中断边界 —— 做成分隔线，不进阶段列表
      if (it.phase === RESUME_PHASE) {
        cur = { key: `sep${out.length}`, separator: true, title: it.title || '继续执行',
                rows: [], state: 'done', ms: 0, passes: 0, startedAt: null }
        out.push(cur)
        continue
      }
      let g = byPhase.get(it.phase)
      if (!g) {
        g = { key: `g${out.length}`, phase: it.phase, title: it.title,
              rows: [], state: 'done', ms: 0, passes: 0, startedAt: null }
        byPhase.set(it.phase, g)
        out.push(g)
      }
      g.title = it.title || g.title
      // ⚠️ 块的状态 = **这个阶段名最后一条事件**的状态。
      // 后端现在会在离开阶段时补发 done，所以「最后一条」就是权威答案。
      // 不要在这里做「有 running 行就标 running」之类的推断 —— 那会被
      // 后续的 done 覆盖掉，实测就是「跑完了界面还在转」。
      g.state = it.state === 'running' ? 'running' : 'done'
      if (it.state === 'running') {
        // 记下开始时间，供「本阶段已用」实时重算
        g.startedAt = it.startedAt || g.startedAt
      } else {
        // 耗时与轮数由工作台在**事件层**聚合好了（那里才看得到每一轮），
        // 这里只负责展示 —— 两处各算一遍必然漂。
        g.ms = it.msTotal ?? it.ms ?? g.ms
        g.passes = it.passes ?? g.passes
        g.startedAt = null
      }
      cur = g
      continue
    }
    // 思考行不进阶段 —— 见组件顶部说明
    if (it.kind === 'think') continue
    if (!cur) {
      // 阶段之前的调用（少见）：挂到一个无名块上，别丢
      cur = { key: 'g0', phase: '', title: '开始', rows: [], state: 'done',
              ms: 0, passes: 0, startedAt: null }
      out.push(cur)
    }
    cur.rows.push(it)
  }

  // 合并连续同类调用（「搜索」×4）—— 与上一版同样的规则，但只在阶段**内部**合并，
  // 所以不会出现「中间夹着被隐藏的思考行导致合不上」而重复两行的问题。
  for (const g of out) {
    if (g.separator) continue
    g.rows = mergeRows(g.rows)
    // 取**最后**一条 running 而不是第一条：并行调用时前面几条可能已经返回，
    // 真正在做的是最新那条
    g.current = [...g.rows].reverse().find((r) => r.state === 'running') || null
    g.badge = badgeOf(g)
  }
  // 反复进入过的阶段：标明轮数，否则「搜索候选 24.4s」看不出它跑了几轮
  for (const g of out) {
    if (g.passes > 1 && g.badge) g.badge = `${g.passes} 轮 · ${g.badge}`
    else if (g.passes > 1) g.badge = `${g.passes} 轮`
  }
  return out
})

/** 连续同类调用合并：`搜索 ×4`。只合并相邻且同类型的已结束行。 */
function mergeRows(rows) {
  const out = []
  for (const it of rows) {
    const prev = out[out.length - 1]
    const canMerge =
      prev && prev.kind === it.kind && it.state !== 'running' &&
      prev.state !== 'running' && !prev.streaming && it.title && prev.title &&
      // 结果不同的不合并 —— 「排除 3 件」与「排除 5 件」是两件事，
      // 合成一个「排除 ×2」会丢掉各自的结果（截图里「排除 5 件 · 3 件」就是这么来的）
      briefOf(prev) === briefOf(it)
    if (canMerge) {
      out[out.length - 1] = {
        ...prev,
        grouped: [...(prev.grouped || [prev]), it],
        ms: (prev.ms || 0) + (it.ms || 0) || prev.ms
      }
    } else out.push(it)
  }
  return out
}

/**
 * 阶段的结果徽章 —— 光说「✓」没用，要说出**筛出了什么**。
 *
 * 从这一阶段的返回里抠出最有信息量的那个数：搜索给件数、排除给
 * 「排除 N 件」、风险给项数、定案给件数。抠不出来就不显示（不编）。
 */
function badgeOf(g) {
  if (g.state === 'running') return ''
  const texts = g.rows.flatMap((r) => [
    String(r.result || ''), ...(r.grouped || []).map((x) => String(x.result || ''))
  ])
  const all = texts.join('\n')
  // 「已排除 5 件」/「排除 12 件」
  const exc = [...all.matchAll(/(?:已)?排除\s*(\d+)\s*件/g)].map((m) => +m[1])
  if (exc.length) return `排除 ${exc.reduce((a, b) => a + b, 0)} 件`
  // 「返回 6 件」/ 样本数
  const found = g.rows.reduce((n, r) => n + (r.sample?.length || 0), 0)
  if (found) return `${found} 件候选`
  // 「已定下 5 件」
  const picked = all.match(/已定下\s*(\d+)\s*件/)
  if (picked) return `定 ${picked[1]} 件`
  const dims = all.match(/评估维度[：:]\s*(.+)/)
  if (dims) return `${dims[1].split(/[、,，]/).filter(Boolean).length} 项维度`
  const risks = all.match(/风险项[：:]\s*(.+)/)
  if (risks) return `${risks[1].split(/[、,，]/).filter(Boolean).length} 项风险`
  return ''
}

/** 折叠状态：当前阶段强制展开，其余默认收起；用户点过就听用户的 */
const userOpen = ref({})
const isOpen = (g) => userOpen.value[g.key] ?? (g.state === 'running')
const toggle = (g) => {
  userOpen.value = { ...userOpen.value, [g.key]: !isOpen(g) }
}

// ── 实时秒数 ──
// tick 只是触发重算的计数器：已用时长必须每次重算，存进数据里就成了
// 「只算一次的假时钟」。10fps 够了，不必每帧。
// ⚠️ 声明必须在 `waiting` / `waitSeconds` **之前** —— 那两个 computed
// 引用它重算，而 `const` 有暂时性死区，放在后面会直接报错。
const tick = ref(0)
let rafId = null
let lastTick = 0
const frame = (now) => {
  rafId = requestAnimationFrame(frame)
  if (now - lastTick < 100) return
  lastTick = now
  tick.value++
}

// ══════════════════════════════════════════════════════════════════
// 「正在思考」行
// ══════════════════════════════════════════════════════════════════
// 模型思考期间界面必须有动静。实测的空窗是**真实存在**的：
//   · 建 run → 首条事件：13.6s（模型冷启动）
//   · 一次 run 内 ≥5s 的静默：5 段，合计 35s
// （对照：用户答题 → 首条新事件只要 0.4s，那段其实没停。）
//
// 判据用「距最后一条事件多久」，而不是「有没有 running 行」：
// 前者才真正对应「界面有没有在动」。阈值 1.2s —— 低于它，正常的事件流
// 会把它闪来闪去；高于它，短静默又盖不住。
const WAIT_AFTER_MS = 1200

/**
 * 最后一条事件的到达时刻（由父组件随 items 一起给）。
 *
 * ⚠️ 不能在这里用 `Date.now()` 自己记 —— 组件重渲染、页面刷新、
 * 事件重放都会重置它，那个秒数就成了「只算一次的假时钟」。
 */
const lastEventAt = computed(() => {
  const items = props.items
  const last = items[items.length - 1]
  return last?.at ? new Date(last.at).getTime() : 0
})

/** 流是否还在跑（跑完了就不该再显示「正在思考」） */
const streaming = computed(() => {
  const st = props.finish?.status
  return st === 'running' || st === 'awaiting'
})

/**
 * 真的要显示等待行吗。
 *
 * 三个条件同时成立才显示：
 *   ① 流还在跑（否则跑完了还转圈）
 *   ② 距最后一条事件超过阈值
 *   ③ 当前没有正在跑的阶段行 —— 有的话那行自己就带呼吸点与秒数，
 *      再叠一个「正在思考」是重复的
 */
const waiting = computed(() => {
  tick.value
  if (!streaming.value) return false
  if (!lastEventAt.value) return true          // 一条事件都还没来，正是最该显示的时候
  const idle = Date.now() - lastEventAt.value
  if (idle < WAIT_AFTER_MS) return false
  const g = groups.value.find((x) => x.state === 'running' && !x.separator)
  if (g && g.current) return false             // 有明确的「正在做」就不重复报
  return true
})

/**
 * 等待文案。
 *
 * 分两种，因为它们对用户的含义不同：
 *   · 一条事件都还没来 → 「正在启动」：这是冷启动（实测最长 45.2s），
 *     用户在等系统就绪，不是等模型回答
 *   · 已有事件、但静默了一阵 → 「正在思考」：模型在推演，属于正常过程
 * 混为一谈的话，45 秒的冷启动会被读成「它想了 45 秒」，观感差很多。
 */
const waitText = computed(() => {
  const hasPhase = props.items.some((x) => x.kind === 'phase')
  if (!hasPhase) return '正在启动…'
  return '正在思考…'
})

/** 已等待秒数（从最后一条事件算起） */
const waitSeconds = computed(() => {
  tick.value
  if (!lastEventAt.value) {
    // 还没有任何事件：从组件挂载算起（父组件会立刻推开始时间）
    const t0 = props.finish?.startedAt
    return t0 ? Math.max(0, Math.round((Date.now() - new Date(t0).getTime()) / 1000)) : 0
  }
  return Math.max(0, Math.round((Date.now() - lastEventAt.value) / 1000))
})

const totalCalls = computed(() => props.items.filter((x) => x.kind === 'call').length)

/**
 * 总耗时 = 各阶段真实耗时之和。
 *
 * ⚠️ 取**阶段**行而不是调用行：调用行本来就不带耗时（后端只在离开阶段时
 * 报一次真实墙上时间，见 _close_phase 的说明）。按调用行求和恒为 0 ——
 * 实测头部因此永远不显示总时长。
 */
const totalMs = computed(() =>
  props.items.reduce(
    (s, x) => s + (typeof x.msTotal === 'number' ? x.msTotal
                   : typeof x.ms === 'number' ? x.ms : 0), 0)
)

/** 头部「正在做什么」：当前阶段 + 它正在做的那件事 */
const live = computed(() => {
  const g = groups.value.find((x) => x.state === 'running')
  if (!g) return null
  const r = g.current
  const what = r ? (r.title || r.detail) : (g.title || '')
  return { text: what ? `${g.title} · ${what}` : `${g.title}…` }
})

/** 开头锚点：把任务的规模先说清楚（有始） */
const startLine = computed(() => {
  const first = props.items[0]
  if (!first) return ''
  return '开始执行'
})

/**
 * 收尾总结（有终）。
 *
 * ⚠️ 只在**真的跑完**时给结论。中途 awaiting 时说「已完成」是撒谎；
 * 那时给的是「等你拍板」——如实说停在哪里。
 */
const summary = computed(() => {
  const f = props.finish
  if (!f) return null
  const parts = []
  if (totalMs.value) parts.push(fmtMs(totalMs.value))
  if (f.categories) parts.push(`${f.categories} 个品类`)
  if (f.total != null) parts.push(`¥${Number(f.total).toLocaleString('en-US')}`)

  // ⚠️ 分隔符不能写死在模板里：没有数据时会出现「已完成 · 」这样的悬空尾巴。
  // 实测「停在等你拍板 ·」——后面什么都没有，看着像加载失败。
  const head = {
    converged: { state: 'done', mark: '✓', label: '已完成' },
    awaiting: { state: 'waiting', mark: '◐', label: '停在等你拍板' },
    failed: { state: 'failed', mark: '✕', label: '执行失败' },
    running: { state: 'running', mark: '◐', label: '进行中' },
  }[f.status]
  if (!head) return null

  const tail = f.status === 'failed' && f.error ? [String(f.error).slice(0, 60)] : parts
  return {
    state: head.state,
    mark: head.mark,
    text: [head.label, ...tail].join(' · '),
  }
})

const briefOf = (r) => {
  if (r.sample?.length) return `${r.sample.length} 件`
  if (r.result) {
    const raw = String(r.result)
    // 模型工具调参失败的报错是给模型看的，不是给用户的（见上一版说明）
    if (/Error invoking tool|Field required|Please fix the error/.test(raw)) return '参数不全，已重试'
    const first = raw.split('\n')[0]
    const m = first.match(/返回\s*(\d+)\s*件/)
    if (m) return `${m[1]} 件`
    if (/没有返回|未找到|暂未/.test(first)) return '无结果'
    return first.slice(0, 22)
  }
  if (r.detail) return String(r.detail).replace(/\s+/g, ' ').slice(0, 22)
  return ''
}

const fmtMs = (ms) => {
  if (ms == null) return ''
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

const elapsedOf = (g) => {
  tick.value
  if (!g.startedAt) return ''
  return fmtMs(Date.now() - g.startedAt)
}

const isNearBottom = () => {
  const el = scrollEl.value
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight < 40
}
const onScroll = () => { atBottom.value = isNearBottom() }
const scrollToBottom = () => {
  const el = scrollEl.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  atBottom.value = true
}

watch(() => props.items.length, async () => {
  if (!atBottom.value) return
  await nextTick()
  const el = scrollEl.value
  if (el) el.scrollTop = el.scrollHeight
})

onMounted(() => {
  rafId = requestAnimationFrame((now) => {
    lastTick = now
    frame(now)
    const el = scrollEl.value
    if (el) el.scrollTop = el.scrollHeight
  })
})
onBeforeUnmount(() => { if (rafId) cancelAnimationFrame(rafId) })
</script>

<style lang="less" scoped>
.xs {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}

.xs-head {
  flex: 0 0 auto;
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 0 0 10px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 8px;
}
.xs-title {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-strong);
}
.xs-prog {
  font-size: 0.68rem;
  color: var(--text-muted);
}
/* 正做什么：头部最显眼的一条 */
.xs-live {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  font-size: 0.7rem;
  color: var(--info);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.xs-live-dot {
  flex: 0 0 auto;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--info);
  animation: xs-breathe 1.2s ease-in-out infinite;
}
.xs-total { font-size: 0.68rem; color: var(--text-faint); }
@keyframes xs-breathe {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.25; }
}
@media (prefers-reduced-motion: reduce) {
  .xs-live-dot { animation: none; }
}
.xs-jump {
  margin-left: auto;
  font-size: 0.7rem;
  font-family: var(--font-body);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--accent-200);
  background: var(--accent-50);
  color: var(--accent-700);
  cursor: pointer;
}

.xs-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding-right: 2px;
}
.xs-empty {
  margin: 10px 0 0;
  font-size: 0.72rem;
  color: var(--text-faint);
}

/* 开头锚点 */
.xs-start {
  margin: 0 0 8px;
  font-size: 0.68rem;
  color: var(--text-faint);
  padding-left: 2px;
}

/* ── 阶段块 ── */
.xg {
  border-bottom: 1px solid var(--border);
  &:last-of-type { border-bottom: none; }
}
.xg-head {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  padding: 7px 2px;
  border: none;
  background: transparent;
  font-family: var(--font-body);
  text-align: left;
  cursor: pointer;
  border-radius: var(--radius-sm);
  &:hover { background: var(--bg-sunken); }
}
/* 阶段点：比调用行的点大，是这一层的结构标记 */
.xg-dot {
  position: relative;
  flex: 0 0 auto;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  box-sizing: border-box;
  &.is-done { background: var(--pos); }
  &.is-running { background: var(--info); }
  &.is-todo { background: var(--bg-surface); border: 1px solid var(--border-strong); }
}
.xg-dot-pulse {
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  border: 1px solid var(--info);
  animation: xg-ring 1.4s ease-out infinite;
}
@keyframes xg-ring {
  0% { transform: scale(0.7); opacity: 0.9; }
  100% { transform: scale(1.9); opacity: 0; }
}
@media (prefers-reduced-motion: reduce) {
  .xg-dot-pulse { animation: none; opacity: 0.5; }
}
/* 阶段名是这一行的主角 */
.xg-name {
  flex: 0 0 auto;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--text-strong);
}
/* 结果徽章：说出这一阶段筛出了什么 */
.xg-badge {
  flex: 0 0 auto;
  font-size: 0.66rem;
  color: var(--text-muted);
  background: var(--bg-sunken);
  border-radius: 3px;
  padding: 0 6px;
}
/* 正在做：阶段头里的实时文字 */
.xg-now {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 0.7rem;
  color: var(--info);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.xg-ms {
  flex: 0 0 auto;
  margin-left: auto;
  font-size: 0.64rem;
  color: var(--text-faint);
}
.xg.is-running .xg-ms { color: var(--info); }
.xg-chev {
  flex: 0 0 auto;
  font-size: 0.74rem;
  line-height: 1;
  color: var(--text-faint);
  transition: transform 0.15s ease-out;
  &.open { transform: rotate(90deg); }
}

/* ── 阶段内明细 ── */
.xg-body {
  padding: 2px 0 8px 15px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.xs-row {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 5px;
  min-width: 0;
}
.xs-dot {
  flex: 0 0 auto;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  align-self: center;
  &.is-done { background: var(--border-strong); }
  &.is-running { background: var(--info); }
}
.xs-mul {
  flex: 0 0 auto;
  font-size: 0.63rem;
  font-weight: 600;
  color: var(--accent-700);
  background: var(--accent-50);
  border-radius: 3px;
  padding: 0 4px;
}
.xs-by {
  flex: 0 0 auto;
  font-size: 0.6rem;
  padding: 0 4px;
  border-radius: 3px;
  &.by-kb { color: var(--text-muted); }
  &.by-rule { color: var(--warn); background: var(--bg-sunken); }
}
.xs-text {
  flex: 0 1 auto;
  font-size: 0.72rem;
  color: var(--text);
  min-width: 0;
}
.xs-brief {
  flex: 0 1 auto;
  font-size: 0.68rem;
  color: var(--text-muted);
  min-width: 0;
}
/* 合并掉的几次：展开在下面，让「×4」可核对 */
.xs-sub {
  flex: 1 0 100%;
  list-style: none;
  margin: 1px 0 0;
  padding: 0 0 0 10px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  li {
    display: flex;
    gap: 7px;
    font-size: 0.66rem;
    line-height: 1.45;
    color: var(--text-faint);
  }
}
.xs-sub-t { min-width: 0; }
.xs-sub-b { margin-left: auto; flex: 0 0 auto; }
.xs-none {
  margin: 0;
  font-size: 0.68rem;
  color: var(--text-faint);
}

/* ── 中断分隔线（「继续执行」）──
   不是阶段，所以视觉上要比阶段头弱：细线 + 小字，居中断开。 */
.xg-sep {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 9px 0 5px;
  padding: 0 2px;
}
.xg-sep-line {
  flex: 1 1 auto;
  height: 1px;
  background: var(--border);
}
.xg-sep-text {
  flex: 0 0 auto;
  font-size: 0.63rem;
  color: var(--text-faint);
}

/* ── 「正在思考」行 ──
   三点动画 + 文案 + 秒数。与主智能体对话界面的 .generating-status 同一套
   语言（那套已经验证过观感），只是这里的宽度只有 300px，所以更紧凑。 */
.xs-wait {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: 10px;
  padding: 7px 9px;
  border-radius: var(--radius-sm);
  background: var(--bg-sunken);
  font-size: 0.72rem;
  color: var(--text-muted);
}
.xs-wait-dots {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  i {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: var(--info);
    animation: xs-dot 1.4s infinite ease-in-out both;
    &:nth-child(1) { animation-delay: -0.32s; }
    &:nth-child(2) { animation-delay: -0.16s; }
    &:nth-child(3) { animation-delay: 0s; }
  }
}
@keyframes xs-dot {
  0%, 80%, 100% { opacity: 0.25; transform: scale(0.8); }
  40% { opacity: 1; transform: scale(1); }
}
@media (prefers-reduced-motion: reduce) {
  .xs-wait-dots i { animation: none; opacity: 0.6; }
}
.xs-wait-text { flex: 0 1 auto; min-width: 0; }
.xs-wait-sec {
  flex: 0 0 auto;
  margin-left: auto;
  font-size: 0.66rem;
  color: var(--text-faint);
}

/* ── 收尾总结 ── */
.xs-sum {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: 10px;
  padding: 9px 10px;
  border-radius: var(--radius-sm);
  background: var(--bg-sunken);
  font-size: 0.74rem;
  color: var(--text-strong);
  &.is-done { color: var(--pos); }
  &.is-waiting { color: var(--accent-700); }
  &.is-failed { color: var(--warn); }
  &.is-running { color: var(--info); }
}
.xs-sum-mark { flex: 0 0 auto; font-size: 0.8rem; }
.xs-sum-text { min-width: 0; }
</style>
