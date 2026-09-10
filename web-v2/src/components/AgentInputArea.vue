<template>
  <MessageInputComponent
    ref="inputRef"
    :key="inputKey"
    :model-value="modelValue"
    @update:modelValue="updateValue"
    :is-loading="isLoading"
    :disabled="disabled"
    :send-button-disabled="sendButtonDisabled"
    :placeholder="placeholder"
    @send="handleSend"
    @keydown="handleKeyDown"
  >
    <template #actions-left>
      <div class="input-actions-left">
        <!-- State Toggle Button -->
        <div
          v-if="hasStateContent"
          class="state-toggle-btn"
          :class="{ active: isPanelOpen }"
          @click="$emit('toggle-panel')"
          title="查看工作状态"
        >
          <FolderCode :size="18" />
          <span>状态</span>
        </div>
        <!-- 对话模型选择器：转发 AgentChatComponent 的 #actions-left-extra 插槽 -->
        <slot name="actions-left-extra"></slot>
      </div>
    </template>
  </MessageInputComponent>
</template>

<script setup>
import { ref, watch } from 'vue'
import MessageInputComponent from '@/components/MessageInputComponent.vue'
import { FolderCode } from 'lucide-vue-next'

const props = defineProps({
  modelValue: { type: String, default: '' },
  isLoading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  sendButtonDisabled: { type: Boolean, default: false },
  placeholder: { type: String, default: '输入问题...' },
  agentId: { type: String, default: '' },
  hasStateContent: { type: Boolean, default: false },
  isPanelOpen: { type: Boolean, default: false }
})

const emit = defineEmits([
  'update:modelValue',
  'send',
  'keydown',
  'toggle-panel'
])

const inputRef = ref(null)

// 用于强制重建输入组件的 key
const inputKey = ref(0)

// 监听 hasStateContent 变化，当从有 state 切换到无 state 时重建组件
watch(
  () => props.hasStateContent,
  (newVal, oldVal) => {
    if (oldVal === true && newVal === false) {
      inputKey.value++
    }
  }
)

const updateValue = (val) => {
  emit('update:modelValue', val)
}

const handleSend = () => {
  emit('send')
}

const handleKeyDown = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  } else {
    emit('keydown', e)
  }
}

defineExpose({
  focus: () => inputRef.value?.focus(),
  closeOptions: () => inputRef.value?.closeOptions()
})
</script>

<style lang="less" scoped>
.input-actions-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.state-toggle-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 8px;
  height: 28px;
  border-radius: 8px;
  font-size: 14px;
  color: var(--gray-600);
  cursor: pointer;
  transition: all 0.2s ease;
  user-select: none;
  background: transparent;
  border: none;

  &:hover {
    color: var(--main-color);
    background: var(--gray-100);
  }

  &.active {
    color: var(--main-color);
    background: var(--main-50);
    font-weight: 500;
  }

  &.disabled {
    opacity: 0.5;
    cursor: not-allowed;
    pointer-events: none;
  }

  span {
    line-height: 1;
  }
}
</style>
