<template>
  <div class="dg">
    <header class="dg-head">
      <div class="dg-title">
        <span class="dg-name">采购决策图</span>
        <span class="dg-scene">{{ meta.scene }} / {{ meta.subject }}</span>
      </div>
      <div class="dg-status">
        <span class="dg-count mono">{{ nodeCount }} / {{ meta.totalExpected }}</span>
        <span class="dg-count-label">节点</span>
        <span class="dg-state" :class="converged ? 'is-done' : 'is-live'">
          {{ converged ? '已收敛' : '收敛中' }}
        </span>
        <span class="dg-layout">
          <button
            v-for="m in LAYOUT_MODES"
            :key="m.key"
            class="dg-layout-btn"
            :class="{ on: layout === m.key }"
            type="button"
            :title="m.tip"
            @click="layout = m.key"
          >{{ m.label }}</button>
        </span>
        <button
          class="dg-follow"
          :class="{ on: follow }"
          type="button"
          :title="follow ? '新增节点时自动居中' : '已暂停跟随，手动操作过画布'"
          @click="toggleFollow"
        >
          {{ follow ? '跟随执行' : '已暂停' }}
        </button>
      </div>
    </header>

    <div class="dg-canvas">
      <GraphCanvas
        ref="graphRef"
        :graph-data="graphData"
        :layout-options="layoutOptions"
        :focus-id="coreId"
        :resolve-node="resolveNode"
        :resolve-edge="resolveEdge"
        :auto-fit="follow"
        @node-click="onNodeClick"
        @canvas-click="$emit('clear-selection')"
      />
    </div>

    <footer class="dg-legend">
      <span v-for="(color, type) in NODE_TYPE_COLOR" :key="type" class="dg-leg">
        <i :style="{ background: color }" />{{ type }}
      </span>
      <span class="dg-leg-hint">虚线 = 非确定关系（替代 / 依赖 / 排除）</span>
    </footer>
  </div>
</template>

<script setup>
/**
 * 采购决策图 —— 决策图的领域层。
 *
 * 通用图谱能力在 @/components/GraphCanvas.vue，这里只做三件事：
 *   1. 把「节点类型 / 生命周期状态 / 关系类型」翻译成视觉
 *   2. 顶部状态条（已展开节点数 / 是否收敛）
 *   3. 图例与「跟随执行」开关
 */
import { ref, computed } from 'vue'
import GraphCanvas from '@/components/GraphCanvas.vue'
import { themeColor } from '@/utils/themeColors'
// 视觉语义表从 data/purchaseDemo.js 拆到 utils/（2026-09-24）——
// 那些是设计资产，不是演示数据，后端接上后照旧生效。
import {
  NODE_TYPE_COLOR,
  RELATION_STYLE,
  NODE_STATE_STYLE,
  SELECTED_RING,
  PRUNED_FILL,
  CORE_TYPE
} from '@/utils/planningGraphStyle'

const props = defineProps({
  graphData: { type: Object, required: true },
  // 元信息由后端 run.meta 提供；默认给空壳，不再用 demo 常量兜底
  meta: { type: Object, default: () => ({}) },
  /** 执行完成后收起动效、停止居中 */
  converged: { type: Boolean, default: false }
})

const emit = defineEmits(['node-click', 'clear-selection'])

const graphRef = ref(null)
const follow = ref(true)

/**
 * 布局二选一，默认辐射。
 *
 * radial 用 G6 的 focusNode：按「到核心任务的最短路径距离」把节点排进同心环，
 * 天然表达「以本次采购任务为核心向外扩散」，也保证核心始终在画布中心。
 * 力导向给出参考图那种有机形态，但核心不一定居中 —— 保留它便于对比取舍。
 */
const layout = ref('radial')
const LAYOUT_MODES = [
  { key: 'radial', label: '辐射', tip: '以采购任务为核心分层扩散' },
  { key: 'force', label: '力导向', tip: '有机形态，节点位置由连接关系决定' }
]

const nodeCount = computed(() => props.graphData?.nodes?.length || 0)

/** 核心节点 id，作为 radial 的焦点；由数据里的类型推导，不写死 */
const coreId = computed(
  () => (props.graphData?.nodes || []).find((n) => n.type === CORE_TYPE)?.id
)

/** 力导向模式返回空对象，让 GraphCanvas 用它的默认参数；辐射模式给完整配置 */
const layoutOptions = computed(() => {
  if (layout.value !== 'radial' || !coreId.value) return {}
  return {
    type: 'radial',
    focusNode: coreId.value,
    unitRadius: 152,
    linkDistance: 152,
    preventOverlap: true,
    nodeSize: 58,
    nodeSpacing: 12,
    strictRadial: false
  }
})

