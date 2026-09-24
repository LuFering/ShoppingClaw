<template>
  <div class="wb">
    <!-- 页头：agent 身份 + 当前任务 + 操作 -->
    <header class="wb-head">
      <span class="wb-sig">采</span>
      <div class="wb-id">
        <p class="wb-name">采办 · 采购规划</p>
        <p class="wb-task">{{ taskLabel }}</p>
      </div>
      <div class="wb-actions">
        <button class="wb-btn" type="button" @click="router.push('/planning')">回入口</button>
        <button v-if="demoStatus.planning" class="wb-btn" type="button" @click="loadSnapshot">
          重试
        </button>
        <button
          class="wb-btn primary"
          type="button"
          :disabled="!deliverables.length || runStatus !== 'converged'"
          @click="produceAll"
        >生成交付</button>
      </div>
    </header>

    <!-- 三栏：过程 / 推理 / 产出 -->
    <div class="wb-body">
      <section class="wb-col wb-col--left">
        <AgentExecStream :items="stream" />
      </section>

      <section class="wb-col wb-col--center">
        <!-- 加载/错误：如实说明，不铺演示数据 -->
        <div v-if="loading" class="wb-state">
          <a-spin tip="正在恢复任务…" />
        </div>
        <div v-else-if="loadError" class="wb-state">
          <p class="hint-err">{{ loadError }}</p>
          <a-button size="small" @click="loadSnapshot">重试</a-button>
        </div>
        <!-- 空态：还没建任务 / 任务刚建、图还没长出来 -->
        <div v-else-if="!graphData.nodes.length" class="wb-state">
          <p class="hint-title">正在规划…</p>
          <p class="hint-sub">阶段推进中，决策图会逐步长出来。</p>
        </div>
        <template v-else>
          <PurchaseDecisionGraph
            :graph-data="graphData"
            :meta="graphMeta"
            :converged="runStatus === 'converged'"
            @node-click="onNodeClick"
            @clear-selection="selectedNode = null"
          />
          <div v-if="selectedNode" class="wb-detail">
            <span class="wb-detail-type" :style="{ color: NODE_TYPE_COLOR[selectedNode.type] }">
              {{ selectedNode.type }}
            </span>
            <span class="wb-detail-name">{{ selectedNode.name }}</span>
            <span class="wb-detail-state mono">{{ STATE_LABEL[selectedNode.state] || selectedNode.state }}</span>
            <span v-if="selectedNode.meta?.pruneReason" class="wb-detail-why">
              排除原因：{{ selectedNode.meta.pruneReason }}
            </span>
            <span v-else-if="selectedNode.meta?.price" class="wb-detail-why mono">
              ¥{{ selectedNode.meta.price }}
            </span>
            <button class="wb-detail-close" type="button" @click="selectedNode = null">×</button>
          </div>
        </template>
      </section>

      <section class="wb-col wb-col--right">
        <DeliverablesPanel
          :items="deliverables"
          :question="pendingQuestion"
          @answer="onAnswer"
          @preview="onPreview"
          @download="onDownload"
        />
      </section>
    </div>

    <!-- 交付物预览：正文由后端按决策图生成 -->
    <a-modal
      v-model:open="previewOpen"
      :title="previewData?.name || '交付物'"
      width="720px"
      :footer="null"
    >
      <pre class="wb-preview mono">{{ previewData?.content || '' }}</pre>
    </a-modal>
  </div>
</template>

