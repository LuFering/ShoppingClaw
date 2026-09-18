<template>
  <BaseToolCall
    :tool-call="toolCall"
    :appearance="appearance"
    :default-expanded="true"
    :force-show-result="hasRecord"
    hide-params
  >
    <template #header>
      <div class="sep-header">
        <span class="note">归档</span>
        <span class="separator">|</span>
        <span class="description">{{ record.target || '购物档案' }}</span>
        <span class="tag" :class="{ 'is-dropped': isDropped }">{{ phaseLabel }}</span>
      </div>
    </template>

    <template #result>
      <div class="archive-card">
        <div v-if="hasMeta" class="meta-grid">
          <div v-if="record.budget" class="meta-item">
            <span class="k">预算</span><span class="v">{{ record.budget }}</span>
          </div>
          <div v-if="record.forWhom" class="meta-item">
            <span class="k">给谁</span><span class="v">{{ record.forWhom }}</span>
          </div>
          <div v-if="record.scenario" class="meta-item">
            <span class="k">场景</span><span class="v">{{ record.scenario }}</span>
          </div>
          <div v-if="record.category" class="meta-item">
            <span class="k">品类</span><span class="v">{{ record.category }}</span>
          </div>
        </div>

        <div class="phase-bar">
          <span
            v-for="(p, i) in PHASES"
            :key="p.key"
            class="phase-node"
            :class="{ 'is-done': i <= currentIdx, 'is-current': i === currentIdx }"
          >
            <span class="phase-dot"></span>
            <span class="phase-label">{{ p.label }}</span>
          </span>
        </div>

        <ul v-if="candidates.length" class="cand-list">
          <li v-for="(c, i) in candidates" :key="i">
            <span class="cand-name">{{ c.name }}</span>
            <span v-if="c.price" class="cand-price">{{ c.price }}</span>
            <span v-if="c.note" class="cand-note">{{ c.note }}</span>
          </li>
        </ul>

        <div v-if="record.risk" class="risk-row">
          <span class="k">风险</span><span class="v">{{ record.risk }}</span>
        </div>

        <div class="archive-actions">
          <button type="button" class="archive-btn" @click.stop="goArchive">去档案看</button>
        </div>
      </div>
    </template>
  </BaseToolCall>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import BaseToolCall from '../BaseToolCall.vue'
import { parseToolCallArgs } from '../toolRegistry'

const props = defineProps({
  toolCall: { type: Object, required: true },
  appearance: { type: String, default: 'card' },
  defaultExpanded: { type: Boolean, default: false }
})

const PHASES = [
  { key: 'need', label: '需求池' },
  { key: 'candidate', label: '候选中' },
  { key: 'decided', label: '已决策' },
  { key: 'using', label: '使用中' },
  { key: 'reviewed', label: '已复盘' }
]

const router = useRouter()

// 结果优先（tool_complete 的完整记录），运行中回退到参数（tool_start 的计划）
const rawResult = computed(
  () =>
    props.toolCall.tool_call_result?.content ??
    props.toolCall.result ??
    props.toolCall.output ??
    props.toolCall.result_preview ??
    null
)

const record = computed(() => {
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

const hasRecord = computed(() => Boolean(record.value.target))
const hasMeta = computed(() =>
  Boolean(record.value.budget || record.value.forWhom || record.value.scenario || record.value.category)
)
const candidates = computed(() => (Array.isArray(record.value.candidates) ? record.value.candidates : []))

const isDropped = computed(() => record.value.phase === 'dropped')
const currentIdx = computed(() => {
  const i = PHASES.findIndex((p) => p.key === record.value.phase)
  return i >= 0 ? i : 1
})
const phaseLabel = computed(() =>
  isDropped.value ? '已放弃' : PHASES[currentIdx.value]?.label || '候选中'
)

const goArchive = () => {
  router.push('/decisions')
}
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
    color: var(--main-700);
    background: var(--main-50);
    white-space: nowrap;
    &.is-dropped { color: var(--gray-500); background: var(--gray-100); }
  }
}

.archive-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px 12px;
  background: var(--gray-0);
  border-radius: 8px;
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 6px 12px;

  .meta-item { display: flex; gap: 6px; font-size: 12px; min-width: 0; }
  .k { flex-shrink: 0; color: var(--gray-500); }
  .v { color: var(--gray-800); word-break: break-word; }
}

.phase-bar {
  display: flex;
  align-items: center;
  gap: 4px;

  .phase-node {
    display: flex;
    align-items: center;
    gap: 3px;
    font-size: 11px;
    color: var(--gray-400);

    .phase-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--gray-200);
      flex-shrink: 0;
    }

    &.is-done { color: var(--gray-600); .phase-dot { background: var(--main-500, var(--main-600)); } }
    &.is-current { color: var(--main-700); font-weight: 600; }
  }

  .phase-node + .phase-node::before {
    content: '';
    width: 10px;
    height: 1px;
    background: var(--gray-200);
    margin-right: 3px;
  }
}

.cand-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 4px;

  li {
    display: flex;
    align-items: baseline;
    gap: 8px;
    font-size: 12px;
    min-width: 0;
  }

  .cand-name { font-weight: 600; color: var(--gray-800); flex-shrink: 0; }
  .cand-price { color: var(--main-700); flex-shrink: 0; }
  .cand-note { color: var(--gray-500); min-width: 0; word-break: break-word; }
}

.risk-row {
  display: flex;
  gap: 6px;
  font-size: 12px;
  .k { flex-shrink: 0; color: var(--gray-500); }
  .v { color: var(--gray-700); word-break: break-word; }
}

.archive-actions { display: flex; }

.archive-btn {
  font: inherit;
  font-size: 12px;
  padding: 3px 12px;
  border: 1px solid var(--gray-150);
  border-radius: 6px;
  background: transparent;
  color: var(--main-700);
  cursor: pointer;

  &:hover { background: var(--main-50); }
}
</style>
