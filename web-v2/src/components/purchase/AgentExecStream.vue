<template>
  <div class="es">
    <header class="es-head">
      <span class="es-title">执行流</span>
      <!--
        不报「第 N / 7 步」了 —— 走法由模型定，分母不存在。
        报「调了几次工具」，那是真实发生、可数的量。
      -->
      <span v-if="toolCount" class="es-prog mono">{{ toolCount }} 次调用</span>
      <span v-if="runningItem" class="es-live">
        <i class="es-live-dot" />进行中
      </span>
      <span v-else-if="totalMs" class="es-total mono">共 {{ fmtMs(totalMs) }}</span>
      <!--
        只看核心步骤：把模型说的话（推理 + 叙述）全折起来，只留工具调用。
        用户说「太一大串」主要就是这类行太多 —— 一次运行模型会吐二十几段，
        每段一行，真正「它做了什么」反而被淹没。
      -->
      <button
        v-if="reasonCount"
        class="es-filter"
        :class="{ on: hideReasoning }"
        type="button"
        :title="hideReasoning ? '显示模型的过程叙述' : '只看核心步骤（隐藏模型叙述）'"
        @click="hideReasoning = !hideReasoning"
      >{{ hideReasoning ? `显示过程 (${reasonCount})` : '只看核心' }}</button>
      <button
        v-if="!atBottom"
        class="es-jump"
        type="button"
        @click="scrollToBottom"
      >回到最新 ↓</button>
    </header>

    <div ref="scrollEl" class="es-scroll" @scroll="onScroll">
      <div
        v-for="item in visibleItems"
        :key="item.phase || item.uid"
        class="es-row"
        :class="{
          'is-live': item.state === 'running',
          'is-reason': isReasoning(item),
        }"
      >
        <div class="es-rail">
          <span class="es-dot" :class="'is-' + item.state">
            <i v-if="item.state === 'running'" class="es-dot-pulse" />
          </span>
          <span v-if="item !== visibleItems[visibleItems.length - 1]" class="es-line" />
        </div>

        <div class="es-body">
          <!--
            ═══════════════════════════════════════════════════════════
            2026-09-26：一屏只留「核心环节」，细节按需展开
            ═══════════════════════════════════════════════════════════
            之前每一行都把推理全文、工具入参、返回原文全铺出来 ——
            一次运行 30+ 行、每行好几行字，滚动条拉不到底，核心步骤反而
            被淹没了。用户要的是「指出核心环节」。

            现在每步**一行**：类型标签 + 做了什么 + 一句话结果 + 耗时。
            想看细节点这一行展开（推理原文 / 入参 / 返回样本）。
            流式期间例外：正在想的那一步把文字显示出来，让「它在动」可见，
            想完自动折回一行。
          -->
          <div class="es-main" role="button" tabindex="0" @click="toggle(item)">
            <span class="es-kind" :class="'k-' + item.kind">{{ KIND_LABEL[item.kind] || item.kind }}</span>
            <!-- 来源标记：llm 模型判断 / kb 知识库命中 / rule 规则兜底。
                 必须显示 —— 否则降级输出和模型判断长得一样，用户无从分辨。 -->
            <span v-if="item.by" class="es-by" :class="'by-' + item.by">{{ BY_LABEL[item.by] || item.by }}</span>

            <!--
              合并行：连续同类调用的「×N」角标。
              它是这一行最重要的信息 —— 一眼看出「这一步做了 5 次」，
              而不是让 5 行一模一样的「搜索…」把列表撑满。
            -->
            <span v-if="item.grouped?.length" class="es-mul mono">×{{ item.grouped.length }}</span>

            <span v-if="item.title" class="es-text">{{ item.title }}</span>

            <!-- 流式期间：显示正在生长的文字（截尾，避免撑开行高） -->
            <span v-if="item.streaming" class="es-live-text">
              {{ tail(item.detail) }}<i class="es-caret" />
            </span>
            <!-- 已结束：一句话结果。有标题时才加「·」当分隔，没标题它就是正文 -->
            <span
              v-else-if="briefOf(item)"
              class="es-brief"
              :class="{ 'is-solo': !item.title }"
            >{{ item.title ? '· ' : '' }}{{ briefOf(item) }}</span>

            <span v-if="item.state === 'running' && !item.streaming" class="es-elapsed mono">{{ elapsedOf(item) }}</span>
            <span v-else-if="item.ms != null" class="es-ms mono">{{ fmtMs(item.ms) }}</span>

            <!-- 有细节才显示可展开的提示 -->
            <span v-if="hasDetail(item)" class="es-chevron" :class="{ open: isOpen(item) }">›</span>
          </div>

          <!-- 展开的细节 -->
          <div v-if="isOpen(item)" class="es-detail">
            <!--
              合并行展开：把合并掉的每一次调用逐条列出。
              合并只是**收起**，不是丢弃 —— 想看「它到底搜了哪几个词」
              点开就有，这才是「简略但不失信息」。
            -->
            <template v-if="item.grouped?.length">
              <p class="es-detail-k">这一步的 {{ item.grouped.length }} 次</p>
              <ul class="es-samples">
                <li v-for="(g, k) in item.grouped" :key="k">
                  <span class="es-sample-n">{{ g.title || g.name }}</span>
                  <span v-if="briefOf(g)" class="es-sample-p mono">{{ briefOf(g) }}</span>
                </li>
              </ul>
            </template>

            <!-- 推理原文：模型逐段吐出来的，不是我们拼的一句话 -->
            <p v-if="item.detail && item.kind === 'think'" class="es-detail-think">{{ item.detail }}</p>

            <template v-if="item.args">
              <p class="es-detail-k">入参</p>
              <p class="es-detail-v mono">{{ fmtArgs(item.args) }}</p>
            </template>

            <template v-if="item.sample?.length">
              <p class="es-detail-k">返回 {{ item.sample.length }} 件</p>
              <ul class="es-samples">
                <li v-for="(s, k) in item.sample" :key="k">
                  <span class="es-sample-n">{{ s.name }}</span>
                  <span v-if="s.price != null" class="es-sample-p mono">¥{{ fmtPrice(s.price) }}</span>
                </li>
              </ul>
            </template>
            <template v-else-if="item.result">
              <p class="es-detail-k">工具返回原文</p>
              <pre class="es-result">{{ item.result }}</pre>
            </template>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 左栏 · agent 任务执行流。
 *
 * ═══════════════════════════════════════════════════════════════════
 * 2026-09-26：从「过程全铺」改成「核心环节 + 按需展开」
 * ═══════════════════════════════════════════════════════════════════
 *
 * 用户原话：「内容能不能做的简略一点，指出核心环节就行，不用这么一大串」。
 *
 * 之前每一行都把三样东西全铺出来：推理全文（常常几百字）、工具入参、
 * 返回原文。一次运行 30+ 行，一屏放不下，**核心步骤反而被淹没了** ——
 * 想看「它搜了几次、最后选了啥」得在字缝里找。
 *
 * 现在：
 *   · 每步**一行** —— 类型标签 + 做了什么 + 一句话结果 + 耗时
 *   · 细节（推理原文 / 入参 / 返回样本）点这一行才展开
 *   · 流式期间例外：正在想的那一步把文字显示出来（截尾 + 光标），
 *     让「它在动」可见；想完自动折回一行
 *
 * 「实时」没有丢：进行中的步骤仍有呼吸点 + 每 100ms 重算的已用秒数，
 * 只是不再把整段推理糊在列表里。
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
const toolCount = computed(() => props.items.filter((x) => x.kind === 'call').length)

