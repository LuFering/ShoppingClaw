<template>
  <div class="assistant-page">
    <!-- ============ 左：助理会话 ============ -->
    <section class="chat-pane">
      <header class="chat-head">
        <h1 class="chat-title">主动助理</h1>
        <span class="chat-status"><span class="dot" />在线 · 监控运行中</span>
        <span v-if="demoStatus.assistant" class="chat-demo">演示数据 · 等待 /api/assistant/overview</span>
      </header>

      <div ref="scrollEl" class="chat-scroll">
        <template v-for="m in messages" :key="m.id">
          <!-- 每日简报卡 -->
          <div v-if="m.kind === 'brief'" class="msg ai">
            <div class="card-msg">
              <div class="card-head">
                <span class="card-kind">每日简报</span>
                <span class="card-time mono">{{ m.time }}</span>
              </div>
              <p class="card-title">{{ m.date }} · 今天需要你知道的</p>
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
            <div class="bubble">{{ m.text }}</div>
            <span class="msg-time mono">{{ m.time }}</span>
          </div>
        </template>
      </div>

      <footer class="chat-input">
        <input
          v-model="draft"
          class="input"
          type="text"
          placeholder="给助理安排任务，如：帮我把洗碗机加进监控…"
          @keydown.enter="send"
        />
        <a-button type="primary" class="send-btn" :disabled="!draft.trim()" @click="send">
          <Send :size="14" />
        </a-button>
      </footer>
    </section>

    <!-- ============ 右：信息区（三 tab） ============ -->
    <aside class="info-pane">
      <div class="info-tabs">
        <button
          v-for="t in tabs"
          :key="t.key"
          class="info-tab"
          :class="{ on: infoTab === t.key }"
          @click="infoTab = t.key"
        >{{ t.label }}</button>
      </div>

      <!-- 今日简报 -->
      <div v-if="infoTab === 'brief'" class="info-body">
        <div class="brief-stats">
          <span class="stat-pill">命中 <b>{{ briefStats.hits }}</b></span>
          <span class="stat-pill">待确认 <b>{{ briefStats.drafts }}</b></span>
          <span class="stat-pill">在盯 <b>{{ briefStats.watching }}</b></span>
        </div>
        <ul class="brief-points">
          <li v-for="(p, i) in briefPoints" :key="i" :class="'pt-' + p.tone">{{ p.text }}</li>
        </ul>
        <p class="brief-note">简报每天 09:00 生成，命中事件实时更新。</p>
      </div>

      <!-- 情报流 -->
      <div v-else-if="infoTab === 'feed'" class="info-body">
        <div v-for="f in feed" :key="f.id" class="feed-row">
          <span class="state" :class="'rs-' + f.result"><span class="dot" />{{ resultLabel(f.result) }}</span>
          <div class="feed-main">
            <p class="feed-title">{{ f.product }}</p>
            <p class="feed-msg">{{ f.change }}</p>
          </div>
          <span class="feed-time mono">{{ f.time }}</span>
        </div>
      </div>

      <!-- 待办 -->
      <div v-else class="info-body">
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
import { ref, nextTick } from 'vue'
import { Send } from 'lucide-vue-next'
import { assistantApi } from '@/apis/assistant_api'
import { demoStatus } from '@/apis/demoStatus'

const hitLabel = (t) => ({ price: '降价', stock: '补货', coupon: '优惠券', rank: '榜单', shop: '店铺活动' }[t] || t)
const resultLabel = (r) => ({ hit: '命中', ok: '成功', empty: '无变化', fail: '失败', run: '执行中' }[r] || r)
const doneText = (a) => ({ viewed: '已查看', archive: '已转存到购物档案', ignored: '已忽略', later: '已稍后处理' }[a] || a)

let seq = 0
const nid = () => `m-${++seq}`

// ===== 数据（assistant_api mock 服务层；后端主动事件/简报聚合接口实现后替换）=====
const messages = ref([])
const briefStats = ref({ hits: 0, drafts: 0, watching: 0 })
const briefPoints = ref([])
const feed = ref([])
const todos = ref([])

