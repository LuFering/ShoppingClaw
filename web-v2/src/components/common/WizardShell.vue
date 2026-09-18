<template>
  <div class="wizard-shell">
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

    <!-- 顶部进度条 -->
    <nav class="stepper">
      <template v-for="(s, i) in steps" :key="s.key">
        <button
          class="step"
          :class="['st-' + stepState(i), { active: i === current }]"
          type="button"
          @click="current = i"
        >
          <span class="step-dot">
            <svg v-if="stepState(i) === 'done'" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7"/></svg>
            <em v-else>{{ i + 1 }}</em>
          </span>
          <span class="step-text">
            <span class="step-label">{{ s.label }}</span>
            <span v-if="s.sub" class="step-sub">{{ s.sub }}</span>
          </span>
        </button>
        <span v-if="i < steps.length - 1" class="step-line" :class="{ filled: i < current }" />
      </template>
    </nav>

    <!-- 主体 -->
    <div class="wiz-body">
      <main class="stage">
        <!-- 持久需求小卡（非需求步时显示，点击回到需求） -->
        <div v-if="current !== 0" class="req-mini" @click="current = 0">
          <span class="rm-badge">需求</span>
          <span class="rm-title">{{ reqTitle }}</span>
          <span class="rm-fields">{{ reqSummary }}</span>
          <span class="rm-go">查看 ▸</span>
        </div>

        <div class="stage-inner">
          <div class="step-head">
            <h2 class="sh-title">{{ steps[current].label }}</h2>
            <p v-if="steps[current].desc" class="sh-desc">{{ steps[current].desc }}</p>
          </div>
          <slot :name="'step-' + steps[current].key" />
        </div>

        <div class="step-nav">
          <button v-if="current > 0" class="sn-btn" type="button" @click="current--">‹ 上一步</button>
          <span class="sn-progress">第 {{ current + 1 }} / {{ steps.length }} 步</span>
          <button v-if="current < steps.length - 1" class="sn-btn primary" type="button" @click="current++">下一步 ›</button>
        </div>
      </main>

      <aside v-show="panelOpen" class="panel">
        <slot name="panel" />
      </aside>
    </div>

    <!-- 底部：修改需求对话 -->
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
  statusTone: { type: String, default: 'live' },
  steps: { type: Array, default: () => [] },
  reqTitle: { type: String, default: '' },
  reqSummary: { type: String, default: '' }
})
const emit = defineEmits(['modify'])

const ICONS = {
  gift: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="8" width="17" height="12.5" rx="1.6"/><path d="M12 8v12.5"/><path d="M12 8S10.2 4 8 4 6 7.2 9 7.6M12 8s1.8-4 4-4 2 3.2-1 3.6"/></svg>',
  plan: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="4" width="14" height="17" rx="2"/><rect x="9" y="2.6" width="6" height="3.4" rx="1"/><path d="M8 11h8M8 15h8"/></svg>'
}
const iconSvg = computed(() => ICONS[props.icon] || '')

// 面板默认收起：首屏先把宽度让给当前步内容；面板内是与步骤不重复的跨步信息
const panelOpen = ref(false)
const draft = ref('')
// 默认停在第 1 步而非最后一步 —— 打开即可看到需求与拆解过程，而不是直接落到「交付」终点
const current = ref(0)

function stepState (i) {
  if (i < current.value) return 'done'
  if (i === current.value) return 'active'
  return 'upcoming'
}

function send () {
  const t = draft.value.trim()
  if (!t) return
  emit('modify', t)
  draft.value = ''
}
</script>

<style lang="less" scoped>
.wizard-shell {
  position: relative;
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
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
    background: var(--accent-50);
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
    .status-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--text-muted); }
  }
  .status.st-live { color: var(--accent-600); border-color: var(--accent-200); }
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

/* 顶部进度条 */
.stepper {
  display: flex;
  align-items: center;
  padding: 13px 28px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-base);
  overflow-x: auto;
}
.step {
  display: flex;
  align-items: center;
  gap: 9px;
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 3px 2px;
  font: inherit;
  color: var(--text-muted);
  white-space: nowrap;
}
.step-dot {
  flex: 0 0 auto;
  width: 26px; height: 26px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid var(--border-strong);
  font-size: 0.74rem; font-style: normal;
  color: var(--text-muted);
  background: var(--bg-surface);
  transition: border-color 0.15s ease-out, background-color 0.15s ease-out, color 0.15s ease-out;
}
.step-text { display: flex; align-items: baseline; gap: 7px; }
.step-label { font-size: 0.82rem; color: var(--text-muted); }
.step-sub { font-size: 0.72rem; color: var(--text-muted); }

