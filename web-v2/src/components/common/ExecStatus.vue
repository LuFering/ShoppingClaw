<template>
  <div class="exec" :class="'st-' + status">
    <button class="exec-head" type="button" @click="open = !open">
      <span class="dot" />
      <span class="label">{{ statusText }}</span>
      <span v-if="meta" class="meta mono">{{ meta }}</span>
      <span class="chev" :class="{ open }" />
    </button>

    <div v-if="open && steps.length" class="exec-body">
      <div v-for="s in steps" :key="s.name" class="step">
        <span class="step-dot" :class="'sd-' + s.state" />
        <span class="step-name">{{ s.name }}</span>
        <span v-if="s.time" class="step-time mono">{{ s.time }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  // running | done | failed —— 与普通对话的状态语义保持一致
  status: { type: String, default: 'done' },
  meta: { type: String, default: '' },
  steps: { type: Array, default: () => [] }
})

const open = ref(false)

const statusText = computed(
  () => ({ running: '运行中', done: '已完成', failed: '执行失败' }[props.status] || '已完成')
)
</script>

<style lang="less" scoped>
.exec {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-surface);
}

.exec-head {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 11px;
  background: transparent;
  border: none;
  cursor: pointer;
  text-align: left;

  .dot {
    flex-shrink: 0;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--text-muted);
  }
  .label { font-size: 0.76rem; color: var(--text); }
  .meta { font-size: 0.72rem; color: var(--text-muted); }
  .chev {
    margin-left: auto;
    width: 0;
    height: 0;
    border-left: 4px solid var(--text-muted);
    border-top: 3px solid transparent;
    border-bottom: 3px solid transparent;
    transition: transform 0.15s ease-out;

    &.open { transform: rotate(90deg); }
  }
}

.st-running .dot { background: var(--info); }
.st-done .dot { background: var(--pos); }
.st-failed .dot { background: var(--neg); }

.exec-body {
  padding: 2px 11px 9px 26px;
  border-top: 1px solid var(--border);
}

.step {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;

  .step-dot {
    flex-shrink: 0;
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: var(--text-muted);
  }
  .sd-done { background: var(--pos); }
  .sd-running { background: var(--info); }
  .sd-failed { background: var(--neg); }

  .step-name {
    font-size: 0.72rem;
    color: var(--text-muted);
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .step-time { margin-left: auto; font-size: 0.72rem; color: var(--text-muted); }
}
</style>
