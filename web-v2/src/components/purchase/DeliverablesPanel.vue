<template>
  <div class="dp">
    <header class="dp-head">
      <span class="dp-title">待交付</span>
      <span class="dp-sub">{{ readyCount }} / {{ items.length }} 已生成</span>
    </header>

    <div class="dp-list">
      <div v-for="d in items" :key="d.id" class="dp-item">
        <div class="dp-row">
          <span class="dp-icon" :class="'is-' + d.state" />
          <span class="dp-name" :class="{ dim: d.state === 'waiting' }">{{ d.name }}</span>
          <span class="dp-state mono" :class="'is-' + d.state">{{ stateLabel(d) }}</span>
        </div>
        <p class="dp-meta">{{ d.meta }}</p>
        <div v-if="d.state === 'running'" class="dp-progress">
          <span :style="{ width: Math.round((d.progress || 0) * 100) + '%' }" />
        </div>
        <div v-if="d.state === 'ready'" class="dp-actions">
          <button class="dp-btn" type="button" @click="$emit('preview', d)">预览</button>
          <button class="dp-btn" type="button" @click="$emit('download', d)">下载</button>
        </div>
      </div>
    </div>

    <!-- agent 停下来等拍板的问题，固定在这里而不是混进左栏执行流 -->
    <div v-if="question" class="dp-ask">
      <p class="dp-ask-text">{{ question.text }}</p>
      <div class="dp-actions">
        <button
          v-for="opt in question.options"
          :key="opt.key"
          class="dp-btn"
          :class="{ primary: opt.primary }"
          type="button"
          @click="$emit('answer', opt.key)"
        >{{ opt.label }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 右栏 · 待交付。
 * 三段：已生成（可预览/下载）、生成中（带进度）、待生成。
 * 末尾是「待确认项」—— agent 的提问必须出现在这里，否则会被左栏的过程信息淹没。
 */
import { computed } from 'vue'

const props = defineProps({
  items: { type: Array, default: () => [] },
  question: { type: Object, default: null }
})

defineEmits(['preview', 'download', 'answer'])

const readyCount = computed(() => props.items.filter((d) => d.state === 'ready').length)

const stateLabel = (d) => ({
  ready: '已生成',
  running: Math.round((d.progress || 0) * 100) + '%',
  waiting: '待生成'
}[d.state] || d.state)
</script>

<style lang="less" scoped>
.dp {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
}

.dp-head {
  flex: 0 0 auto;
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 0 0 10px;
  border-bottom: 1px solid var(--border);
}
.dp-title {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-strong);
}
.dp-sub {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--text-muted);
}

.dp-list {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.dp-item {
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
  &:last-child { border-bottom: none; }
}
.dp-row {
  display: flex;
  align-items: center;
  gap: 7px;
}
.dp-icon {
  flex: 0 0 auto;
  width: 11px;
  height: 14px;
  border: 1px solid var(--border-strong);
  border-radius: 2px;
  &.is-ready { border-color: var(--accent-500); }
  &.is-running { border-color: var(--info); }
  &.is-waiting { border-color: var(--border); }
}
.dp-name {
  font-size: 0.78rem;
  color: var(--text-strong);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  &.dim { color: var(--text-muted); }
}
.dp-state {
  margin-left: auto;
  flex: 0 0 auto;
  font-size: 0.68rem;
  &.is-ready { color: var(--pos); }
  &.is-running { color: var(--info); }
  &.is-waiting { color: var(--text-faint); }
}
.dp-meta {
  margin: 3px 0 0;
  font-size: 0.7rem;
  line-height: 1.5;
  color: var(--text-muted);
}
.dp-progress {
  margin-top: 6px;
  height: 4px;
  border-radius: 2px;
  background: var(--border);
  overflow: hidden;
  span {
    display: block;
    height: 100%;
    border-radius: 2px;
    background: var(--info);
    transition: width 0.3s ease-out;
  }
}
.dp-actions {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}
.dp-btn {
  font-family: var(--font-body);
  font-size: 0.7rem;
  padding: 3px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-strong);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.15s ease-out, border-color 0.15s ease-out;
  &:hover { color: var(--text); border-color: var(--border-strong); }
  &.primary {
    background: var(--accent-solid);
    border-color: var(--accent-solid);
    color: var(--on-accent);
  }
}

.dp-ask {
  flex: 0 0 auto;
  border: 1px solid var(--accent-200);
  border-radius: var(--radius-sm);
  background: var(--accent-50);
  padding: 10px 12px;
}
.dp-ask-text {
  margin: 0;
  font-size: 0.75rem;
  line-height: 1.55;
  color: var(--text);
}
</style>
