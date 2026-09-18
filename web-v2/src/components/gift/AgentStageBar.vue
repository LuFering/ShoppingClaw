<template>
  <div class="sb">
    <span class="sb__rail" />

    <div class="sb__in">
      <div class="sb__row">
        <span class="sb__who">策展人</span>

        <span class="sb__stages">
          <span
            v-for="s in stages"
            :key="s.key"
            class="st"
            :class="`is-${s.state}`"
            :title="s.by"
          >
            <i class="st__dot" />{{ s.label }}
          </span>
        </span>

        <button class="sb__more" type="button" @click="$emit('expand')">
          {{ settled ? '看全过程' : '展开全过程' }}
        </button>
      </div>

      <!-- 只显示当前这一句：上一句被替换掉，所以这一行永远不会变长 -->
      <p class="sb__live">
        <b v-if="by && running" class="sb__by">{{ by }}</b>
        <template v-if="running">
          <span class="sb__tx">{{ text }}</span><i class="sb__caret" />
        </template>
        <template v-else-if="settled">
          <span class="sb__done">方案定了 · {{ count }} 段推理已收进时间线，随时可回看</span>
        </template>
        <template v-else>
          <span class="sb__idle">还没有开始</span>
        </template>
      </p>
    </div>
  </div>
</template>

<script setup>
/**
 * agent 状态条 —— 推理可见性的第一层（常驻一行）。
 *
 * 它回答的是「agent 现在在干什么」，所以：
 *   · 五个阶段是**有限的**，永不增长（不是事件列表）
 *   · 实时文字只显示**当前这一句**，新句子把旧句子覆盖掉 —— 这一行的高度是常数
 *   · 完整原文不在这里，在「思考时间线」覆盖层里
 *
 * 这三条合起来才是「一屏装得下长推理」的答案：可见性靠锚点分散，不靠把一条流拉长。
 */
defineProps({
  stages: { type: Array, default: () => [] },
  by: { type: String, default: '' },
  text: { type: String, default: '' },
  running: { type: Boolean, default: false },
  settled: { type: Boolean, default: false },
  count: { type: Number, default: 0 }
})

defineEmits(['expand'])
</script>

<style lang="less" scoped>
.sb {
  position: relative;
  flex: 0 0 auto;
  display: flex;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
}
.sb__rail {
  flex: 0 0 2px;
  background: var(--gift-accent);
}

.sb__in {
  flex: 1 1 auto;
  min-width: 0;
  padding: 9px 26px 10px;
}

.sb__row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.sb__who {
  font-size: 0.72rem;
  letter-spacing: 0.06em;
  color: var(--gift-accent);
  flex: 0 0 auto;
}

.sb__stages {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
}
.st {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 0.71rem;
  padding: 3px 10px;
  border-radius: 99px;
  border: 1px solid var(--border);
  color: var(--text-faint);
  white-space: nowrap;
  flex: 0 0 auto;
}
.st__dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--border-strong);
}
.st.is-done {
  border-color: var(--gift-accent-line);
  color: var(--gift-accent);
}
.st.is-done .st__dot { background: var(--gift-accent); }
.st.is-now {
  border-color: var(--gift-accent);
  background: var(--gift-accent-soft);
  color: var(--gift-accent);
}
.st.is-now .st__dot {
  background: var(--gift-accent);
  animation: st-pulse 1.2s ease-in-out infinite;
}
@keyframes st-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.25; }
}
@media (prefers-reduced-motion: reduce) {
  .st.is-now .st__dot { animation: none; }
}

.sb__more {
  margin-left: auto;
  flex: 0 0 auto;
  font-family: var(--font-body);
  font-size: 0.71rem;
  padding: 3px 11px;
  border-radius: 99px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}
.sb__more:hover { border-color: var(--border-strong); color: var(--text); }

.sb__live {
  display: flex;
  align-items: baseline;
  gap: 7px;
  margin: 7px 0 0;
  min-width: 0;
  font-size: 0.76rem;
  line-height: 1.5;
}
.sb__by {
  flex: 0 0 auto;
  font-weight: 400;
  color: var(--gift-accent);
}
.sb__tx,
.sb__done,
.sb__idle {
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sb__idle { color: var(--text-faint); }

.sb__caret {
  display: inline-block;
  width: 2px;
  height: 0.82em;
  margin-left: 2px;
  vertical-align: -0.06em;
  background: var(--gift-accent);
  animation: sb-caret 1s steps(2, start) infinite;
}
@keyframes sb-caret {
  0%, 50% { opacity: 1; }
  50.01%, 100% { opacity: 0; }
}
@media (prefers-reduced-motion: reduce) {
  .sb__caret { animation: none; }
}
</style>
