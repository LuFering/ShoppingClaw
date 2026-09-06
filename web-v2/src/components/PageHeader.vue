<script setup>
defineProps({
  title: { type: String, required: true },
  desc: { type: String, default: '' }
})
</script>

<template>
  <header class="page-head">
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
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
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
