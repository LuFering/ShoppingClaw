<template>
  <div class="reasoning-block" :class="{ 'is-active': isActive }">
    <p class="rb-text">{{ displayText }}</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  content: { type: String, default: '' },
  isActive: { type: Boolean, default: false },
})

// 长推理折叠为末尾若干行，避免占据过多版面
const MAX = 400
const displayText = computed(() => {
  const t = String(props.content || '').trim()
  if (t.length <= MAX) return t
  return `…${t.slice(-MAX)}`
})
</script>

<style lang="less" scoped>
.reasoning-block {
  width: 100%;
  padding: 4px 2px 4px 10px;
  border-left: 2px solid var(--gray-200, #e5e7eb);
  margin-left: 2px;
  transition: border-color 0.2s ease;

  &.is-active {
    border-left-color: var(--main-300, #7fd1e0);
  }
}

.rb-text {
  margin: 0;
  font-size: 12px;
  line-height: 1.65;
  color: var(--gray-500, #6b7280);
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
