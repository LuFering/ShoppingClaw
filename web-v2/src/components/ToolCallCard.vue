<template>
  <div class="tool-call-card" :class="{ 'expanded': isExpanded, 'compact': compact }">
    <!-- Tool Header (always visible) -->
    <div class="tool-header" @click="$emit('toggle-expand')">
      <ChevronRight
        size="10"
        class="tool-chevron"
        :class="{ 'expanded': isExpanded }"
      />
      
      <!-- Icon -->
      <div class="tool-icon-wrapper">
        <span v-if="tool.icon" class="icon-emoji">{{ tool.icon }}</span>
        <LoaderCircle v-else-if="isRunning" size="14" class="spinner-icon" />
        <Zap v-else size="14" class="default-icon" />
      </div>

      <!-- Loading spinner alongside emoji -->
      <LoaderCircle v-if="isRunning && tool.icon" size="12" class="inline-spinner" />

      <!-- Tool Info -->
      <div class="tool-info">
        <span class="tool-name">{{ tool.name }}</span>
        <span v-if="getToolArg() && !isExpanded" class="tool-arg-preview">
          {{ getToolArg() }}
        </span>
      </div>

      <!-- Duration Badge -->
      <span v-if="tool.duration && tool.status === 'completed'" class="duration-badge">
        {{ formatDuration(tool.duration) }}
      </span>
    </div>

    <!-- Tool Detail (expandable) -->
    <transition name="detail-expand">
      <div v-if="isExpanded" class="tool-detail">
        <!-- Input -->
        <div v-if="tool.args && Object.keys(tool.args).length > 0" class="detail-block">
          <div class="detail-label">Input</div>
          <div class="detail-box"><ToolOutputView :output="tool.args" /></div>
        </div>

        <!-- Output -->
        <div v-if="tool.output != null" class="detail-block">
          <div class="detail-label">Output</div>
          <div class="detail-box"><ToolOutputView :output="tool.output" /></div>
        </div>

        <!-- Running State -->
        <div v-if="isRunning && !tool.output" class="running-state">
          <LoaderCircle size="14" class="animate-spin" />
          <span>执行中...</span>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { ChevronRight, Zap, LoaderCircle } from 'lucide-vue-next'
import ToolOutputView from '@/components/ToolOutputView.vue'

const props = defineProps({
  tool: {
    type: Object,
    required: true
  },
  isExpanded: {
    type: Boolean,
    default: false
  },
  compact: {
    type: Boolean,
    default: false
  }
})

defineEmits(['toggle-expand', 'click'])

const isRunning = computed(() => props.tool.status === 'running')

const getToolArg = () => {
  if (!props.tool.args) return ''
  
  // Handle string args
  if (typeof props.tool.args === 'string') {
    return props.tool.args.slice(0, 80)
  }
  
  const fn = props.tool.name || ''
  
  // Smart arg extraction based on tool name
  if (fn.includes('search')) {
    return props.tool.args.query || props.tool.args.search_query || ''
  }
  if (fn.includes('exec') || fn === 'execute') {
    return props.tool.args.command || ''
  }
  if (fn.includes('file') || fn === 'read_file' || fn === 'write_file') {
    return props.tool.args.file_path || props.tool.args.file || ''
  }
  if (fn.includes('crawl') || fn.startsWith('browser_')) {
    return props.tool.args.url || ''
  }
  
  // Fallback: first string value
  const vals = Object.values(props.tool.args)
  if (vals.length > 0 && typeof vals[0] === 'string') {
    return String(vals[0]).slice(0, 80)
  }
  
  return ''
}

const formatDuration = (ms) => {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}
</script>

<style lang="less" scoped>
.tool-call-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  transition: border-color 0.15s ease-out;
  overflow: hidden;

  &:hover { border-color: var(--border-strong); }
}

/* Header */
.tool-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s ease-out;
}
.tool-header:hover {
  background: var(--bg-sunken);
}

.tool-chevron {
  color: var(--text-faint);
  transition: transform 0.15s ease-out;
  flex-shrink: 0;
}
.tool-chevron.expanded {
  transform: rotate(90deg);
}

.tool-icon-wrapper {
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: var(--bg-sunken);
  flex-shrink: 0;
}
.icon-emoji { font-size: 15px; line-height: 1; }
.spinner-icon { color: var(--info); animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.default-icon { color: var(--text-faint); }
.inline-spinner { color: var(--info); animation: spin 0.8s linear infinite; flex-shrink: 0; }

.tool-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.tool-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-strong);
  font-family: var(--font-mono);
}
.tool-arg-preview {
  font-size: 11px;
  color: var(--text-faint);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
  background: var(--bg-sunken);
  padding: 2px 6px;
  border-radius: 4px;
}

.duration-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--accent-50);
  color: var(--accent-700);
  flex-shrink: 0;
}

/* Detail */
.tool-detail {
  border-top: 1px solid var(--border);
  padding: 10px 12px;
  background: var(--bg-sunken);
}
.detail-block { margin-bottom: 10px; }
.detail-block:last-child { margin-bottom: 0; }
.detail-label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.05em;
  color: var(--text-faint);
  margin-bottom: 6px;
}
.detail-box {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 10px;
  max-height: 240px;
  overflow-y: auto;
}

.running-state {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 12px;
  color: var(--info);
}
.animate-spin { animation: spin 0.8s linear infinite; }

/* Transitions */
.detail-expand-enter-active,
.detail-expand-leave-active {
  transition: all 0.18s ease;
  overflow: hidden;
}
.detail-expand-enter-from,
.detail-expand-leave-to {
  opacity: 0;
  max-height: 0;
}
.detail-expand-enter-to,
.detail-expand-leave-from {
  opacity: 1;
  max-height: 500px;
}
</style>
