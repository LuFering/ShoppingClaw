<template>
  <div class="assistant-page">
    <!-- ============ 左：助理会话 ============ -->
    <section class="chat-pane">
      <header class="chat-head">
        <h1 class="chat-title">主动助理</h1>
        <span class="chat-status">
          <span class="dot" :class="{ off: !briefStats.watching }" />
          {{ briefStats.watching ? `在盯 ${briefStats.watching} 个任务` : '暂无监控任务' }}
        </span>
        <span v-if="demoStatus.assistant" class="chat-demo">接口不可用 · /api/assistant/overview</span>
      </header>

      <div ref="scrollEl" class="chat-scroll">
        <!-- 加载态（U4）：首次进入不再闪空白 -->
        <div v-if="loading" class="state-hint">
          <a-spin tip="加载助理数据…" />
        </div>
        <!-- 错误态：如实说明并给重试 -->
        <div v-else-if="loadError" class="state-hint">
          <p class="hint-err">{{ loadError }}</p>
          <a-button size="small" @click="initState">重试</a-button>
        </div>
        <!-- 空态（U4）：引导用户起步，而不是留白 -->
        <div v-else-if="!messages.length" class="state-hint">
          <p class="hint-title">还没有情报</p>
          <p class="hint-sub">在对话里说「帮我盯一下 XX 的价格」，这里就会有它的动静。</p>
        </div>

        <template v-for="m in messages" :key="m.id">
          <!-- 每日简报卡 -->
          <div v-if="m.kind === 'brief'" class="msg ai">
            <div class="card-msg">
              <div class="card-head">
                <span class="card-kind">今日简报</span>
                <span class="card-time mono">{{ m.time }}</span>
              </div>
              <p class="card-title">{{ m.date ? m.date + ' · ' : '' }}{{ m.title }}</p>
              <ul class="card-points">
                <li v-for="(p, i) in m.points" :key="i" :class="'pt-' + p.tone">{{ p.text }}</li>
              </ul>
            </div>
          </div>

          <!-- 命中提醒卡 -->
          <div v-else-if="m.kind === 'hit'" class="msg ai">
            <div class="card-msg" :class="{ done: !!m.done }">
              <div class="card-head">
                <span class="card-kind"><span class="dot" :class="'d-' + m.hitType" />{{ hitLabel(m.hitType) }}提醒</span>
                <span class="card-time mono">{{ m.time }}</span>
              </div>
              <p class="card-title">{{ m.product }}</p>
              <p class="card-change mono">{{ m.change }}</p>
              <p class="card-src">来自「{{ m.source }}」</p>
              <div v-if="!m.done" class="card-actions">
                <a-button size="small" @click="actHit(m, 'view')">查看证据</a-button>
                <a-button size="small" @click="actHit(m, 'archive')">转档案</a-button>
                <a-button size="small" @click="actHit(m, 'ignore')">忽略</a-button>
              </div>
              <p v-else class="card-done">{{ doneText(m.done) }}</p>
            </div>
          </div>

          <!-- 待确认草稿卡 -->
          <div v-else-if="m.kind === 'draft'" class="msg ai">
            <div class="card-msg" :class="{ done: !!m.done }">
              <div class="card-head">
                <span class="card-kind">待确认草稿</span>
                <span class="card-time mono">{{ m.time }}</span>
              </div>
              <p class="card-title">{{ m.product }}</p>
              <p class="card-src">{{ m.summary }}</p>
              <div v-if="!m.done" class="card-actions">
                <a-button size="small" type="primary" @click="actDraft(m, 'view')">查看</a-button>
                <a-button size="small" @click="actDraft(m, 'later')">稍后</a-button>
              </div>
              <p v-else class="card-done">{{ doneText(m.done) }}</p>
            </div>
          </div>

          <!-- 普通对话 -->
          <div v-else-if="m.kind === 'user'" class="msg user">
            <div class="bubble">{{ m.text }}</div>
            <span class="msg-time mono">{{ m.time }}</span>
          </div>
          <div v-else class="msg ai">
            <!-- AI 回复按 Markdown 渲染（与 AgentMessageComponent 同一套 MdPreview），
                 否则「已帮你挂上盯价任务：**蓝牙音箱**」会把星号原样显示出来 -->
            <div class="bubble bubble-md">
              <MdPreview :model-value="m.text" :preview-theme="'github'" />
            </div>
            <span class="msg-time mono">{{ m.time }}</span>
          </div>
        </template>
      </div>

      <footer class="chat-input">
        <!-- U3：多行输入（Enter 发送 / Shift+Enter 换行），与其他对话入口一致。
             原先这里是单行 <input>，长指令会被截断看不到自己写了什么。 -->
        <textarea
          ref="inputEl"
          v-model="draft"
          class="input"
          rows="1"
          :disabled="sending"
          placeholder="给助理安排任务，如：帮我把洗碗机加进监控…（Shift+Enter 换行）"
          @keydown.enter.exact.prevent="send"
          @input="autoGrow"
        />
        <a-button type="primary" class="send-btn" :loading="sending" :disabled="!draft.trim()" @click="send">
          <Send v-if="!sending" :size="14" />
        </a-button>
      </footer>
    </section>

    <!-- ============ 右：我在盯什么 / 我该做什么（U2） ============ -->
    <!--
      右栏刻意**不再**放简报与情报流：
        · 简报已经是左栏第一张卡，右栏再放一遍是同一条信息看两遍；
        · 情报流与左栏「命中提醒」卡同源（都来自 task_execution_logs），
          同样重复。
      改放左栏没有的维度 —— 左栏讲「现在发生了什么」，右栏讲
      「我在盯什么（任务清单）/ 我该做什么（待办）」。
    -->
    <aside class="info-pane">
      <div class="info-tabs">
        <button
          v-for="t in tabs"
          :key="t.key"
          class="info-tab"
          :class="{ on: infoTab === t.key }"
          @click="infoTab = t.key"
        >{{ t.label }}<span v-if="t.count" class="tab-count">{{ t.count }}</span></button>
      </div>

      <!-- 监控任务清单 -->
      <div v-if="infoTab === 'watching'" class="info-body">
        <div v-if="!watching.length" class="info-empty">
          <p class="hint-title">还没有监控任务</p>
          <p class="hint-sub">在左边的输入框说「帮我盯一下 XX 的价格」，任务会出现在这里。</p>
        </div>
        <div v-for="w in watching" :key="w.id" class="watch-row">
          <span class="state" :class="w.active ? 'rs-ok' : 'rs-empty'">
            <span class="dot" />{{ w.active ? '监控中' : '已暂停' }}
          </span>
          <div class="watch-main">
            <p class="watch-title">{{ w.name }}</p>
            <p class="watch-target">{{ w.target }}</p>
            <p class="watch-meta">
              {{ w.freq }}<template v-if="w.nextAt"> · 下次 {{ w.nextAt }}</template>
              <template v-if="w.runCount"> · 已跑 {{ w.runCount }} 次</template>
            </p>
          </div>
        </div>
      </div>

      <!-- 进行中：跨域汇总 -->
      <div v-else-if="infoTab === 'inflight'" class="info-body">
        <div v-if="!inflight.length" class="info-empty">
          <p class="hint-title">现在没有在跑的事</p>
          <p class="hint-sub">发起一次采购规划或代购送礼，进度会出现在这里。</p>
        </div>
        <div
          v-for="it in inflight"
          :key="it.id"
          class="todo-row inflight-row"
          role="button"
          tabindex="0"
          :aria-label="`${it.domainLabel}：${it.title}，${it.statusLabel}，点击打开`"
          @click="openInflight(it)"
          @keydown.enter.prevent="openInflight(it)"
        >
          <span class="state" :class="'rs-' + it.status">
            <span class="dot" />{{ it.statusLabel }}
          </span>
          <div class="todo-main">
            <p class="todo-title">
              <span class="inflight-domain">{{ it.domainLabel }}</span>{{ it.title }}
            </p>
            <p class="todo-note">{{ it.note }}</p>
            <p class="inflight-at mono">{{ it.at }}</p>
          </div>
        </div>
      </div>

      <!-- 待办 -->
      <div v-else class="info-body">
        <div v-if="!todos.length" class="info-empty">
          <p class="hint-title">没有待办</p>
          <p class="hint-sub">购物档案里等你确认的记录会出现在这里。</p>
        </div>
        <div v-for="t in todos" :key="t.id" class="todo-row">
          <span class="state" :class="'st-' + t.kind"><span class="dot" />{{ t.kindLabel }}</span>
          <div class="todo-main">
            <p class="todo-title">{{ t.text }}</p>
            <p class="todo-note">{{ t.note }}</p>
          </div>
        </div>
      </div>
    </aside>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { Send } from 'lucide-vue-next'
