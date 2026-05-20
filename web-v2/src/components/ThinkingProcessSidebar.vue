<template>
  <div
    class="thinking-sidebar"
    :class="{ 'sidebar-open': isOpen, 'no-transition': isInitialRender }"
  >
    <div class="sidebar-content">
      <!-- Header -->
      <div class="sidebar-header">
        <div class="header-left">
          <div v-if="isProcessing" class="status-indicator processing">
            <div class="spinner-ring"></div>
          </div>
          <div v-else-if="hasError" class="status-indicator error">
            <AlertCircle size="16" />
          </div>
          <div v-else-if="hasCompletedSteps" class="status-indicator completed">
            <CheckCircle size="16" />
          </div>
          <div class="header-title">
            <Brain size="18" />
            <span>{{ headerTitle }}</span>
          </div>
        </div>
        <div class="header-actions">
          <div class="toggle-btn" @click="closeSidebar">
            <PanelRightClose size="20" />
          </div>
        </div>
      </div>

      <!-- Content Area -->
      <div class="thinking-content">
        <!-- Empty State -->
        <div v-if="!hasAnyContent" class="empty-state">
          <Brain size="48" class="empty-icon" />
          <p class="empty-text">暂无思考过程</p>
          <p class="empty-hint">开始对话后,AI 的思考过程将在这里实时展示</p>
        </div>

        <div v-else class="sections-container">
          <!-- ═══ Thinking Section ═══ -->
          <section v-if="thinkingItems.length > 0" class="thinking-section">
            <div
              @click="sections.thinking.expanded = !sections.thinking.expanded"
              class="section-header"
            >
              <ChevronRight
                size="12"
                class="chevron-icon"
                :class="{ 'expanded': sections.thinking.expanded }"
              />
              <Lightbulb size="13" class="section-icon thinking" />
              <span class="section-title">思考过程</span>
              <div v-if="isCurrentlyThinking" class="thinking-dots">
                <span v-for="i in 3" :key="i" class="dot" :style="{ animationDelay: `${(i-1) * 200}ms` }"></span>
              </div>
            </div>
            <div v-if="sections.thinking.expanded" ref="thinkingContentRef" class="section-content thinking-content">
              <div class="thinking-text">
                {{ aggregatedThinkingContent }}
              </div>
              <div v-if="isCurrentlyThinking" class="processing-indicator">
                <span class="pulse-dot"></span>
                <span>思考中...</span>
              </div>
            </div>
          </section>

          <!-- ═══ Steps/Plan Section ═══ -->
          <section v-if="normalizedPlanSteps.length > 0" class="steps-section">
            <div
              @click="sections.steps.expanded = !sections.steps.expanded"
              class="section-header"
            >
              <ChevronRight
                size="12"
                class="chevron-icon"
                :class="{ 'expanded': sections.steps.expanded }"
              />
              <ListChecks size="13" class="section-icon steps" />
              <span class="section-title">任务进度</span>
              <span class="step-counter">{{ completedStepsCount }}/{{ normalizedPlanSteps.length }}</span>
            </div>
            <div v-if="sections.steps.expanded" class="section-content steps-content">
              <!-- Progress Bar -->
              <div class="progress-bar-wrapper">
                <div
                  class="progress-bar"
                  :class="{ 'completed': allStepsCompleted }"
                  :style="{ width: progressPercent + '%' }"
                ></div>
              </div>
              <!-- Steps List -->
              <div class="steps-list">
                <div
                  v-for="step in normalizedPlanSteps"
                  :key="step.id"
                  @click="selectStep(step.id)"
                  class="step-item"
                  :class="{
                    'selected': selectedStepId === step.id,
                    'running': step.status === 'running',
                    'completed': step.status === 'completed',
                    'failed': step.status === 'failed'
                  }"
                >
                  <div class="step-status">
                    <CheckCircle v-if="step.status === 'completed'" size="14" class="status-icon completed" />
                    <LoaderCircle v-else-if="step.status === 'running'" size="14" class="status-icon running" />
                    <AlertCircle v-else-if="step.status === 'failed'" size="14" class="status-icon failed" />
                    <Circle v-else size="14" class="status-icon pending" />
                  </div>
                  <span class="step-description">{{ step.description || step.title }}</span>
                  <span v-if="step.toolCallIds?.length" class="step-tool-count">{{ step.toolCallIds.length }}</span>
                </div>
              </div>
            </div>
          </section>

          <!-- ═══ Tools Section ═══ -->
          <section v-if="visibleToolItems.length > 0 || isProcessing" class="tools-section">
            <div
              @click="sections.tools.expanded = !sections.tools.expanded"
              class="section-header"
            >
              <ChevronRight
                size="12"
                class="chevron-icon"
                :class="{ 'expanded': sections.tools.expanded }"
              />
              <Wrench size="13" class="section-icon tools" />
              <span class="section-title">工具调用</span>
              <span v-if="selectedStepId" @click.stop="clearStepFilter" class="filter-badge">
                {{ visibleToolItems.length }}/{{ toolItems.length }} ×
              </span>
              <span v-else-if="toolItems.length > 0" class="tool-counter">{{ toolItems.length }}</span>
            </div>
            <div v-if="sections.tools.expanded" ref="toolsContentRef" class="section-content tools-content">
              <div class="tools-list">
                <!-- Empty state when filtered -->
                <div v-if="selectedStepId && visibleToolItems.length === 0" class="empty-filter">
                  该步骤没有关联的工具
                </div>
                <div v-for="item in visibleToolItems" :key="item.id" class="tool-item">
                  <!-- Tool Header -->
                  <div
                    @click="toggleToolExpand(item.id)"
                    class="tool-header"
                    :class="{ 'expanded': expandedToolIds.has(item.id) }"
                  >
                    <ChevronRight
                      size="10"
                      class="tool-chevron"
                      :class="{ 'expanded': expandedToolIds.has(item.id) }"
                    />
                    <span v-if="item.icon" class="tool-icon">{{ item.icon }}</span>
                    <LoaderCircle v-else-if="isToolRunning(item)" size="14" class="tool-loading" />
                    <Zap v-else size="14" class="tool-icon-default" />
                    <div class="tool-info">
                      <span class="tool-name">{{ item.name }}</span>
                      <span v-if="getToolArg(item) && !expandedToolIds.has(item.id)" class="tool-arg-preview">
                        {{ getToolArg(item) }}
                      </span>
                    </div>
                    <span v-if="item.duration && item.status === 'completed'" class="tool-duration">
                      {{ formatDuration(item.duration) }}
                    </span>
                  </div>
                  <!-- Tool Detail -->
                  <div v-if="expandedToolIds.has(item.id)" class="tool-detail">
                    <div v-if="item.args && Object.keys(item.args).length > 0" class="detail-block">
                      <div class="detail-label">Input</div>
                      <pre class="detail-content">{{ safeStringify(item.args) }}</pre>
                    </div>
                    <div v-if="item.output != null" class="detail-block">
                      <div class="detail-label">Output</div>
                      <pre class="detail-content">{{ safeStringify(item.output) }}</pre>
                    </div>
                    <div v-if="isToolRunning(item) && !item.output" class="tool-running">
                      <LoaderCircle size="14" class="animate-spin" />
                      <span>执行中...</span>
                    </div>
                  </div>
                </div>
              </div>
              <!-- Processing indicator at bottom -->
              <div v-if="isProcessing" class="processing-footer">
                <span class="pulse-dot"></span>
                <span>处理中...</span>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick, watch } from 'vue'
