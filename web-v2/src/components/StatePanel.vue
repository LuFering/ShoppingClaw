<template>
  <div
    id="agent-state-panel"
    class="side-panel side-panel--state"
    :class="{
      'is-visible': open,
      'is-docked': open && mode === 'dock',
      'is-floating': open && mode === 'float'
    }"
  >
    <div class="state-panel">
      <div class="side-panel__header state-panel-header">
        <span class="state-panel-title">状态</span>
        <div class="state-panel-header-actions">
          <button
            type="button"
            class="state-refresh-btn"
            title="刷新状态"
            aria-label="刷新状态"
            @click="$emit('refresh')"
          >
            <RefreshCw :size="14" />
          </button>
          <button
            type="button"
            class="state-refresh-btn"
            :title="mode === 'dock' ? '悬浮显示' : '停靠到右侧'"
            @click="$emit('toggle-mode')"
          >
            <component :is="mode === 'dock' ? PanelTop : PanelBottom" :size="14" />
          </button>
          <button
            type="button"
            class="state-refresh-btn"
            aria-label="关闭状态面板"
            @click="$emit('close')"
          >
            <PanelRightClose :size="14" />
          </button>
        </div>
      </div>

      <div class="state-panel-body">
        <!-- 本轮统计 -->
        <section class="state-section" :class="{ 'is-collapsed': !isExpanded('stats') }">
          <button
            type="button"
            class="state-section-header"
            :aria-expanded="isExpanded('stats')"
            @click="toggle('stats')"
          >
            <span class="state-section-label">
              <span class="state-section-title">本轮统计</span>
              <ChevronDown
                :size="15"
                class="state-section-chevron"
                :class="{ 'is-collapsed': !isExpanded('stats') }"
              />
            </span>
          </button>
          <div class="state-collapse-panel" :class="{ 'is-expanded': isExpanded('stats') }">
            <div class="state-collapse-inner">
              <div class="state-section-content">
                <template v-if="statistics">
                  <div class="state-kv"><span>耗时</span><strong>{{ fmtSeconds(statistics.time_cost) }}</strong></div>
                  <div class="state-kv"><span>工具调用</span><strong>{{ statistics.total_tool_calls ?? 0 }}</strong></div>
                  <div class="state-kv"><span>失败</span><strong :class="{ 'is-neg': statistics.failed_calls > 0 }">{{ statistics.failed_calls ?? 0 }}</strong></div>
                </template>
                <p v-else class="state-empty">暂无进行中的轮次，发送消息后这里会显示实时统计。</p>
              </div>
            </div>
          </div>
        </section>

        <!-- 待办 / 计划 -->
        <section class="state-section" :class="{ 'is-collapsed': !isExpanded('todos') }">
          <button
            type="button"
            class="state-section-header"
            :aria-expanded="isExpanded('todos')"
            @click="toggle('todos')"
          >
            <span class="state-section-label">
              <span class="state-section-title">待办</span>
              <ChevronDown
                :size="15"
                class="state-section-chevron"
                :class="{ 'is-collapsed': !isExpanded('todos') }"
              />
            </span>
            <span v-if="totalTodoCount" class="state-section-meta">
              {{ completedTodoCount }}/{{ totalTodoCount }}
            </span>
          </button>
          <div class="state-collapse-panel" :class="{ 'is-expanded': isExpanded('todos') }">
            <div class="state-collapse-inner">
              <div class="state-section-content">
                <div v-if="planSteps.length" class="todo-panel-list">
                  <div
                    v-for="(todo, index) in planSteps"
                    :key="todo.id || todo.description || index"
                    class="todo-item"
                    :class="{ completed: normalizeStatus(todo.status) === 'completed' }"
                  >
                    <span
                      class="todo-status-indicator"
                      :class="`is-${normalizeStatus(todo.status)}`"
                    ></span>
                    <div class="todo-item-body">
                      <span class="todo-item-text" :title="todo.description || todo.title">
                        {{ todo.description || todo.title }}
                      </span>
                    </div>
                  </div>
                </div>
                <p v-else class="state-empty">暂无计划步骤。</p>
              </div>
            </div>
          </div>
        </section>

        <!-- 产物 -->
        <section class="state-section" :class="{ 'is-collapsed': !isExpanded('artifacts') }">
          <button
            type="button"
            class="state-section-header"
            :aria-expanded="isExpanded('artifacts')"
            @click="toggle('artifacts')"
          >
            <span class="state-section-label">
              <span class="state-section-title">产物</span>
              <ChevronDown
                :size="15"
                class="state-section-chevron"
                :class="{ 'is-collapsed': !isExpanded('artifacts') }"
              />
            </span>
            <span v-if="products.length" class="state-section-meta">{{ products.length }}</span>
          </button>
          <div class="state-collapse-panel" :class="{ 'is-expanded': isExpanded('artifacts') }">
            <div class="state-collapse-inner">
              <div class="state-section-content">
                <div v-if="products.length" class="state-list">
                  <div v-for="(p, i) in products" :key="i" class="state-list-item">
                    <Package :size="15" class="state-list-item-icon" />
                    <div class="state-list-item-body">
                      <div class="state-list-item-title">{{ p.title || p.name || '商品卡' }}</div>
                      <div v-if="p.price" class="state-list-item-meta">{{ p.price }}</div>
                    </div>
                  </div>
                </div>
                <p v-else class="state-empty">本轮暂无商品产物。</p>
              </div>
            </div>
          </div>
        </section>

        <!-- 子智能体 -->
        <section class="state-section" :class="{ 'is-collapsed': !isExpanded('subagents') }">
          <button
            type="button"
            class="state-section-header"
            :aria-expanded="isExpanded('subagents')"
            @click="toggle('subagents')"
          >
            <span class="state-section-label">
              <span class="state-section-title">子智能体</span>
              <ChevronDown
                :size="15"
                class="state-section-chevron"
                :class="{ 'is-collapsed': !isExpanded('subagents') }"
              />
            </span>
            <span v-if="subagents.length" class="state-section-meta">{{ subagents.length }}</span>
          </button>
          <div class="state-collapse-panel" :class="{ 'is-expanded': isExpanded('subagents') }">
            <div class="state-collapse-inner">
              <div class="state-section-content">
                <div v-if="subagents.length" class="state-list">
                  <div v-for="(s, i) in subagents" :key="i" class="state-list-item">
                    <Bot :size="15" class="state-list-item-icon" />
                    <div class="state-list-item-body">
                      <div class="state-list-item-title">{{ s.name }}</div>
                      <div class="state-list-item-meta">{{ s.status || '' }}</div>
                    </div>
                  </div>
                </div>
                <p v-else class="state-empty">本轮未派发子智能体。</p>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, computed } from 'vue'
