// 主页欢迎区聚合 API（契约先行：真实请求 → 失败降级内置演示数据）
// 契约（后端待实现，详见 docs/api-contracts.md）：
//   GET /api/chat/home/suggestions → {success, data:{prompts: string[]}}
//   GET /api/events/recent?limit=8 → {success, data:[{id,type,main,sub,time}]}
import { apiGet } from './base'
import { demoStatus } from './demoStatus'

const FALLBACK_PROMPTS = [
  '帮我选 3000 元降噪耳机',
  '618 该买扫地机器人吗',
  '对比 iPhone 16 和华为 Pura 70',
  '推荐性价比笔记本电脑',
  '学生党平价手机推荐',
  '哪些家电值得囤货'
]

// 降级事件卡（type 语义见 statusTypeMeta）
const FALLBACK_EVENTS = [
  { id: 'st-1', type: 'coupon', main: '你领的 ¥100 券明天过期', sub: '戴森 V12 · 旗舰店', time: '明天' },
  { id: 'st-2', type: 'price', main: '添可芙万 3.0 降到 ¥2199', sub: '已到你的目标价', time: '2小时前' },
  { id: 'st-3', type: 'stock', main: '看中的通勤背包有货了', sub: 'Incase Icon · 灰色 M', time: '昨天' },
  { id: 'st-4', type: 'decide', main: '洗地机已比 3 款，等你拍板', sub: '预算 5000 · 给爸妈用', time: '昨天' }
]

const okArr = (r) => (r?.status === 'fulfilled' ? r.value : null)

export const homeApi = {
  // 一次取回欢迎区两块数据；任一真实端点失败则该块降级，demoStatus.home 置 true
  async getHomeData() {
    const [sug, ev] = await Promise.allSettled([
      apiGet('/api/chat/home/suggestions', {}, false),
      // 端点已于 2026-09-23 实现（/api/events/recent，见 events_router.py）。
      // 保留 silent：未登录时这里是 401，属预期降级，不该往控制台刷红。
      apiGet('/api/events/recent?limit=8', { silent: true }, true)
    ])
    const sugRes = okArr(sug)
    const evRes = okArr(ev)

    const prompts =
      Array.isArray(sugRes?.data?.prompts) && sugRes.data.prompts.length ? sugRes.data.prompts : FALLBACK_PROMPTS
    // 只有**请求失败**才降级为演示数据。请求成功但为空 = 确实还没有事件，
    // 必须如实显示空 —— 否则新用户会看到「戴森 V12 券明天过期」这类编造内容
    // （与 decisions_api.js 的教训同源：真实空档案不能补演示种子）。
    const events = Array.isArray(evRes?.data) ? evRes.data : FALLBACK_EVENTS

    const failed = []
    if (!sugRes) failed.push('suggestions')
    if (!evRes) failed.push('events')
    demoStatus.home = failed.length > 0

    return { prompts, events, demo: failed.length > 0, demoParts: failed }
  }
}

export default homeApi
