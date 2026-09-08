# 前端开发指南（web-v2）

Vue 3 + Vite + Ant Design Vue 4 + ECharts/G6 的购物助手前端。

## 1. 环境与命令

```bash
cd web-v2
npm ci              # 安装依赖（锁文件 package-lock.json；勿混用 pnpm）
npm run dev         # 开发：http://localhost:5173（0.0.0.0 可局域网访问）
npm run build       # 生产构建 → dist/
npm run lint        # eslint 修复
npm run format      # prettier 格式化
```

- `/api` 请求在开发期由 Vite 代理到 `VITE_API_URL || http://localhost:5050`
  （配置见 `vite.config.js`）；后端地址不同时：
  `VITE_API_URL=http://<ip>:5050 npm run dev`
- 生产部署：构建产物上传 `/www/wwwroot/shoppingclaw`（Nginx 静态服务，
  `/api` 反代到 `127.0.0.1:5050`）。

## 2. 目录结构

```
web-v2/src/
├── main.js · App.vue        # 入口与根组件
├── apis/                    # API 封装层（base.js 统一 fetch+鉴权+错误）
│   ├── base.js              # apiGet/apiPost/apiDelete/apiPut；自动加 Authorization
│   ├── agent_api.js         # 对话 SSE（fetch 流式读 body）
│   ├── auth_api.js / user.js 等
│   ├── home_api.js          # 首页（含推荐语 suggestions）
│   ├── task_api.js · mcp_api.js · assistant_api.js …
├── stores/                  # Pinia：user（token/角色）、thread、settings…
├── router/                  # 路由与守卫（登录拦截）
├── views/                   # 页面：登录/注册/首页/对话/任务/模型/知识库/设置…
├── components/              # 组件（AgentChatComponent.vue 等核心对话组件）
├── composables/ utils/ assets/ public/
```

## 3. 数据流约定

- 所有请求走 `apis/` 封装，页面/组件不直接 fetch（SSE 除外，
  见 `agent_api.js` 的流式模式）。
- 认证态统一在 `stores/user.js`：`token` 存 localStorage
  （键 `user_token`），`getAuthHeaders()` 产出 `Authorization: Bearer`；
  `base.js` 自动附加，**业务代码不要手工拼 header**。
- 响应错误统一 `message.error` 展示；遇 `401` 应跳登录页并清理本地态。
- 登录/注册表单提交 **FormData**（`/api/auth/token` 是 OAuth2 form），
  其余接口 JSON。

## 4. SSE 消费（对话流）

唯一消费点在 `AgentChatComponent.vue`（`handleSSEEvent` 的 switch）：

- 用 `fetch` + `ReadableStream` 逐行解析 `event:` / `data:` 帧；
- 事件名与负载结构 = 后端 `src/services/sse_protocol.py` 枚举（文档：
  [对话 API · SSE 事件协议](../api/chat.md#sse-事件协议)）；
- **新增事件类型必须双端同步**：后端枚举 + 本组件 switch；
- 渲染时序：thinking 面板 / 工具卡片 / 正文打字机按事件类型分流。

## 5. 规范

- 组件 `<script setup>` 组合式 API；样式 scoped；antd 组件按需引入。
- 目录职责：**页面逻辑进 views，可复用 UI 进 components，状态进 stores，
  请求进 apis**——避免组件里堆业务请求。
- 新增页面路由先看 `router/` 的登录守卫与布局。
- 提交前 `npm run lint` 与格式化；UI 改动提交附截图。

## 6. 常见问题

| 现象 | 原因/处置 |
| --- | --- |
| 登录报 `Unexpected token 'I'...` | 响应非 JSON：后端没起/502（Vite 代理目标未启动）。先 `curl http://localhost:5050/api/system/health` |
| 明明登录却弹"认证失败" | token 过期或后端可选鉴权依赖用错（见故障手册），重新登录 |
| `[object Object]` 弹窗 | 前端把后端错误对象当文本展示，检查错误提取用 `err.detail ?? err.message` |
| 改了代理不生效 | 重启 `npm run dev`；dev 容器内热更新需 usePolling（已开启） |