/**
 * 这一行是不是「模型的推理」（草稿纸）。
 *
 * 用户说「太一大串」主要就是这类行太多 —— 模型一次思考会吐十几段，
 * 每段一行就把工具调用（真正的核心步骤）挤没了。
 */
const isReasoning = (item) => item.kind === 'think' && item.thinkKind === 'reasoning'

/** 模型叙述行数 —— 为 0 时不显示「只看核心」按钮（没什么可藏的） */
const reasonCount = computed(() => props.items.filter((x) => x.kind === 'think').length)

/**
 * 默认**只看核心**。
 *
 * ═══════════════════════════════════════════════════════════════════
 * 2026-09-27：默认值从 false 改成 true
 * ═══════════════════════════════════════════════════════════════════
 * 用户第三次提这件事：「左边执行流还是内容太密集了，简化到显示模型做了
 * 什么、正在做什么、得到的简要结果就行」。
 *
 * 前两次我只是把行**压扁**（一屏一行、细节按需展开），但没有改**默认
 * 显示什么** —— 默认仍然是全量，一次运行 32 行里二十几行是模型的思考与
 * 叙述。用户要的是「它做了什么」，那是工具调用。所以默认就该是核心视图，
 * 想看模型的推理过程再点开。
 */
const hideReasoning = ref(true)

/**
 * 连续同类调用合并成一行。
 *
 * 「搜索 X」出现 8 次就是 8 行几乎一样的字 —— 这是密集感的第二大来源
 *（第一大是模型叙述，已默认折起）。合并成「搜索  ×8」一行，点开看
 * 每一次搜的是什么。
 *
 * ⚠️ 只合并**连续**的同类调用，且**必须有标题**：
 *   · 不连续不能合 —— 中间夹着别的步骤，合了会打乱时序
 *     （「搜 → 排除 → 搜」变成一个「搜 ×2」是错的，排除确实发生在两次搜索之间）
 *   · 正在跑的那条不合并 —— 它要单独显示实时秒数与流式文字
 *   · 阶段行（phase）不合并 —— 它是分段的锚点，合了就没有节奏了
 * 合并后的行**保留最后一次调用**作为代表，并挂上 `grouped` 供展开。
 */
const GROUPABLE = new Set(['call', 'retrieve'])

