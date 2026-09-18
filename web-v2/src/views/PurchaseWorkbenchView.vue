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
        <button
          class="wb-btn"
          type="button"
          :disabled="converged"
          @click="running = !running"
        >{{ running ? '暂停' : '继续' }}</button>
        <button class="wb-btn" type="button" @click="resetRun">
          {{ converged ? '重跑收敛' : '从头开始' }}
        </button>
        <button class="wb-btn" type="button" @click="router.push('/planning')">回入口</button>
        <button class="wb-btn primary" type="button" @click="produceAll">生成交付</button>
      </div>
    </header>

    <!-- 三栏：过程 / 推理 / 产出 -->
    <div class="wb-body">
      <section class="wb-col wb-col--left">
        <AgentExecStream :items="stream" />
      </section>

      <section class="wb-col wb-col--center">
        <PurchaseDecisionGraph
          :graph-data="graphData"
          :meta="graphMeta"
          :converged="converged"
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
      </section>

      <section class="wb-col wb-col--right">
        <DeliverablesPanel
          :items="deliverables"
          :question="pendingQuestion"
          @answer="onAnswer"
        />
      </section>
    </div>
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
 * 目前数据是 mock。后端 planning_agent 接上后，把 useRoute 的 query 换成真实任务 id，
 * 三个数据源分别改为 SSE / 图数据接口 / 交付物接口即可。
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AgentExecStream from '@/components/purchase/AgentExecStream.vue'
import PurchaseDecisionGraph from '@/components/purchase/PurchaseDecisionGraph.vue'
import DeliverablesPanel from '@/components/purchase/DeliverablesPanel.vue'
import {
  buildDecisionGraph,
  DECISION_GRAPH_META,
  EXEC_STREAM,
  DELIVERABLES,
  PENDING_QUESTION,
  NODE_TYPE_COLOR
} from '@/data/purchaseDemo'

const route = useRoute()
const router = useRouter()

const STATE_LABEL = {
  pending: '待探索',
  active: '探索中',
  candidate: '候选',
  selected: '已采纳',
  pruned: '已排除'
}

const taskLabel = computed(() => {
  const scene = route.query.scene || DECISION_GRAPH_META.scene
  const budget = route.query.budget
  const parts = [scene]
  if (budget) parts.push('¥' + Number(budget).toLocaleString('en-US'))
  return parts.join(' · ')
})

const graphMeta = computed(() => ({
  ...DECISION_GRAPH_META,
  scene: route.query.scene || DECISION_GRAPH_META.scene
}))

/* ── 收敛演示 ──
 * 默认直接给收敛态（静置，不抖动）；点「重跑」才从 0.3 推到 1，
 * 让用户看到节点逐个点亮。不默认播放，是因为每推一次都要重算力导向布局，
 * 自动播放会让画面持续微抖。 */
const progress = ref(1)
const running = ref(false)
let timer = null

const graphData = computed(() => buildDecisionGraph(progress.value))
const converged = computed(() => progress.value >= 1)

const tick = () => {
  if (!running.value || progress.value >= 1) {
    if (progress.value >= 1) {
      running.value = false
      clearInterval(timer)
      timer = null
    }
    return
  }
  progress.value = Math.min(1, progress.value + 0.12)
}
onMounted(() => {
  timer = setInterval(tick, 560)
})
onBeforeUnmount(() => clearInterval(timer))

const resetRun = () => {
  progress.value = 0.3
  running.value = true
  selectedNode.value = null
  deliverables.value = DELIVERABLES.map((d) => ({ ...d }))
  pendingQuestion.value = {
    ...PENDING_QUESTION,
    options: PENDING_QUESTION.options.map((o) => ({ ...o }))
  }
}

/* ── 决策图交互 ── */
const selectedNode = ref(null)
const onNodeClick = (node) => { selectedNode.value = node }

/* ── 右栏 ── */
const deliverables = ref(DELIVERABLES.map((d) => ({ ...d })))
const pendingQuestion = ref({
  ...PENDING_QUESTION,
  options: PENDING_QUESTION.options.map((o) => ({ ...o }))
})

const produceAll = () => {
  deliverables.value = deliverables.value.map((d) => ({ ...d, state: 'ready' }))
  progress.value = 1
}

const onAnswer = (key) => {
  const label = pendingQuestion.value.options.find((o) => o.key === key)?.label || key
  pendingQuestion.value = null
  stream.value.push({
    kind: 'think',
    title: `按你的选择「${label}」调整预算口径`,
    detail: '已更新决策图的「约束」节点',
    state: 'done',
    time: '刚刚'
  })
}

const stream = ref(EXEC_STREAM.map((s) => ({ ...s })))
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
  &.primary {
    background: var(--accent-solid);
    border-color: var(--accent-solid);
    color: var(--on-accent);
    &:hover { background: var(--accent-600); }
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
