import { apiGet } from './base'

/**
 * 模型相关 API
 * 契约见 docs/api/chat.md（GET /api/chat/models）
 */
export const modelApi = {
  // 获取服务端支持的模型目录（按提供商分组）
  // → { providers: [{ id, name, default, models: ["provider/model", ...] }] }
  getChatModels: () => apiGet('/api/chat/models'),
}
