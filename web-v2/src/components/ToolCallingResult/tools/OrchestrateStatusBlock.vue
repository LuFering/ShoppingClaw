<template>
  <!-- 只在有实际内容时渲染：
       orchestrate 会随 ORCHESTRATION_REVEAL_STEPS 渐进显形 5 次
       （同一 tool_call_id 重发 tool_start，step 递增）。
       若每次都渲染空壳，用户会看到这一行反复闪烁。
       rows 为空且无 decision 时说明这一档还没内容，直接不渲染。 -->
  <div v-if="hasContent" class="orch-status" :class="{ 'is-active': isActive }">
    <div class="os-head">
      <Route :size="12" class="os-icon" />
      <span class="os-title">主智能体编排</span>
      <span v-if="decision" class="os-decision">{{ decision }}</span>
    </div>

    <ul v-if="rows.length" class="os-list">
      <li v-for="(r, i) in rows" :key="`o-${i}`">
        <span class="os-dot" :class="running ? 'is-loading' : 'is-done'"></span>
        <span class="os-name">{{ r.name }}</span>
        <span v-if="r.detail" class="os-detail">{{ r.detail }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Route } from 'lucide-vue-next'

const props = defineProps({
  toolCall: { type: Object, default: () => ({}) },
  isActive: { type: Boolean, default: false }
})

const orch = computed(() => props.toolCall?.orchestration || {})

const status = computed(() => orch.value.status || props.toolCall?.status || '')
const running = computed(() => status.value === 'running' || status.value === 'calling')

const decision = computed(() => orch.value.decision || '')

/** 有任一栏有内容才渲染 —— 避免渐进显形的中间档显示空壳。 */
const hasContent = computed(() => {
  const o = orch.value || {}
  const has = (k) => Array.isArray(o[k]) && o[k].length > 0
  if (has('skills') || has('rag') || has('mcp') || has('dispatch')) return true
  return Boolean(decision.value)
})

/** 把 skills / rag / mcp / dispatch 摊平成一列状态行。 */
const rows = computed(() => {
  const out = []
  const push = (arr) => {
    for (const x of arr || []) {
      if (!x) continue
      out.push({ name: x.name || x.id || '', detail: x.detail || x.task || '' })
    }
  }
  push(orch.value.skills)
  push(orch.value.rag)
  push(orch.value.mcp)
  push(orch.value.dispatch)
  return out
})
</script>

<style lang="less" scoped>
.orch-status {
  width: 100%;
  padding: 4px 2px 4px 10px;
  border-left: 2px solid var(--gray-200, #e5e7eb);
  margin-left: 2px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  transition: border-color 0.2s ease;

  &.is-active {
    border-left-color: var(--main-300, #7fd1e0);
  }
}

.os-head {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  min-width: 0;
}

.os-icon {
  color: var(--gray-400, #9ca3af);
  flex-shrink: 0;
}

.os-title {
  font-weight: 600;
  color: var(--gray-600, #4b5563);
  flex-shrink: 0;
}

.os-decision {
  min-width: 0;
  color: var(--gray-500, #6b7280);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.os-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 3px;

  li {
    display: flex;
    align-items: baseline;
    gap: 6px;
    font-size: 12px;
    min-width: 0;
  }
}

.os-dot {
  flex-shrink: 0;
  width: 6px;
  height: 6px;
  margin-top: 5px;
  border-radius: 50%;
  background: var(--color-success-500, #22c55e);

  &.is-loading {
    background: var(--gray-300, #d1d5db);
    animation: os-pulse 1.1s ease-in-out infinite;
  }
}

.os-name {
  flex-shrink: 0;
  font-weight: 600;
  color: var(--main-700, #0369a1);
}

.os-detail {
  min-width: 0;
  font-size: 12px;
  color: var(--gray-600, #4b5563);
  word-break: break-word;
}

@keyframes os-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

@media (prefers-reduced-motion: reduce) {
  .os-dot.is-loading { animation: none; }
}
</style>