import {
  Brain,
  PanelRightClose,
  LoaderCircle,
  CheckCircle,
  Circle,
  ChevronRight,
  Lightbulb,
  ListChecks,
  Wrench,
  Zap,
  AlertCircle
} from 'lucide-vue-next'

const props = defineProps({
  isOpen: {
    type: Boolean,
    default: false
  },
  thinkingSteps: {
    type: Array,
    default: () => []
  },
  isInitialRender: {
    type: Boolean,
    default: false
  },
  isProcessing: {
    type: Boolean,
    default: false
  },
  planSteps: {
    type: Array,
    default: () => []
  },
  toolCalls: {
    type: Array,
    default: () => []
  },
  hasError: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['close', 'step-select'])

// Section expand states
const sections = reactive({
  thinking: { expanded: true },
  steps: { expanded: true },
  tools: { expanded: true }
})

// Step filter
const selectedStepId = ref(null)

// Tool expand tracking
const expandedToolIds = reactive(new Set())

// Refs for auto-scroll
const thinkingContentRef = ref(null)
const toolsContentRef = ref(null)

// Computed properties
const thinkingItems = computed(() =>
  props.thinkingSteps.filter(s => s.type === 'thinking' && s.content)
)

const normalizeStatus = (status) => {
  const value = String(status || 'pending').toLowerCase()
  if (['completed', 'complete', 'done', 'success', 'called'].includes(value)) return 'completed'
  if (['running', 'in_progress', 'active', 'processing', 'calling'].includes(value)) return 'running'
  if (['failed', 'error', 'cancelled', 'canceled'].includes(value)) return 'failed'
  return 'pending'
}

const normalizedPlanSteps = computed(() =>
  (props.planSteps || []).map((step, index) => {
    const description = step.description || step.content || step.title || `步骤 ${index + 1}`
    return {
      ...step,
      id: String(step.id || `step_${index + 1}`),
      description,
      title: step.title || description,
      status: normalizeStatus(step.status),
      toolCallIds: step.toolCallIds || step.tool_call_ids || []
    }
  })
)

const toolItems = computed(() =>
  (props.toolCalls || []).map((tool, index) => {
    const meta = tool.tool_meta || {}
    const toolCallId = String(tool.toolCallId || tool.tool_call_id || tool.id || '')
    return {
      ...tool,
      id: String(tool.id || toolCallId || `${tool.name || 'tool'}-${index}`),
      name: tool.name || tool.function || meta.name || 'unknown',
      args: tool.args || {},
      output: tool.output ?? tool.content ?? null,
      status: normalizeStatus(tool.status),
      duration: tool.duration ?? tool.duration_ms ?? null,
      icon: tool.icon || meta.icon,
      toolCallId
    }
  })
)

const aggregatedThinkingContent = computed(() =>
  thinkingItems.value.map(s => (s.content || '').trim()).filter(Boolean).join('\n\n').replace(/\n{3,}/g, '\n\n')
)

const isCurrentlyThinking = computed(() => {
  if (!props.isProcessing) return false
  const lastItem = props.thinkingSteps[props.thinkingSteps.length - 1]
  return lastItem?.type === 'thinking'
})

const completedStepsCount = computed(() =>
  normalizedPlanSteps.value.filter(s => s.status === 'completed').length
)

const allStepsCompleted = computed(() =>
  normalizedPlanSteps.value.length > 0 && normalizedPlanSteps.value.every(s => s.status === 'completed')
)

const progressPercent = computed(() => {
  const total = normalizedPlanSteps.value.length || 1
  const done = completedStepsCount.value
  return Math.round((done / total) * 100)
})

const hasAnyContent = computed(() =>
  thinkingItems.value.length > 0 || normalizedPlanSteps.value.length > 0 || toolItems.value.length > 0
)

const hasCompletedSteps = computed(() => completedStepsCount.value > 0)

const headerTitle = computed(() => {
  if (props.hasError) return '推理失败'
  if (props.isProcessing) return '思考中...'
  if (hasCompletedSteps.value) return '推理完成'
  return '思考过程'
})

// Step filtering for tools
const stepToolCallIds = computed(() => {
  if (!selectedStepId.value) return null
  const step = normalizedPlanSteps.value.find(s => s.id === selectedStepId.value)
  if (!step?.toolCallIds?.length) return new Set()
  return new Set(step.toolCallIds)
})

const visibleToolItems = computed(() => {
  if (!stepToolCallIds.value) return toolItems.value
  return toolItems.value.filter(item => stepToolCallIds.value.has(item.toolCallId))
})

// Methods
const closeSidebar = () => {
  emit('close')
}

const selectStep = (stepId) => {
  selectedStepId.value = selectedStepId.value === stepId ? null : stepId
  emit('step-select', selectedStepId.value)
}

const clearStepFilter = () => {
  selectedStepId.value = null
}

const toggleToolExpand = (id) => {
  if (expandedToolIds.has(id)) {
    expandedToolIds.delete(id)
  } else {
    expandedToolIds.add(id)
  }
}

const isToolRunning = (tool) => tool.status === 'running'

const getToolArg = (tool) => {
  if (!tool.args) return ''
  if (typeof tool.args === 'string') return tool.args.slice(0, 80)
  const fn = tool.name || ''
  if (fn.includes('search')) return tool.args.query || tool.args.search_query || ''
  if (fn.includes('exec') || fn === 'execute') return tool.args.command || ''
  if (fn.includes('file') || fn === 'read_file' || fn === 'write_file') return tool.args.file_path || tool.args.file || ''
  const vals = Object.values(tool.args)
  if (vals.length > 0 && typeof vals[0] === 'string') return String(vals[0]).slice(0, 80)
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
    if (json.length > 10000) return json.slice(0, 10000) + '\n...'
    return json
  } catch (e) {
    return String(e)
  }
}

