<template>
  <div class="es">
    <header class="es-head">
      <span class="es-title">执行流</span>
      <!-- 阶段进度：总共几步、现在第几步。等待有了边界，焦虑感完全不同。 -->
      <span v-if="phases.length" class="es-prog mono">
        第 {{ phaseNow }} / {{ phases.length }} 步
      </span>
      <!-- 整体状态：有步骤在跑时给一个会动的指示，静止的界面看起来像卡死 -->
      <span v-if="runningItem" class="es-live">
        <i class="es-live-dot" />进行中
      </span>
      <span v-else-if="totalMs" class="es-total mono">共 {{ fmtMs(totalMs) }}</span>
      <button
        v-if="!atBottom"
        class="es-jump"
        type="button"
        @click="scrollToBottom"
      >回到最新 ↓</button>
    </header>

    <div ref="scrollEl" class="es-scroll" @scroll="onScroll">
      <div
        v-for="(item, i) in items"
        :key="item.phase || i"
        class="es-row"
        :class="{ 'is-live': item.state === 'running' }"
      >
        <div class="es-rail">
          <span class="es-dot" :class="'is-' + item.state">
            <i v-if="item.state === 'running'" class="es-dot-pulse" />
          </span>
          <span v-if="i < items.length - 1" class="es-line" />
        </div>
        <div class="es-body">
          <span class="es-kind" :class="'k-' + item.kind">{{ KIND_LABEL[item.kind] || item.kind }}</span>
          <!--
            来源标记：这一步的结论是怎么来的。后端带 `by`：
              llm  模型判断   · kb  知识库检索命中   · rule 规则兜底
            **必须显示出来** —— 之前规则兜底的输出在界面上和模型判断长得
            一模一样，用户无从分辨，这正是「用假推理忽悠」的观感来源。
            宁可显示「规则兜底」也不假装。
          -->
          <span v-if="item.by" class="es-by" :class="'by-' + item.by">
            {{ BY_LABEL[item.by] || item.by }}
          </span>
          <p class="es-text" :class="{ dim: item.state === 'todo' }">
            {{ item.title }}
            <span v-if="item.state === 'running' && !item.streaming && item.detail" class="es-hint">· {{ item.detail }}</span>
          </p>

          <!--
            推理正文：模型逐段吐出来的原文，不是我们拼的一句话。
            流式期间带光标；结束后光标消失、文字留着 —— 这段文字**不删**，
            它是这次判断的依据，用户随时能回看。

            reasoning（它的自言自语）弱化成灰色；content（它要说的话）用正文色。
            两者不区分的话，用户会以为模型在胡言乱语 —— 实测 reasoning 里
            确实有试错和自我纠正（「第2是下水管隔音，场景太窄」这种）。
          -->
          <p
            v-if="item.streaming || (item.kind === 'think' && item.detail)"
            class="es-think"
            :class="{ 'is-reasoning': item.thinkKind === 'reasoning' }"
          >{{ item.detail }}<i v-if="item.streaming" class="es-caret" /></p>

          <!--
            真实入参与真实返回样本（call 事件带）。
            这是「不假」的关键：用户能核对它**真的搜了什么、搜回来什么**，
            而不是只看一句由 len() 拼出来的「返回 6 个 SKU」。
          -->
          <div v-if="item.args || item.sample?.length" class="es-tool">
            <p v-if="item.args" class="es-tool-line">
              <span class="es-tool-k">入参</span>
              <span class="es-tool-v mono">{{ fmtArgs(item.args) }}</span>
            </p>
            <template v-if="item.sample?.length">
              <p class="es-tool-k">返回</p>
              <ul class="es-samples">
                <li v-for="(s, k) in item.sample" :key="k">
                  <span class="es-sample-n">{{ s.name }}</span>
                  <span v-if="s.price != null" class="es-sample-p mono">¥{{ fmtPrice(s.price) }}</span>
                </li>
              </ul>
            </template>
          </div>

          <!-- 正在跑的这一步：显示**实时**已用时长，让「它在动」可见 -->
          <p v-if="item.state === 'running' && !item.streaming" class="es-meta">
            <span class="es-elapsed mono">{{ elapsedOf(item) }}</span>
            <i class="es-caret" />
          </p>
          <p v-else-if="item.detail && !item.streaming && item.kind !== 'think'" class="es-detail" :class="{ dim: item.state === 'todo' }">{{ item.detail }}</p>
          <p class="es-time mono">
            <span v-if="item.ms != null" class="es-ms">{{ fmtMs(item.ms) }}</span>
            <span v-if="item.time">{{ item.time }}</span>
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 左栏 · agent 任务执行流。
 *
 * 三种条目用「标签色 + 措辞」区分，不拆成三套组件：
 *   think 思考（紫） / retrieve 检索（蓝） / call 调用（中性） / produce 产出（绿）
 * 数据源来自 SSE。
 *
 * ═══════════════════════════════════════════════════════════════════
 * 2026-09-25：补上「实时」元素
 * ═══════════════════════════════════════════════════════════════════
 *
 * 之前只有「跑完的条目」—— 一个静态列表。但这一步最慢要 9 秒（MCP 检索）
 * 到 8 秒（模型取舍），期间界面完全不动，看起来像卡死。
 *
 * 现在有三种实时元素（都对应真实数据，不做假动画）：
 *   1. 正在跑的条目：呼吸点 + **实时累加**的已用秒数（每 100ms 跳一次）
 *   2. 跑完的条目：真实耗时（后端给 ms，给了就用；没给用本地计时）
 *   3. 头部：进行中指示 / 全部耗时合计
 *
 * 计时用 requestAnimationFrame 而不是 setInterval：标签页切到后台时
 * rAF 自动停，回来再继续 —— 不会在后台空转，也不会算出离谱的时长。
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
const totalMs = computed(() =>
  props.items.reduce((sum, x) => sum + (typeof x.ms === 'number' ? x.ms : 0), 0)
)

