# 对话 API（/api/chat/*）

对话链路：**线程(thread)是消息容器** → `POST /agent/{agent_name}` SSE 流式对话
→ `GET /agent/{agent_id}/history` 拉历史。sessions 是线程的别名接口层
（同一实体，`thread_id` 通用），保留供旧前端页面使用。

> agent_name 注意：注册的 agent id 为 `MasterAgent`（不存在 `shopping_agent`）。

## 1. 发起对话（SSE）⭐

`POST /api/chat/agent/{agent_name}` — 认证：必选；限流：20 次/分/用户

Body（application/json）：

```json
{
  "query": "推荐 200 元以内的无线耳机",
  "config": { "thread_id": "可选-续接对话时传上次的 id", "model": "deepseek/deepseek-chat" },
  "meta": {},
  "image_content": null
}
```

`config.model`（可选）：本次对话使用的模型，格式 `provider/model`（可选值见
`GET /api/chat/models`）。由 `DynamicModelMiddleware` 在运行时解析，加载失败
自动回退服务端默认模型（记 warning，不报错）；未传则用默认模型。

响应：`text/event-stream`（HTTP 200 保持连接，直到 `done` 或 `error` 事件）。

```bash
curl -N -X POST http://localhost:5050/api/chat/agent/MasterAgent \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"query":"推荐200元内耳机","config":{}}'
```

### SSE 事件协议

协议定义唯一事实来源：`src/services/sse_protocol.py`（EventType 枚举）。
每条 SSE 消息格式：

```
event: <event_type>
data: {json 事件负载}

```

事件类型清单：

| event | 方向 | 负载要点 | 前端用途 |
| --- | --- | --- | --- |
| `message_chunk` | 生成中 | 增量文本（打字机） | 追加正文 |
| `message_chunk_done` | 结束 | — | 收尾 |
| `thinking` | 生成中 | 推理/思考内容 | 思考面板 |
| `plan` / `plan_update` | 生成中 | 计划与更新 | 计划展示 |
| `step_start` / `step_complete` | 生成中 | 步骤 | 步骤条 |
| `tool_start` / `tool_complete` | 生成中 | 工具名/入参/结果 | 工具调用卡片 |
| `agent_state` | 生成中 | agent 状态快照 | 状态区 |
| `title` | 首轮生成 | `{"type":"title","thread_id":"...","title":"..."}` | 更新会话标题 |
| `done` | 结束 | `{"type":"done","statistics":{total_tool_calls,total_duration_ms,failed_calls,time_cost}}` | 结束对话轮 |
| `error` | 异常 | `{"type":"error","detail":...}` | 错误提示 |

负载字段以流中实际 JSON 为准（OpenAPI 不含 SSE 事件，**改事件先改
`sse_protocol.py` 枚举与前端 `AgentChatComponent.vue` 的 switch**）。

### 调用方处理要点

- `message_chunk`/`thinking` 等需前端逐块累加渲染；
- 收到 `done` 或 `error` 才关闭连接；主动停止调 stop 接口；
- 用户消息与最终 AI 消息都会持久化（PG→Redis 影子），历史接口可拉回；
- 中断/异常时服务端尽力保存已生成内容，客户端断连不产生空消息。

## 2. 线程管理

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/chat/thread` | 新建线程 `{agent_id, title?}` → 201/200 `ThreadResponse` |
| GET | `/api/chat/threads?agent_id=&limit=100&offset=0` | 我的线程列表 |
| PUT | `/api/chat/thread/{thread_id}` | 更新线程（标题/置顶等） |
| DELETE | `/api/chat/thread/{thread_id}` | 删除线程（PG + Redis 双删） |

`ThreadResponse`：`{id, user_id, agent_id, title, is_pinned, created_at,
updated_at}`。

## 3. 会话别名接口（sessions，兼容层）

POST `/api/chat/sessions`（同 thread 创建）· GET `/api/chat/sessions` ·
DELETE `/api/chat/sessions/{thread_id}` ·
PATCH `/api/chat/sessions/{thread_id}/title`（body `{title: "..."}`）。
推荐新代码统一用 thread 接口。

## 4. 消息操作

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/chat/agent/{agent_id}/history?thread_id=` | **历史消息**：PG 优先，空/异常降级 Redis/内存；返回 `{"history":[{role,content,type,timestamp},...]}` |
| GET | `/api/chat/agent/{agent_id}/state?thread_id=` | Agent 图状态视图 |
| POST | `/api/chat/history/{thread_id}/regenerate` | 重新生成上一条 AI 回复 |
| DELETE | `/api/chat/history/{thread_id}/messages/{msg_id}` | 删除单条消息 |

## 5. 记忆接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/chat/memory` | 用户全局记忆 → `{user_id, global_memory, has_memory}` |
| PUT | `/api/chat/memory` | body `{content}` 覆盖写全局记忆（400 若为空） |
| GET | `/api/chat/memory/session/{thread_id}` | 会话级上下文记忆 |
| PUT | `/api/chat/memory/session/{thread_id}` | 更新会话上下文 |

## 6. Agent 元信息

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/chat/default_agent` | → `{default_agent_id}`（config 无则取第一个） |
| GET | `/api/chat/agent` | → `{agents:[{id, name, ...}]}` |
| GET | `/api/chat/agent/{agent_id}` | 单 agent 详情（能力/模型信息） |
| GET | `/api/chat/models` | 可选模型目录（见下） |
| POST | `/api/chat/agent/{agent_id}/stop` | 中断当前正在生成的 SSE 会话 |

`GET /api/chat/models` — 认证：无需密钥信息，返回静态目录
`{"providers": [{"id": "deepseek", "name": "DeepSeek", "default":
"deepseek/deepseek-chat", "models": ["deepseek/deepseek-chat", ...]}]}`。
每个模型 spec 可直接作为对话请求 `config.model` 的值；目录来源
`src/config/static/models.py` 的 `DEFAULT_CHAT_MODEL_PROVIDERS`。

## 7. 运行状态

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/chat/rate-limit-status` | → `{user_id, max_requests_per_minute:20, window_seconds:60, remaining}` |
| GET | `/api/chat/system/statistics` | → `{sse_sessions, memory_store, timestamp}` 运行统计 |

## 8. 首页推荐（可选鉴权）

`GET /api/chat/home/suggestions` — 认证：可选（`get_current_user`）

- 登录用户 → 个性化推荐（结合其偏好/记忆）
- 未登录 → 通用推荐
- 语义契约同时参考前端 `web-v2/src/apis/home_api.js` 与
  `src/services/home/suggestion_service.py`（注意：该文件当前未入库，是
  **已知待提交代码**，见 AGENTS.md）。

返回：`{"suggestions": [...]}` 或 `{"data": ...}` 结构以实际响应为准
（前端 home_api.js 为消费方契约）。