const initState = async () => {
  const s = await assistantApi.getInitialState()
  seq = 0 // 让 nid 从头计数，避免与种子 id 冲突
  messages.value = s.messages
  briefStats.value = s.brief.stats
  briefPoints.value = s.brief.points
  feed.value = s.feed
  todos.value = s.todos
}
initState()

// ===== 卡片动作（P4 转真实跳转/写入）=====
const actHit = (m, action) => {
  m.done = action
  if (action === 'view') pushAi(`「${m.product}」的证据：近 7 天价格快照与本次变化明细。对话引擎接入后，这里会展示完整快照图。`)
  else if (action === 'archive') pushAi(`已把「${m.product}」存入购物档案的需求池，可随时在档案里继续。`)
  else pushAi('已忽略这条提醒，之后同类事件仍会正常上报。')
}
const actDraft = (m, action) => {
  m.done = action
  pushAi(action === 'view' ? `「${m.product}」的完整草稿在购物档案的需求池里，去确认后就会进入候选。` : '已稍后处理，稍后会再提醒你。')
}

// ===== 输入与发送（回复生成在 assistant_api；P4 换真实对话引擎）=====
const draft = ref('')
const scrollEl = ref(null)
const pushAi = (text) => {
  messages.value.push({ id: nid(), kind: 'ai', text, time: '刚刚' })
  nextTick(() => { scrollEl.value?.scrollTo({ top: scrollEl.value.scrollHeight, behavior: 'smooth' }) })
}
const send = async () => {
  const text = draft.value.trim()
  if (!text) return
  messages.value.push({ id: nid(), kind: 'user', text, time: '刚刚' })
  draft.value = ''
  nextTick(() => { scrollEl.value?.scrollTo({ top: scrollEl.value.scrollHeight, behavior: 'smooth' }) })
  // 真实 POST /api/assistant/messages 优先，失败降级本地回复（api 层处理）
  const reply = await assistantApi.sendMessage(text)
  pushAi(reply)
}

// ===== 右栏 =====
const tabs = [
  { key: 'brief', label: '今日简报' },
  { key: 'feed', label: '情报流' },
  { key: 'todo', label: '待办' }
]
const infoTab = ref('brief')
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
.chat-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.78rem;
  color: var(--text-muted);
  .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--pos); }
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
  align-items: center;
  gap: 10px;
  padding: 12px 24px 16px;
  border-top: 1px solid var(--border);
}
.input {
  flex: 1;
  height: 38px;
  padding: 0 14px;
  font-family: var(--font-body);
  font-size: 0.86rem;
  color: var(--text);
  background: var(--bg-surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  outline: none;
  transition: border-color 0.15s ease-out;
  &:focus { border-color: var(--accent-500); }
  &::placeholder { color: var(--text-faint); }
}
.send-btn { flex-shrink: 0; }

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

/* 简报 */
.brief-stats {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.brief-points {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 9px;
  li { font-size: 0.83rem; line-height: 1.55; color: var(--text); }
  .pt-pos { &::before { content: '↑'; color: var(--pos); margin-right: 6px; font-family: var(--font-mono); } }
  .pt-accent { &::before { content: '◆'; color: var(--accent-500); margin-right: 6px; font-size: 0.7rem; } }
  .pt-warn { &::before { content: '！'; color: var(--warn); margin-right: 6px; font-family: var(--font-mono); } }
  .pt-muted { &::before { content: '·'; color: var(--text-faint); margin-right: 6px; } }
}
.brief-note { margin: 16px 0 0; font-size: 0.74rem; color: var(--text-faint); }

/* 情报流 */
.feed-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 9px 0;
  border-bottom: 1px solid var(--border);
  &:last-child { border-bottom: none; }
}
.feed-main { flex: 1; min-width: 0; }
.feed-title { margin: 0; font-size: 0.84rem; font-weight: 600; color: var(--text-strong); }
.feed-msg { margin: 1px 0 0; font-size: 0.76rem; color: var(--text-muted); line-height: 1.5; }
.feed-time { font-size: 0.68rem; color: var(--text-faint); flex-shrink: 0; margin-top: 2px; }

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

@media (max-width: 1100px) {
  .assistant-page { grid-template-columns: 1fr; }
  .info-pane { display: none; }
}
</style>
