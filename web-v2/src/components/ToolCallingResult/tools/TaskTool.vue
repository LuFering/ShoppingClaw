<template>
  <BaseToolCall :tool-call="toolCall">
    <template #header>
      <div class="sep-header">
        <span class="subagent">{{ subagentDisplayName }}</span>
        <span v-if="runStatusLabel" class="run-status" :class="runStatusClass">{{ runStatusLabel }}</span>
        <span class="separator" v-if="shortDescription">|</span>
        <span class="description" v-if="shortDescription">{{ shortDescription }}</span>
      </div>
    </template>

    <template #params>
      <div v-if="description" class="task-description">{{ description }}</div>
    </template>

    <template #result="{ resultContent }">
      <div class="task-result">
        <MdPreview
          :modelValue="String(resultContent)"
          :theme="theme"
          previewTheme="github"
          class="md-preview-wrapper flat-md-preview"
        />
      </div>
    </template>
  </BaseToolCall>
</template>

<script setup>
import { computed } from 'vue'
import BaseToolCall from '../BaseToolCall.vue'
import { MdPreview } from 'md-editor-v3'
import 'md-editor-v3/lib/preview.css'
import { useThemeStore } from '@/stores/theme'
import { parseToolCallArgs, getToolCallDisplayStatus, getToolName } from '../toolRegistry'

const props = defineProps({
  toolCall: {
    type: Object,
    required: true
  }
})

const themeStore = useThemeStore()
const theme = computed(() => (themeStore.isDark ? 'dark' : 'light'))

const parsedArgs = computed(() => parseToolCallArgs(props.toolCall))

// 子智能体展示名：优先运行记录名 > display_label > 参数中的 subagent_type > 工具名映射
const subagentRun = computed(() => props.toolCall.subagent_run || null)
const subagentDisplayName = computed(() => {
  return (
    subagentRun.value?.subagent_name ||
    props.toolCall.display_label ||
    parsedArgs.value.subagent_type ||
    parsedArgs.value.subagent ||
    getToolName('task') ||
    '子智能体'
  )
})

const description = computed(
  () => parsedArgs.value.description || subagentRun.value?.description || ''
)

// 运行状态（对标 Yuxi）：failed → error
const rawStatus = computed(() => getToolCallDisplayStatus(props.toolCall))
const runStatus = computed(() => (rawStatus.value === 'error' ? 'failed' : rawStatus.value))
const runStatusLabel = computed(() => {
  if (runStatus.value === 'completed') return '已完成'
  if (runStatus.value === 'failed') return '失败'
  if (runStatus.value === 'running') return '运行中'
  return ''
})
const runStatusClass = computed(() => ({
  'is-running': runStatus.value === 'running',
  'is-completed': runStatus.value === 'completed',
  'is-failed': runStatus.value === 'failed'
}))

const shortDescription = computed(() => {
  const desc = description.value
  if (!desc) return ''
  return desc.length > 50 ? desc.slice(0, 50) + '...' : desc
})
</script>

<style lang="less" scoped>
.sep-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  width: 100%;
  overflow: hidden;

  .subagent {
    font-weight: 600;
    color: var(--main-700);
    white-space: nowrap;
    flex-shrink: 0;
  }

  .run-status {
    flex-shrink: 0;
    font-size: 12px;
    padding: 1px 8px;
    border-radius: 999px;
    white-space: nowrap;
    &.is-running { background: var(--main-50); color: var(--main-700); }
    &.is-completed { background: var(--color-success-50, var(--gray-100)); color: var(--color-success-500, var(--gray-600)); }
    &.is-failed { background: var(--color-error-50); color: var(--color-error-500); }
  }
}

.task-description {
  border-radius: 8px;
  font-size: 13px;
  color: var(--gray-800);
}

.task-result {
  padding: 12px;
  background: var(--gray-0);
  border-radius: 8px;

  :deep(.md-editor-preview-wrapper) {
    padding: 0;
  }

  :deep(.md-editor-preview) {
    font-size: 14px;
    color: var(--gray-800);
    background: transparent;
  }
}
</style>