import { MdPreview } from 'md-editor-v3'
import 'md-editor-v3/lib/preview.css'
import { assistantApi } from '@/apis/assistant_api'
import { apiPost } from '@/apis/base'
import { demoStatus } from '@/apis/demoStatus'
import { useUserStore } from '@/stores/user'
import { doneText, hitLabel } from '@/utils/statusMeta'

const userStore = useUserStore()

const router = useRouter()

// 忽略事件：真的调后端，不是只改本地状态
const dismissEvent = async (eid) => {
  try {
    await apiPost(`/api/events/${encodeURIComponent(eid)}/dismiss`, {}, {}, true)
  } catch { /* 忽略失败只让卡片留在原地，不打断界面 */ }
  await initState()
}

// 语义文案统一走 @/utils/statusMeta（U5）—— 原先这里内联了
// hitLabel / resultLabel / doneText 三张表，而 AgentChatComponent 里
// 另有一份 statusTypeMeta，加一种类型要改两处，必然会漂。

let seq = 0
const nid = () => `m-${++seq}`

// ===== 数据（真实后端：GET /api/assistant/overview）=====
// 2026-09-23：原「本地种子 + 关键词兜底」形态已删除，全部改由聚合接口驱动。
// 刷新即恢复历史（修 U1）—— 卡片序列由后端实时合成，不再存在内存里。
const loading = ref(true)
const loadError = ref('')
const sending = ref(false)
// 服务端合成的卡片序列（简报/命中/草稿）与本地这一轮的对话分开存：
// initState() 会整体替换服务端序列，若把本地消息也放进去，建完任务后的
// 刷新会把用户刚发的消息和回复一起抹掉。
const serverMessages = ref([])
const localMessages = ref([])
const messages = computed(() => [...serverMessages.value, ...localMessages.value])
const briefStats = ref({ hits: 0, drafts: 0, watching: 0 })
const watching = ref([])
const todos = ref([])
// 「进行中」tab：跨域汇总（采购/送礼 run + 最近有命中的监控 + 近 7 天档案）
const inflight = ref([])

