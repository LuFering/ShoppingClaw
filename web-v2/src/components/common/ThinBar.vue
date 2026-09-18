<template>
  <div class="thin-bar" :class="'tone-' + tone">
    <span class="fill" :style="{ width: pct + '%' }" />
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  value: { type: Number, required: true },
  max: { type: Number, default: 100 },
  // accent（默认）| pos 完成 | warn 临近 | neg 超支 | muted 未开始
  tone: { type: String, default: 'accent' }
})

const pct = computed(() => {
  if (!props.max) return 0
  return Math.max(0, Math.min(100, (props.value / props.max) * 100))
})
</script>

<style lang="less" scoped>
.thin-bar {
  height: 4px;
  border-radius: 2px;
  background: var(--bg-sunken);
  overflow: hidden;

  .fill {
    display: block;
    height: 100%;
    border-radius: 2px;
    background: var(--accent-500);
    transition: width 0.15s ease-out;
  }
}

.tone-pos .fill { background: var(--pos); }
.tone-warn .fill { background: var(--warn); }
.tone-neg .fill { background: var(--neg); }
.tone-muted .fill { background: var(--text-muted); }
</style>
