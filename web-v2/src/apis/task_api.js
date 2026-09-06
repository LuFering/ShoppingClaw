// 定时任务 API —— 直连后端 /api/tasks（真实接口，免鉴权）
// 后端路由：server/routers/task_router.py（挂载 /api/tasks）
// 字段差异在此层收敛：前端任务模型 ⇄ TaskRecord.to_dict()
import { apiGet, apiPost, apiPut, apiDelete } from './base'

// ── 时间与频率换算 ──────────────────────────────────────────
const pad = (n) => String(n).padStart(2, '0')
export const fmtClock = (iso) => {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  const today = new Date()
  const sameDay = d.toDateString() === today.toDateString()
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`
  if (sameDay) return `今天 ${hm}`
  const diff = Math.round((d - today) / 86400000)
  if (diff === 1) return `明天 ${hm}`
  return `${d.getMonth() + 1}/${d.getDate()} ${hm}`
}
export const fmtAgo = (iso) => {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  const diff = Date.now() - d.getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return '刚刚'
  if (m < 60) return `${m}分钟前`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}小时前`
  const dd = Math.floor(h / 24)
  if (dd <= 7) return `${dd}天前`
  return d.toLocaleDateString('zh-CN')
}

// cron 表达式 → 展示文本（仅支持本项目会生成的 每天/每周 形态）
const cronToText = (cron) => {
  if (!cron) return ''
  const p = String(cron).trim().split(/\s+/)
  if (p.length !== 5) return cron
  const [, min, hour, , dow] = p
  const hm = `${pad(hour)}:${pad(min)}`
  if (dow === '*') return `每天 ${hm}`
  const map = { 1: '一', 2: '二', 3: '三', 4: '四', 5: '五', 6: '六', 0: '日' }
  const days = String(dow).split(',').map((d) => map[d] || d).join('、')
  return `每周${days} ${hm}`
}

// 后端 last_result.status（ok/no_results/no_match/error）→ 前端五态（hit/ok/empty/fail/run）
const mapLastResult = (status) => {
  const s = String(status || '').toLowerCase()
  if (s === 'ok') return 'ok'
  if (s === 'no_results' || s === 'no_match') return 'empty'
  if (s === 'error' || s === 'failed' || s === 'fail') return 'fail'
  if (s === 'running') return 'run'
  return 'empty'
}

// TaskRecord.to_dict() → 前端任务行
export const toFrontTask = (t) => ({
  id: t.id,
  type: t.task_type,
  name: t.name,
  target: describeTarget(t),
  freq: t.interval_seconds ? `每 ${t.interval_seconds / 3600} 小时` : cronToText(t.cron_expression) || '—',
  nextAt: fmtClock(t.next_run_at),
  lastResult: mapLastResult(t.last_result?.status),
  lastAt: fmtAgo(t.last_run_at),
  lastSummary: t.last_result?.summary || '',
  enabled: t.status === 'active',
  busy: false,
  isAi: t.task_type === 'agent',
  taskParams: t.task_params || {},
  intervalSeconds: t.interval_seconds,
  cronExpression: t.cron_expression,
  runCount: t.run_count || 0,
  notifyEnabled: !!t.notify_enabled
})

// 从 task_params 生成「监控对象 / 指令」列文本
const describeTarget = (t) => {
  const p = t.task_params || {}
  if (t.task_type === 'price') {
    const base = p.product_name || p.keyword || ''
    return p.target_price ? `${base} · 目标 ¥${(p.target_price / 100).toFixed(0)}` : base || '—'
  }
  if (t.task_type === 'coupon') {
    const base = p.keyword || ''
    return p.min_coupon_amount ? `${base} · ≥¥${(p.min_coupon_amount / 100).toFixed(0)}券` : base || '—'
  }
  if (t.task_type === 'rank') return [p.keyword, p.product_name && `盯 ${p.product_name}`].filter(Boolean).join(' · ') || '—'
  if (t.task_type === 'shop') return p.shop_name || '—'
  if (t.task_type === 'stock') return p.product_name || '—'
  if (t.task_type === 'agent') return (p.prompt || '').slice(0, 40) || '—'
  return '—'
}