const initState = async ({ silent = false } = {}) => {
  // silent：建完任务后的后台刷新，不该让整页回到骨架屏
  if (!silent) loading.value = true
  loadError.value = ''
  try {
    const s = await assistantApi.getInitialState()
    serverMessages.value = s.messages
    briefStats.value = s.brief.stats
    watching.value = s.watching
    todos.value = s.todos
    inflight.value = s.inflight || []
  } catch (e) {
    if (!silent) loadError.value = '助理数据加载失败'
  } finally {
    loading.value = false
  }
}
initState()

// ===== 实时推送（SSE）=====
// 后端 GET /api/events/stream 早已实现，但此前**没有任何消费方** ——
// 页面只在挂载时拉一次 overview，用户开着页面时任务命中了也不会出现，
// 得手动刷新，与「主动触达」的定位不符。
//
// 这里不用 EventSource：它无法携带 Authorization 头（而 /api/events/stream
// 要求登录）。改用 fetch + ReadableStream 手动解析，与 AgentChatComponent
// 消费对话流的方式一致。
// 收到 notify_event 后不做增量合并，直接重拉一次 overview ——
// 后端注释里写明的预期用法，省得前端维护两套会漂移的状态。
let sseAbort = null
let sseRetry = null
let closing = false
let backoff = 2000

