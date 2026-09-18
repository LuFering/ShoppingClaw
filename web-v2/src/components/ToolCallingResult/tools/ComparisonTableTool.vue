<template>
  <BaseToolCall
    :tool-call="toolCall"
    :appearance="appearance"
    :default-expanded="true"
    :force-show-result="hasTable"
    hide-params
  >
    <template #header>
      <div class="sep-header">
        <span class="note">对比</span>
        <span class="separator">|</span>
        <span class="description">{{ table.title || `${columns.length} 款` }}</span>
      </div>
    </template>

    <template #result>
      <div class="cmp-wrap">
        <div class="cmp-scroll">
          <table class="cmp-table">
            <thead>
              <tr>
                <th class="cmp-corner"></th>
                <th
                  v-for="(c, i) in columns"
                  :key="i"
                  :class="{ 'is-winner': i === winnerIdx }"
                >
                  {{ c }}
                  <span v-if="i === winnerIdx" class="win-badge">推荐</span>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, ri) in rows" :key="ri">
                <th class="row-label">{{ r.label }}</th>
                <td
                  v-for="(v, ci) in r.values"
                  :key="ci"
                  :class="{ 'is-winner': ci === winnerIdx }"
                >{{ v }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-if="conclusion" class="cmp-conclusion">{{ conclusion }}</p>
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

const table = computed(() => {
  const raw = rawResult.value
  if (raw) {
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      const data = parsed?.data || parsed
      if (data && typeof data === 'object') return data
    } catch {
      /* 非 JSON：回退参数 */
    }
  }
  return parseToolCallArgs(props.toolCall) || {}
})

const columns = computed(() => (Array.isArray(table.value.columns) ? table.value.columns : []))
const rows = computed(() =>
  (Array.isArray(table.value.rows) ? table.value.rows : []).filter((r) => r && Array.isArray(r.values))
)
const winnerIdx = computed(() => {
  const w = table.value.winner
  if (w == null) return -1
  return typeof w === 'number' ? w : Number(w.column ?? -1)
})
const conclusion = computed(() => table.value.winner?.reason || table.value.conclusion || '')
const hasTable = computed(() => columns.value.length > 0 && rows.value.length > 0)
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
}

.cmp-wrap {
  padding: 8px 10px;
  background: var(--gray-0);
  border-radius: 8px;
}

.cmp-scroll {
  overflow-x: auto;
}

.cmp-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;

  th,
  td {
    padding: 6px 8px;
    text-align: left;
    border-bottom: 1px solid var(--gray-100);
    color: var(--gray-700);
    white-space: nowrap;
  }

  thead th {
    font-weight: 600;
    color: var(--gray-800);
    border-bottom: 1px solid var(--gray-150);
  }

  .cmp-corner {
    width: 88px;
  }

  .row-label {
    font-weight: 500;
    color: var(--gray-500);
    white-space: nowrap;
  }

  .is-winner {
    background: var(--main-50);
    color: var(--main-700);
    font-weight: 600;
  }

  tbody tr:last-child th,
  tbody tr:last-child td {
    border-bottom: none;
  }
}

.win-badge {
  margin-left: 5px;
  font-size: 10px;
  font-weight: 400;
  padding: 0 5px;
  border-radius: 999px;
  color: var(--main-700);
  background: var(--main-100, var(--main-50));
}

.cmp-conclusion {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--gray-700);
}
</style>