const groupedItems = computed(() => {
  const src = props.items
  const out = []
  for (const it of src) {
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
      // 代表行沿用上一条，但把这一条并进去
      out[out.length - 1] = {
        ...prev,
        grouped: [...(prev.grouped || [prev]), it],
        // 结果取最新一次的，耗时是这一组的总和
        result: it.result || prev.result,
        sample: it.sample?.length ? it.sample : prev.sample,
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
 * 「只看核心」= **只留工具调用与阶段**，把模型说的话全折起来。
 *
 * ⚠️ 不能只滤 reasoning：模型还有一路 `content`（它给用户看的叙述），
 * 一次运行同样有十几段。只滤 reasoning 实测 28 行 → 22 行，几乎没变化
 * —— 用户要的「核心环节」是**它做了什么**（查了什么、搜了什么、排除了
 * 什么、定了什么），那些是 call 行。
 *
 * 但**正在流式输出的那条要留**：否则点了之后界面完全静止，
 * 用户会以为卡住了。
 */
const visibleItems = computed(() => {
  // 空行先剔掉：模型每一轮思考会先起一条流式行，若下一步没跟上收尾
  // （run 结束、或事件被节流），它会永远停在 streaming 状态 —— 于是
  // 绕过下面的过滤，在「只看核心」里留下一排没有文字的空「思考」行。
  // 实测一次运行有 4~5 条这样的空行。
  const rows = groupedItems.value.filter(
    (x) => !(x.kind === 'think' && !String(x.detail || '').trim() && !x.streaming)
  )
  return hideReasoning.value
    ? rows.filter((x) => x.kind !== 'think' || (x.streaming && String(x.detail || '').trim()))
    : rows
})

/**
 * 展开的行。
 *
 * 用 Set 存**行对象引用**（不是下标）—— 行会被 push 进来，下标会漂。
 */
const expanded = ref(new Set())
const isOpen = (item) => expanded.value.has(item)
const toggle = (item) => {
  if (!hasDetail(item)) return
  const next = new Set(expanded.value)
  if (next.has(item)) next.delete(item)
  else next.add(item)
  expanded.value = next
}

/** 这行有没有可展开的东西 */
const hasDetail = (item) =>
  Boolean(item.args || item.result || item.sample?.length ||
          (item.detail && item.kind === 'think'))

/**
 * 一句话结果 —— 收起时显示的摘要。
 *
 * 工具调用优先用返回样本的**件数**（「6 件」比「返回 6 件商品…」一眼）；
 * 没有样本就取返回原文的第一行去掉前缀。
 */
const briefOf = (item) => {
  if (item.sample?.length) return `${item.sample.length} 件`
  if (item.result) {
    const first = String(item.result).split('\n')[0]
    // 「关键词「隔音材料」返回 6 件：」→ 只留「6 件」
    const m = first.match(/返回\s*(\d+)\s*件/)
    if (m) return `${m[1]} 件`
    if (/没有返回|未找到|暂未/.test(first)) return '无结果'
    return first.slice(0, 26)
  }
  if (item.kind === 'think' && item.detail) return item.detail.replace(/\s+/g, ' ').slice(0, 34)
  if (item.detail) return String(item.detail).slice(0, 34)
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
/* 「只看核心」开关：默认态低调，开启时高亮 —— 让用户知道当前被过滤了 */
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
.es-filter + .es-jump { margin-left: 6px; }

.es-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding-right: 2px;
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
  一行的主体。用 flex + 单行省略，保证**永远占一行** ——
  这是「简略」的关键：不管标题多长、结果多长，都截断而不是折行。
*/
.es-main {
  display: flex;
  align-items: center;
  gap: 5px;
  min-height: 20px;
  cursor: pointer;
  border-radius: var(--radius-sm);
  &:hover { background: var(--bg-sunken); }
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

.es-text {
  font-size: 0.75rem;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 0 1 auto;
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

/* 一句话结果：比标题弱，但仍然是一行 */
.es-brief {
  flex: 0 1 auto;
  font-size: 0.71rem;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
  /* 没有标题时它就是这行的正文（思考行）—— 用正文色、去掉「·」前缀感 */
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

/* 可展开提示：只在有细节时出现 */
.es-chevron {
  flex: 0 0 auto;
  font-size: 0.72rem;
  line-height: 1;
  color: var(--text-faint);
  transition: transform 0.15s ease-out;
  &.open { transform: rotate(90deg); }
}

/* ── 展开的细节 ── */
.es-detail {
  margin: 4px 0 6px;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  background: var(--bg-sunken);
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.es-detail-think {
  margin: 0;
  font-size: 0.71rem;
  line-height: 1.6;
  color: var(--text);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 200px;
  overflow-y: auto;
}
.es-detail-k {
  margin: 0;
  font-size: 0.62rem;
  color: var(--text-faint);
}
.es-detail-v {
  margin: 0;
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
.es-result {
  margin: 0;
  max-height: 160px;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-family: var(--font-mono);
  font-size: 0.66rem;
  line-height: 1.5;
  color: var(--text-muted);
}
</style>
