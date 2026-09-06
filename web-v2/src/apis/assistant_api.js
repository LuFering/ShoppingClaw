// 主动助理 API（契约先行：真实请求 → 失败降级内置演示数据）
// 契约（后端待实现，详见 docs/api-contracts.md）：
//   GET  /api/assistant/overview       → {success, data:{messages, brief, feed, todos}}
//   POST /api/assistant/messages       body {text} → {success, data:{reply}}
// 事件数据（feed/brief）与 /api/events/recent 同源（任务日志聚合），后端实现一处即可两处受益。
import { apiGet, apiPost } from './base'
import { demoStatus } from './demoStatus'

let seq = 0
const nid = () => `m-${++seq}`

// 初始会话（对齐真实事件序列会产出的消息形态）
const seedMessages = () => [
  {
    id: nid(), kind: 'brief', time: '今天 09:00', date: '每日简报',
    points: [
      { tone: 'pos', text: '扫地机器人 G20 降价 ¥100，进入你的目标区间' },
      { tone: 'accent', text: '戴森 V12 旗舰店发现 ¥100 可领券' },
      { tone: 'muted', text: '「冰箱」草稿待你确认，已等 1 天' }
    ]
  },
  {
    id: nid(), kind: 'hit', hitType: 'stock', time: '今天 10:24',
    product: 'Incase Icon 灰色 M', change: '缺货状态解除，现有货',
    source: '通勤背包补货'
  },
  {
    id: nid(), kind: 'draft', time: '昨天 21:00', product: '冰箱',
    summary: '海尔 501L 变频对开门（约 ¥5699）：静音 38dB、一级能效；注意散热空间'
  },
  { id: nid(), kind: 'user', time: '昨天 20:12', text: '帮我把洗碗机加进监控' },
  { id: nid(), kind: 'ai', time: '昨天 20:12', text: '好的，已创建「洗碗机盯价」任务（每 6 小时一次），可在监控任务页查看与调整。' }
]

const brief = () => ({
  stats: { hits: 2, drafts: 1, watching: 5 },
  points: [
    { tone: 'pos', text: '扫地机器人 G20 降价 ¥100，进入你的目标区间' },
    { tone: 'accent', text: '戴森 V12 旗舰店发现 ¥100 可领券' },
    { tone: 'warn', text: '添可店铺活动接口超时，已自动重试 1 次' },
    { tone: 'muted', text: '「冰箱」草稿待你确认，已等 1 天' }
  ]
})

const feed = () => [
  { id: 'f1', result: 'hit', product: '扫地机器人 石头 G20', change: '¥2999 → ¥2899，进入目标区间', time: '10:30' },
  { id: 'f2', result: 'hit', product: '戴森 V12 旗舰店', change: '发现 ¥100 可领券', time: '09:00' },
  { id: 'f3', result: 'empty', product: '添可芙万 3.0', change: '价格未变，仍 ¥2199', time: '08:00' },
  { id: 'f4', result: 'fail', product: '添可店铺活动', change: '接口超时，已重试 1 次', time: '07:45' },
  { id: 'f5', result: 'ok', product: '每日决策汇总', change: '生成 1 条待确认草稿（冰箱）', time: '昨天 21:00' }
]

const todos = () => [
  { id: 't1', kind: 'draft', kindLabel: '待确认', text: '「冰箱」草稿待确认', note: '已等 1 天 · 确认后进入候选' },
  { id: 't2', kind: 'buy', kindLabel: '该下单', text: '洗烘一体机 ¥5499', note: '已到目标价，装修完工即可拍板' },
  { id: 't3', kind: 'wait', kindLabel: '继续等', text: '安全座椅等 618', note: '目标 ¥2599 以内 · 可叠加以旧换新' }
]

// 降级时的关键词回复（真实对话引擎接入后不再走到）
export const generateReply = (text) => {
  if (/监控|盯|提醒/.test(text)) return '好的，已创建监控任务（演示）。任务引擎接入后，这里会直接建到你的任务列表里。'
  if (/档案|记录|记/.test(text)) return '已帮你记到购物档案的需求池（演示）。'
  return '已收到。对话引擎接入（P4）后我会真正理解并执行这句话；当前为界面演示阶段。'
}

const delay = (ms) => new Promise((r) => setTimeout(r, ms))

export const assistantApi = {
  async getInitialState() {
    try {
      const res = await apiGet('/api/assistant/overview', {}, false)
      if (!res?.data) throw new Error('bad shape')
      demoStatus.assistant = false
      return res.data
    } catch {
      demoStatus.assistant = true
      await delay(80)
      return { messages: seedMessages(), brief: brief(), feed: feed(), todos: todos() }
    }
  },

  // 发送一句给助理；真实端点失败时走降级回复（保留拟人延迟）
  async sendMessage(text) {
    try {
      const res = await apiPost('/api/assistant/messages', { text }, {}, false)
      return res?.data?.reply || '（后端返回为空）'
    } catch {
      await delay(700)
      return generateReply(text)
    }
  },

  async getBrief() {
    const res = await apiGet('/api/assistant/overview', {}, false).catch(() => null)
    return res?.data?.brief || brief()
  }
}

export default assistantApi
