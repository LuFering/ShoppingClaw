<template>
  <div class="es">
    <header class="es-head">
      <span class="es-title">执行流</span>
      <span v-if="toolCount" class="es-prog mono">{{ toolCount }} 次调用</span>

      <!--
        正在做什么 —— 放在**头部**，一眼就能看到，不用去列表里找。
        用户的原话：「给出模型执行任务时的实时状态，已经做了什么，正在做什么」。
        正在做的那件事是该回答的第二个问题，值得占最显眼的位置。
      -->
      <span v-if="runningItem" class="es-live" :title="runningItem.title || ''">
        <i class="es-live-dot" />{{ runningText }}
      </span>
      <span v-else-if="totalMs" class="es-total mono">共 {{ fmtMs(totalMs) }}</span>

      <button
        v-if="hiddenCount"
        class="es-filter"
        type="button"
        :title="'显示模型的推理过程（' + hiddenCount + ' 条）'"
        @click="showReasoning = !showReasoning"
      >{{ showReasoning ? '只看核心' : `显示过程 (${hiddenCount})` }}</button>

      <button v-if="!atBottom" class="es-jump" type="button" @click="scrollToBottom">
        回到最新 ↓
      </button>
    </header>

    <div ref="scrollEl" class="es-scroll" @scroll="onScroll">
      <div
        v-for="(item, i) in visibleItems"
        :key="item.uid"
        class="es-row"
        :class="{ 'is-live': item.state === 'running' }"
      >
        <div class="es-rail">
          <span class="es-dot" :class="'is-' + item.state">
            <i v-if="item.state === 'running'" class="es-dot-pulse" />
          </span>
          <span v-if="i !== visibleItems.length - 1" class="es-line" />
        </div>

        <div class="es-body">
          <!--
            ═══════════════════════════════════════════════════════════
            2026-09-27：左栏只讲「状态」，不再展开任何细节
            ═══════════════════════════════════════════════════════════
            用户原话：「左侧不用在详情展示入参数据和返回详情，左侧要做的，
            就是给出模型执行任务时的实时状态，已经做了什么，正在做什么」。

            所以整块**可展开的详情**（入参 / 工具返回原文 / 返回样本 /
            推理全文）连同它的展开箭头一起去掉了。一行的职责只剩三件事：
              ① 这一步是什么（类型标签）
              ② 它做了什么 / 正在做什么（标题 + 一句话结果）
              ③ 花了多久（耗时；正在跑的用实时秒数）

            要核对细节该去**右边**——那里是交付物（报告/对比表/预算表），
            是给人读的结论。左栏是过程的状态灯，不是日志查看器。
          -->
          <div class="es-main">
            <span class="es-kind" :class="'k-' + item.kind">{{ KIND_LABEL[item.kind] || item.kind }}</span>
            <!-- 合并角标：连续同类调用的次数，一眼看出「这一步做了 N 次」 -->
            <span v-if="item.grouped?.length" class="es-mul mono">×{{ item.grouped.length }}</span>
            <span v-if="item.by" class="es-by" :class="'by-' + item.by">{{ BY_LABEL[item.by] || item.by }}</span>

            <span v-if="item.title" class="es-text">{{ item.title }}</span>

            <!-- 正在做：显示生长中的文字尾巴，让「它在动」看得见 -->
            <span v-if="item.streaming" class="es-live-text">
              {{ tail(item.detail) }}<i class="es-caret" />
            </span>
            <!-- 已完成：一句话结果 -->
            <span
              v-else-if="briefOf(item)"
              class="es-brief"
              :class="{ 'is-solo': !item.title }"
            >{{ item.title ? '· ' : '' }}{{ briefOf(item) }}</span>

            <span v-if="item.state === 'running' && !item.streaming" class="es-elapsed mono">{{ elapsedOf(item) }}</span>
            <span v-else-if="item.ms != null" class="es-ms mono">{{ fmtMs(item.ms) }}</span>
          </div>
        </div>
      </div>

      <!-- 全部跑完且一条都没有时不至于空白 -->
      <p v-if="!visibleItems.length" class="es-empty">还没有开始执行。</p>
    </div>
  </div>
</template>

