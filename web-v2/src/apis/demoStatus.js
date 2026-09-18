import { reactive } from 'vue'

// 各数据域是否处于「演示数据」降级态：
// API 层真实请求失败 → 置 true（页面显示标记）；真实数据可用 → 置 false。
// 契约清单见 web-v2/docs/api-contracts.md
export const demoStatus = reactive({
  home: false,      // 主页欢迎区（文本云 / 事件卡）
  mcp: false,       // MCP 连接
  decisions: false, // 购物档案
  assistant: false  // 主动助理
})
