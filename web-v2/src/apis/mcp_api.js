// MCP 数据源 API（契约先行：真实请求 → 失败降级 localStorage 演示数据）
// 契约（后端待实现，详见 docs/api-contracts.md）：
//   GET    /api/mcp/servers                → {success, data:[McpServer]}
//   POST   /api/mcp/servers                （创建，后端分配 id）
//   PUT    /api/mcp/servers/{id}           （更新）
//   DELETE /api/mcp/servers/{id}
//   POST   /api/mcp/servers/{id}/test      → {success, data:{ok:boolean, message}}
//   GET    /api/mcp/market                 → {success, data:[{name,cap,tools,installed}]}
//   PUT    /api/mcp/market/{name}/install  body {installed:boolean}
import { apiGet, apiPost, apiPut, apiDelete } from './base'
import { demoStatus } from './demoStatus'
const SERVERS_KEY = 'sc_mcp_servers_v1'
const MARKET_KEY = 'sc_mcp_market_v1'

// ⚠️ 2026-09-22：种子数据已清空。
// 这里原本是编造的服务器列表（含 mcp.jd.example.com / mcp.tb.example.com
// 这类占位域名）和一个不存在的"市场"。后端 /api/mcp/* 现已实现，
// 降级分支改为返回空列表 —— 后端故障时显示"暂无数据"，
// 好过让用户以为这些服务器真的存在。
const seedServers = []
const seedMarket = []

const load = (key, seed) => {
  try {
    const raw = localStorage.getItem(key)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return JSON.parse(JSON.stringify(seed))
}
const save = (key, val) => localStorage.setItem(key, JSON.stringify(val))
const delay = (ms = 200) => new Promise((r) => setTimeout(r, ms))

// 真实请求失败 → 降级 local，并按需标记演示态
const withFallback = async (request, fallback, markFailed = true) => {
  try {
    const data = await request()
    if (markFailed) demoStatus.mcp = false
    return data
  } catch {
    if (markFailed) demoStatus.mcp = true
    return fallback()
  }
}

export const mcpApi = {
  async listServers() {
    return withFallback(
      async () => {
        const res = await apiGet('/api/mcp/servers', {}, false)
        if (!res?.data) throw new Error('bad shape')
        return res.data
      },
      async () => {
        await delay(120)
        return load(SERVERS_KEY, seedServers)
      }
    )
  },

  // 有 id 走 PUT（更新），无 id 走 POST（创建，后端分配 id）；本地 id 在真后端 404 后自动落 local
  async upsertServer(server) {
    const request = server.id
      ? apiPut(`/api/mcp/servers/${server.id}`, server, {}, false)
      : apiPost('/api/mcp/servers', server, {}, false)
    return withFallback(
      async () => {
        const res = await request
        return res?.data || server
      },
      async () => {
        await delay()
        const list = load(SERVERS_KEY, seedServers)
        const i = list.findIndex((s) => s.id === server.id)
        if (i >= 0) list[i] = { ...list[i], ...server }
        else list.unshift(server)
        save(SERVERS_KEY, list)
        return server
      },
      false // 写操作失败不置演示标记（读操作已标记）
    )
  },

  async removeServer(id) {
    return withFallback(
      async () => {
        await apiDelete(`/api/mcp/servers/${id}`, {}, false)
        return true
      },
      async () => {
        save(SERVERS_KEY, load(SERVERS_KEY, seedServers).filter((s) => s.id !== id))
        return true
      },
      false
    )
  },

  async testConnection(server) {
    return withFallback(
      async () => {
        const res = await apiPost(`/api/mcp/servers/${server.id}/test`, {}, {}, false)
        return !!res?.data?.ok
      },
      async () => {
        await delay(800)
        return Math.random() > 0.2
      },
      false
    )
  },

  async listMarket() {
    return withFallback(
      async () => {
        const res = await apiGet('/api/mcp/market', {}, false)
        if (!res?.data) throw new Error('bad shape')
        return res.data
      },
      async () => {
        await delay(120)
        return load(MARKET_KEY, seedMarket)
      },
      false // 市场跟随 listServers 的演示态，避免双重标记
    )
  },

  async markMarketInstalled(name, installed) {
    return withFallback(
      async () => {
        await apiPut(`/api/mcp/market/${encodeURIComponent(name)}/install`, { installed }, {}, false)
        return true
      },
      async () => {
        const list = load(MARKET_KEY, seedMarket)
        const m = list.find((x) => x.name === name)
        if (m) m.installed = installed
        save(MARKET_KEY, list)
        return true
      },
      false
    )
  }
}

export default mcpApi
