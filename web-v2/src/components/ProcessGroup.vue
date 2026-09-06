<template>
  <div class="process-group" :class="{ live }">
    <button class="pg-summary" :aria-expanded="expanded" @click="expanded = !expanded">
      <Atom :size="14" class="pg-icon" :class="{ spin: live && runningCount > 0 }" />
      <span class="pg-text">{{ summaryText }}</span>
      <span v-if="metaText" class="pg-meta">{{ metaText }}</span>
      <span v-if="statusTag" class="pg-tag" :class="{ fail: failedCount > 0 }">{{ statusTag }}</span>
      <span v-if="durationText" class="pg-duration mono">{{ durationText }}</span>
      <ChevronDown :size="14" class="pg-chevron" :class="{ open: expanded }" />
    </button>

    <div class="pg-panel" :class="{ open: expanded }">
      <div class="pg-inner">
        <div v-if="planSteps.length" class="pg-section">
          <StepMessage v-for="ps in planSteps" :key="ps.id || ps.description" :step="ps" />
        </div>
        <div v-if="thinkingLines.length" class="pg-section pg-thinking">
          <p v-for="(line, i) in thinkingLines" :key="i" class="pg-think-line">{{ line }}</p>
        </div>
        <div v-if="toolCalls.length" class="pg-section">
          <ToolCallCard
            v-for="tc in toolCalls"
            :key="tc.toolCallId || tc.id"
            :tool="tc"
            :is-expanded="expandedToolIds.has(tc.toolCallId || tc.id)"
            @toggle-expand="toggleTool(tc.toolCallId || tc.id)"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Atom, ChevronDown } from 'lucide-vue-next'
import StepMessage from '@/components/StepMessage.vue'
import ToolCallCard from '@/components/ToolCallCard.vue'

const props = defineProps({
  steps: { type: Array, default: () => [] },
  planSteps: { type: Array, default: () => [] },
  toolCalls: { type: Array, default: () => [] },
  // 进行中的实时过程组：强制展开；结束（live 变 false）自动收起为摘要
  live: { type: Boolean, default: false }
})

// Yuxi 式：默认收起为耗时摘要行；live 时强制展开
const expanded = ref(props.live)
const expandedToolIds = ref(new Set())
watch(
  () => props.live,
  (v) => {
    expanded.value = v
    // 新一轮开始（live 变 true）时收起所有工具卡展开
    if (v) expandedToolIds.value = new Set()
  },
  { immediate: true }
)

const toggleTool = (id) => {
  const next = new Set(expandedToolIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedToolIds.value = next
}

const thinkingLines = computed(() =>
  (props.steps || [])
    .filter((s) => s.type === 'thinking' && s.content)
    .map((s) => s.content.trim())
    .filter(Boolean)
)

const toolNames = computed(() => {
  const seen = new Set()
  const names = []
  for (const t of props.toolCalls || []) {
    const n = (t.name || t.function || '').trim()
    if (n && !seen.has(n)) { seen.add(n); names.push(n) }
  }
  return names
})

const failedCount = computed(() => (props.toolCalls || []).filter((t) => t.status === 'failed').length)
const runningCount = computed(() => (props.toolCalls || []).filter((t) => t.status === 'running' || t.status === 'calling').length)

const summaryText = computed(() => {
  const parts = []
  if (thinkingLines.value.length) parts.push(`已思考 ${thinkingLines.value.length} 段`)
  if (props.toolCalls.length) {
    parts.push(
      props.toolCalls.length === 1
        ? `调用：${toolNames.value[0] || '工具'}`
        : `已调用 ${props.toolCalls.length} 个工具`
    )
  }
  if (!parts.length) return props.live ? '思考中…' : '本轮无过程数据'
  return parts.join(' · ')
})

const metaText = computed(() =>
  props.toolCalls.length > 1 ? toolNames.value.slice(0, 3).join('、') + (toolNames.value.length > 3 ? ` +${toolNames.value.length - 3}` : '') : ''
)

const statusTag = computed(() => {
  if (props.live) return runningCount.value > 0 ? '进行中' : ''
  return failedCount.value > 0 ? `${failedCount.value} 失败` : ''
})

const durationText = computed(() => {
  const total = (props.toolCalls || []).reduce((sum, t) => sum + (t.duration || t.duration_ms || 0), 0)
  if (!total) return ''
  return total >= 1000 ? `${(total / 1000).toFixed(1)}s` : `${total}ms`
})
</script>

<style lang="less" scoped>
.process-group {
  width: 100%;
  margin: 6px 0;
}

.pg-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 30px;
  padding: 4px 2px;
  border: none;
  border-bottom: 1px solid var(--gray-150);
  background: transparent;
  font-family: var(--font-body);
  font-size: 12px;
  color: var(--gray-500);
  cursor: pointer;
  text-align: left;
  transition: color 0.15s ease-out;

  &:hover, &:focus-visible { color: var(--gray-700); outline: none; }
}

.pg-icon {
  flex-shrink: 0;
  color: var(--gray-500);
  .live & { color: var(--accent-600); }
  &.spin { animation: pg-rotate 1.2s linear infinite; }
}
@keyframes pg-rotate { to { transform: rotate(360deg); } }

.pg-text {
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pg-meta {
  font-size: 11px;
  color: var(--gray-400);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pg-tag {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--accent-700);
  &.fail { color: var(--neg); }
}

.pg-duration {
  flex-shrink: 0;
  margin-left: auto;
  font-size: 11px;
  color: var(--gray-400);
}

.pg-chevron {
  flex-shrink: 0;
  color: var(--gray-400);
  transition: transform 0.15s ease-out;
  &.open { transform: rotate(180deg); }
}

/* grid 0fr→1fr 高度过渡（与配置二级展开同一手法） */
.pg-panel {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.15s ease-out;
  &.open { grid-template-rows: 1fr; }
}
.pg-inner { overflow: hidden; }

.pg-section {
  padding: 10px 2px 4px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.pg-thinking {
  border-left: 2px solid var(--gray-150);
  margin-left: 6px;
  padding-left: 10px;
}
.pg-think-line {
  margin: 0;
  font-size: 0.8rem;
  color: var(--text-muted);
  line-height: 1.6;
}
</style>
