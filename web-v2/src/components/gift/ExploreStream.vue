<template>
  <section class="ex">
    <header class="ex__hd">
      <h2 class="ex__title">礼物探索流</h2>
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
        </div>

        <!-- 实时行动描述：只在运行中的那一步出现 -->
        <p v-if="s.status === 'running'" class="st__live">
          {{ s.live }}<i class="st__caret" />
        </p>

        <!-- 关键依据：每一步都要有，这是「可核对」的落点 -->
        <p v-else-if="s.status === 'done'" class="st__ev">
          <i class="st__evk">依据</i>{{ s.evidence }}
        </p>
        <p v-else-if="s.status === 'skipped'" class="st__ev st__ev--why">{{ s.why }}</p>

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
 * 两个刻意的取舍：
 *   1. 状态只有三种：进行中 / 已完成 / 已跳过（跳过必须写明为什么，不留空白）
 *   2. **被排除的候选不删除**，理由留在原地 —— 否则用户无法回答"为什么最后只剩 3 件"
 */
import { computed } from 'vue'

const props = defineProps({
  steps: { type: Array, default: () => [] },
  excluded: { type: Array, default: () => [] },
  stageKey: { type: String, default: '' },
  doneCount: { type: Number, default: 0 }
})

const shownExcluded = computed(() => props.excluded.filter((e) => e.shown))
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