/**
 * 阶段进度：已完成的 / 总共几个。
 *
 * 建 run 时后端就把 7 个阶段全部铺下来了，所以这个分母从第一秒就成立 ——
 * 用户一开始就知道「总共 7 步、现在第 3 步」，而不是看着一条条冒出来
 * 不知道还有多久。
 */
const phases = computed(() => props.items.filter((x) => x.kind === 'phase'))
const phaseDone = computed(() => phases.value.filter((x) => x.state === 'done').length)
const phaseNow = computed(() => {
  const i = phases.value.findIndex((x) => x.state === 'running')
  return i >= 0 ? i + 1 : Math.min(phaseDone.value + 1, phases.value.length)
})

// ── 实时秒数 ──────────────────────────────────────────────
// tick 只是用来触发重算的计数器：已用时长必须每帧重算（见 elapsedOf），
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

const fmtMs = (ms) => {
  if (ms == null) return ''
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

/** 价格是「元」，整数不显示小数点 */
const fmtPrice = (v) => {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return Number.isInteger(n) ? String(n) : n.toFixed(2)
}

/** 工具入参：`{"q":"隔音材料","page_size":6}` → `q=隔音材料 · page_size=6` */
const fmtArgs = (args) => {
  if (!args || typeof args !== 'object') return ''
  return Object.entries(args)
    .map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : v}`)
    .join(' · ')
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
  margin-bottom: 10px;
}
.es-title {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-strong);
}
/* 阶段进度：取代原来的静态说明「调用 · 检索 · 思考」——
   那句是分类标签，而这里给的是**进程信息**（第几步 / 共几步）。 */
.es-prog {
  font-size: 0.68rem;
  color: var(--text-muted);
}
.es-live {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 0.68rem;
  color: var(--info);
}
.es-live-dot {
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

.es-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding-right: 2px;
}

.es-row {
  display: flex;
  gap: 9px;
}
.es-rail {
  flex: 0 0 9px;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.es-dot {
  position: relative;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  margin-top: 4px;
  flex: 0 0 auto;
  &.is-done { background: var(--pos); }
  &.is-running { background: var(--info); }
  &.is-todo {
    background: var(--bg-surface);
    border: 1px solid var(--border-strong);
    box-sizing: border-box;
  }
}
/* 正在跑的那一步：外扩的呼吸圈，一眼能扫到 */
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
  padding-bottom: 12px;
}
.es-row:last-child .es-body { padding-bottom: 0; }
/* 正在跑的一行整体提亮，与已完成的拉开层次 */
.es-row.is-live .es-text { color: var(--text-strong); font-weight: 500; }

.es-kind {
  display: inline-block;
  font-size: 0.66rem;
  padding: 1px 6px;
  border-radius: 4px;
  margin-bottom: 3px;
  background: var(--bg-sunken);
  // 与项目既有的 .state 写法一致：靠文字色区分类型，不堆彩色胶囊容器
  &.k-phase { color: var(--text-muted); }
  &.k-think { color: #9581cc; }
  &.k-retrieve { color: var(--info); }
  &.k-call { color: var(--text-muted); }
  &.k-produce { color: var(--pos); }
}

/* 来源标记：模型判断 / 规则兜底。刻意做得比 es-kind 更弱 ——
   它是注脚，不该抢判断本身的注意力；但降级时用警示色，确保看得见。 */
.es-by {
  display: inline-block;
  margin-left: 5px;
  margin-bottom: 3px;
  font-size: 0.62rem;
  padding: 1px 5px;
  border-radius: 4px;
  &.by-llm { color: var(--text-faint); background: transparent; }
  /* 检索命中：中性偏正，不抢眼 */
  &.by-kb { color: var(--text-muted); background: transparent; }
  /* 降级用警示色 + 底色，确保在一屏「思考」里能一眼扫到 */
  &.by-rule { color: var(--warn); background: var(--bg-sunken); }
}
.es-text {
  margin: 0;
  font-size: 0.76rem;
  line-height: 1.5;
  color: var(--text);
  &.dim { color: var(--text-faint); }
}
/* 「正在做」的说明跟在标题后面，弱一档 */
.es-hint {
  color: var(--text-muted);
  font-weight: 400;
  font-size: 0.72rem;
}
.es-meta {
  display: flex;
  align-items: center;
  gap: 2px;
  margin: 3px 0 0;
}
.es-elapsed {
  font-size: 0.68rem;
  color: var(--info);
}
/* 光标：告诉用户这行还在长 */
.es-caret {
  display: inline-block;
  width: 2px;
  height: 0.72em;
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
.es-detail {
  margin: 2px 0 0;
  font-size: 0.7rem;
  line-height: 1.5;
  color: var(--text-muted);
  &.dim { color: var(--text-faint); }
}

/* 推理正文：模型原文，逐段长出来。比 es-detail 更"实"（是内容不是注脚），
   所以用正文色、行距放开一点，读起来像一段话而不是一条日志。 */
.es-think {
  margin: 3px 0 0;
  font-size: 0.74rem;
  line-height: 1.65;
  color: var(--text);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  /* reasoning（模型的自言自语）弱化：它是过程，不是结论 */
  &.is-reasoning {
    color: var(--text-muted);
    font-size: 0.72rem;
  }
}

/* 工具的真实入参与返回样本 */
.es-tool {
  margin: 5px 0 0;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  background: var(--bg-sunken);
}
.es-tool-line {
  display: flex;
  gap: 6px;
  margin: 0;
}
.es-tool-k {
  flex: 0 0 auto;
  margin: 0 0 3px;
  font-size: 0.64rem;
  color: var(--text-faint);
}
.es-tool-v {
  font-size: 0.68rem;
  color: var(--text-muted);
  overflow-wrap: anywhere;
}
.es-samples {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  li {
    display: flex;
    gap: 8px;
    font-size: 0.69rem;
    line-height: 1.45;
  }
}
.es-sample-n {
  color: var(--text-muted);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.es-sample-p {
  margin-left: auto;
  flex: 0 0 auto;
  color: var(--text-faint);
}

.es-time {
  display: flex;
  gap: 6px;
  margin: 2px 0 0;
  font-size: 0.66rem;
  color: var(--text-faint);
}
.es-ms { color: var(--text-muted); }
</style>