<script setup>
/**
 * 采购智能体 · 工作台执行页
 *
 * 三栏分工：
 *   左 = 它做了什么（执行流）
 *   中 = 它怎么想的（决策图）
 *   右 = 我能拿到什么（待交付 + 待确认）
 * 三者不重复：图里不出现文件，交付区不出现推理，执行流不出现结论。
 *
 * 数据来源（2026-09-24 接真后端，原先全是 purchaseDemo 的 mock）：
 *   · 首屏 → GET /api/planning/runs/{id}      快照，刷新即恢复（不重放事件）
 *   · 增量 → GET /api/planning/runs/{id}/events  SSE，after_seq 续传
 *   · 拍板 → POST /api/planning/runs/{id}/answer
 * 三处共用同一本事件账（planning_events），前后端不会漂。
 *
 * 图的「渐进长出」由后端驱动：每个阶段跑完发一条 graph 事件（整图），
 * 前端只负责替换 —— 合并逻辑在服务端一处，前端不做第二套。
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AgentExecStream from '@/components/purchase/AgentExecStream.vue'
import PurchaseDecisionGraph from '@/components/purchase/PurchaseDecisionGraph.vue'
import DeliverablesPanel from '@/components/purchase/DeliverablesPanel.vue'
import { planningApi } from '@/apis/planning_api'
import { demoStatus } from '@/apis/demoStatus'
import {
  NODE_TYPE_COLOR,
  STATE_LABEL
} from '@/utils/planningGraphStyle'

const route = useRoute()
const router = useRouter()

// ── 任务实例 ──────────────────────────────────────────────
// run id 优先取 query（入口页建好后带过来）；没有则说明是直接访问
// /planning/run —— 如实提示回入口，不编一个假任务出来。
const runId = ref(String(route.query.run || ''))
const runStatus = ref('running')
const loading = ref(true)
const loadError = ref('')

const graphData = ref({ nodes: [], edges: [] })
const graphMeta = ref({})
const stream = ref([])
const deliverables = ref([])
const pendingQuestion = ref(null)

const taskLabel = computed(() => {
  const parts = []
  const scene = route.query.scene
  if (scene) parts.push(scene)
  // 预算只挂在 query 上做展示：表单给的是原话（「¥6万」），预设给的是数字。
  // 数字才格式化，字符串原样显示 —— 对「¥6万」做 Number() 会得到 NaN。
  const budget = route.query.budget
  if (budget) {
    const n = Number(budget)
    parts.push(Number.isFinite(n) && n > 0 ? '¥' + n.toLocaleString('en-US') : String(budget))
  }
  return parts.join(' · ') || '采购规划任务'
})

// ── 事件 → 界面 ───────────────────────────────────────────
// 后端只发这 8 类（刻意不学 chat 的 15 种）：
//   phase / think / retrieve / call / graph / question / deliverable / done
const applyEvent = (kind, payload) => {
  switch (kind) {
    case 'phase':
      stream.value.push({
        kind: 'think',
        title: payload.label || payload.phase,
        state: 'done',
        time: nowClock()
      })
      break
    case 'think':
    case 'retrieve':
    case 'call':
    case 'produce':
      stream.value.push({
        kind,
        title: payload.title || '',
        detail: payload.detail || '',
        state: 'done',
        time: nowClock()
      })
      break
    case 'graph':
      // 整图替换 —— 合并已在服务端做过
      graphData.value = {
        nodes: payload.nodes || [],
        edges: payload.edges || []
      }
      break
    case 'question':
      pendingQuestion.value = {
        text: payload.text,
        options: (payload.options || []).map((o) => ({ ...o }))
      }
      runStatus.value = 'awaiting'
      break
    case 'deliverable':
      upsertDeliverable(payload)
      break
    case 'done':
      runStatus.value = payload.status || 'converged'
      if (payload.status === 'failed') {
        loadError.value = payload.error || '任务执行失败'
      }
      break
    default:
      break
  }
}

const upsertDeliverable = (d) => {
  if (!d?.id) return
  const i = deliverables.value.findIndex((x) => x.id === d.id)
  const item = { id: d.id, name: d.name, meta: d.meta, state: d.state, progress: d.progress }
  if (i >= 0) deliverables.value[i] = { ...deliverables.value[i], ...item }
  else deliverables.value.push(item)
}

const nowClock = () => {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

// ── 载入 ──────────────────────────────────────────────────
let abort = null

const loadSnapshot = async () => {
  if (!runId.value) {
    loading.value = false
    loadError.value = '缺少任务 ID —— 请从入口页开始一次采购规划。'
    return
  }
  loading.value = true
  loadError.value = ''
  try {
    const run = await planningApi.getRun(runId.value)
    runStatus.value = run.status
    graphData.value = run.graph
    graphMeta.value = run.meta || {}
    pendingQuestion.value = run.question
      ? { text: run.question.text, options: run.question.options || [] }
      : null
    // 交付物：快照里没有清单，靠事件补齐；已收敛时用约定的三件套占位
    if (run.status === 'converged') {
      for (const d of DELIVERABLE_FALLBACK) upsertDeliverable({ ...d, state: 'ready' })
    }
    subscribe()
  } catch (e) {
    loadError.value = e?.message || '任务加载失败'
    demoStatus.planning = true
  } finally {
    loading.value = false
  }
}

const DELIVERABLE_FALLBACK = [
  { id: 'd-plan', name: '采购方案.md', meta: '含清单、顺序与依赖' },
  { id: 'd-compare', name: '候选对比表', meta: '按硬约束逐项横比' },
  { id: 'd-budget', name: '预算分配表', meta: '按类别拆分预算' }
]

// 事件流：断线自动重连并带 after_seq 续传（事件落库且 seq 单调，所以能这么做）
let lastSeq = 0
let retrying = false

const subscribe = async () => {
  if (!runId.value) return
  abort?.abort?.()
  abort = new AbortController()
  try {
    await planningApi.streamEvents(runId.value, {
      afterSeq: lastSeq,
      signal: abort.signal,
      onEvent: (kind, payload, seq) => {
        if (seq) lastSeq = Math.max(lastSeq, seq)
        applyEvent(kind, payload)
      }
    })
  } catch (e) {
    // abort 是主动断开，不重连
    if (abort?.signal?.aborted) return
    if (retrying) return
    retrying = true
    setTimeout(() => { retrying = false; subscribe() }, 2000)
    return
  }
  // 流自然结束（收敛/失败）后不再重连
}

// ── 卡片动作 ──────────────────────────────────────────────
const selectedNode = ref(null)
const onNodeClick = (node) => { selectedNode.value = node }

const onAnswer = async (key) => {
  if (!runId.value) return
  try {
    const run = await planningApi.answer(runId.value, key)
    runStatus.value = run.status
    pendingQuestion.value = run.question
      ? { text: run.question.text, options: run.question.options || [] }
      : null
    // 续跑会产生新事件，重新订阅（带 after_seq，不重放）
    subscribe()
  } catch (e) {
    loadError.value = e?.message || '提交回答失败'
  }
}

const previewOpen = ref(false)
const previewData = ref(null)

const onPreview = async (d) => {
  if (!runId.value) return
  try {
    previewData.value = await planningApi.getDeliverable(runId.value, d.id)
    previewOpen.value = true
  } catch (e) {
    loadError.value = e?.message || '交付物加载失败'
  }
}

const onDownload = async (d) => {
  if (!runId.value) return
  try {
    const data = await planningApi.getDeliverable(runId.value, d.id)
    if (!data?.content) return
    const blob = new Blob([data.content], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = data.name || 'deliverable.md'
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    loadError.value = e?.message || '下载失败'
  }
}

const produceAll = () => {
  // 收敛后交付物已由后端产出；这里只是把右栏状态对齐
  deliverables.value = deliverables.value.map((d) => ({ ...d, state: 'ready' }))
}

onMounted(loadSnapshot)
onBeforeUnmount(() => { try { abort?.abort?.() } catch { /* ignore */ } })
</script>