<script setup>
/**
 * 左栏 · agent 执行流的**状态视图**。
 *
 * ═══════════════════════════════════════════════════════════════════
 * 2026-09-27：去掉详情展开，左栏只留「状态」
 * ═══════════════════════════════════════════════════════════════════
 * 用户原话：「左侧不用在详情展示入参数据和返回详情，左侧要做的，就是给出
 * 模型执行任务时的实时状态，已经做了什么，正在做什么」。
 *
 * 这个组件此前经历了两轮「压扁」：先是把过程全铺改成一屏一行，再是默认
 * 只看核心、连续同类调用合并。但一直保留着「点开看入参/返回原文/返回样本」
 * 这条退路 —— 那让它本质上还是个日志查看器。
 *
 * 现在把那条退路也去掉。理由不只是「更简洁」：
 *   · **入参与原始返回是给排障用的，不是给用户用的。** 「q=隔音材料,
 *     page_size=6」对下决定没有任何帮助；用户要的是「它搜了隔音材料、
 *     拿到 6 件」。
 *   · **要核对细节该去右边。** 右栏的交付物（报告 / 对比表 / 预算表）
 *     就是给人读的结论，那里有逐件的价格、理由、用量依据。同一份信息
 *     在两处各展示一遍，只会让两处都做不深。
 *   · 左栏越干净，「正在做什么」就越醒目 —— 那才是这一栏存在的意义。
 *
 * 保留的实时元素：进行中那行的呼吸点、每 100ms 重算的已用秒数、
 * 正在生成文字的尾巴与光标。这些是「实时」的载体，一个都不能少。
 */
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'

const props = defineProps({
  items: { type: Array, default: () => [] }
})

const KIND_LABEL = {
  phase: '阶段',
  think: '思考',
  retrieve: '检索',
  call: '调用',
  produce: '产出'
}

// 结论的来源。三种要能分辨，不能把检索结果说成模型判断。
const BY_LABEL = {
  llm: '模型判断',
  kb: '知识库命中',
  rule: '规则兜底'
}

const scrollEl = ref(null)
const atBottom = ref(true)

const runningItem = computed(() => props.items.find((x) => x.state === 'running'))

/** 头部那句话：优先用正在做的那件事的标题，没有就退回一个泛称 */
const runningText = computed(() => {
  const it = runningItem.value
  if (!it) return ''
  const t = String(it.title || '').trim()
  return t || (it.kind === 'think' ? '正在思考…' : '正在执行…')
})

const totalMs = computed(() =>
  props.items.reduce((sum, x) => sum + (typeof x.ms === 'number' ? x.ms : 0), 0)
)
const toolCount = computed(() => props.items.filter((x) => x.kind === 'call').length)

/** 模型叙述的行数 —— 为 0 时不显示「显示过程」按钮 */
const reasonRows = computed(() => props.items.filter((x) => x.kind === 'think'))

/**
 * 默认**只看核心**。
 *
 * 用户要的是「它做了什么」，那是工具调用；模型的自言自语属于过程噪音，
 * 想看再点开。实测默认全量是 32 行、核心视图是 16 行。
 */
const showReasoning = ref(false)
const hiddenCount = computed(() => reasonRows.value.length)

/**
 * 连续同类调用合并成一行。
 *
 * 「搜索 X」出现 8 次就是 8 行几乎一样的字。合并成「搜索 ×8」，点开看
 * 每一次 —— 但**只在「显示过程」里给展开**（见下面的说明）。
 *
 * ⚠️ 只合并**连续**的同类调用：中间夹着别的步骤就不合并，否则会打乱时序
 * （「搜 → 排除 → 搜」变成一个「搜 ×2」是错的，排除确实发生在两次搜索之间）。
 */
const GROUPABLE = new Set(['call', 'retrieve'])

const groupedItems = computed(() => {
  const out = []
  for (const it of props.items) {
    const prev = out[out.length - 1]
    const canMerge =
      prev &&
      GROUPABLE.has(it.kind) &&
      prev.kind === it.kind &&
      it.state !== 'running' &&
      prev.state !== 'running' &&
      !prev.streaming &&
      it.title && prev.title
    if (canMerge) {
      out[out.length - 1] = {
        ...prev,
        grouped: [...(prev.grouped || [prev]), it],
        result: it.result || prev.result,
        ms: (prev.ms || 0) + (it.ms || 0) || prev.ms,
        by: it.by || prev.by,
      }
    } else {
      out.push(it)
    }
  }
  return out
})

/**
 * 实际渲染的行。
 *
 * 空行先剔掉：模型每轮思考先起一条流式行，若下一步没跟上收尾（run 结束、
 * 或事件被节流），它会永远停在 streaming 状态，于是绕过过滤，留下一排
 * 没有文字的空「思考」行 —— 实测一次运行有 4~5 条。
 *
 * 「只看核心」= 只留工具调用与阶段。正在流式输出的那条要留，否则界面
 * 完全静止，用户会以为卡住了。
 */
