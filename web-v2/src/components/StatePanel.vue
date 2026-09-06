<template>
  <aside class="state-panel" :class="{ open, float: mode === 'float' }">
    <div class="sp-clip">
      <header class="sp-head">
        <h3 class="sp-title">运行状态</h3>
        <div class="sp-tools">
          <button
            class="sp-close"
            :title="mode === 'dock' ? '悬浮显示' : '停靠到右侧'"
            @click="$emit('toggle-mode')"
          >
            <component :is="mode === 'dock' ? PanelTop : PanelBottom" :size="15" />
          </button>
          <button class="sp-close" aria-label="关闭运行状态" @click="$emit('close')">
            <PanelRightClose :size="16" />
          </button>
        </div>
      </header>

      <div class="sp-body">
        <!-- 本轮统计 -->
        <section class="sp-section">
          <p class="sp-label">本轮统计</p>
          <template v-if="statistics">
            <div class="sp-kv"><span>耗时</span><b class="mono">{{ fmtSeconds(statistics.time_cost) }}</b></div>
            <div class="sp-kv"><span>工具调用</span><b class="mono">{{ statistics.total_tool_calls ?? 0 }}</b></div>
            <div class="sp-kv"><span>失败</span><b class="mono" :class="{ 'is-neg': statistics.failed_calls > 0 }">{{ statistics.failed_calls ?? 0 }}</b></div>
          </template>
          <p v-else class="sp-empty">暂无进行中的轮次，发送消息后这里会显示实时统计。</p>
        </section>

        <!-- 计划与待办 -->
        <section class="sp-section">
          <p class="sp-label">计划与待办</p>
          <template v-if="planSteps.length">
            <StepMessage v-for="ps in planSteps" :key="ps.id || ps.description" :step="ps" />
          </template>
          <p v-else class="sp-empty">暂无计划步骤。</p>
        </section>

        <!-- 产物 -->
        <section class="sp-section">
          <p class="sp-label">产物</p>
          <template v-if="products.length">
            <div v-for="(p, i) in products" :key="i" class="sp-product">
              <span class="sp-product-name">{{ p.title || p.name || '商品卡' }}</span>
              <span v-if="p.price" class="mono">{{ p.price }}</span>
            </div>
          </template>
          <p v-else class="sp-empty">本轮暂无商品产物。</p>
        </section>

        <!-- 子智能体 -->
        <section class="sp-section">
          <p class="sp-label">子智能体</p>
          <template v-if="subagents.length">
            <div v-for="(s, i) in subagents" :key="i" class="sp-kv">
              <span>{{ s.name }}</span>
              <b class="mono">{{ s.status || '' }}</b>
            </div>
          </template>
          <p v-else class="sp-empty">本轮未派发子智能体。</p>
        </section>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { PanelRightClose, PanelTop, PanelBottom } from 'lucide-vue-next'
import StepMessage from '@/components/StepMessage.vue'

defineProps({
  open: { type: Boolean, default: false },
  mode: { type: String, default: 'dock' }, // dock | float
  statistics: { type: Object, default: null }, // { time_cost, total_tool_calls, failed_calls }
  planSteps: { type: Array, default: () => [] },
  products: { type: Array, default: () => [] },
  subagents: { type: Array, default: () => [] }
})
defineEmits(['close', 'toggle-mode'])

const fmtSeconds = (v) => {
  const n = Number(v)
  if (!n || Number.isNaN(n)) return '—'
  return n >= 1 ? `${n.toFixed(1)}s` : `${Math.round(n * 1000)}ms`
}
</script>

<style lang="less" scoped>
.state-panel {
  width: 0;
  overflow: hidden;
  transition: width 0.15s ease-out;
  border-left: 1px solid transparent;
  &.open {
    width: 340px;
    border-left-color: var(--border);
  }
  // 悬浮模式：覆盖在聊天区右侧，不挤占宽度
  &.float {
    position: absolute;
    right: 0;
    top: 0;
    bottom: 0;
    width: 340px;
    z-index: 20;
    border-left: 1px solid var(--border);
    box-shadow: -8px 0 24px var(--shadow-2);
    background: var(--bg-surface);
  }
}

.sp-clip {
  width: 340px;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-surface);
}

.sp-head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px 10px;
  border-bottom: 1px solid var(--border);
}
.sp-title {
  font-family: var(--font-display);
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-strong);
  margin: 0;
}
.sp-tools {
  display: flex;
  align-items: center;
  gap: 2px;
}
.sp-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  &:hover { color: var(--text-strong); background: var(--bg-sunken); }
}

.sp-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 4px 16px 20px;
}

.sp-section {
  padding: 12px 0;
  border-bottom: 1px solid var(--border);
  &:last-child { border-bottom: none; }
}
.sp-label {
  margin: 0 0 8px;
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  color: var(--text-faint);
}
.sp-kv {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 0.82rem;
  color: var(--text-muted);
  padding: 3px 0;
  b { color: var(--text-strong); font-weight: 600; .is-neg { color: var(--neg); } }
}
.sp-empty { margin: 0; font-size: 0.78rem; color: var(--text-faint); line-height: 1.6; }

.sp-product {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 0.82rem;
  color: var(--text);
  padding: 3px 0;
  .sp-product-name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  color: var(--text-muted);
}
</style>
