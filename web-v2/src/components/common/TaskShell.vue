<template>
  <div class="task-shell">
    <header class="head">
      <div class="head-left">
        <span class="head-icon" v-if="iconSvg" v-html="iconSvg" />
        <div class="head-titles">
          <h1 class="title">{{ title }}</h1>
          <p class="sub">{{ subtitle }}</p>
        </div>
      </div>
      <div class="head-right">
        <span v-if="status" class="status" :class="'st-' + statusTone">
          <i class="status-dot" />{{ status }}
        </span>
        <button class="toggle" type="button" @click="panelOpen = !panelOpen">
          {{ panelOpen ? '收起面板' : '信息面板' }}
        </button>
      </div>
    </header>

    <div class="body">
      <main class="convo">
        <div class="stream">
          <slot name="conversation" />
          <button class="add-card" type="button" @click="$emit('add')">+ 新建需求卡片</button>
        </div>

        <div class="bottom">
          <div class="input-bar">
            <span class="ib-label">修改需求</span>
            <input
              v-model="draft"
              class="ib-input"
              :placeholder="inputPlaceholder"
              @keyup.enter="send"
            />
            <button class="ib-send" type="button" @click="send">发送</button>
          </div>
          <p v-if="appliedMsg" class="ib-applied">{{ appliedMsg }}</p>
        </div>
      </main>

      <aside v-show="panelOpen" class="panel">
        <slot name="panel" />
      </aside>
    </div>

    <slot name="overlays" />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  inputPlaceholder: { type: String, default: '' },
  appliedMsg: { type: String, default: '' },
  icon: { type: String, default: '' },
  status: { type: String, default: '' },
  statusTone: { type: String, default: 'live' }
})
const emit = defineEmits(['modify', 'add'])

const ICONS = {
  gift: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="8" width="17" height="12.5" rx="1.6"/><path d="M12 8v12.5"/><path d="M12 8S10.2 4 8 4 6 7.2 9 7.6M12 8s1.8-4 4-4 2 3.2-1 3.6"/></svg>',
  plan: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="4" width="14" height="17" rx="2"/><rect x="9" y="2.6" width="6" height="3.4" rx="1"/><path d="M8 11h8M8 15h8"/></svg>'
}
const iconSvg = computed(() => ICONS[props.icon] || '')

const panelOpen = ref(true)
const draft = ref('')

function send () {
  const t = draft.value.trim()
  if (!t) return
  emit('modify', t)
  draft.value = ''
}
</script>

<style lang="less" scoped>
.task-shell {
  position: relative; /* 抽屉的定位参照 */
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  height: 100vh;
  min-height: 0;
  overflow: hidden;
  background: var(--bg-base);
  color: var(--text);
  font-family: var(--font-body);
}
.mono { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 28px 12px;
  border-bottom: 1px solid var(--border);

  .head-left { display: flex; align-items: center; gap: 12px; min-width: 0; }
  .head-icon {
    flex: 0 0 auto;
    width: 38px; height: 38px;
    display: flex; align-items: center; justify-content: center;
    color: var(--accent-600);
    background: rgba(23, 138, 103, 0.12);
    border-radius: 10px;
  }
  .head-titles { min-width: 0; }
  .title {
    margin: 0;
    font-family: var(--font-display);
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-strong);
    letter-spacing: -0.01em;
  }
  .sub { margin: 3px 0 0; font-size: 0.76rem; color: var(--text-muted); }

  .head-right { display: flex; align-items: center; gap: 10px; flex: 0 0 auto; }
  .status {
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 0.72rem; color: var(--text-muted);
    padding: 4px 10px; border-radius: 999px;
    border: 1px solid var(--border); background: var(--bg-surface);
    .status-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--text-faint); }
  }
  .status.st-live { color: var(--accent-600); border-color: rgba(23, 138, 103, 0.3); }
  .status.st-live .status-dot { background: var(--accent-500); }
  .status.st-done { color: var(--pos); }
  .status.st-done .status-dot { background: var(--pos); }

  .toggle {
    padding: 5px 12px;
    font-size: 0.76rem;
    color: var(--text-muted);
    background: transparent;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    cursor: pointer;

    &:hover { border-color: var(--border-strong); color: var(--text); }
  }
}

.body {
  display: flex;
  flex-direction: row;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}

/* 对话流主列（对标 chat-box：垂直滚动 + 底部固定输入框） */
.convo {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.stream {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  max-width: 880px;
  width: 100%;
  margin: 0 auto;
  padding: 22px 26px 8px;
}

.add-card {
  margin: 18px 0 6px;
  width: 100%;
  padding: 9px 15px;
  font-size: 0.78rem;
  color: var(--text-muted);
  background: transparent;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-sm);
  cursor: pointer;

  &:hover { color: var(--text); border-color: var(--accent-500); }
}

/* 底部固定输入（对标 message-input-wrapper） */
.bottom {
  flex: 0 0 auto;
  padding: 10px 26px 14px;
  background: linear-gradient(to top, var(--bg-base) 70%, transparent);
}
.input-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  max-width: 880px;
  margin: 0 auto;

  .ib-label {
    flex: 0 0 auto;
    font-size: 0.7rem;
    letter-spacing: 0.05em;
    color: var(--text-faint);
    white-space: nowrap;
  }
  .ib-input {
    flex: 1 1 auto;
    min-width: 0;
    padding: 9px 13px;
    font-family: var(--font-body);
    font-size: 0.82rem;
    color: var(--text);
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    outline: none;

    &::placeholder { color: var(--text-faint); }
    &:focus { border-color: var(--accent-500); }
  }
  .ib-send {
    flex: 0 0 auto;
    padding: 8px 16px;
    font-size: 0.78rem;
    color: var(--bg-surface);
    background: var(--accent-500);
    border: none;
    border-radius: var(--radius-sm);
    cursor: pointer;

    &:hover { background: var(--accent-600); }
  }
}
.ib-applied {
  max-width: 880px;
  margin: 7px auto 0;
  font-size: 0.72rem;
  color: var(--pos);
}

/* 信息面板（对标 StatePanel：可收起、补充聚合视图） */
.panel {
  flex: 0 0 300px;
  overflow-y: auto;
  padding: 16px 18px;
  border-left: 1px solid var(--border);
  background: var(--bg-surface);
}

@media (max-width: 1100px) {
  .body { flex-direction: column; overflow-y: auto; }
  .convo { flex: 1 1 auto; min-height: 60vh; }
  .panel { flex: 0 0 auto; width: 100%; border-left: none; border-top: 1px solid var(--border); }
  .head { flex-direction: column; align-items: flex-start; gap: 10px; }
}
</style>
