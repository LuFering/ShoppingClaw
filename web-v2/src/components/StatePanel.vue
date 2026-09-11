<template>
  <div
    id="agent-state-panel"
    class="side-panel side-panel--state"
    :class="{
      'is-visible': open,
      'is-docked': open && docked,
      'is-floating': open && !docked
    }"
    :style="{ flexBasis: open && docked ? `${dockWidth}px` : '0px' }"
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
            :aria-label="mode === 'dock' ? '悬浮显示' : '停靠到右侧'"
            @click="$emit('toggle-mode')"
          >
            <component :is="mode === 'dock' ? PanelTop : PanelBottom" :size="14" />
          </button>
          <button
            type="button"
            class="state-refresh-btn"
            title="关闭"
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
            aria-controls="state-section-stats"
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
            <span v-if="statistics" class="state-section-meta">
              {{ statistics.total_tool_calls ?? 0 }} 工具
            </span>
          </button>
          <div class="state-collapse-panel" :class="{ 'is-expanded': isExpanded('stats') }">
            <div class="state-collapse-inner">
              <div id="state-section-stats" class="state-section-content">
                <div v-if="statistics" class="state-list">
                  <div class="state-list-item">
                    <Timer :size="15" class="state-list-item-icon" />
                    <div class="state-list-item-body">
                      <div class="state-list-item-title">耗时</div>
                      <div class="state-list-item-meta">{{ fmtSeconds(statistics.time_cost) }}</div>
                    </div>
                  </div>
                  <div class="state-list-item">
                    <Wrench :size="15" class="state-list-item-icon" />
                    <div class="state-list-item-body">
                      <div class="state-list-item-title">工具调用</div>
                      <div class="state-list-item-meta">
                        {{ statistics.total_tool_calls ?? 0 }} 次
                        <template v-if="statistics.failed_calls > 0"> · {{ statistics.failed_calls }} 失败</template>
                      </div>
                    </div>
                  </div>
                </div>
                <div v-else class="state-panel-empty">暂无进行中的轮次</div>
              </div>
            </div>
          </div>
        </section>

        <!-- 待办 -->
        <section class="state-section" :class="{ 'is-collapsed': !isExpanded('todos') }">
          <button
            type="button"
            class="state-section-header"
            :aria-expanded="isExpanded('todos')"
            aria-controls="state-section-todos"
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
              <div id="state-section-todos" class="state-section-content">
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
                    >
                      <span
                        v-if="normalizeStatus(todo.status) === 'in_progress'"
                        class="todo-status-indicator__pulse"
                      ></span>
                    </span>
                    <div class="todo-item-body">
                      <span class="todo-item-text" :title="todo.description || todo.title">
                        {{ todo.description || todo.title }}
                      </span>
                    </div>
                  </div>
                </div>
                <div v-else class="state-panel-empty">暂无计划步骤</div>
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
            aria-controls="state-section-artifacts"
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
              <div id="state-section-artifacts" class="state-section-content">
                <div v-if="products.length" class="state-list">
                  <div v-for="(p, i) in products" :key="i" class="state-list-item">
                    <Package :size="15" class="state-list-item-icon" />
                    <div class="state-list-item-body">
                      <div class="state-list-item-title" :title="p.title || p.name || '商品卡'">
                        {{ p.title || p.name || '商品卡' }}
                      </div>
                      <div v-if="p.price" class="state-list-item-meta">{{ p.price }}</div>
                    </div>
                  </div>
                </div>
                <div v-else class="state-panel-empty">本轮暂无产物</div>
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
            aria-controls="state-section-subagents"
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
              <div id="state-section-subagents" class="state-section-content">
                <div v-if="subagents.length" class="state-list">
                  <div v-for="(s, i) in subagents" :key="i" class="state-list-item">
                    <Bot :size="15" class="state-list-item-icon" />
                    <div class="state-list-item-body">
                      <div class="state-list-item-title state-subagent-title">
                        <span>{{ s.name }}</span>
                        <span
                          class="state-subagent-status-icon"
                          :class="subagentStatusClass(s.status)"
                        ></span>
                      </div>
                      <div class="state-list-item-meta">{{ s.status || '' }}</div>
                    </div>
                  </div>
                </div>
                <div v-else class="state-panel-empty">本轮未派发子智能体</div>
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
import { ChevronDown, RefreshCw, PanelRightClose, PanelTop, PanelBottom, Package, Bot, Timer, Wrench } from 'lucide-vue-next'

