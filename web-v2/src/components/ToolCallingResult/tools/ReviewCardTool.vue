<template>
  <BaseToolCall
    :tool-call="toolCall"
    :appearance="appearance"
    :default-expanded="true"
    :force-show-result="hasReview"
    hide-params
  >
    <template #header>
      <div class="sep-header">
        <span class="note">复盘</span>
        <span class="separator">|</span>
        <span class="description">{{ data.target || '购物档案' }}</span>
        <span v-if="data.repurchase" class="tag" :class="data.repurchase === 'yes' ? 'is-yes' : 'is-no'">
          {{ data.repurchase === 'yes' ? '会复购' : '不回购' }}
        </span>
      </div>
    </template>

    <template #result>
      <div class="review-card">
        <div v-if="data.rating" class="rating-row">
          <span class="stars">
            <span
              v-for="i in 5"
              :key="i"
              class="star"
              :class="{ 'is-on': i <= Number(data.rating) }"
            ></span>
          </span>
          <span class="rating-num">{{ data.rating }}/5</span>
        </div>

        <div v-if="pros.length || cons.length" class="pc-grid">
          <ul v-if="pros.length" class="pc-list">
            <li v-for="(p, i) in pros" :key="`p-${i}`">
              <span class="mark is-pro">+</span><span>{{ p }}</span>
            </li>
          </ul>
          <ul v-if="cons.length" class="pc-list">
            <li v-for="(c, i) in cons" :key="`c-${i}`">
              <span class="mark is-con">−</span><span>{{ c }}</span>
            </li>
          </ul>
        </div>

        <p v-if="data.note" class="review-note">{{ data.note }}</p>
      </div>
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

const pros = computed(() => (Array.isArray(data.value.pros) ? data.value.pros.filter(Boolean) : []))
const cons = computed(() => (Array.isArray(data.value.cons) ? data.value.cons.filter(Boolean) : []))
const hasReview = computed(() =>
  Boolean(data.value.target || data.value.note || pros.value.length || cons.value.length)
)
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
    white-space: nowrap;
    &.is-yes { color: var(--color-success-700); background: var(--color-success-50, var(--gray-100)); }
    &.is-no { color: var(--gray-500); background: var(--gray-100); }
  }
}

.review-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  background: var(--gray-0);
  border-radius: 8px;
}

.rating-row {
  display: flex;
  align-items: center;
  gap: 8px;

  .stars { display: inline-flex; gap: 3px; }

  .star {
    width: 10px;
    height: 10px;
    border-radius: 2px;
    background: var(--gray-200);
    &.is-on { background: var(--color-warning-500, var(--main-600)); }
  }

  .rating-num { font-size: 12px; color: var(--gray-500); }
}

.pc-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 4px 16px;
}

.pc-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 3px;

  li {
    display: flex;
    align-items: baseline;
    gap: 6px;
    font-size: 12px;
    color: var(--gray-800);
    min-width: 0;
  }

  .mark {
    flex-shrink: 0;
    font-weight: 600;
    &.is-pro { color: var(--color-success-500); }
    &.is-con { color: var(--gray-400); }
  }
}

.review-note {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--gray-700);
}
</style>