const visibleItems = computed(() => {
  const rows = groupedItems.value.filter(
    (x) => !(x.kind === 'think' && !String(x.detail || '').trim() && !x.streaming)
  )
  return showReasoning.value
    ? rows
    : rows.filter((x) => x.kind !== 'think' || (x.streaming && String(x.detail || '').trim()))
})

/**
 * 一句话结果 —— 收起状态下这行显示的结论。
 *
 * 工具调用优先用返回样本的**件数**（「6 件」比「返回 6 件商品…」一眼）；
 * 没有样本就取返回原文的第一行去掉前缀。
 */
const briefOf = (item) => {
  if (item.sample?.length) return `${item.sample.length} 件`
  if (item.result) {
    const raw = String(item.result)
    // ⚠️ 模型的**工具调用参数错误**（LangChain 校验失败）不要原样贴出来。
    // 原文是「Error invoking tool 'drop_candidates' with kwargs {...} with
    // error: reason: Field required. Please fix the error and try again.」
    // —— 那是给模型看的、要它自己改了重试的指令，不是给用户看的。
    // 甩给用户的结果是：界面上一条几百字的英文报错，而他什么也做不了。
    // （模型通常真的会自己重试并成功，所以这只是过程噪音。）
    if (/Error invoking tool|Field required|Please fix the error/.test(raw)) {
      return '参数不全，已重试'
    }
    const first = raw.split('\n')[0]
    const m = first.match(/返回\s*(\d+)\s*件/)
    if (m) return `${m[1]} 件`
    if (/没有返回|未找到|暂未/.test(first)) return '无结果'
    return first.slice(0, 26)
  }
  if (item.detail) return String(item.detail).replace(/\s+/g, ' ').slice(0, 34)
  return ''
}

/** 流式期间显示文字的**尾巴** —— 头会被滚动条挤走，尾巴才是「正在想」 */
const tail = (text) => {
  const t = String(text || '').replace(/\s+/g, ' ').trim()
  return t.length > 48 ? '…' + t.slice(-48) : t
}

const fmtMs = (ms) => {
  if (ms == null) return ''
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

// ── 实时秒数 ──────────────────────────────────────────────
// tick 只是用来触发重算的计数器：已用时长必须每帧重算，
// 存在数据里的话就成了「只算一次的假时钟」。
const tick = ref(0)
let rafId = null
let lastTick = 0

const frame = (now) => {
  rafId = requestAnimationFrame(frame)
  if (now - lastTick < 100) return   // 10fps 够了，不必每帧
  lastTick = now
  tick.value++
}

const elapsedOf = (item) => {
  tick.value   // 建立依赖，让每 100ms 重算
  if (!item.startedAt) return ''
  return fmtMs(Date.now() - item.startedAt)
}

const isNearBottom = () => {
  const el = scrollEl.value
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight < 40
}

const onScroll = () => {
  // 用户往上翻说明在看历史，此时停止自动跟随
  atBottom.value = isNearBottom()
}

const scrollToBottom = () => {
  const el = scrollEl.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  atBottom.value = true
}

watch(
  () => props.items.length,
  async () => {
    if (!atBottom.value) return
    await nextTick()
    const el = scrollEl.value
    if (el) el.scrollTop = el.scrollHeight
  }
)

onMounted(() => {
  rafId = requestAnimationFrame((now) => {
    lastTick = now
    frame(now)
    const el = scrollEl.value
    if (el) el.scrollTop = el.scrollHeight
  })
})
onBeforeUnmount(() => {
  if (rafId) cancelAnimationFrame(rafId)
})
</script>

<style lang="less" scoped>
.es {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}

.es-head {
  flex: 0 0 auto;
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 0 0 10px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 8px;
}
.es-title {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-strong);
}
.es-prog {
  font-size: 0.68rem;
  color: var(--text-muted);
}
/* 正在做什么：头部最显眼的一条，字要比别的行重 */
.es-live {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  font-size: 0.7rem;
  color: var(--info);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.es-live-dot {
  flex: 0 0 auto;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--info);
  animation: es-breathe 1.2s ease-in-out infinite;
}
.es-total {
  font-size: 0.68rem;
  color: var(--text-faint);
}
@keyframes es-breathe {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.25; }
}
@media (prefers-reduced-motion: reduce) {
  .es-live-dot { animation: none; }
}
.es-jump {
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
/* 「显示过程」开关：默认态低调，开启时高亮 —— 让用户知道当前被过滤了 */
.es-filter {
  margin-left: auto;
  font-size: 0.66rem;
  font-family: var(--font-body);
  padding: 1px 7px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-strong);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.15s ease-out, border-color 0.15s ease-out;
  &:hover { color: var(--text); }
  &.on {
    border-color: var(--accent-500);
    background: var(--accent-50);
    color: var(--accent-700);
  }
}
/* 有开关时「回到最新」不再靠 margin-left:auto 顶到右边 */
.es-filter ~ .es-jump { margin-left: 6px; }