// Auto-scroll functions
const scrollThoughtsToBottom = () => {
  nextTick(() => {
    if (thinkingContentRef.value) {
      thinkingContentRef.value.scrollTop = thinkingContentRef.value.scrollHeight
    }
  })
}

const scrollToolsToBottom = () => {
  nextTick(() => {
    if (toolsContentRef.value) {
      toolsContentRef.value.scrollTop = toolsContentRef.value.scrollHeight
    }
  })
}

// Watch for content changes and auto-scroll
watch(aggregatedThinkingContent, scrollThoughtsToBottom)
watch(() => toolItems.value.length, scrollToolsToBottom)
</script>

<style lang="less" scoped>
.thinking-sidebar {
  width: 0;
  height: 100%;
  background-color: var(--gray-0);
  transition: all 0.3s ease;
  display: flex;
  flex-direction: column;
  border: none;
  overflow: hidden;
  flex-shrink: 0;

  .sidebar-content {
    width: 420px;
    min-width: 420px;
    height: 100%;
    display: flex;
    flex-direction: column;
    opacity: 1;
    transform: translateX(0);
    transition:
      opacity 0.2s ease,
      transform 0.3s ease;
  }

  &:not(.sidebar-open) .sidebar-content {
    opacity: 0;
    transform: translateX(12px);
  }

  &.no-transition {
    transition: none !important;
  }

  &.sidebar-open {
    width: 420px;
    max-width: 500px;
    border-left: 1px solid var(--gray-200);
  }

  // Header
  .sidebar-header {
    height: var(--header-height);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 16px;
    border-bottom: 1px solid var(--gray-150);
    flex-shrink: 0;
    background-color: var(--gray-0);

    .header-left {
      display: flex;
      align-items: center;
      gap: 10px;
      flex: 1;
    }

    .status-indicator {
      flex-shrink: 0;

      &.processing {
        position: relative;
        width: 16px;
        height: 16px;

        .spinner-ring {
          position: absolute;
          inset: 0;
          border-radius: 50%;
          border: 2px solid var(--main-200);
          border-top-color: var(--main-500);
          animation: spin 0.8s linear infinite;
        }
      }

      &.error {
        width: 16px;
        height: 16px;
        border-radius: 50%;
        background: var(--color-error-500);
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
      }

      &.completed {
        width: 16px;
        height: 16px;
        border-radius: 50%;
        background: linear-gradient(135deg, #10b981, #14b8a6);
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
      }
    }

    .header-title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-weight: 600;
      font-size: 14px;
      color: var(--gray-900);
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .toggle-btn {
      cursor: pointer;
      height: 28px;
      width: 28px;
      display: flex;
      justify-content: center;
      align-items: center;
      border-radius: 6px;
      transition: background-color 0.2s;
      color: var(--gray-600);

      &:hover {
        background-color: var(--gray-100);
        color: var(--main-color);
      }
    }
  }

  // Content Area
  .thinking-content {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
  }

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    text-align: center;
    padding: 40px 20px;

    .empty-icon {
      color: var(--gray-300);
      margin-bottom: 16px;
    }

    .empty-text {
      font-size: 15px;
      font-weight: 500;
      color: var(--gray-700);
      margin: 0 0 8px 0;
    }

    .empty-hint {
      font-size: 13px;
      color: var(--gray-500);
      margin: 0;
      line-height: 1.5;
    }
  }

  // Sections Container
  .sections-container {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  // Section Base Styles
  section {
    border: 1px solid var(--gray-200);
    border-radius: 8px;
    background: var(--gray-0);
    overflow: hidden;
    transition: all 0.2s ease;
  }

  .section-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 14px;
    cursor: pointer;
    user-select: none;
    transition: background-color 0.15s;
    border-bottom: 1px solid transparent;

    &:hover {
      background-color: var(--gray-50);
    }

    &.expanded + .section-content {
      border-top-color: var(--gray-150);
    }

    .chevron-icon {
      color: var(--gray-400);
      transition: transform 0.15s;
      flex-shrink: 0;

      &.expanded {
        transform: rotate(90deg);
      }
    }

    .section-icon {
      flex-shrink: 0;

      &.thinking {
        color: #f59e0b;
      }

      &.steps {
        color: #8b5cf6;
      }

      &.tools {
        color: #3b82f6;
      }
    }

    .section-title {
      font-size: 12px;
      font-weight: 600;
      color: var(--gray-700);
      flex: 1;
    }

    .thinking-dots {
      display: flex;
      gap: 3px;
      margin-left: 4px;

      .dot {
        width: 3px;
        height: 3px;
        border-radius: 50%;
        background: var(--main-400);
        animation: bounce-dot 1.5s infinite;
      }
    }

    .step-counter,
    .tool-counter {
      font-size: 10px;
      font-weight: 700;
      color: var(--gray-500);
      background: var(--gray-100);
      padding: 2px 6px;
      border-radius: 4px;
      tabular-nums: true;
    }

    .filter-badge {
      font-size: 10px;
      padding: 2px 8px;
      border-radius: 12px;
      background: var(--main-50);
      color: var(--main-600);
      border: 1px solid var(--main-200);
      cursor: pointer;
      transition: all 0.15s;
      font-weight: 600;

      &:hover {
        background: var(--main-100);
      }
    }
  }

  .section-content {
    padding: 10px 14px;
    animation: section-reveal 0.2s ease-out;
  }

  @keyframes section-reveal {
    from {
      opacity: 0;
      transform: translateY(-6px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  // Thinking Section
  .thinking-content {
    .thinking-text {
      padding: 10px 12px;
      font-size: 12px;
      line-height: 1.7;
      color: var(--gray-700);
      background: var(--gray-50);
      border-radius: 10px;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: 'SF Mono', Monaco, monospace;
      border: 1px solid var(--gray-150);
      max-height: 300px;
      overflow-y: auto;
    }

    .processing-indicator {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 11px;
      color: var(--main-500);
      padding: 8px 4px;
      margin-top: 4px;

      .pulse-dot {
        position: relative;
        width: 8px;
        height: 8px;

        &::before {
          content: '';
          position: absolute;
          inset: 0;
          border-radius: 50%;
          background: var(--main-400);
          animation: ping 1.5s cubic-bezier(0, 0, 0.2, 1) infinite;
        }

        &::after {
          content: '';
          position: absolute;
          inset: 0;
          border-radius: 50%;
          background: var(--main-500);
        }
      }
    }
  }

  // Steps Section
  .steps-content {
    .progress-bar-wrapper {
      width: 100%;
      height: 4px;
      background: var(--gray-100);
      border-radius: 2px;
      overflow: hidden;
      margin-bottom: 8px;

      .progress-bar {
        height: 100%;
        border-radius: 2px;
        background: linear-gradient(90deg, var(--main-400), var(--main-500));
        transition: width 0.5s ease-out;

        &.completed {
          background: linear-gradient(90deg, #10b981, #14b8a6);
        }
      }
    }

    .steps-list {
      display: flex;
      flex-direction: column;
      gap: 4px;

      .step-item {
        display: flex;
        align-items: flex-start;
        gap: 8px;
        padding: 6px 8px;
        border-radius: 6px;
        cursor: pointer;
        transition: all 0.15s;
        user-select: none;

        &:hover {
          background: var(--gray-50);
        }

        &.selected {
          background: var(--main-50);
          border: 1px solid var(--main-200);
        }

        &.running {
          background: linear-gradient(90deg, var(--main-50), var(--gray-0));
          border-left: 2px solid var(--main-400);
        }

        &.failed {
          background: #fffbeb;
          border-left: 2px solid #f59e0b;
        }

        .step-status {
          flex-shrink: 0;
          width: 16px;
          height: 16px;
          margin-top: 1px;
          display: flex;
          align-items: center;
          justify-content: center;

          .status-icon {
            &.completed {
              color: #10b981;
            }

            &.running {
              color: var(--main-500);
              animation: spin 1s linear infinite;
            }

            &.pending {
              color: var(--gray-300);
            }

            &.failed {
              color: #f59e0b;
            }
          }
        }

        .step-description {
          flex: 1;
          font-size: 12px;
          line-height: 1.5;
          color: var(--gray-700);
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;

          .running & {
            color: var(--gray-900);
            font-weight: 500;
          }

          .failed & {
            color: #92400e;
            font-weight: 500;
          }

          .selected & {
            color: var(--main-700);
            font-weight: 500;
          }
        }

        .step-tool-count {
          flex-shrink: 0;
          font-size: 10px;
          font-family: monospace;
          color: var(--gray-400);
          margin-top: 1px;
        }
      }
    }
  }

  // Tools Section
  .tools-content {
    padding: 8px;
    background: linear-gradient(180deg, var(--gray-50), var(--gray-0));
    border-radius: 8px;

    .tools-list {
      display: flex;
      flex-direction: column;
      gap: 4px;

      .empty-filter {
        text-align: center;
        font-size: 11px;
        color: var(--gray-400);
        padding: 12px;
      }

      .tool-item {
        .tool-header {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 6px 8px;
          border-radius: 6px;
          cursor: pointer;
          transition: all 0.15s;
          border: 1px solid transparent;

          &:hover {
            background: var(--gray-0);
          }

          &.expanded {
            background: var(--gray-0);
            border-color: var(--gray-200);
            box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
          }

          .tool-chevron {
            color: var(--gray-400);
            transition: transform 0.15s;
            flex-shrink: 0;

            &.expanded {
              transform: rotate(90deg);
            }
          }

          .tool-icon,
          .tool-loading,
          .tool-icon-default {
            flex-shrink: 0;
            font-size: 14px;
          }

          .tool-loading {
            color: var(--main-500);
          }

          .tool-info {
            flex: 1;
            min-width: 0;
            display: flex;
            align-items: center;
            gap: 6px;

            .tool-name {
              font-size: 11px;
              font-family: monospace;
              font-weight: 600;
              color: var(--gray-700);
              flex-shrink: 0;
            }

            .tool-arg-preview {
              font-size: 11px;
              color: var(--gray-400);
              truncate: true;
              max-width: 180px;
              overflow: hidden;
              text-overflow: ellipsis;
              white-space: nowrap;
            }
          }

          .tool-duration {
            flex-shrink: 0;
            font-size: 10px;
            font-family: monospace;
            padding: 2px 6px;
            border-radius: 4px;
            background: #ecfdf5;
            color: #059669;
          }
        }

        .tool-detail {
          margin-top: 4px;
          margin-left: 16px;
          margin-right: 4px;
          display: flex;
          flex-direction: column;
          gap: 8px;
          padding: 10px 12px;
          border-radius: 8px;
          background: var(--gray-0);
          border: 1px solid var(--gray-200);
          animation: tool-detail-slide 0.15s ease-out;

          .detail-block {
            .detail-label {
              font-size: 10px;
              color: var(--gray-400);
              margin-bottom: 4px;
              text-transform: uppercase;
              letter-spacing: 0.05em;
              font-weight: 600;
            }

            .detail-content {
              font-size: 11px;
              line-height: 1.5;
              white-space: pre-wrap;
              word-break: break-word;
              color: var(--gray-700);
              background: var(--gray-50);
              border-radius: 6px;
              padding: 8px 10px;
              border: 1px solid var(--gray-150);
              max-height: 200px;
              overflow-y: auto;
              font-family: 'SF Mono', Monaco, monospace;
            }
          }

          .tool-running {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
            color: var(--gray-400);
            padding: 8px;
            justify-content: center;

            .animate-spin {
              animation: spin 1s linear infinite;
              color: var(--main-500);
            }
          }
        }
      }
    }

    .processing-footer {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 11px;
      color: var(--main-500);
      padding: 8px 4px;
      margin-top: 4px;

      .pulse-dot {
        position: relative;
        width: 8px;
        height: 8px;

        &::before {
          content: '';
          position: absolute;
          inset: 0;
          border-radius: 50%;
          background: var(--main-400);
          animation: ping 1.5s cubic-bezier(0, 0, 0.2, 1) infinite;
        }

        &::after {
          content: '';
          position: absolute;
          inset: 0;
          border-radius: 50%;
          background: var(--main-500);
        }
      }
    }
  }
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

@keyframes bounce-dot {
  0% { transform: translateY(0); }
  20% { transform: translateY(-3px); }
  40% { transform: translateY(0); }
  100% { transform: translateY(0); }
}

@keyframes ping {
  75%, 100% {
    transform: scale(2);
    opacity: 0;
  }
}

@keyframes tool-detail-slide {
  from {
    opacity: 0;
    max-height: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    max-height: 500px;
    transform: translateY(0);
  }
}

// Scrollbar styling
.thinking-content::-webkit-scrollbar {
  width: 5px;
}

.thinking-content::-webkit-scrollbar-track {
  background: transparent;
}

.thinking-content::-webkit-scrollbar-thumb {
  background: var(--gray-300);
  border-radius: 5px;
}

.thinking-content::-webkit-scrollbar-thumb:hover {
  background: var(--gray-400);
}
</style>