const toggleFollow = () => {
  follow.value = !follow.value
  if (follow.value) graphRef.value?.fitView?.()
}

const stateOf = (node) => NODE_STATE_STYLE[node.state] || NODE_STATE_STYLE.candidate

/** 节点视觉：大小表达重要程度，颜色表达类型，透明度表达状态 */
const resolveNode = (node) => {
  const st = stateOf(node)
  const color = NODE_TYPE_COLOR[node.type] || NODE_TYPE_COLOR['决策依据']
  const base = node.type === CORE_TYPE ? 46 : 14 + (node.importance ?? 3) * 5.5
  const size = Math.round(base * st.scale)

  // canvas 不认 CSS 变量，所有颜色必须在这里解析成真实色值
  const surface = themeColor('--bg-surface')
  const raised = themeColor('--bg-raised', surface)

  return {
    size,
    // 淘汰节点降饱和：用中性灰替代本色；待探索节点中空
    fill: node.state === 'pending' ? 'transparent' : st.muted ? PRUNED_FILL : color,
    // 选中环 / 核心环 / 其余用画布底色描边（让重叠节点自然分层，不靠阴影）
    stroke: node.state === 'selected'
      ? SELECTED_RING
      : node.type === CORE_TYPE
        ? raised
        : node.state === 'pending'
          ? color
          : surface,
    lineWidth: node.type === CORE_TYPE ? 3 : st.lineWidth,
    opacity: st.opacity,
    labelFill: st.muted ? themeColor('--text-faint') : themeColor('--text')
  }
}

/** 关系视觉：线型表达确定与否，颜色随关系类型 */
const resolveEdge = (edge) => {
  const style = RELATION_STYLE[edge.type] || RELATION_STYLE['依据']
  const nodes = props.graphData?.nodes || []
  const from = nodes.find((n) => n.id === edge.source_id)
  const to = nodes.find((n) => n.id === edge.target_id)
  // 任一端未点亮，整条边也示弱，避免「连线已出现但节点还没来」
  const dim = [from, to].some((n) => !n || n.state === 'pending' || n.state === 'pruned')

  return {
    stroke: style.color,
    lineDash: style.dash ? [4, 3] : undefined,
    opacity: dim ? 0.32 : 0.8,
    labelFill: dim ? themeColor('--text-faint') : themeColor('--text-muted')
  }
}

const onNodeClick = (nodeData) => {
  emit('node-click', nodeData?.data?.original || nodeData)
}
</script>

<style lang="less" scoped>
.dg {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.dg-head {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
}

.dg-title {
  display: flex;
  align-items: baseline;
  gap: 9px;
  min-width: 0;
}
.dg-name {
  font-size: 0.86rem;
  font-weight: 600;
  color: var(--text-strong);
}
.dg-scene {
  font-size: 0.72rem;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dg-status {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
}
.dg-count {
  font-family: var(--font-mono);
  font-size: 0.76rem;
  font-weight: 600;
  color: var(--text-strong);
}
.dg-count-label {
  font-size: 0.7rem;
  color: var(--text-muted);
}
.dg-state {
  font-size: 0.7rem;
  padding: 2px 8px;
  border-radius: 99px;
  border: 1px solid var(--border);
  &.is-live { color: var(--accent-600); }
  &.is-done { color: var(--pos); }
}
.dg-layout {
  display: inline-flex;
  gap: 2px;
  padding: 2px;
  border-radius: var(--radius-sm);
  background: var(--bg-sunken);
  flex: 0 0 auto;
}
.dg-layout-btn {
  font-family: var(--font-body);
  font-size: 0.7rem;
  padding: 2px 8px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: background-color 0.15s ease-out, color 0.15s ease-out;
  &:hover { color: var(--text); }
  &.on { background: var(--bg-surface); color: var(--text-strong); }
}
.dg-follow {
  font-size: 0.7rem;
  font-family: var(--font-body);
  padding: 3px 9px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.15s ease-out, border-color 0.15s ease-out;
  &:hover { border-color: var(--border-strong); color: var(--text); }
  &.on { color: var(--accent-600); border-color: var(--accent-200); }
}

.dg-canvas {
  flex: 1 1 auto;
  min-height: 260px;
}

.dg-legend {
  flex: 0 0 auto;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 12px;
  padding: 9px 14px;
  border-top: 1px solid var(--border);
  font-size: 0.7rem;
  color: var(--text-muted);
}
.dg-leg {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
  i {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    display: block;
    flex: 0 0 auto;
  }
}
.dg-leg-hint {
  color: var(--text-faint);
  margin-left: auto;
  white-space: nowrap;
}

@media (max-width: 900px) {
  .dg-scene, .dg-leg-hint { display: none; }
}
</style>
