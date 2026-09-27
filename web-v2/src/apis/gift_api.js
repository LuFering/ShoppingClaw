/**
 * 送礼智能体 API —— 任务实例（run）的增删查 + 事件流。
 *
 * 后端：`server/routers/gift_router.py`
 *   POST /api/gift/runs                        建实例，立即返回
 *   GET  /api/gift/runs                        列表
 *   GET  /api/gift/runs/{id}                   首屏快照
 *   GET  /api/gift/runs/{id}/events?after_seq= SSE 增量
 *   POST /api/gift/runs/{id}/revise            标记某组档案待补充
 *   GET  /api/gift/runs/{id}/deliverables/{k}  交付物内容
 *
 * run 形状见后端 `GiftRun.to_dict()`：
 *   {id, status, recipient, occasion, budget, signals,
 *    profile:[…], understanding:{…}, profileHead:{…}, error, created_at, updated_at}
 *
 * 事件 kind 与 `useGiftWorkbench.apply()` 的 `ev.t` **一一对应**：
 *   stage / step / live / excluded / profile / understanding / deliverable / done
 * 所以前端状态机不改，只把产出源从 mock 换到这里。
 *
 * 降级策略：沿用 assistant_api.js 的教训 —— 接口失败**不补演示数据**，
 * 如实返回空 + demoStatus。
 */
import { apiGet, apiPost } from './base'
import { demoStatus } from './demoStatus'

const EMPTY_RUN = {
  id: '',
  status: 'failed',
  recipient: '',
  occasion: '',
  budget: 0,
  signals: [],
  profile: [],
  understanding: {},
  profileHead: {},
  error: ''
}

export const normalizeRun = (d) => {
  const src = d && typeof d === 'object' ? d : {}
  return {
    ...EMPTY_RUN,
    ...src,
    signals: Array.isArray(src.signals) ? src.signals : [],
    profile: Array.isArray(src.profile) ? src.profile : [],
    understanding: src.understanding && typeof src.understanding === 'object' ? src.understanding : {},
    profileHead: src.profileHead && typeof src.profileHead === 'object' ? src.profileHead : {}
  }
}

/** 建一次送礼推演。后端立即返回，七步推演在后台跑。
 *
 * signals 传**中文标签**（「真的用得上」等），不传前端内部 key ——
 * 后端按标签查品类映射表（stages.SIGNAL_TO_GOODS），
 * 传内部 key 会查不到、静默退化成兜底关键词。
 * 入口页的 SIGNALS.label 已经是后端认的说法，所以直接透传即可。
 */
export const giftApi = {
  async createRun({ recipient, occasion, budget, signals }) {
    const res = await apiPost('/api/gift/runs', {
      recipient: recipient || '',
      occasion: occasion || '',
      budget: Number(budget) || 0,
      signals: Array.isArray(signals) ? signals : []
    }, {}, true)
    if (!res?.data?.id) throw new Error('创建失败：返回缺少 id')
    demoStatus.gift = false
    return normalizeRun(res.data)
  },

  async listRuns(limit = 20) {
    try {
      const res = await apiGet(`/api/gift/runs?limit=${limit}`, {}, true)
      demoStatus.gift = false
      return Array.isArray(res?.data) ? res.data.map(normalizeRun) : []
    } catch {
      demoStatus.gift = true
      return []
    }
  },

  async getRun(runId) {
    const res = await apiGet(`/api/gift/runs/${encodeURIComponent(runId)}`, {}, true)
    if (!res?.data) throw new Error('任务不存在')
    demoStatus.gift = false
    return normalizeRun(res.data)
  },

  /** 标记某个档案组为待补充（「改一下」按钮）。 */
  async revise(runId, key) {
    const res = await apiPost(
      `/api/gift/runs/${encodeURIComponent(runId)}/revise`, { key }, {}, true
    )
    return normalizeRun(res?.data)
  },

  async getDeliverable(runId, key) {
    const res = await apiGet(
      `/api/gift/runs/${encodeURIComponent(runId)}/deliverables/${encodeURIComponent(key)}`,
      {}, true
    )
    return res?.data || null
  },

  /**
   * 回答 agent 的提问 → 它从停下的地方接着跑。
   *
   * ⚠️ 这个端点此前不存在（后端能停但没人能答），与 planning_api 同名同形。
   */
  async answer(runId, key) {
    const res = await apiPost(
      `/api/gift/runs/${encodeURIComponent(runId)}/answer`,
      { key }, {}, true
    )
    return res?.data || null
  },

  /**
   * 订阅推演事件流。
   *
   * 不用 EventSource：无法携带 Authorization 头，而端点要求登录。
   * 用 fetch + ReadableStream（与 planning_api 同法）。
   *
   * @param {number} afterSeq 续传游标
   * @param {function} onEvent (kind, payload, seq) => void
   */
  async streamEvents(runId, { afterSeq = 0, onEvent, signal } = {}) {
    let headers = { Accept: 'text/event-stream' }
    try {
      const { useUserStore } = await import('@/stores/user')
      headers = { ...headers, ...useUserStore().getAuthHeaders() }
    } catch { /* 未登录则不带头，后端会 401 */ }

    const resp = await fetch(
      `/api/gift/runs/${encodeURIComponent(runId)}/events?after_seq=${afterSeq}`,
      { headers, signal }
    )
    if (!resp.ok || !resp.body) throw new Error(`事件流不可用（HTTP ${resp.status}）`)

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    let curEvent = null
    try {
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() || ''
        for (const line of lines) {
          const t = line.trim()
          if (t.startsWith('event:')) curEvent = t.slice(6).trim()
          else if (t.startsWith('data:')) {
            let d = {}
            try { d = JSON.parse(t.slice(5)) } catch { d = {} }
            onEvent?.(curEvent, d.payload || {}, d.seq ?? 0)
          }
        }
      }
    } finally {
      try { reader.cancel() } catch { /* ignore */ }
    }
  }
}

export default giftApi
