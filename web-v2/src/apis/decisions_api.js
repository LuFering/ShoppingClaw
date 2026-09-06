// 购物档案 API（契约先行：真实请求 → 失败降级 localStorage 演示数据）
// 契约（后端待实现，详见 docs/api-contracts.md）：
//   GET   /api/decisions          → {success, data:[ShoppingRecord]}（全量，含各阶段）
//   PUT   /api/decisions/batch    body {records:[ShoppingRecord]}（整册同步：前端以整体保存模式工作）
//   DELETE /api/decisions         （重置为空）
// ShoppingRecord 结构见 docs/api-contracts.md（phase 五状态机 + 分段字段）
import { apiGet, apiPut, apiDelete } from './base'
import { demoStatus } from './demoStatus'
import { seedRecords } from './decisions_seed'

const KEY = 'sc_decisions_v1'
const delay = (ms = 120) => new Promise((r) => setTimeout(r, ms))

const loadLocal = () => {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return JSON.parse(JSON.stringify(seedRecords()))
}

export const decisionsApi = {
  async load() {
    try {
      const res = await apiGet('/api/decisions', {}, false)
      if (!res?.data) throw new Error('bad shape')
      demoStatus.decisions = false
      return res.data
    } catch {
      demoStatus.decisions = true
      await delay(100)
      return loadLocal()
    }
  },

  // 整册同步（页面 deep-watch 全量保存；后端可整册 upsert 或差分，契约按整册最简）
  async saveAll(records) {
    try {
      await apiPut('/api/decisions/batch', { records }, {}, false)
      demoStatus.decisions = false
      return true
    } catch {
      localStorage.setItem(KEY, JSON.stringify(records))
      return false
    }
  },

  async reset() {
    try { await apiDelete('/api/decisions', {}, false) } catch { /* 后端未实现时静默 */ }
    localStorage.removeItem(KEY)
    return JSON.parse(JSON.stringify(seedRecords()))
  }
}

export default decisionsApi