.step.done .step-dot { border-color: var(--pos); color: var(--pos); }
.step.done .step-label { color: var(--text); }
.step.active .step-dot { border-color: var(--accent-solid); background: var(--accent-solid); color: var(--on-accent); }
.step.active .step-label { color: var(--text-strong); font-weight: 600; }
.step.upcoming .step-dot { border-color: var(--border); }
.step:hover .step-label { color: var(--text-strong); }

.step-line {
  flex: 1 1 auto;
  height: 2px;
  margin: 0 14px;
  min-width: 22px;
  background: var(--border);
  border-radius: 2px;
}
.step-line.filled { background: var(--pos); }

/* 主体 */
.wiz-body {
  display: flex;
  flex-direction: row;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}
.stage {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  padding: 18px 28px 12px;
}
.stage-inner { max-width: 780px; margin: 0 auto; }

/* 持久需求小卡 */
.req-mini {
  display: flex;
  align-items: center;
  gap: 10px;
  max-width: 780px;
  margin: 0 auto 16px;
  padding: 8px 14px;
  background: var(--bg-surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: border-color 0.15s ease-out;
  &:hover { border-color: var(--accent-500); }

  .rm-badge { flex: 0 0 auto; font-size: 0.72rem; letter-spacing: 0.04em; color: var(--on-accent); background: var(--accent-solid); padding: 2px 8px; border-radius: 5px; }
  .rm-title { flex: 0 0 auto; font-size: 0.8rem; font-weight: 600; color: var(--text-strong); }
  .rm-fields { flex: 1 1 auto; min-width: 0; font-size: 0.72rem; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .rm-go { flex: 0 0 auto; font-size: 0.72rem; color: var(--accent-600); }
}

/* 步标题 */
.step-head { margin-bottom: 14px; }
.sh-title {
  margin: 0;
  font-family: var(--font-display);
  font-size: 1.06rem;
  font-weight: 600;
  color: var(--text-strong);
}
.sh-desc { margin: 4px 0 0; font-size: 0.76rem; color: var(--text-muted); line-height: 1.6; }

/* 步内导航 */
.step-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  max-width: 780px;
  margin: 22px auto 6px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
}
.sn-progress { font-size: 0.72rem; color: var(--text-muted); }
.sn-btn {
  padding: 7px 15px;
  font-size: 0.78rem;
  color: var(--text);
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: border-color 0.15s ease-out, background-color 0.15s ease-out;
  &:hover { border-color: var(--border-strong); }

  &.primary {
    color: var(--on-accent);
    background: var(--accent-solid);
    border-color: var(--accent-solid);
    &:hover { background: var(--accent-600); border-color: var(--accent-600); }
  }
}

/* 底部固定输入 */
.bottom {
  flex: 0 0 auto;
  padding: 10px 28px 14px;
  background: var(--bg-base);
  border-top: 1px solid var(--border);
}
.input-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  max-width: 880px;
  margin: 0 auto;

  .ib-label {
    flex: 0 0 auto;
    font-size: 0.72rem;
    letter-spacing: 0.05em;
    color: var(--text-muted);
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
    &::placeholder { color: var(--text-muted); }
    &:focus { border-color: var(--accent-500); }
  }
  .ib-send {
    flex: 0 0 auto;
    padding: 8px 16px;
    font-size: 0.78rem;
    color: var(--on-accent);
    background: var(--accent-solid);
    border: none;
    border-radius: var(--radius-sm);
    cursor: pointer;
    transition: background-color 0.15s ease-out;
    &:hover { background: var(--accent-600); }
  }
}
.ib-applied {
  max-width: 880px;
  margin: 7px auto 0;
  font-size: 0.72rem;
  color: var(--pos);
}

/* 信息面板 */
.panel {
  flex: 0 0 300px;
  overflow-y: auto;
  padding: 16px 18px;
  border-left: 1px solid var(--border);
  background: var(--bg-surface);
}

@media (max-width: 1100px) {
  .wiz-body { flex-direction: column; overflow-y: auto; }
  .stage { flex: 1 1 auto; min-height: 60vh; }
  .panel { flex: 0 0 auto; width: 100%; border-left: none; border-top: 1px solid var(--border); }
  .head { flex-direction: column; align-items: flex-start; gap: 10px; }
}
</style>