const stopStream = () => {
  closing = true
  if (sseRetry) { clearTimeout(sseRetry); sseRetry = null }
  try { sseAbort?.abort() } catch { /* ignore */ }
  sseAbort = null
}

// 标签页切回前台时补一次：SSE 在后台可能被浏览器挂起，
// 不补的话用户切回来看到的是过期数据。
const onVisible = () => {
  if (document.visibilityState === 'visible') initState({ silent: true })
}

// 指数退避重连，上限 30s。它是长连接，正常时不会走到这里。
const scheduleReconnect = () => {
  if (closing) return
  if (sseRetry) clearTimeout(sseRetry)
  sseRetry = setTimeout(() => { startStream() }, backoff)
  backoff = Math.min(backoff * 2, 30000)
}

const startStream = async () => {
  closing = false
  let headers = { Accept: 'text/event-stream' }
  try { headers = { ...headers, ...userStore.getAuthHeaders() } } catch { /* 未登录则跳过实时推送 */ }

  let resp
  try {
    sseAbort = new AbortController()
    resp = await fetch('/api/events/stream', { headers, signal: sseAbort.signal })
  } catch { return scheduleReconnect() }
  if (!resp.ok || !resp.body) return scheduleReconnect()

  backoff = 2000   // 连上了就重置退避
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() || ''
      let isNotify = false
      for (const line of lines) {
        const t = line.trim()
        if (t.startsWith('event:')) isNotify = t.slice(6).trim() === 'notify_event'
        else if (isNotify && t.startsWith('data:')) {
          // 收到就刷新。不解析 payload —— overview 是唯一真相。
          initState({ silent: true })
          isNotify = false
        }
      }
    }
  } catch { /* abort 或网络中断，走下面的重连 */ }
  try { reader.cancel() } catch { /* ignore */ }
  scheduleReconnect()
}

onMounted(() => {
  startStream()
  document.addEventListener('visibilitychange', onVisible)
})
onBeforeUnmount(() => {
  stopStream()
  document.removeEventListener('visibilitychange', onVisible)
})

// ===== 卡片动作 =====
// 2026-09-23：原先这三句都是"假装做了"的演示话术（说「已存入购物档案」
// 但实际什么都没写）。现在：忽略 → 真的调 dismiss 接口；
// 查看 → 跳价格历史/档案页看真东西；转档案 → 跳档案页由用户操作。
const actHit = async (m, action) => {
  if (action === 'ignore') {
    // 卡片 id 形如 msg-log-10（后端由执行日志合成），去掉 msg- 前缀还原成
    // log-10。忽略集合与事件流共用，见 notify_service.dismissed_ids。
    // 注意不能按 m.source（=taskId）分流：它恒为真，会让 dismiss 永远走不到。
    await dismissEvent(String(m.id || '').replace(/^msg-/, ''))
  } else if (action === 'view') {
    // 价格证据：跳到监控任务页（价格历史在那里）
    router.push({ path: '/tasks' })
  } else {
    // 转档案：跳购物档案，由用户在档案里确认
    router.push({ path: '/decisions' })
  }
}
const actDraft = (m, action) => {
  if (action === 'view') router.push({ path: '/decisions' })
}

// ===== 输入与发送 =====
const draft = ref('')
const scrollEl = ref(null)
const inputEl = ref(null)

// U3：textarea 随内容长高（1~6 行封顶），超过就内部滚动
const autoGrow = () => {
  const el = inputEl.value
  if (!el) return
  el.style.height = 'auto'
  const line = 22
  const max = line * 6
  el.style.height = `${Math.min(el.scrollHeight, max)}px`
  el.style.overflowY = el.scrollHeight > max ? 'auto' : 'hidden'
}

