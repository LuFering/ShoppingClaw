<template>
  <div class="agent-flow-panel" :class="{ 'panel-open': isOpen, 'no-transition': isInitialRender }">
    <div class="panel-content">
      <!-- Header -->
      <div class="panel-header">
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
          <button class="close-btn" @click="closePanel" title="关闭面板">
            <PanelRightClose size="20" />
          </button>
        </div>
      </div>

      <!-- Content Area with flexible layout -->
      <div class="panel-body">
        <!-- Empty State -->
        <div v-if="!hasAnyContent" class="empty-state">
          <Brain size="48" class="empty-icon" />
          <p class="empty-text">暂无执行流程</p>
          <p class="empty-hint">开始对话后，AI 的执行流程将在这里实时展示</p>
        </div>

        <div v-else class="sections-container">
          <!-- ═══ Thinking Section ═══ -->
          <section v-if="thinkingItems.length > 0" class="flow-section">
            <div
              @click="toggleSection('thinking')"
              class="section-header"
              :class="{ 'active': isCurrentlyThinking || sections.thinking.expanded }"
            >
              <ChevronRight
                size="12"
                class="chevron"
                :class="{ 'expanded': sections.thinking.expanded }"
              />
              <Lightbulb size="13" class="section-icon thinking" />
              <span class="section-title">思考过程</span>
              <div v-if="isCurrentlyThinking" class="thinking-dots">
                <span v-for="i in 3" :key="i" class="dot" :style="{ animationDelay: `${(i-1) * 200}ms` }"></span>
              </div>
            </div>
            <transition name="section-expand">
              <div v-if="sections.thinking.expanded" ref="thinkingContentRef" class="section-content thinking-content">
                <div class="thinking-text">
                  {{ aggregatedThinkingContent }}
                </div>
                <div v-if="isCurrentlyThinking" class="processing-indicator">
                  <span class="pulse-dot"></span>
                  <span>思考中...</span>
                </div>
              </div>
            </transition>
          </section>

          <!-- ═══ Plan/Todos Section ═══ -->
          <section v-if="normalizedPlanSteps.length > 0" class="flow-section">
            <div
              @click="toggleSection('steps')"
              class="section-header"
              :class="{ 'active': sections.steps.expanded }"
            >
              <ChevronRight
                size="12"
                class="chevron"
                :class="{ 'expanded': sections.steps.expanded }"
              />
              <ListChecks size="13" class="section-icon steps" />
              <span class="section-title">任务进度</span>
              <span class="step-counter">{{ completedStepsCount }}/{{ normalizedPlanSteps.length }}</span>
            </div>
            <transition name="section-expand">
              <div v-if="sections.steps.expanded" class="section-content steps-content">
                <!-- Progress Bar -->
                <div class="progress-bar-wrapper">
                  <div
                    class="progress-bar-fill"
                    :class="{ 'completed': allStepsCompleted }"
                    :style="{ width: progressPercent + '%' }"
                  ></div>
                </div>
                <!-- Steps List -->
                <div class="steps-list">
                  <StepMessage
                    v-for="step in normalizedPlanSteps"
                    :key="step.id"
                    :step="step"
                    :is-selected="selectedStepId === step.id"
                    @click="selectStep(step.id)"
                    @tool-click="handleToolClick"
                  />
                </div>
              </div>
            </transition>
          </section>

          <!-- ═══ Tools Section ═══ -->
          <section v-if="visibleToolItems.length > 0 || isProcessing" class="flow-section">
            <div
              @click="toggleSection('tools')"
              class="section-header"
              :class="{ 'active': sections.tools.expanded }"
            >
              <ChevronRight
                size="12"
                class="chevron"
                :class="{ 'expanded': sections.tools.expanded }"
              />
              <Wrench size="13" class="section-icon tools" />
              <span class="section-title">工具调用</span>
              <span v-if="selectedStepId" @click.stop="clearStepFilter" class="filter-badge">
                {{ visibleToolItems.length }}/{{ toolItems.length }} ×
              </span>
              <span v-else-if="toolItems.length > 0" class="tool-counter">{{ toolItems.length }}</span>
            </div>
            <transition name="section-expand">
              <div v-if="sections.tools.expanded" ref="toolsContentRef" class="section-content tools-content">
                <div class="tools-list">
                  <!-- Empty state when filtered -->
                  <div v-if="selectedStepId && visibleToolItems.length === 0" class="empty-filter">
                    该步骤没有关联的工具
                  </div>
                  <ToolCallCard
                    v-for="item in visibleToolItems"
                    :key="item.id"
                    :tool="item"
                    :is-expanded="expandedToolIds.has(item.id)"
                    @toggle-expand="toggleToolExpand(item.id)"
                    @click="handleToolClick(item)"
                  />
                </div>
                <!-- Processing indicator at bottom -->
                <div v-if="isProcessing" class="processing-footer">
                  <span class="pulse-dot"></span>
                  <span>处理中...</span>
                </div>
              </div>
            </transition>
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
  CheckCircle,
  ChevronRight,
  Lightbulb,
  ListChecks,
  Wrench,
  AlertCircle
} from 'lucide-vue-next'
import StepMessage from './StepMessage.vue'
import ToolCallCard from './ToolCallCard.vue'

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

const emit = defineEmits(['close', 'step-select', 'tool-click'])

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
const closePanel = () => {
  emit('close')
}

