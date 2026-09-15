// 购物档案 API（后端已实现：shopping_decisions 表 + /api/decisions）
// 契约：
//   GET   /api/decisions          → {success, data:[ShoppingRecord]}（全量，含各阶段）
//   PUT   /api/decisions/batch    body {records:[ShoppingRecord]}（整册同步：前端以整体保存模式工作）
//   DELETE /api/decisions         （重置为空）
// 注意：三个请求都必须带认证（requiresAuth=true）；未登录或接口异常时降级 localStorage 演示数据。
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
      const res = await apiGet('/api/decisions', {}, true)
      if (!res?.data) throw new Error('bad shape')
      demoStatus.decisions = false

      // 后端已接通但该用户还没有任何档案：把演示种子写进去作为初始档案
      // （与 reset() 语义一致：种子就是初始基线，避免首次进入是空白页）
      if (Array.isArray(res.data) && res.data.length === 0) {
        const seed = JSON.parse(JSON.stringify(seedRecords()))
        try {
          await apiPut('/api/decisions/batch', { records: seed }, {}, true)
        } catch { /* 写入失败不影响展示 */ }
        return seed
      }
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
      await apiPut('/api/decisions/batch', { records }, {}, true)
      demoStatus.decisions = false
      return true
    } catch {
      localStorage.setItem(KEY, JSON.stringify(records))
      return false
    }
  },

  async reset() {
    try { await apiDelete('/api/decisions', {}, true) } catch { /* 后端未实现时静默 */ }
    localStorage.removeItem(KEY)
    return JSON.parse(JSON.stringify(seedRecords()))
  }
}

export default decisionsApi
