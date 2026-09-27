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
  /**
   * @deprecated 不再渲染。
   *
   * 2026-09-28 全站页头改极简（对齐「主动助理 / 购物档案」那两页）：
   * 只留「标题 + 统计胶囊」，印章与描述行都去掉了。
   * 保留这个 prop 是为了让调用方传参不报错 —— 各页会在同一次改动里
   * 陆续清掉它，清完即可删掉这里。
   */
  desc: { type: String, default: '' }
})
</script>

<template>
  <header class="page-head">
    <div class="page-head-text">
      <h1 class="page-title">{{ title }}</h1>
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
/* ⚠️ 印章（.page-mark）与描述行（.page-desc）的样式已删 ——
   2026-09-28 全站页头改极简后没有元素再用它们。
   极简式的参照是「主动助理 / 购物档案」：只有标题 + 统计胶囊。 */
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
.page-head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
  padding-top: 2px;
}
</style>