// 前端 freq 形态 → 后端（二选一）
const buildSchedule = ({ freqMode, intervalHours, dailyTime, weekDays }) => {
  if (freqMode === 'interval') {
    return { interval_seconds: Math.max(1, Number(intervalHours) || 2) * 3600 }
  }
  const [hour = '21', min = '00'] = String(dailyTime || '21:00').split(':')
  if (freqMode === 'weekly') {
    const days = (weekDays || []).length ? weekDays.join(',') : '1,2,3,4,5'
    return { cron_expression: `${min} ${hour} * * ${days}` }
  }
  return { cron_expression: `${min} ${hour} * * *` }
}

// 平台显示
export const PLATFORMS = [{ value: 'taobao', label: '淘宝' }]

// ── 接口 ────────────────────────────────────────────────────
export const taskApi = {
  // 任务列表（可选过滤）
  async getTasks({ status, taskType } = {}) {
    const q = new URLSearchParams()
    if (status) q.set('status', status)
    if (taskType) q.set('task_type', taskType)
    q.set('limit', '200')
    const res = await apiGet(`/api/tasks${q.toString() ? `?${q}` : ''}`, {}, false)
    return (res.data || []).map(toFrontTask)
  },

  async getTask(id) {
    const res = await apiGet(`/api/tasks/${id}`, {}, false)
    return toFrontTask(res.data)
  },

  // 创建（结构化参数见 executors：price/stock/coupon/rank/shop/agent）
  async createTask({ name, type, taskParams, freqMode, intervalHours, dailyTime, weekDays, notifyEnabled = true }) {
    const body = {
      name,
      task_type: type,
      task_params: taskParams || {},
      notify_enabled: notifyEnabled,
      notify_channels: notifyEnabled ? ['inapp'] : [],
      ...buildSchedule({ freqMode, intervalHours, dailyTime, weekDays })
    }
    const res = await apiPost('/api/tasks', body, {}, false)
    return res.data
  },

  async updateTask(id, patch) {
    const body = { ...patch }
    // 允许用前端 freq 形态更新调度
    if (patch.freqMode) {
      const s = buildSchedule(patch)
      delete body.freqMode; delete body.intervalHours; delete body.dailyTime; delete body.weekDays
      Object.assign(body, s)
    }
    const res = await apiPut(`/api/tasks/${id}`, body, {}, false)
    return res.data
  },

  // 启停
  async setEnabled(id, enabled) {
    const res = await apiPut(`/api/tasks/${id}`, { status: enabled ? 'active' : 'paused' }, {}, false)
    return res.data
  },

  async deleteTask(id) {
    await apiDelete(`/api/tasks/${id}`, {}, false)
  },

  // 立即执行（结果异步写入日志）
  async triggerTask(id) {
    await apiPost(`/api/tasks/${id}/trigger`, {}, {}, false)
  },

  // 单任务执行日志
  async getTaskLogs(taskId, limit = 10) {
    const res = await apiGet(`/api/tasks/${taskId}/logs?limit=${limit}`, {}, false)
    return (res.data || []).map((lg) => ({
      id: lg.id,
      time: fmtClock(lg.started_at),
      result: mapLastResult(lg.result_data?.status || lg.status),
      msg: lg.error_message || summarizeLog(lg.result_data),
      taskId: lg.task_id
    }))
  },

  // 价格历史
  async getPriceHistory(productId, days = 7) {
    const res = await apiGet(`/api/tasks/price-history/${encodeURIComponent(productId)}?days=${days}`, {}, false)
    return res // { data, trend, total }
  }
}

const summarizeLog = (result) => {
  if (!result || typeof result !== 'object') return ''
  return result.summary || result.alert || (typeof result.message === 'string' ? result.message : '') || JSON.stringify(result).slice(0, 80)
}

export default taskApi
