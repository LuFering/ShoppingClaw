<template>
  <BaseToolCall
    :tool-call="toolCall"
    :appearance="appearance"
    :default-expanded="true"
    :force-show-result="reminders.length > 0"
    hide-params
  >
    <template #header>
      <div class="sep-header">
        <span class="note">提醒</span>
        <span class="separator">|</span>
        <span class="description">{{ data.target || '购物档案' }}</span>
        <span class="tag">{{ reminders.length }} 条</span>
      </div>
    </template>

    <template #result>
      <ul class="rem-list">
        <li v-for="(r, i) in reminders" :key="i">
          <span class="rem-icon"></span>
          <span class="rem-text">{{ r.text }}</span>
          <span v-if="r.at" class="rem-at">{{ r.at }}</span>
        </li>
      </ul>
    </template>
  </BaseToolCall>
</template>

<script setup>
import { computed } from 'vue'
import BaseToolCall from '../BaseToolCall.vue'
import { parseToolCallArgs } from '../toolRegistry'

const props = defineProps({
  toolCall: { type: Object, required: true },
  appearance: { type: String, default: 'card' },
  defaultExpanded: { type: Boolean, default: false }
})

const rawResult = computed(
  () =>
    props.toolCall.tool_call_result?.content ??
    props.toolCall.result ??
    props.toolCall.output ??
    props.toolCall.result_preview ??
    null
)

const data = computed(() => {
  const raw = rawResult.value
  if (raw) {
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      const d = parsed?.data || parsed
      if (d && typeof d === 'object') return d
    } catch {
      /* 非 JSON：回退参数 */
    }
  }
  return parseToolCallArgs(props.toolCall) || {}
})

// 兼容两种写法：['换刷头'] 与 [{ text, at }]
const reminders = computed(() => {
  const list = data.value.reminders
  if (!Array.isArray(list)) return []
  return list
    .map((r) => (typeof r === 'string' ? { text: r, at: '' } : r))
    .filter((r) => r && r.text)
})
</script>

<style lang="less" scoped>
.sep-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  width: 100%;
  overflow: hidden;

  .note { font-weight: 500; color: var(--gray-600); flex-shrink: 0; }
  .separator { color: var(--gray-300); flex-shrink: 0; }
  .description {
    color: var(--gray-600);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }
  .tag {
    flex-shrink: 0;
    font-size: 11px;
    padding: 0 6px;
    border-radius: 999px;
    color: var(--gray-600);
    background: var(--gray-100);
    white-space: nowrap;
  }
}

.rem-list {
  margin: 0;
  padding: 8px 12px;
  list-style: none;
  background: var(--gray-0);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;

  li {
    display: flex;
    align-items: baseline;
    gap: 8px;
    font-size: 12px;
    min-width: 0;
  }

  .rem-icon {
    flex-shrink: 0;
    width: 6px;
    height: 6px;
    margin-top: 5px;
    border-radius: 2px;
    background: var(--color-warning-500, var(--main-600));
  }

  .rem-text { color: var(--gray-800); flex: 1; min-width: 0; word-break: break-word; }
  .rem-at { flex-shrink: 0; color: var(--gray-500); }
}
</style>