const scrollToEnd = () => {
  nextTick(() => { scrollEl.value?.scrollTo({ top: scrollEl.value.scrollHeight, behavior: 'smooth' }) })
}
const pushAi = (text) => {
  localMessages.value.push({ id: nid(), kind: 'ai', text, time: '刚刚' })
  scrollToEnd()
}
const send = async () => {
  const text = draft.value.trim()
  if (!text || sending.value) return
  localMessages.value.push({ id: nid(), kind: 'user', text, time: '刚刚' })
  draft.value = ''
  nextTick(autoGrow)
  scrollToEnd()
  sending.value = true
  try {
    const { text: reply, created } = await assistantApi.sendMessage(text)
    pushAi(reply)
    // 建出任务后刷新一次：新任务要立刻出现在「在盯 N 个任务」和情报流里，
    // 否则用户看到的是建之前的旧数字，像是没生效。
    if (created) await initState({ silent: true })
  } finally {
    sending.value = false
  }
}

// ===== 右栏（U2：只放左栏没有的维度）=====
// 简报与情报流已从左栏的重复位置撤掉（简报是左栏第一张卡，情报流与
// 命中卡同源）。count 用真实数据算，不写死。
const tabs = computed(() => [
  { key: 'watching', label: '监控任务', count: watching.value.length },
  { key: 'todo', label: '待办', count: todos.value.length },
  // 「进行中」：跨域视角。与前两个 tab 刻意互补 ——
  //   前两个是**清单**（我在盯什么 / 我该做什么）
  //   这个是**最近动态**（正在跑什么 / 刚跑完什么）
  // 所以监控只取「最近有命中的」、档案只取「近 7 天更新过的」，
  // 不是把前两个 tab 的内容再列一遍。
  { key: 'inflight', label: '进行中', count: inflight.value.length },
])
const infoTab = ref('watching')

/** 点「进行中」的条目 → 直达对应工作台（route 由后端给，前端不拼） */
const openInflight = (it) => {
  if (it?.route) router.push(it.route)
}
</script>

<style lang="less" scoped>
/* 工作台：左会话 + 右信息区，各自内部滚动（行高锁死防整页滚动） */
.assistant-page {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 400px;
  grid-template-rows: minmax(0, 1fr);
  width: 100%;
  height: 100%;
  color: var(--text);
  overflow: hidden;
}

/* ===== 左：会话 ===== */
.chat-pane {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  border-right: 1px solid var(--border);
}
.chat-head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 24px 12px;
  border-bottom: 1px solid var(--border);
}
.chat-title {
  font-family: var(--font-display);
  font-size: 1.35rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-strong);
  margin: 0;
}
/* 加载 / 错误 / 空三态（U4） */
.state-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 40px 16px;
  text-align: center;
}
.hint-title { margin: 0; font-size: 0.92rem; font-weight: 600; color: var(--text-strong); }
.hint-sub { margin: 0; font-size: 0.8rem; color: var(--text-muted); line-height: 1.6; max-width: 320px; }
.hint-err { margin: 0; font-size: 0.82rem; color: var(--neg); }

.chat-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.78rem;
  color: var(--text-muted);
  .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--pos); }
  /* 没有监控任务时不该假装在跑（U6） */
  .dot.off { background: var(--text-faint); }
}
.chat-demo {
  font-size: 0.72rem;
  color: var(--text-faint);
}

.chat-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 消息 */
.msg { display: flex; flex-direction: column; max-width: 560px; }
.msg.user { align-self: flex-end; align-items: flex-end; }
.msg.ai { align-self: flex-start; align-items: flex-start; }
.msg-time { margin-top: 3px; font-size: 0.68rem; color: var(--text-faint); }

