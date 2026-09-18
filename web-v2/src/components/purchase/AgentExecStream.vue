<template>
  <div class="es">
    <header class="es-head">
      <span class="es-title">执行流</span>
      <span class="es-sub">调用 · 检索 · 思考</span>
      <button
        v-if="!atBottom"
        class="es-jump"
        type="button"
        @click="scrollToBottom"
      >回到最新 ↓</button>
    </header>

    <div ref="scrollEl" class="es-scroll" @scroll="onScroll">
      <div v-for="(item, i) in items" :key="i" class="es-row">
        <div class="es-rail">
          <span class="es-dot" :class="'is-' + item.state" />
          <span v-if="i < items.length - 1" class="es-line" />
        </div>
        <div class="es-body">
          <span class="es-kind" :class="'k-' + item.kind">{{ KIND_LABEL[item.kind] || item.kind }}</span>
          <p class="es-text" :class="{ dim: item.state === 'todo' }">{{ item.title }}</p>
          <p v-if="item.detail" class="es-detail" :class="{ dim: item.state === 'todo' }">{{ item.detail }}</p>
          <p v-if="item.time" class="es-time mono">{{ item.time }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 左栏 · agent 任务执行流。
 *
 * 三种条目用「标签色 + 措辞」区分，不拆成三套组件：
 *   think 思考（紫） / retrieve 检索（蓝） / call 调用（中性） / produce 产出（绿）
 * 数据源接上后应来自 SSE：thinking → think，tool_start/tool_complete → call/retrieve，
 * 返回条数写进 detail。
 */
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'

const props = defineProps({
  items: { type: Array, default: () => [] }
})

const KIND_LABEL = {
  think: '思考',
  retrieve: '检索',
  call: '调用',
  produce: '产出'
}

const scrollEl = ref(null)
const atBottom = ref(true)

const isNearBottom = () => {
  const el = scrollEl.value
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight < 40
}

const onScroll = () => {
  // 用户往上翻说明在看历史，此时停止自动跟随
  atBottom.value = isNearBottom()
}

const scrollToBottom = () => {
  const el = scrollEl.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  atBottom.value = true
}

watch(
  () => props.items.length,
  async () => {
    if (!atBottom.value) return
    await nextTick()
    const el = scrollEl.value
    if (el) el.scrollTop = el.scrollHeight
  }
)

let rafId = null
onMounted(() => {
  rafId = requestAnimationFrame(() => {
    const el = scrollEl.value
    if (el) el.scrollTop = el.scrollHeight
  })
})
onBeforeUnmount(() => {
  if (rafId) cancelAnimationFrame(rafId)
})
</script>

<style lang="less" scoped>
.es {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}

.es-head {
  flex: 0 0 auto;
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 0 0 10px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 10px;
}
.es-title {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-strong);
}
.es-sub {
  font-size: 0.7rem;
  color: var(--text-muted);
}
.es-jump {
  margin-left: auto;
  font-size: 0.7rem;
  font-family: var(--font-body);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--accent-200);
  background: var(--accent-50);
  color: var(--accent-700);
  cursor: pointer;
}

.es-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding-right: 2px;
}

.es-row {
  display: flex;
  gap: 9px;
}
.es-rail {
  flex: 0 0 9px;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.es-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  margin-top: 4px;
  flex: 0 0 auto;
  &.is-done { background: var(--pos); }
  &.is-running { background: var(--info); }
  &.is-todo {
    background: var(--bg-surface);
    border: 1px solid var(--border-strong);
    box-sizing: border-box;
  }
}
.es-line {
  flex: 1 1 auto;
  width: 1px;
  background: var(--border);
  margin-top: 2px;
}

.es-body {
  min-width: 0;
  padding-bottom: 12px;
}
.es-row:last-child .es-body { padding-bottom: 0; }

.es-kind {
  display: inline-block;
  font-size: 0.66rem;
  padding: 1px 6px;
  border-radius: 4px;
  margin-bottom: 3px;
  background: var(--bg-sunken);
  // 与项目既有的 .state 写法一致：靠文字色区分类型，不堆彩色胶囊容器
  &.k-think { color: #9581cc; }
  &.k-retrieve { color: var(--info); }
  &.k-call { color: var(--text-muted); }
  &.k-produce { color: var(--pos); }
}
.es-text {
  margin: 0;
  font-size: 0.76rem;
  line-height: 1.5;
  color: var(--text);
  &.dim { color: var(--text-faint); }
}
.es-detail {
  margin: 2px 0 0;
  font-size: 0.7rem;
  line-height: 1.5;
  color: var(--text-muted);
  &.dim { color: var(--text-faint); }
}
.es-time {
  margin: 2px 0 0;
  font-size: 0.66rem;
  color: var(--text-faint);
}
</style>