const toggleSection = (section) => {
  sections[section].expanded = !sections[section].expanded
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

const handleToolClick = (tool) => {
  emit('tool-click', tool)
}

// Auto-scroll to bottom for thinking and tools sections
const scrollThinkingToBottom = () => {
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

watch(aggregatedThinkingContent, scrollThinkingToBottom)
watch(() => toolItems.value.length, scrollToolsToBottom)
</script>

<style scoped>
.agent-flow-panel {
  width: 0;
  height: 100%;
  background: var(--gray-0);
  transition: all 0.3s ease;
  display: flex;
  flex-direction: column;
  border: none;
  overflow: hidden;
  flex-shrink: 0;
}

.agent-flow-panel:not(.panel-open) .panel-content {
  opacity: 0;
  transform: translateX(12px);
}

.panel-content {
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

.agent-flow-panel.panel-open {
  width: 420px;
  max-width: 500px;
  border-left: 1px solid var(--gray-200);
}

.no-transition {
  transition: none !important;
}

/* Header */
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color, #f3f4f6);
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-indicator {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
}

.status-indicator.processing .spinner-ring {
  width: 16px;
  height: 16px;
  border: 2px solid #e0e7ff;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.status-indicator.completed {
  background: linear-gradient(135deg, #34d399, #10b981);
  color: white;
}

.status-indicator.error {
  background: #fbbf24;
  color: white;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #1f2937);
}

.close-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  border-radius: 8px;
  cursor: pointer;
  color: var(--text-secondary, #6b7280);
  transition: all 0.2s;
}

.close-btn:hover {
  background: var(--hover-bg, #f3f4f6);
  color: var(--text-primary, #1f2937);
}

/* Body */
.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  color: var(--text-tertiary, #9ca3af);
}

.empty-icon {
  margin-bottom: 16px;
  opacity: 0.4;
}

.empty-text {
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 8px;
}

.empty-hint {
  font-size: 12px;
  line-height: 1.5;
}

.sections-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* Section */
.flow-section {
  border: 1px solid var(--border-color, #f3f4f6);
  border-radius: 12px;
  overflow: hidden;
  background: white;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  cursor: pointer;
  user-select: none;
  transition: all 0.2s;
}

.section-header:hover {
  background: var(--hover-bg, #f9fafb);
}

.section-header.active {
  background: linear-gradient(to right, rgba(59, 130, 246, 0.05), transparent);
}

.chevron {
  color: var(--text-tertiary, #d1d5db);
  transition: transform 0.2s;
}

.chevron.expanded {
  transform: rotate(90deg);
}

.section-icon {
  flex-shrink: 0;
}

.section-icon.thinking {
  color: #f59e0b;
}

.section-icon.steps {
  color: #8b5cf6;
}

.section-icon.tools {
  color: #3b82f6;
}

.section-title {
  flex: 1;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #374151);
}

.thinking-dots {
  display: flex;
  gap: 3px;
}

.dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: #3b82f6;
  animation: bounce 1.4s infinite;
}

@keyframes bounce {
  0%, 80%, 100% { transform: translateY(0); }
  40% { transform: translateY(-4px); }
}

.step-counter,
.tool-counter {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--bg-secondary, #f3f4f6);
  color: var(--text-secondary, #6b7280);
}

.filter-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 12px;
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
  cursor: pointer;
  transition: all 0.2s;
}

.filter-badge:hover {
  background: rgba(59, 130, 246, 0.15);
}

/* Section Content */
.section-content {
  border-top: 1px solid var(--border-color, #f3f4f6);
}

.thinking-content {
  padding: 16px;
  max-height: 400px;
  overflow-y: auto;
}

.thinking-text {
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-secondary, #4b5563);
  white-space: pre-wrap;
  word-break: break-word;
  background: linear-gradient(135deg, rgba(245, 158, 11, 0.05), rgba(251, 191, 36, 0.02));
  padding: 12px;
  border-radius: 8px;
  border: 1px solid rgba(245, 158, 11, 0.15);
}

.processing-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  font-size: 12px;
  color: #3b82f6;
}

.pulse-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #3b82f6;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* Steps */
.steps-content {
  padding: 12px 16px;
}

.progress-bar-wrapper {
  width: 100%;
  height: 4px;
  background: var(--bg-secondary, #f3f4f6);
  border-radius: 2px;
  margin-bottom: 12px;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #3b82f6, #60a5fa);
  border-radius: 2px;
  transition: width 0.5s ease-out;
}

.progress-bar-fill.completed {
  background: linear-gradient(90deg, #10b981, #34d399);
}

.steps-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* Tools */
.tools-content {
  padding: 12px 16px;
  max-height: 500px;
  overflow-y: auto;
}

.tools-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.empty-filter {
  text-align: center;
  padding: 16px;
  font-size: 12px;
  color: var(--text-tertiary, #9ca3af);
}

.processing-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 8px 0;
  font-size: 12px;
  color: #3b82f6;
}

/* Transitions */
.section-expand-enter-active,
.section-expand-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}

.section-expand-enter-from,
.section-expand-leave-to {
  opacity: 0;
  max-height: 0;
}

.section-expand-enter-to,
.section-expand-leave-from {
  opacity: 1;
  max-height: 1000px;
}

/* Responsive */
@media (max-width: 768px) {
  .agent-flow-panel {
    width: 100%;
  }
}
</style>