.bubble {
  padding: 8px 14px;
  border-radius: var(--radius);
  font-size: 0.86rem;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.msg.user .bubble {
  background: var(--accent-50);
  color: var(--text-strong);
  border-bottom-right-radius: 3px;
}
.msg.ai .bubble {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-bottom-left-radius: 3px;
}
/* MdPreview 自带白底与内边距，这里让它融进气泡里（只留气泡自己的边框） */
.bubble-md {
  padding: 2px 14px;
  width: 100%;
  :deep(.md-editor-preview-wrapper) { padding: 0; background: transparent; }
  :deep(.md-editor-preview) { background: transparent; font-family: var(--font-body); }
  :deep(p) { margin: 6px 0; font-size: 0.86rem; line-height: 1.6; }
  :deep(p:first-child) { margin-top: 8px; }
  :deep(p:last-child) { margin-bottom: 8px; }
}

/* 主动消息卡片（白卡 + 排版层级，无彩色容器） */
.card-msg {
  width: 100%;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 16px;
  &.done { opacity: 0.65; }
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 6px;
}
.card-kind {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.76rem;
  font-weight: 600;
  color: var(--text-muted);
  .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
  .d-price { background: var(--pos); }
  .d-stock { background: var(--info); }
  .d-coupon { background: var(--accent-500); }
  .d-rank { background: var(--warn); }
  .d-shop { background: var(--text-faint); }
}
.card-time { font-size: 0.68rem; color: var(--text-faint); }
.card-title { margin: 0 0 2px; font-size: 0.94rem; font-weight: 600; color: var(--text-strong); }
.card-change { margin: 0 0 2px; font-size: 0.84rem; color: var(--accent-700); }
.card-src { margin: 0; font-size: 0.74rem; color: var(--text-faint); }
.card-points {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 5px;
  li { font-size: 0.82rem; line-height: 1.55; color: var(--text); }
  .pt-pos { &::before { content: '↑'; color: var(--pos); margin-right: 6px; font-family: var(--font-mono); } }
  .pt-accent { &::before { content: '◆'; color: var(--accent-500); margin-right: 6px; font-size: 0.7rem; } }
  .pt-warn { &::before { content: '！'; color: var(--warn); margin-right: 6px; font-family: var(--font-mono); } }
  .pt-muted { &::before { content: '·'; color: var(--text-faint); margin-right: 6px; } }
}
.card-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.card-done { margin: 8px 0 0; font-size: 0.78rem; color: var(--text-faint); }

/* 输入区 */
.chat-input {
  flex-shrink: 0;
  display: flex;
  align-items: flex-end;   /* 多行时按钮跟底对齐 */
  gap: 10px;
  padding: 12px 24px 16px;
  border-top: 1px solid var(--border);
}
/* U3：textarea 多行——随内容长高，1~6 行（高度由 autoGrow 控制），
   因此这里不写死 height，只定最小高度与内边距。 */
.input {
  flex: 1;
  min-height: 38px;
  max-height: 132px;
  padding: 9px 14px;
  font-family: var(--font-body);
  font-size: 0.86rem;
  line-height: 22px;
  color: var(--text);
  background: var(--bg-surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  outline: none;
  resize: none;
  overflow-y: hidden;
  transition: border-color 0.15s ease-out;
  &:focus { border-color: var(--accent-500); }
  &::placeholder { color: var(--text-faint); }
  &:disabled { opacity: 0.6; }
}
.send-btn { flex-shrink: 0; margin-bottom: 2px; }

/* ===== 右：信息区 ===== */
.info-pane {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--bg-surface);
}
.info-tabs {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px 10px;
  border-bottom: 1px solid var(--border);
}
.info-tab {
  border: none;
  background: transparent;
  padding: 0 0 4px;
  font-size: 0.88rem;
  font-family: var(--font-body);
  color: var(--text-muted);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: color 0.15s ease-out, border-color 0.15s ease-out;
  &:hover { color: var(--text-strong); }
  &.on {
    color: var(--text-strong);
    font-weight: 600;
    border-bottom-color: var(--accent-500);
  }
}
.info-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 14px 20px 20px;
}

