<template>
  <section class="ex">
    <header class="ex__hd">
      <h2 class="ex__title">礼物探索流</h2>
      <span v-if="runningStep" class="ex__live">
        <i class="ex__live-dot" />进行中
      </span>
      <span v-else-if="totalMs" class="ex__total mono">共 {{ fmtMs(totalMs) }}</span>
      <span class="ex__prog mono">{{ doneCount }}/{{ steps.length }}</span>
    </header>

    <ol class="ex__list">
      <li
        v-for="(s, i) in steps"
        :key="s.key"
        class="st"
        :class="[`is-${s.status}`, { 'is-stage': stageKey === s.key }]"
      >
        <div class="st__head">
          <span class="st__no mono">{{ String(i + 1).padStart(2, '0') }}</span>
          <span class="st__label">{{ s.label }}</span>
          <span class="st__mark" />
          <span v-if="s.status === 'skipped'" class="st__skip">已跳过</span>
          <!-- 真实耗时：后端给 ms 就用，没给就不显示（不编一个） -->
          <span v-if="s.status === 'done' && s.ms != null" class="st__ms mono">{{ fmtMs(s.ms) }}</span>
        </div>

        <!-- 运行中：hint 是后端从图里取的「正在做什么」 -->
        <p v-if="s.status === 'running'" class="st__live">
          {{ s.hint || '正在处理…' }}<i class="st__caret" />
        </p>
        <p v-if="s.status === 'running'" class="st__elapsed mono">{{ elapsedOf(s) }}</p>

        <!-- 关键依据：每一步都要有，这是「可核对」的落点 -->
        <p v-else-if="s.status === 'done'" class="st__ev">
          <i class="st__evk">依据</i>{{ s.evidence }}
        </p>
        <p v-else-if="s.status === 'skipped'" class="st__ev st__ev--why">{{ s.why }}</p>

        <!--
          这一步在做什么的补充说明。
          ⚠️ 它由后端的 `live` 事件送来，而那条事件是在节点**跑完之后**发的
          （与 done 同一批）—— 所以原先把显示条件写成 `status === 'running'`
          等于永远不显示：文案到的时候状态已经是 done 了。
          这里改成「有就显示」，与状态解耦。
        -->
        <p v-if="s.live" class="st__note">{{ s.live }}</p>

        <!-- 被排除的候选保留理由，不删除 -->
        <ul v-if="s.key === 'exclude' && shownExcluded.length" class="exc">
          <li v-for="e in shownExcluded" :key="e.name">
            <span class="exc__n">{{ e.name }}</span>
            <span class="exc__w">{{ e.why }}</span>
          </li>
        </ul>
      </li>
    </ol>
  </section>
</template>

<script setup>
/**
 * 左栏 · 礼物探索流
 *
 * 用户规格：按时间展示 理解关系 → 提取需求 → 检索商品 → 比价验货 → 排除候选 → 组合礼盒 → 生成寄语，
 * 并标明**执行状态**与**关键依据**。
 *
 * 三个刻意的取舍：
 *   1. 状态只有三种：进行中 / 已完成 / 已跳过（跳过必须写明为什么，不留空白）
 *   2. **被排除的候选不删除**，理由留在原地 —— 否则用户无法回答"为什么最后只剩 3 件"
 *   3. 耗时一律用**实测**值：后端 step 事件带 ms 就用它，没有就退回本地计时
 *      （从收到 running 那一刻起算）。都不存在时**不显示**，不编一个数字。
 *
 * ═══════════════════════════════════════════════════════════════════
 * 2026-09-25：补上实时元素
 * ═══════════════════════════════════════════════════════════════════
 *
 * 原先 running 与 done 由后端在同一瞬间发出（都挂在节点跑完之后），
 * 所以「进行中」那一行从来来不及显示 —— 步骤会直接从灰跳到完成。
 * 现在后端从图的 debug 流里取到节点**开始执行**的时点，running 提前发出，
 * 中间那段真实的等待（检索 ~9s、模型组合 ~8s）才看得见。
 *
 * 计时用 requestAnimationFrame：标签页切到后台会自动停，回来再继续。
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  steps: { type: Array, default: () => [] },
  excluded: { type: Array, default: () => [] },
  stageKey: { type: String, default: '' },
  doneCount: { type: Number, default: 0 }
})

const shownExcluded = computed(() => props.excluded.filter((e) => e.shown))

const runningStep = computed(() => props.steps.find((s) => s.status === 'running'))
const totalMs = computed(() =>
  props.steps.reduce((sum, s) => sum + (typeof s.ms === 'number' ? s.ms : 0), 0)
)

const fmtMs = (ms) => {
  if (ms == null) return ''
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

// tick 只用来触发重算 —— 已用时长每 100ms 重算一次，而不是存成固定值
const tick = ref(0)
let rafId = null
let lastTick = 0
const frame = (now) => {
  rafId = requestAnimationFrame(frame)
  if (now - lastTick < 100) return
  lastTick = now
  tick.value++
}
const elapsedOf = (s) => {
  tick.value   // 建立依赖
  if (!s.startedAt) return ''
  return fmtMs(Date.now() - s.startedAt)
}

onMounted(() => { rafId = requestAnimationFrame((n) => { lastTick = n; frame(n) }) })
onBeforeUnmount(() => { if (rafId) cancelAnimationFrame(rafId) })
</script>

<style lang="less" scoped>
.ex { padding: 4px 0 24px; }

.ex__hd {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 0 16px 12px;
}
.ex__title {
  font-family: var(--font-display);
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-strong);
  margin: 0;
}
.ex__prog { margin-left: auto; font-size: 0.7rem; color: var(--text-faint); }
/* 进行中 / 合计耗时：与 es 那边同一套语言，两个 agent 保持一致 */
.ex__live {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-left: 2px;
  font-size: 0.68rem;
  color: var(--gift-accent);
}
.ex__live-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--gift-accent);
  animation: ex-breathe 1.2s ease-in-out infinite;
}
@keyframes ex-breathe {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.25; }
}
@media (prefers-reduced-motion: reduce) {
  .ex__live-dot { animation: none; }
}
.ex__total { margin-left: 2px; font-size: 0.68rem; color: var(--text-faint); }

