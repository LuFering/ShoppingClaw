/**
 * 采购规划 API —— 任务实例（run）的增删查 + 事件流。
 *
 * 后端：`server/routers/planning_router.py`
 *   POST /api/planning/runs                       建实例，立即返回
 *   GET  /api/planning/runs                       列表（入口页「进行中 N 个」）
 *   GET  /api/planning/runs/{id}                  首屏快照
 *   GET  /api/planning/runs/{id}/events?after_seq= SSE 增量
 *   POST /api/planning/runs/{id}/answer           回答待确认
 *   GET  /api/planning/runs/{id}/deliverables/{d} 交付物正文
 *
 * run 的形状见后端 `PlanningRun.to_dict()`：
 *   {id, status, scene, budget, duration, constraints, subject,
 *    graph:{nodes, edges}, meta, question, error, created_at, updated_at}
 *
 * 降级策略：沿用 assistant_api.js 的教训 —— **接口失败时不补演示数据**，
 * 如实返回空 + 置 demoStatus，让界面显示空态而不是编造内容。
 */
import { apiGet, apiPost } from './base'
import { demoStatus } from './demoStatus'

const EMPTY_RUN = {
  id: '',
  status: 'failed',
  scene: '',
  budget: '',
  duration: '',
  constraints: [],
  subject: '',
  graph: { nodes: [], edges: [] },
  meta: {},
  question: null,
  error: ''
}

/** 结构守卫：缺字段一律补齐，视图层不用到处写 `x && x.length`。 */
export const normalizeRun = (d) => {
  const src = d && typeof d === 'object' ? d : {}
  const g = src.graph && typeof src.graph === 'object' ? src.graph : {}
  return {
    ...EMPTY_RUN,
    ...src,
    constraints: Array.isArray(src.constraints) ? src.constraints : [],
    graph: {
      nodes: Array.isArray(g.nodes) ? g.nodes : [],
      edges: Array.isArray(g.edges) ? g.edges : []
    },
    meta: src.meta && typeof src.meta === 'object' ? src.meta : {}
  }
}

export const planningApi = {
  /** 建一次规划任务。后端立即返回 run_id + 空图，图在后台长。 */
  async createRun(params) {
    const res = await apiPost('/api/planning/runs', params, {}, true)
    if (!res?.data?.id) throw new Error('创建任务失败：返回缺少 id')
    demoStatus.planning = false
    return normalizeRun(res.data)
  },

  async listRuns(limit = 20) {
    try {
      const res = await apiGet(`/api/planning/runs?limit=${limit}`, {}, true)
      demoStatus.planning = false
      return Array.isArray(res?.data) ? res.data.map(normalizeRun) : []
    } catch {
      demoStatus.planning = true
      return []
    }
  },

  /** 首屏快照：刷新页面走这里，一次拿全（不重放事件）。 */
  async getRun(runId) {
    const res = await apiGet(`/api/planning/runs/${encodeURIComponent(runId)}`, {}, true)
    if (!res?.data) throw new Error('任务不存在')
    demoStatus.planning = false
    return normalizeRun(res.data)
  },

  async answer(runId, key) {
    const res = await apiPost(
      `/api/planning/runs/${encodeURIComponent(runId)}/answer`, { key }, {}, true
    )
    return normalizeRun(res?.data)
  },

  async getDeliverable(runId, did) {
    const res = await apiGet(
      `/api/planning/runs/${encodeURIComponent(runId)}/deliverables/${encodeURIComponent(did)}`,
      {}, true
    )
    return res?.data || null
  },

  /**
   * 标记这条采购已交付 —— 「生成交付」按钮的动作。
   *
   * 与「取交付物正文」是两件事：正文在收敛时就算好并下发过了；这个接口
   * 记的是**用户的交付确认**，历史列表据此把「待交付」变成「已交付」。
   * 未收敛时后端返回 409，这里如实抛错给界面提示。
   */
  async markDelivered(runId) {
    const res = await apiPost(
      `/api/planning/runs/${encodeURIComponent(runId)}/deliver`, {}, {}, true
    )
    return res?.data || null
  },

  /**
   * 导出产出物：`fmt` ∈ {pdf, csv, md}。拿到字节流 → 触发浏览器下载。
   *
   * 不走 `apiGet`：那个封装会 `res.json()`，而这些是二进制/纯文本文件。
   *
   * ⚠️ 不能把 token 拼进 URL（`?token=`）：那样 token 会进浏览器历史、
   * nginx 日志、Referer —— 后端也不认这种传法，会 401。
   */
  async exportArtifact(runId, did, fmt, filename) {
    let headers = {}
    try {
      const { useUserStore } = await import('@/stores/user')
      headers = useUserStore().getAuthHeaders()
    } catch { /* 未登录则由后端 401 */ }

    const resp = await fetch(
      `/api/planning/runs/${encodeURIComponent(runId)}`
      + `/deliverables/${encodeURIComponent(did)}/export/${encodeURIComponent(fmt)}`,
      { headers }
    )
    if (!resp.ok) throw new Error(`导出失败（HTTP ${resp.status}）`)

    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename || `artifact.${fmt}`
    document.body.appendChild(a)
    a.click()
    a.remove()
    // 交给浏览器读完再释放，立即 revoke 在部分浏览器上会导致下载失败
    setTimeout(() => URL.revokeObjectURL(url), 10_000)
    return true
  },

  /**
   * 订阅事件流。
   *
   * 不用 EventSource：它无法携带 Authorization 头，而该端点要求登录。
   * 改用 fetch + ReadableStream（与 AgentChatComponent 消费对话流同法）。
   *
   * @param {string} runId
   * @param {object} opts
   * @param {number} opts.afterSeq  续传游标：只收 seq 更大的事件
   * @param {function} opts.onEvent (kind, payload, seq) => void
   * @param {AbortSignal} opts.signal
   */
  async streamEvents(runId, { afterSeq = 0, onEvent, signal } = {}) {
    let headers = { Accept: 'text/event-stream' }
    try {
      const { useUserStore } = await import('@/stores/user')
      headers = { ...headers, ...useUserStore().getAuthHeaders() }
    } catch { /* 未登录则不带头，后端会 401，由调用方处理 */ }

    const resp = await fetch(
      `/api/planning/runs/${encodeURIComponent(runId)}/events?after_seq=${afterSeq}`,
      { headers, signal }
    )
    if (!resp.ok || !resp.body) {
      throw new Error(`事件流不可用（HTTP ${resp.status}）`)
    }

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

export default planningApi