import { ChevronDown, RefreshCw, PanelRightClose, PanelTop, PanelBottom, Package, Bot } from 'lucide-vue-next'

const props = defineProps({
  open: { type: Boolean, default: false },
  mode: { type: String, default: 'dock' }, // dock | float
  statistics: { type: Object, default: null },
  planSteps: { type: Array, default: () => [] },
  products: { type: Array, default: () => [] },
  subagents: { type: Array, default: () => [] }
})
defineEmits(['close', 'toggle-mode', 'refresh'])

// 折叠态：默认全部展开（Yuxi 式 section 折叠）
const expandedSections = reactive({
  stats: true,
  todos: true,
  artifacts: true,
  subagents: true
})
const isExpanded = (key) => expandedSections[key] !== false
const toggle = (key) => { expandedSections[key] = !isExpanded(key) }

const normalizeStatus = (status) => {
  const v = String(status || 'pending').toLowerCase()
  if (['completed', 'complete', 'done', 'success'].includes(v)) return 'completed'
  if (['in_progress', 'running', 'active', 'processing'].includes(v)) return 'in_progress'
  if (['failed', 'error', 'cancelled', 'canceled'].includes(v)) return 'failed'
  return 'pending'
}

const totalTodoCount = computed(() => (props.planSteps || []).length)
const completedTodoCount = computed(
  () => (props.planSteps || []).filter((s) => normalizeStatus(s.status) === 'completed').length
)