.es-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding-right: 2px;
}
.es-empty {
  margin: 10px 0 0;
  font-size: 0.72rem;
  color: var(--text-faint);
}

.es-row {
  display: flex;
  gap: 8px;
}

/* ── 时间线 ── */
.es-rail {
  flex: 0 0 7px;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.es-dot {
  position: relative;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-top: 7px;
  flex: 0 0 auto;
  &.is-done { background: var(--pos); }
  &.is-running { background: var(--info); }
  &.is-todo {
    background: var(--bg-surface);
    border: 1px solid var(--border-strong);
    box-sizing: border-box;
  }
}
.es-dot-pulse {
  position: absolute;
  inset: -3px;
  border-radius: 50%;
  border: 1px solid var(--info);
  animation: es-ring 1.4s ease-out infinite;
}
@keyframes es-ring {
  0% { transform: scale(0.7); opacity: 0.9; }
  100% { transform: scale(1.8); opacity: 0; }
}
@media (prefers-reduced-motion: reduce) {
  .es-dot-pulse { animation: none; opacity: 0.5; }
}
.es-line {
  flex: 1 1 auto;
  width: 1px;
  background: var(--border);
  margin-top: 2px;
}

.es-body {
  min-width: 0;
  flex: 1 1 auto;
  padding-bottom: 3px;
}

/*
  一行。flex + 单行省略，保证**永远占一行** ——
  这是「简略」的关键：不管标题多长、结果多长，都截断而不是折行。
*/
.es-main {
  display: flex;
  align-items: center;
  gap: 5px;
  min-height: 20px;
}

.es-kind {
  flex: 0 0 auto;
  font-size: 0.64rem;
  padding: 0 4px;
  border-radius: 3px;
  background: var(--bg-sunken);
  color: var(--text-muted);
  // 与项目既有的 .state 写法一致：靠文字色区分类型，不堆彩色胶囊容器
  &.k-phase { color: var(--text-faint); }
  &.k-think { color: #9581cc; }
  &.k-retrieve { color: var(--info); }
  &.k-call { color: var(--text-muted); }
  &.k-produce { color: var(--pos); }
}
.es-by {
  flex: 0 0 auto;
  font-size: 0.6rem;
  padding: 0 4px;
  border-radius: 3px;
  &.by-llm { color: var(--text-faint); }
  &.by-kb { color: var(--text-muted); }
  &.by-rule { color: var(--warn); background: var(--bg-sunken); }
}
/* 合并角标：连续同类调用的次数。比类型标签更醒目 —— 它是这行的量词 */
.es-mul {
  flex: 0 0 auto;
  font-size: 0.64rem;
  font-weight: 600;
  color: var(--accent-700);
  background: var(--accent-50);
  padding: 0 5px;
  border-radius: 3px;
}

.es-text {
  font-size: 0.75rem;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 0 1 auto;
}
/* 一句话结果：比标题弱，但仍然是一行 */
.es-brief {
  flex: 0 1 auto;
  font-size: 0.71rem;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
  /* 没有标题时它就是这行的正文（思考行）—— 用正文色 */
  &.is-solo {
    color: var(--text);
    font-size: 0.73rem;
  }
}
/* 流式中的文字尾巴 */
.es-live-text {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 0.71rem;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.es-caret {
  display: inline-block;
  width: 2px;
  height: 0.7em;
  margin-left: 2px;
  vertical-align: -0.06em;
  background: var(--info);
  animation: es-caret 1s steps(2, start) infinite;
}
@keyframes es-caret {
  0%, 50% { opacity: 1; }
  50.01%, 100% { opacity: 0; }
}
@media (prefers-reduced-motion: reduce) {
  .es-caret { animation: none; }
}

.es-elapsed, .es-ms {
  flex: 0 0 auto;
  margin-left: auto;
  font-size: 0.64rem;
  color: var(--text-faint);
}
.es-elapsed { color: var(--info); }
</style>
