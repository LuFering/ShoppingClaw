<template>
  <div v-if="message.message_type === 'multimodal_image' && message.image_content" class="message-image">
    <img :src="`data:image/jpeg;base64,${message.image_content}`" alt="上传的图片" />
  </div>
  <div class="message-box" :class="[message.type, customClasses]">
    <!-- 用户消息 -->
    <div v-if="message.type === 'human'" class="message-copy-btn human-copy"
      @click="copyToClipboard(message.content)" :class="{ 'is-copied': isCopied }">
      <Check v-if="isCopied" size="14" />
      <Copy v-else size="14" />
    </div>
    <p v-if="message.type === 'human'" class="message-text">{{ message.content }}</p>
    <p v-else-if="message.type === 'system'" class="message-text-system">{{ message.content }}</p>

    <!-- AI 消息 -->
    <div v-else-if="message.type === 'ai'" class="assistant-message">
      <MdPreview
        v-if="message.content"
        editorId="preview-only"
        :theme="'light'"
        previewTheme="github"
        :showCodeRowNumber="false"
        :modelValue="message.content.trim()"
        class="message-md"
      />
      <div v-else-if="isProcessing" class="empty-block" style="padding: 8px 0; color: var(--gray-400);">
        思考中...
      </div>

      <!-- 错误提示 -->
      <div v-if="displayError" class="error-hint">
        <span v-if="getErrorMessage">{{ getErrorMessage }}</span>
        <span v-else-if="message.error_type === 'interrupted'">回答生成已中断</span>
        <span v-else-if="message.error_type === 'unexpect'">生成过程中出现异常</span>
        <span v-else>{{ message.error_type || '未知错误' }}</span>
      </div>

      <div v-if="message.isStoppedByUser" class="retry-hint">
        你停止生成了本次回答
        <span class="retry-link" @click="emit('retryStoppedMessage', message.id)">重新编辑问题</span>
      </div>
    </div>

    <!-- 自定义内容 -->
    <slot></slot>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Copy, Check } from 'lucide-vue-next'
import { MdPreview } from 'md-editor-v3'
import 'md-editor-v3/lib/preview.css'

const props = defineProps({
  message: { type: Object, required: true },
  isProcessing: { type: Boolean, default: false },
  customClasses: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['retry', 'retryStoppedMessage'])

const isCopied = ref(false)

const copyToClipboard = async (text) => {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const textArea = document.createElement('textarea')
      textArea.value = text
      textArea.style.position = 'fixed'
      textArea.style.left = '-999999px'
      textArea.style.top = '-999999px'
      document.body.appendChild(textArea)
      textArea.focus()
      textArea.select()
      document.execCommand('copy')
      document.body.removeChild(textArea)
    }
    isCopied.value = true
    setTimeout(() => { isCopied.value = false }, 2000)
  } catch (err) {
    console.error('Failed to copy: ', err)
  }
}

const displayError = computed(() => {
  return !!(props.message.error_type || props.message.extra_metadata?.error_type)
})

const getErrorMessage = computed(() => {
  if (props.message.error_message) return props.message.error_message
  if (props.message.extra_metadata?.error_message) return props.message.extra_metadata.error_message
  return null
})
</script>

<style lang="less" scoped>
.message-box {
  display: inline-block;
  border-radius: 1.5rem;
  margin: 0.8rem 0;
  padding: 0.625rem 1.25rem;
  user-select: text;
  word-break: break-word;
  word-wrap: break-word;
  font-size: 15px;
  line-height: 24px;
  box-sizing: border-box;
  color: var(--gray-10000);
  max-width: 100%;
  position: relative;
  letter-spacing: 0.25px;

  &.human, &.sent {
    max-width: 95%;
    color: var(--gray-1000);
    background-color: var(--main-50);
    align-self: flex-end;
    border-radius: 0.5rem;
    padding: 0.5rem 1rem;
  }

  &.assistant, &.received, &.ai {
    color: initial;
    width: 100%;
    text-align: left;
    margin: 0;
    padding: 0px;
    background-color: transparent;
    border-radius: 0;
  }

  .message-text {
    max-width: 100%;
    margin-bottom: 0;
    white-space: pre-line;
  }

  .message-copy-btn {
    cursor: pointer;
    color: var(--gray-400);
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0;
    flex-shrink: 0;
    &:hover { color: var(--main-color); }
    &.is-copied { color: var(--color-success-500); opacity: 1; }
    &.human-copy {
      position: absolute;
      left: -28px;
      bottom: 8px;
    }
  }

  &:hover {
    .message-copy-btn { opacity: 1; }
  }

  .message-text-system {
    max-width: 100%;
    margin-bottom: 0;
    white-space: pre-line;
    color: var(--gray-600);
    font-style: italic;
    font-size: 14px;
    padding: 8px 12px;
    background-color: var(--gray-50);
    border-left: 3px solid var(--gray-300);
    border-radius: 4px;
  }

  .assistant-message { width: 100%; }

  .error-hint {
    margin: 10px 0;
    padding: 8px 16px;
    border-radius: 8px;
    font-size: 14px;
    display: flex;
    align-items: center;
    gap: 8px;
    background-color: var(--color-error-50);
    color: var(--color-error-500);
    span { line-height: 1.5; }
  }

  .empty-block { padding: 8px 0; color: var(--gray-400); }
}

.retry-hint {
  margin-top: 8px;
  padding: 8px 16px;
  color: var(--gray-600);
  font-size: 14px;
  text-align: left;
}

.retry-link {
  color: var(--color-info-500);
  cursor: pointer;
  margin-left: 4px;
  &:hover { text-decoration: underline; }
}

.message-image {
  border-radius: 12px;
  overflow: hidden;
  margin-left: auto;
  border: 1px solid rgba(255, 255, 255, 0.2);
  img {
    max-width: 100%;
    max-height: 200px;
    object-fit: contain;
  }
}
</style>

<style lang="less">
.message-md {
  margin: 8px 0;
  .md-editor-preview-wrapper {
    max-width: 100%;
    padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', monospace;
    #preview-only-preview {
      font-size: 1rem;
      line-height: 1.75;
      color: var(--gray-1000);
    }
    h1, h2 { font-size: 1.2rem; }
    h3, h4 { font-size: 1.1rem; }
    strong { font-weight: 500; }
    ul, ol { padding-left: 1.625rem; }
    ul li::marker, ol li::marker { color: var(--main-bright); }
    li > p, ol > p, ul > p { margin: 0.25rem 0; }
    a { color: var(--main-700); }
    code {
      font-size: 13px;
      background-color: var(--gray-25);
    }
    .md-editor-code {
      border: var(--gray-50);
      border-radius: 8px;
    }
    p:last-child { margin-bottom: 0; }
  }
}
</style>
