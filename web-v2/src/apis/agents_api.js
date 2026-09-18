// 智能体管理 API
// - 列表/详情：真实 GET /api/chat/agent（agent 为代码注册制）
// - 创建/更新/删除/启停：后端暂无 agent CRUD 端点 —— 本地暂存层（localStorage），
//   待后端实现（如 /api/agents）后仅需替换下方 LOCAL 实现
import { apiGet } from './base'

const LOCAL_KEY = 'sc_agents_local_v1'

const loadLocal = () => {
  try { return JSON.parse(localStorage.getItem(LOCAL_KEY)) || [] } catch { return [] }
}
const saveLocal = (list) => localStorage.setItem(LOCAL_KEY, JSON.stringify(list))

const delay = (ms = 180) => new Promise((r) => setTimeout(r, ms))

export const agentsApi = {
  // 真实注册 agent + 本地暂存 agent（本地项覆盖同 id 注册项）
  async listAgents() {
    let registered = []
    try {
      const res = await apiGet('/api/chat/agent')
      registered = (res.agents || []).map((a) => ({
        id: a.id,
        name: a.name,
        desc: a.description || '',
        model: a.model || a.capabilities?.model || '',
        welcome: (a.examples && a.examples[0]) || '',
        sources: [],
        enabled: true,
        updatedAt: '—',
        builtin: true
      }))
    } catch {
      // 真实注册源不可用时抛出让页面呈现错误态（而非误显示"空"）
      throw new Error('智能体服务不可用（后端未启动？）')
    }
    const local = loadLocal()
    const merged = [...registered]
    for (const l of local) {
      const i = merged.findIndex((m) => m.id === l.id)
      if (i >= 0) merged[i] = { ...merged[i], ...l }
      else merged.unshift(l)
    }
    return merged
  },

  // 本地暂存（后端实现后替换为真实 POST/PUT）
  async upsertAgent(agent) {
    await delay()
    const list = loadLocal()
    const i = list.findIndex((a) => a.id === agent.id)
    if (i >= 0) list[i] = { ...list[i], ...agent }
    else list.unshift({ ...agent, builtin: false })
    saveLocal(list)
    return agent
  },

  async removeAgent(id) {
    await delay()
    saveLocal(loadLocal().filter((a) => a.id !== id))
  }
}

export default agentsApi