.ex__list {
  list-style: none;
  margin: 0;
  padding: 0;
  position: relative;
}
/* 时间线：一条发丝线串起七步，位置感由它来给 */
.ex__list::before {
  content: '';
  position: absolute;
  left: 27px;
  top: 8px;
  bottom: 20px;
  width: 1px;
  background: var(--border);
}

.st {
  position: relative;
  padding: 9px 16px 9px 44px;
}
.st__head {
  display: flex;
  align-items: center;
  gap: 7px;
}
.st__no {
  position: absolute;
  left: 16px;
  font-size: 0.66rem;
  color: var(--text-faint);
  background: var(--bg-base);
  padding: 1px 0;
  width: 22px;
  text-align: center;
}
.st__label {
  font-size: 0.81rem;
  font-weight: 500;
  color: var(--text-muted);
}
.st__mark {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  border: 1px solid var(--border-strong);
  flex: 0 0 auto;
}
.st__skip { font-size: 0.66rem; color: var(--text-faint); }
/* 真实耗时：靠右，弱于标题 */
.st__ms {
  margin-left: auto;
  font-size: 0.66rem;
  color: var(--text-faint);
}

/* 进行中 */
.st.is-running .st__label { color: var(--text-strong); }
.st.is-running .st__mark {
  border-color: var(--gift-accent);
  background: var(--gift-accent);
  animation: st-pulse 1.2s ease-in-out infinite;
}
@keyframes st-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.25; }
}
@media (prefers-reduced-motion: reduce) {
  .st.is-running .st__mark { animation: none; }
}
.st.is-running .st__no { color: var(--gift-accent); }

/* 已完成 */
.st.is-done .st__mark { border-color: var(--gift-accent); background: var(--gift-accent); }

/* 已跳过：灰掉并划掉 */
.st.is-skipped .st__label { color: var(--text-faint); text-decoration: line-through; }
.st.is-skipped .st__mark { border-style: dashed; }

.st__live {
  font-size: 0.74rem;
  line-height: 1.6;
  color: var(--text);
  margin: 5px 0 0;
}
/* 实时累加的已用时长 —— 让「它还在动」这件事可见 */
.st__elapsed {
  margin: 2px 0 0;
  font-size: 0.68rem;
  color: var(--gift-accent);
}
.st__caret {
  display: inline-block;
  width: 2px;
  height: 0.8em;
  margin-left: 2px;
  vertical-align: -0.06em;
  background: var(--gift-accent);
  animation: st-caret 1s steps(2, start) infinite;
}
@keyframes st-caret {
  0%, 50% { opacity: 1; }
  50.01%, 100% { opacity: 0; }
}
@media (prefers-reduced-motion: reduce) {
  .st__caret { animation: none; }
}

.st__ev {
  font-size: 0.72rem;
  line-height: 1.6;
  color: var(--text-faint);
  margin: 4px 0 0;
}
.st__evk {
  font-style: normal;
  color: var(--gift-accent);
  margin-right: 6px;
}
.st__ev--why { color: var(--text-faint); }
/* 步骤说明（后端 live 事件）：比依据更弱，是注解不是结论 */
.st__note {
  margin: 3px 0 0;
  font-size: 0.69rem;
  line-height: 1.55;
  color: var(--text-faint);
}

/* 被排除的候选 */
.exc {
  list-style: none;
  margin: 7px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.exc li {
  display: flex;
  gap: 8px;
  font-size: 0.71rem;
  line-height: 1.5;
}
.exc__n {
  color: var(--text-muted);
  text-decoration: line-through;
  flex: 0 0 auto;
  max-width: 46%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.exc__w { color: var(--chart-palette-4); }
</style>
