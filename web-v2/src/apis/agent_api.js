import { apiGet, apiPost, apiDelete, apiPut } from './base'
import { useUserStore } from '@/stores/user'

export const agentApi = {
  sendAgentMessage: (agentId, data, options = {}) => {
    const { signal, headers: extraHeaders, ...restOptions } = options || {}
    return fetch(`/api/chat/agent/${agentId}`, {
      method: 'POST',
      body: JSON.stringify(data),
      signal,
      headers: {
        'Content-Type': 'application/json',
        ...useUserStore().getAuthHeaders(),
        ...(extraHeaders || {})
      },
      ...restOptions
    })
  },

  getDefaultAgent: () => apiGet('/api/chat/default_agent'),

  getAgents: () => apiGet('/api/chat/agent'),

  getAgentDetail: (agentId) => apiGet(`/api/chat/agent/${agentId}`),

  getAgentHistory: (agentId, threadId) =>
    apiGet(`/api/chat/agent/${agentId}/history?thread_id=${threadId}`),

  getAgentState: (agentId, threadId) =>
    apiGet(`/api/chat/agent/${agentId}/state?thread_id=${threadId}`),
}

export const threadApi = {
  getThreads: (agentId = null, limit = 100, offset = 0) => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    if (agentId) params.set('agent_id', agentId)
    return apiGet(`/api/chat/threads?${params.toString()}`)
  },

  createThread: (agentId, title, metadata) =>
    apiPost('/api/chat/thread', {
      agent_id: agentId,
      title: title || '新的对话',
      metadata: metadata || {}
    }),

  updateThread: (threadId, title, is_pinned) =>
    apiPut(`/api/chat/thread/${threadId}`, { title, is_pinned }),

  deleteThread: (threadId) => apiDelete(`/api/chat/thread/${threadId}`),
}

// 注：原 personalApi（/api/personal/*）与 categoryApi（/api/category/*）已移除——
// 后端无对应端点、前端亦无渲染消费（主页欢迎区改走 apis/home_api.js 的契约端点）。
// 若将来需要"最近浏览/收藏/热榜"，先在 docs/api-contracts.md 定契约再实现。
