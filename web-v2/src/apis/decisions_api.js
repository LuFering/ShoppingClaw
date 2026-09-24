// 购物档案 API（后端已实现：shopping_decisions 表 + /api/decisions）
// 契约：
//   GET   /api/decisions          → {success, data:[ShoppingRecord]}（全量，含各阶段）
//   PUT   /api/decisions/batch    body {records:[ShoppingRecord]}（整册同步：前端以整体保存模式工作）
//   DELETE /api/decisions         （重置为空）
// 注意：三个请求都必须带认证（requiresAuth=true）；未登录或接口异常时降级 localStorage 演示数据。
import { apiGet, apiPut, apiDelete } from './base'
import { demoStatus } from './demoStatus'
// 演示种子已停用（2026-09-22）：档案必须是真实数据，不再用它填充。
// 文件保留在 ./decisions_seed，将来若要做「新用户引导态」可显式启用。
// import { seedRecords } from './decisions_seed'

// ── 提醒归一化 ──────────────────────────────────────────────
// 历史上有两种形状（实测 DB 里并存）：
//   · 老：前端种子写的裸字符串   "下单前确认接口供电"
//   · 新：购后助手 set_reminder 写的对象  {id, text, at, done}
// 两个消费方（档案页 / 对话里的 ReminderListTool）都按对象读，
// 裸字符串会渲染成空行。在**读取边界**统一升级，之后所有下游都只需处理对象。
// 后端 set_reminder 已同步改为写 `at`（原来是 `due`，前端读不到）。
export const normReminders = (list) => {
  if (!Array.isArray(list)) return []
  return list
    .map((r) => {
      if (typeof r === 'string') return { id: '', text: r.trim(), at: '', done: false }
      if (r && typeof r === 'object') {
        return {
          id: r.id || '',
          text: String(r.text || '').trim(),
          at: r.at || r.due || '',   // 兼容老的 due
          done: !!r.done
        }
      }
      return null
    })
    .filter((r) => r && r.text)
}

// 整条记录过一遍：reminders 之外原样透传
const normRecord = (rec) =>
  rec && typeof rec === 'object' ? { ...rec, reminders: normReminders(rec.reminders) } : rec

const KEY = 'sc_decisions_v1'
const delay = (ms = 120) => new Promise((r) => setTimeout(r, ms))

const loadLocal = () => {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) return JSON.parse(raw).map(normRecord)
  } catch { /* ignore */ }
  // 降级路径也**不**补种子：接口异常时宁可显示空白 + 错误提示，
  // 也不要把演示数据伪装成用户的真实档案。
  return []
}

export const decisionsApi = {
  async load() {
    try {
      const res = await apiGet('/api/decisions', {}, true)
      if (!res?.data) throw new Error('bad shape')
      demoStatus.decisions = false

      // 后端返回空 = 该用户确实还没有档案，如实返回空（空白态）。
      // ⚠️ 2026-09-22：这里**不要**补种子数据 —— 曾经把演示种子写进后端
      // 再当真实档案返回，用户看到的是看起来完全真实的假档案
      // （demoStatus 只在接口异常时才为 true，页面上没有任何提示）。
      // 真实档案应由对话中的购后助手归档产生，而不是凭空造一批。
      return Array.isArray(res.data) ? res.data.map(normRecord) : []
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
    // 重置 = 清空，不是「重置成演示数据」
    return []
  }
}

export default decisionsApi
