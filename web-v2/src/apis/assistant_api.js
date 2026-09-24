/** 主动助理 API —— 已接真实后端（2026-09-23 P1/P2；2026-09-24 补 watching）

契约（后端已实现，见 server/routers/assistant_router.py）：
  GET  /api/assistant/overview → {success, data:{messages, brief, feed, todos, watching}}
  POST /api/assistant/messages → {success, data:{reply, created}}

历史：本文件原先是「契约先行 + 内置演示数据」形态 —— 两个端点都是 404，
      所有卡片数据来自本地硬编码种子，卡片动作只说一句话不写任何东西。
      P1 打通事件层（/api/events/recent）、P2 打通聚合层（/api/assistant/overview），
      种子函数与关键词兜底回复已全部删除。

降级策略：接口失败时**不补演示数据**（与 decisions_api.js 的教训同源 ——
      把演示数据伪装成真实数据比显示空白更有害），只置 demoStatus 提示。
*/
import { apiGet, apiPost } from './base'
import { demoStatus } from './demoStatus'

const EMPTY = {
  messages: [],
  brief: { stats: { hits: 0, drafts: 0, watching: 0 }, points: [] },
  feed: [],
  todos: [],
  watching: []
}

// 结构守卫：后端任何一个子块聚合失败都会返回空的那块，
// 这里统一补齐成空壳，避免视图层到处写 `x && x.length`
const normalize = (d) => {
  const src = d && typeof d === 'object' ? d : {}
  const brief = src.brief && typeof src.brief === 'object' ? src.brief : {}
  const stats = brief.stats && typeof brief.stats === 'object' ? brief.stats : {}
  return {
    messages: Array.isArray(src.messages) ? src.messages : [],
    brief: {
      stats: {
        hits: Number(stats.hits) || 0,
        drafts: Number(stats.drafts) || 0,
        watching: Number(stats.watching) || 0
      },
      points: Array.isArray(brief.points) ? brief.points : []
    },
    feed: Array.isArray(src.feed) ? src.feed : [],
    todos: Array.isArray(src.todos) ? src.todos : [],
    // 在盯的监控任务（右栏「监控任务」tab，U2）
    watching: Array.isArray(src.watching) ? src.watching : []
  }
}

export const assistantApi = {
  async getInitialState() {
    try {
      const res = await apiGet('/api/assistant/overview', {}, true)
      if (!res?.data) throw new Error('bad shape')
      demoStatus.assistant = false
      return normalize(res.data)
    } catch {
      // 接口不可用：如实返回空 + 标记，不补演示数据
      demoStatus.assistant = true
      return EMPTY
    }
  },

  // 仅取简报（右栏 tab 切换时用；整体已由 overview 覆盖，这里走同一端点）
  async getBrief() {
    try {
      const res = await apiGet('/api/assistant/overview', {}, true)
      const d = normalize(res?.data)
      demoStatus.assistant = false
      return d.brief
    } catch {
      demoStatus.assistant = true
      return EMPTY.brief
    }
  },

  // 对话发送（POST /api/assistant/messages）
  // 监控类意图后端会真的建任务，reply 是确认文案；其余走 MasterAgent。
  // 失败时如实告知，不编造回复 —— 说「已经帮你挂上监控了」而实际没建，
  // 正是方案 §0 第 3 点批评的那种撒谎。
  async sendMessage(text) {
    try {
      const res = await apiPost('/api/assistant/messages', { text }, {}, true)
      const reply = res?.data?.reply
      if (typeof reply === 'string' && reply.trim()) {
        return { text: reply, created: !!res.data.created }
      }
      throw new Error('bad shape')
    } catch (e) {
      return { text: `助理暂时没能处理这条消息：${e?.message || '请求失败'}`, created: false }
    }
  }
}

export default assistantApi