/* 右栏 tab 上的计数（U2：用真实条数，不写死） */
.tab-count {
  display: inline-block;
  margin-left: 5px;
  padding: 0 5px;
  border-radius: 8px;
  background: var(--bg-hover, rgba(0, 0, 0, 0.06));
  font-size: 0.68rem;
  font-weight: 500;
  color: var(--text-muted);
  vertical-align: 1px;
}

/* 右栏空态（U2）—— 不留白，给一句怎么起步 */
.info-empty {
  padding: 24px 4px;
  text-align: center;
}
.info-empty .hint-title { margin: 0 0 4px; }

/* 监控任务 */
.watch-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
  &:last-child { border-bottom: none; }
}
.watch-main { flex: 1; min-width: 0; }
.watch-title { margin: 0; font-size: 0.84rem; font-weight: 600; color: var(--text-strong); }
.watch-target { margin: 2px 0 0; font-size: 0.78rem; color: var(--text); line-height: 1.5; }
.watch-meta { margin: 3px 0 0; font-size: 0.72rem; color: var(--text-faint); }

/* 状态圆点+文字（五态语义，无胶囊容器） */
.state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.76rem;
  font-weight: 500;
  white-space: nowrap;
  flex-shrink: 0;
  .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
}
.rs-hit { color: var(--accent-700); }
.rs-ok { color: var(--pos); }
.rs-empty { color: var(--text-faint); font-weight: 400; }
.rs-fail { color: var(--neg); }
.rs-run { color: var(--info); }
/* 「进行中」tab 的状态色 —— 沿用本文件的 `rs-` 前缀（run state）。
   原先我写的是 `is-*`，与这个文件的约定不符（这里用 rs-* / st-*），
   会导致状态点全是默认色、看不出区别。 */
.rs-running { color: var(--info); }
.rs-awaiting { color: var(--warn); }
.rs-converged { color: var(--pos); }
.rs-failed { color: var(--neg); }
.rs-hit { color: var(--accent-700); }
.rs-moved { color: var(--text-muted); }

/* 可点的行：给一点悬停反馈，让「能点进去」这件事看得出来 */
.inflight-row {
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: background 0.15s ease-out;
  &:hover { background: var(--bg-sunken); }
}
/* 领域标签：小字弱色，用来区分「这是采购还是送礼」 */
.inflight-domain {
  display: inline-block;
  margin-right: 6px;
  padding: 0 5px;
  border-radius: 3px;
  font-size: 0.68rem;
  font-weight: 500;
  color: var(--text-muted);
  background: var(--bg-sunken);
}
.inflight-at { margin: 3px 0 0; font-size: 0.68rem; color: var(--text-faint); }

.st-draft { color: var(--info); }
.st-buy { color: var(--pos); }
.st-wait { color: var(--text-muted); }

/* 待办 */
.todo-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
  &:last-child { border-bottom: none; }
}
.todo-main { flex: 1; min-width: 0; }
.todo-title { margin: 0; font-size: 0.84rem; font-weight: 600; color: var(--text-strong); }
.todo-note { margin: 2px 0 0; font-size: 0.76rem; color: var(--text-muted); line-height: 1.5; }

/* U7：窄屏改单列堆叠，而不是把右栏直接 display:none。
   原先的写法会让「监控任务 / 待办」两个 tab 无声消失 —— 用户既看不到
   自己在盯什么，也没有任何提示说明它们去哪了。现在改成上下排列，
   整页可滚动（宽屏时是左右两栏各自内部滚，行高锁死）。 */
@media (max-width: 1100px) {
  .assistant-page {
    grid-template-columns: 1fr;
    grid-template-rows: minmax(320px, 1fr) auto;
    height: auto;
    min-height: 100%;
    overflow: visible;
  }
  .chat-pane {
    border-right: none;
    border-bottom: 1px solid var(--border);
    min-height: 320px;
  }
  .info-pane {
    /* 给右栏一个上限，避免任务多时把对话区挤到屏幕外 */
    max-height: 60vh;
  }
}
</style>