const props = defineProps({
  open: { type: Boolean, default: false },
  mode: { type: String, default: 'dock' }, // dock | float
  docked: { type: Boolean, default: false },
  dockWidth: { type: Number, default: 340 },
  statistics: { type: Object, default: null },
  planSteps: { type: Array, default: () => [] },
  products: { type: Array, default: () => [] },
  subagents: { type: Array, default: () => [] }
})
defineEmits(['close', 'toggle-mode', 'refresh'])

// 折叠态：默认全部展开
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

const subagentStatusClass = (status) => {
  const v = normalizeStatus(status)
  if (v === 'completed') return 'state-subagent-completed-icon'
  if (v === 'failed') return 'state-subagent-failed-icon'
  if (v === 'in_progress') return 'state-subagent-running-icon'
  return ''
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
/* ═══ 面板外框（对标 Yuxi .side-panel / .side-panel--state）═══ */
.side-panel {
  flex: 0 0 auto;
  overflow: hidden;
  background: var(--gray-0);
  border: 1px solid var(--gray-150);
  border-radius: 10px;
  box-shadow:
    0 16px 40px var(--shadow-1),
    0 2px 10px var(--shadow-0);
  z-index: 20;
  min-width: 0;
  opacity: 0;
  pointer-events: none;
  transform: translateX(10px);
  will-change: width, flex-basis, opacity, transform;
  transition:
    width 0.24s cubic-bezier(0.16, 1, 0.3, 1),
    flex-basis 0.24s cubic-bezier(0.16, 1, 0.3, 1),
    opacity 0.22s ease,
    transform 0.24s cubic-bezier(0.16, 1, 0.3, 1);

  &.is-visible {
    opacity: 1;
    pointer-events: auto;
    transform: translateX(0);
  }
}

.side-panel--state {
  height: auto;
  max-width: min(340px, calc(100vw - 24px));
  min-width: 0;
  box-shadow: 0 4px 16px var(--shadow-0);
  overflow: hidden;

  &.is-docked {
    align-self: flex-start;
    margin: 8px 0;
    border-width: 0;
    box-shadow: none;
    transition:
      flex-basis 0.24s cubic-bezier(0.16, 1, 0.3, 1),
      margin 0.24s cubic-bezier(0.16, 1, 0.3, 1),
      opacity 0.22s ease,
      transform 0.24s cubic-bezier(0.16, 1, 0.3, 1),
      border-width 0.24s ease,
      box-shadow 0.24s ease;

    &.is-visible {
      margin: 8px 8px 8px 0;
      border-width: 1px;
      box-shadow: 0 4px 16px var(--shadow-0);
      min-width: 0;
    }
  }

  &.is-floating {
    position: absolute;
    top: 8px;
    right: 8px;
    width: min(340px, calc(100% - 24px));
    min-width: 0;
    margin: 0;
    z-index: 26;
    box-shadow:
      0 12px 28px var(--shadow-1),
      0 2px 8px var(--shadow-0);
  }

  &.is-docked .state-panel,
  &.is-floating .state-panel {
    height: auto;
    max-height: calc(100vh - 16px);
  }
}

.state-panel {
  width: 340px;
  min-width: 340px;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--gray-0);
  flex-shrink: 0;
  box-sizing: border-box;
}

/* ═══ 头部 ═══ */
.side-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: var(--header-height);
  padding: 4px 12px;
  background: var(--gray-25);
  border-bottom: 1px solid var(--gray-100);
  flex-shrink: 0;
}

.state-panel-header {
  padding: 10px 14px;
  padding-bottom: 0px;
  background: transparent;
  border-bottom: none;
}

.state-panel-header-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.state-refresh-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: none;
  border-radius: 6px;
  color: var(--gray-500);
  background: transparent;
  cursor: pointer;
  opacity: 0;
  pointer-events: none;
  transition:
    opacity 0.16s ease,
    color 0.16s ease,
    background-color 0.16s ease;

  &:hover:not(:disabled) {
    color: var(--main-700);
    background: var(--gray-100);
  }

  &:disabled {
    cursor: not-allowed;
  }
}

.state-panel:hover .state-refresh-btn,
.state-panel:focus-within .state-refresh-btn,
.state-refresh-btn:focus-visible {
  opacity: 1;
  pointer-events: auto;
}