<style lang="less" scoped>
.wb {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--bg-base);
}

/* 页头 */
.wb-head {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 18px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-surface);
}
.wb-sig {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 7px;
  background: var(--accent-50);
  color: var(--accent-700);
  font-size: 0.78rem;
  font-weight: 600;
}
.wb-id {
  min-width: 0;
}
.wb-name {
  margin: 0;
  font-size: 0.86rem;
  font-weight: 600;
  color: var(--text-strong);
}
.wb-task {
  margin: 1px 0 0;
  font-size: 0.72rem;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.wb-actions {
  margin-left: auto;
  display: flex;
  gap: 6px;
  flex: 0 0 auto;
}
.wb-btn {
  font-family: var(--font-body);
  font-size: 0.74rem;
  padding: 5px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-strong);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.15s ease-out, border-color 0.15s ease-out, background-color 0.15s ease-out;
  &:hover { color: var(--text); }
  &:disabled { opacity: 0.45; cursor: not-allowed; }
  &.primary {
    background: var(--accent-solid);
    border-color: var(--accent-solid);
    color: var(--on-accent);
    &:hover:not(:disabled) { background: var(--accent-600); }
  }
}

/* 三栏 */
.wb-body {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-columns: 268px minmax(0, 1fr) 288px;
}
.wb-col {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 14px 16px;
  &--left { border-right: 1px solid var(--border); }
  &--center { padding: 14px; }
  &--right {
    border-left: 1px solid var(--border);
    background: var(--bg-sunken);
    overflow-y: auto;
  }
}

/* 中栏的加载 / 错误 / 空三态 */
.wb-state {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  text-align: center;
}
.hint-title { margin: 0; font-size: 0.92rem; font-weight: 600; color: var(--text-strong); }
.hint-sub { margin: 0; font-size: 0.8rem; color: var(--text-muted); line-height: 1.6; max-width: 320px; }
.hint-err { margin: 0; font-size: 0.82rem; color: var(--neg); }

/* 节点详情条 */
.wb-detail {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
  margin-top: 9px;
  padding: 8px 11px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  font-size: 0.74rem;
}
.wb-detail-type {
  font-weight: 600;
  flex: 0 0 auto;
}
.wb-detail-name {
  color: var(--text-strong);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wb-detail-state {
  font-size: 0.7rem;
  color: var(--text-muted);
  padding: 1px 7px;
  border-radius: 99px;
  background: var(--bg-sunken);
  flex: 0 0 auto;
}
.wb-detail-why {
  color: var(--text-muted);
  min-width: 0;
}
.wb-detail-close {
  margin-left: auto;
  flex: 0 0 auto;
  width: 20px;
  height: 20px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--text-faint);
  font-size: 0.9rem;
  line-height: 1;
  cursor: pointer;
  &:hover { color: var(--text); background: var(--bg-sunken); }
}

/* 交付物预览 */
.wb-preview {
  margin: 0;
  max-height: 60vh;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.78rem;
  line-height: 1.7;
  color: var(--text);
}

@media (max-width: 1100px) {
  .wb-body {
    grid-template-columns: minmax(0, 1fr);
    grid-auto-rows: minmax(0, auto);
    overflow-y: auto;
  }
  .wb-col {
    &--left {
      border-right: none;
      border-bottom: 1px solid var(--border);
      max-height: 320px;
    }
    &--center { min-height: 420px; }
    &--right {
      border-left: none;
      border-top: 1px solid var(--border);
    }
  }
}
</style>