const fmtSeconds = (v) => {
  const n = Number(v)
  if (!n || Number.isNaN(n)) return '—'
  return n >= 1 ? `${n.toFixed(1)}s` : `${Math.round(n * 1000)}ms`
}
</script>

<style lang="less" scoped>
.side-panel--state {
  width: 0;
  flex-shrink: 0;
  overflow: hidden;
  transition: width 0.15s ease-out;
  border-left: 1px solid transparent;

  &.is-visible.is-docked {
    width: 340px;
    border-left-color: var(--gray-150);
  }

  &.is-floating {
    position: absolute;
    right: 0;
    top: 0;
    bottom: 0;
    width: 340px;
    z-index: 20;
    border-left: 1px solid var(--gray-150);
    box-shadow: -8px 0 24px var(--shadow-2);
    background: var(--gray-0);
  }
}

.state-panel {
  width: 340px;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--gray-0);
}

.state-panel-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px 10px;
  border-bottom: 1px solid var(--gray-150);
}

.state-panel-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--gray-1000);
}

.state-panel-header-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}

.state-refresh-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--gray-500);
  cursor: pointer;
  transition: all 0.15s ease;
  &:hover { color: var(--gray-1000); background: var(--gray-100); }
}

.state-panel-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 4px 16px 20px;
}

.state-section {
  padding: 12px 0;
  border-bottom: 1px solid var(--gray-150);
  &:last-child { border-bottom: none; }
}

.state-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 0;
  margin: 0 0 8px;
  border: none;
  background: transparent;
  cursor: pointer;
  color: var(--gray-500);
}

.state-section-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.state-section-title {
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  color: var(--gray-500);
}

.state-section-chevron {
  transition: transform 0.2s ease;
  &.is-collapsed { transform: rotate(-90deg); }
}

.state-section-meta {
  font-size: 0.72rem;
  color: var(--gray-400);
  font-variant-numeric: tabular-nums;
}

.state-collapse-panel {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.2s ease;
  &.is-expanded { grid-template-rows: 1fr; }
}
.state-collapse-inner {
  overflow: hidden;
  min-height: 0;
}

.state-kv {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 0.82rem;
  color: var(--gray-600);
  padding: 3px 0;
  strong {
    color: var(--gray-1000);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    &.is-neg { color: var(--color-error-500); }
  }
}

.state-empty {
  margin: 0;
  font-size: 0.78rem;
  color: var(--gray-400);
  line-height: 1.6;
}

.todo-panel-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.todo-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 0.82rem;
  color: var(--gray-700);
  &.completed .todo-item-text {
    color: var(--gray-400);
    text-decoration: line-through;
  }
}
.todo-status-indicator {
  flex-shrink: 0;
  width: 12px;
  height: 12px;
  margin-top: 3px;
  border-radius: 50%;
  border: 1.5px solid var(--gray-300);
  &.is-completed { border-color: var(--main-500); background: var(--main-500); }
  &.is-in_progress { border-color: var(--main-500); background: var(--main-100); }
  &.is-failed { border-color: var(--color-error-500); background: var(--color-error-500); }
}
.todo-item-text {
  line-height: 1.5;
  word-break: break-word;
}

.state-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.state-list-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 0.82rem;
  color: var(--gray-700);
}
.state-list-item-icon {
  flex-shrink: 0;
  color: var(--gray-400);
}
.state-list-item-body { min-width: 0; }
.state-list-item-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.state-list-item-meta {
  font-size: 0.75rem;
  color: var(--gray-400);
}
</style>
