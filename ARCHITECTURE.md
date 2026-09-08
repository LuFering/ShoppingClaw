# ShoppingClaw 架构概览

> 高层导读。修改不熟悉的模块前，请先阅读本文件与
> [docs/architecture/](docs/architecture/) 下的详细文档。

## 系统边界

```
┌─────────────┐   HTTP /api   ┌──────────────────────┐
│   web-v2    │ ────────────▶ │  FastAPI (server/)    │
│ (Vue 3,5173)│ ◀───── SSE ── │  :5050, uvicorn 单进程│
└─────────────┘               └──────────┬───────────┘
                                         │
                        ┌────────────────┼─────────────────┐
                        ▼                ▼                 ▼
              ┌────────────────┐ ┌────────────┐  ┌───────────────────┐
              │   PostgreSQL    │ │   Redis    │  │  外部系统          │
              │ (主真相存储)     │ │ (影子/加速) │  │ LLM API · JD SDK · │
              │ 会话/用户/任务   │ │ 缓存/限流   │  │ MCP(sinataoke_cn)  │
              └────────────────┘ └────────────┘  └───────────────────┘
```

## 分层职责

| 层 | 位置 | 职责 | 关键规则 |
| --- | --- | --- | --- |
| 路由层 | `server/routers/` | 参数解析、鉴权、限流、HTTP/SSE 出参 | 不做业务逻辑 |
| 服务层 | `src/services/` | 对话编排、存储桥接、任务执行、SSE 封装 | 业务核心 |
| Agent 层 | `src/agents/` | Master/子 Agent 图、中间件链、工具 | 决策引擎 |
| 仓储层 | `src/repositories/` | 单表读写封装 | 直接面对 ORM |
| 模型层 | `src/storage/postgres/models_business.py` | SQLAlchemy 表定义 | 业务表唯一来源 |

## 核心设计决策

1. **PostgreSQL 是唯一主真相**。`conversations.messages` 以 JSONB 做事件溯源式
   追加（每条消息带 `role/content/type/timestamp`）；Redis 只是影子/加速层，
   Redis 故障只降级、绝不阻断业务（桥接层 `MessageStoreBridge` 全面容错）。
   → 详见 [docs/architecture/storage.md](docs/architecture/storage.md)

2. **Agent 是"决策执行引擎"，不是对话机器人**。Master Agent 通过 9+ 层中间件
   （SSE 监控 → 内容守卫 → 工具调用修复/卸载 → 次数限制 → 任务拆解 → 文件系统
   → 子 Agent 调度 → 思考过程提取）维护全局 `MasterContext`；子 Agent 是封装为
   Tool 的黑盒执行器，以 `tool_calls` 启动。
   → 详见 [docs/architecture/backend.md](docs/architecture/backend.md)

3. **消息流全链路可见**。`POST /api/chat/agent/{agent}` 返回 SSE 流，事件协议
   由 `src/services/sse_protocol.py` 统一定义；前端逐事件渲染打字机文本、
   thinking 面板、工具调用与交付卡片。
   → 详见 [docs/api/chat.md](docs/api/chat.md)

4. **导入纪律**。容器内以 `src.*`、`server.*` 绝对导入（禁止 `ShoppingClaw.*`
   前缀）；`src/agents` 中少量 `from agents/from deepagents` 顶层导入是**不可达
   死代码**（镜像不含顶层包），不得作为新代码范例。

## 运行时拓扑（docker compose）

| 服务 | 容器 | 端口 | 说明 |
| --- | --- | --- | --- |
| api | shoppingclaw-api | 127.0.0.1:5050（可配） | uvicorn 单事件循环 |
| postgres | shoppingclaw-postgres | 仅容器网络 | PG16，业务数据 + LangGraph checkpointer |
| redis | shoppingclaw-redis | 仅容器网络 | 影子存储/缓存/限流 |

开发模式：`server/`、`src/`、`.env`、`saves/`、`models/` bind mount 进容器，
代码改动即热重载（uvicorn 需重启或 `--reload` 由 compose command 决定）。

## 请求生命周期（一次对话）

1. 前端 `POST /api/chat/agent/{agent_name}`（Bearer JWT + 限流检查）
2. 路由层组装 `query/config(thread_id)/meta` → `stream_agent_chat`
3. 服务层：线程存在性 → 用户消息先落 PG（主）→ bridge 镜像 Redis
4. LangGraph 图执行：中间件发 SSE 事件（thinking/tool_call/…），文本块累积
5. 结束：标题生成、AI 消息落 PG → bridge 镜像 → `done` 事件与统计
6. 任一步骤失败均有兜底：异常/断连分支仍尽力保存已累积内容

## 相关文档

- [后端架构](docs/architecture/backend.md)（模块地图/Agent 系统/生命周期细节）
- [存储与持久化](docs/architecture/storage.md)（一致性模型/消息时序）
- [SSE 事件协议](docs/api/chat.md#sse-事件协议)
- [部署运维](docs/operations/deployment.md)
