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
          <pre class="detail-content">{{ safeStringify(tool.args) }}</pre>
        </div>

        <!-- Output -->
        <div v-if="tool.output != null" class="detail-block">
          <div class="detail-label">Output</div>
          <pre class="detail-content">{{ safeStringify(tool.output) }}</pre>
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

const safeStringify = (value) => {
  const seen = new WeakSet()
  try {
    const json = JSON.stringify(value ?? null, (key, v) => {
      if (key === '__proto__') return undefined
      if (typeof v === 'object' && v !== null) {
        if (seen.has(v)) return '[Circular]'
        seen.add(v)
      }
      return v
    }, 2)
    
    if (!json) return ''
    if (json.length > 5000) return json.slice(0, 5000) + '\n...'
    return json
  } catch (e) {
    return String(e)
  }
}
</script>

<style scoped>
.tool-call-card {
  border: 1px solid var(--border-color, #f3f4f6);
  border-radius: 10px;
  background: white;
  transition: all 0.2s;
  overflow: hidden;
}

.tool-call-card:hover {
  border-color: var(--border-hover, #e5e7eb);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.tool-call-card.compact {
  border-radius: 8px;
}

/* Header */
.tool-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
}

.tool-header:hover {
  background: var(--hover-bg, #f9fafb);
}

.tool-chevron {
  color: var(--text-tertiary, #d1d5db);
  transition: transform 0.2s;
  flex-shrink: 0;
}

.tool-chevron.expanded {
  transform: rotate(90deg);
}

.tool-icon-wrapper {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: var(--bg-secondary, #f3f4f6);
  flex-shrink: 0;
}

.icon-emoji {
  font-size: 16px;
  line-height: 1;
}

.spinner-icon {
  color: #3b82f6;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.default-icon {
  color: var(--text-tertiary, #9ca3af);
}

.inline-spinner {
  color: #3b82f6;
  animation: spin 0.8s linear infinite;
}

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
  color: var(--text-primary, #374151);
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
}

.tool-arg-preview {
  font-size: 11px;
  color: var(--text-tertiary, #9ca3af);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
  background: var(--bg-secondary, #f9fafb);
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px solid var(--border-color, #f3f4f6);
}

.duration-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 6px;
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.1), rgba(52, 211, 153, 0.08));
  color: #10b981;
  border: 1px solid rgba(16, 185, 129, 0.2);
  flex-shrink: 0;
}

/* Detail */
.tool-detail {
  border-top: 1px solid var(--border-color, #f3f4f6);
  padding: 12px;
  background: var(--bg-secondary, #f9fafb);
}

.detail-block {
  margin-bottom: 12px;
}

.detail-block:last-child {
  margin-bottom: 0;
}

.detail-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-tertiary, #9ca3af);
  margin-bottom: 6px;
}

.detail-content {
  font-size: 11px;
  line-height: 1.6;
  color: var(--text-secondary, #4b5563);
  background: white;
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid var(--border-color, #e5e7eb);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow-y: auto;
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
}

.running-state {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  font-size: 12px;
  color: #3b82f6;
}

.animate-spin {
  animation: spin 0.8s linear infinite;
}

/* Transitions */
.detail-expand-enter-active,
.detail-expand-leave-active {
  transition: all 0.2s ease;
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