@media (hover: none) {
  .state-refresh-btn {
    opacity: 1;
    pointer-events: auto;
  }
}

.state-panel-title {
  min-width: 0;
  font-size: 14px;
  font-weight: 400;
  color: var(--gray-500);
}

.state-section-meta {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--gray-500);
}

.state-panel-body {
  flex: 1;
  min-height: 0;
  padding: 8px 14px 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: auto;
}

/* ═══ 分区 ═══ */
.state-section {
  display: flex;
  flex-direction: column;

  .state-collapse-panel.is-expanded {
    margin-top: 6px;
  }
}

.state-collapse-panel {
  display: grid;
  grid-template-rows: 0fr;
  transition:
    grid-template-rows 0.24s cubic-bezier(0.16, 1, 0.3, 1),
    visibility 0.24s ease;
  visibility: hidden;
  min-width: 0;

  &.is-expanded {
    grid-template-rows: 1fr;
    visibility: visible;
  }
}

.state-collapse-inner {
  overflow: hidden;
  min-height: 0;
  opacity: 0;
  transform: translateY(-4px);
  transition:
    opacity 0.2s ease,
    transform 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}

.state-collapse-panel.is-expanded .state-collapse-inner {
  opacity: 1;
  transform: translateY(0);
}

.state-section-header {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;

  &:hover {
    .state-section-title,
    .state-section-chevron {
      color: var(--gray-900);
    }
  }

  &:focus-visible {
    outline: 2px solid var(--main-200);
    outline-offset: 2px;
  }
}

.state-section-label {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.state-section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--gray-800);
}

.state-section-chevron {
  flex-shrink: 0;
  color: var(--gray-400);
  transition:
    transform 0.22s cubic-bezier(0.16, 1, 0.3, 1),
    color 0.18s ease;

  &.is-collapsed {
    transform: rotate(-90deg);
  }
}

.state-section-content {
  min-width: 0;
}

.state-panel-empty {
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--gray-25);
  color: var(--gray-500);
  font-size: 13px;
  text-align: center;
}

/* ═══ 待办 ═══ */
.todo-panel-list {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.todo-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 0;
}

.todo-status-indicator {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-sizing: border-box;
  border: 1.5px solid var(--gray-400);
  background: transparent;

  &.is-completed {
    border-color: var(--gray-400);
    background: var(--gray-100);
  }

  &.is-cancelled {
    border-color: var(--gray-400);
    border-style: dashed;
    background: var(--gray-50);
  }
}

.todo-status-indicator__pulse {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--second-500);
  animation: todoStatusPulse 1.2s ease-in-out infinite;
}

@keyframes todoStatusPulse {
  0%,
  100% {
    opacity: 0.35;
    transform: scale(0.78);
  }
  50% {
    opacity: 1;
    transform: scale(1);
  }
}

.todo-item-body {
  min-width: 0;
}

.todo-item-text {
  font-size: 13px;
  line-height: 1.5;
  color: var(--gray-700);
  word-break: break-word;
}

.todo-item.completed .todo-item-text {
  color: var(--gray-500);
  text-decoration: line-through;
}

/* ═══ 列表 ═══ */
.state-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.state-list-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 7px 9px;
  border: 1px solid var(--gray-100);
  border-radius: 10px;
  background: var(--gray-25);
  color: inherit;
  text-align: left;
}

.state-list-item-icon {
  width: 15px;
  height: 15px;
  flex-shrink: 0;
  font-size: 15px;
  color: var(--gray-500);
}

.state-list-item-body {
  min-width: 0;
  flex: 1;
}

.state-list-item-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--gray-900);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.state-list-item-meta {
  margin-top: 1px;
  font-size: 12px;
  line-height: 1.25;
  color: var(--gray-500);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.state-subagent-title {
  display: flex;
  align-items: center;
  gap: 6px;
}

.state-subagent-title span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.state-subagent-status-icon {
  flex-shrink: 0;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--gray-300);
}

.state-subagent-completed-icon {
  background: var(--color-success-700);
}

.state-subagent-failed-icon {
  background: var(--color-error-700);
}

.state-subagent-running-icon {
  background: var(--color-info-700);
}

@media (prefers-reduced-motion: reduce) {
  .state-section-chevron,
  .state-collapse-panel,
  .state-collapse-inner {
    transition: none;
  }

  .todo-status-indicator__pulse {
    animation: none;
  }
}
</style>
