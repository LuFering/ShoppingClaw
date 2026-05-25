<template>
  <div
    class="step-message"
    :class="{
      'selected': isSelected,
      'running': step.status === 'running',
      'completed': step.status === 'completed',
      'failed': step.status === 'failed'
    }"
    @click="$emit('click')"
  >
    <!-- Step Header -->
    <div class="step-header">
      <!-- Status Icon -->
      <div class="status-icon-wrapper">
        <div v-if="step.status === 'running'" class="spinner">
          <div class="spinner-ring"></div>
        </div>
        <div v-else-if="step.status === 'completed'" class="check-icon">
          <CheckCircle size="14" />
        </div>
        <div v-else-if="step.status === 'failed'" class="error-icon">
          <AlertCircle size="14" />
        </div>
        <div v-else class="pending-icon">
          <Circle size="14" />
        </div>
      </div>

      <!-- Content -->
      <div class="step-content">
        <div class="step-description">{{ step.description }}</div>
        
        <div class="step-meta">
          <span v-if="step.tools?.length" class="tool-count">{{ step.tools.length }}</span>
          <ChevronRight size="12" class="expand-icon" :class="{ 'expanded': isExpanded }" />
        </div>
      </div>
    </div>

    <!-- Tools List (expandable) -->
    <transition name="tools-expand">
      <div v-if="isExpanded && step.tools?.length" class="step-tools">
        <ToolCallCard
          v-for="(tool, index) in step.tools"
          :key="index"
          :tool="tool"
          :compact="true"
          @click="$emit('tool-click', tool)"
        />
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { CheckCircle, AlertCircle, Circle, ChevronRight } from 'lucide-vue-next'
import ToolCallCard from './ToolCallCard.vue'

const props = defineProps({
  step: {
    type: Object,
    required: true
  },
  isSelected: {
    type: Boolean,
    default: false
  }
})

defineEmits(['click', 'tool-click'])

const isExpanded = ref(true)

// Auto-expand when step is running
watch(() => props.step.status, (newStatus) => {
  if (newStatus === 'running') {
    isExpanded.value = true
  }
}, { immediate: true })
</script>

<style scoped>
.step-message {
  display: flex;
  flex-direction: column;
  padding: 8px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.step-message:hover {
  background: var(--hover-bg, #f9fafb);
}

.step-message.selected {
  background: rgba(59, 130, 246, 0.08);
  border-color: rgba(59, 130, 246, 0.2);
}

.step-message.running {
  background: linear-gradient(to right, rgba(59, 130, 246, 0.05), transparent);
}

.step-header {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.status-icon-wrapper {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 2px;
}

.spinner {
  position: relative;
  width: 16px;
  height: 16px;
}

.spinner-ring {
  position: absolute;
  inset: 0;
  border: 2px solid #e0e7ff;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.check-icon {
  color: #10b981;
}

.error-icon {
  color: #ef4444;
}

.pending-icon {
  color: #d1d5db;
}

.step-content {
  flex: 1;
  min-width: 0;
}

.step-description {
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-primary, #374151);
  margin-bottom: 4px;
  
  /* Line clamp for long descriptions */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.step-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tool-count {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--bg-secondary, #f3f4f6);
  color: var(--text-secondary, #6b7280);
}

.expand-icon {
  color: var(--text-tertiary, #d1d5db);
  transition: transform 0.2s;
}

.expand-icon.expanded {
  transform: rotate(90deg);
}

/* Tools List */
.step-tools {
  margin-top: 8px;
  margin-left: 30px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* Transitions */
.tools-expand-enter-active,
.tools-expand-leave-active {
  transition: all 0.25s ease;
  overflow: hidden;
}

.tools-expand-enter-from,
.tools-expand-leave-to {
  opacity: 0;
  max-height: 0;
}

.tools-expand-enter-to,
.tools-expand-leave-from {
  opacity: 1;
  max-height: 500px;
}
</style>
