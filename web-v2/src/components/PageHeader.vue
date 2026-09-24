<script setup>
/**
 * 页面抬头 —— 全站统一。
 *
 * 一条规则：**desc 写「这里能做什么」，不写「这个 agent 是什么样」**。
 *   好：「把组合采购拆成清单，判断留在决策图上可回看」  ← 功能性
 *   坏：「我拆清单、排顺序、盯依赖」                ← 自述/抒情，AI 味来源
 * 自述式文案与导航项、标题三处重复表达同一件事，是页面上最明显的冗余。
 *
 * `mark` 插槽给需要印章的 agent 页（采 / 礼）—— 印章是身份标识，
 * 放进抬头里，页面就别再自己画一条身份带了（那样标题会重复两遍）。
 *
 * 印章配色走 `--mark-bg` / `--mark-fg` 两个 CSS 变量：默认取站点主色（emerald），
 * 送礼这类有独立情境色的 agent 在页面根上覆盖即可。**不要再套一层自绘的章** ——
 * 那样会出现两个同尺寸方框叠在一起。
 */
defineProps({
  title: { type: String, required: true },
  desc: { type: String, default: '' }
})
</script>

<template>
  <header class="page-head">
    <span v-if="$slots.mark" class="page-mark"><slot name="mark" /></span>
    <div class="page-head-text">
      <h1 class="page-title">{{ title }}</h1>
      <p v-if="desc" class="page-desc">{{ desc }}</p>
      <div v-if="$slots.stats" class="stat-strip">
        <slot name="stats" />
      </div>
    </div>
    <div v-if="$slots.actions" class="page-head-actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style lang="less" scoped>
.page-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 18px;
}
/* 印章：与标题同排，替代原先「抬头 + 身份带」两份标题。
   配色可由页面通过 --mark-bg / --mark-fg 覆盖 —— 送礼用暖金，
   采购沿用站点主色，两者身份区分不靠"再画一个章"实现。 */
.page-mark {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  margin-top: 2px;
  border-radius: 9px;
  background: var(--mark-bg, var(--accent-50));
  color: var(--mark-fg, var(--accent-700));
  font-size: 0.88rem;
  font-weight: 600;
}
.page-head-text {
  flex: 1 1 auto;
  min-width: 0;
}
.page-title {
  font-family: var(--font-display);
  font-size: 1.35rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-strong);
  margin: 0;
}
.page-desc {
  font-size: 0.84rem;
  color: var(--text-muted);
  margin: 4px 0 0;
  line-height: 1.6;
  max-width: 640px;
}
.page-head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
  padding-top: 2px;
}
</style>
