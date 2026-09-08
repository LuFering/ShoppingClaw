# 项目概览

## 它解决什么问题

ShoppingClaw 是一个**以决策为中心的电商智能体系统**：用户用一句自然语言
描述消费意图（"对比 A 与 B 谁更值得买"、"200 元内有什么好耳机"、
"盯一下这款的价格，降价提醒我"），系统完成 **意图 → 信息收集 → 分析 →
结构化决策/行动** 的闭环，而不是简单的一问一答。

## 核心能力

| 能力 | 说明 | 主要实现 |
| --- | --- | --- |
| 多轮对话 | SSE 流式、打字机效果、可中断 | `server/routers/chat_rounter.py` + `src/services/chat_stream_service.py` |
| 多 Agent 决策 | Master Agent 拆解任务，子 Agent 协作执行 | `src/agents/` |
| 商品检索与追踪 | 京东 SDK 工具链（搜索/详情/价格） | `src/jd/` + `src/agents/master_agent` 工具集 |
| 导购转链 | 淘宝联盟/多多进宝 MCP | `src/services/mcp_service.py` |
| 定时监控 | 价格/库存/券/排名/店铺任务，cron 或 interval | `src/services/task_executors/` + `scheduler_service.py` |
| 持久化对话 | 线程/会话与消息历史（PG 主 + Redis 影子） | `conversation_repository.py` + `redis_store.py` |
| 用户记忆 | 长期偏好记忆 + 会话上下文 | `src/services/user_memory.py`、`memory_store.py` |
| 意图识别 | 本地意图分类（含 gap 检测） | `src/services/intent_service.py`、`gap/` |
| 知识库 | Chroma 向量库 RAG（商品 FAQ） | `src/knowledge/` |
| 辅助决策 | 商品对比 / 推荐 / 首页引导推荐语 | `comparison_service.py`、`recommend_service.py`、`home/suggestion_service.py` |
| 治理 | JWT、管理员、审计日志、限流 | `server/utils/auth_middleware.py`、`server/middleware/` |

## 关键术语

| 术语 | 含义 |
| --- | --- |
| Agent / 智能体 | 由 LangGraph 图 + 中间件链组成的决策单元 |
| Master Agent | 主智能体，唯一决策大脑（agent id 为 `MasterAgent`） |
| SubAgent | 子智能体（Researcher/Critic/Analyst/Memory 等），封装为 Tool 由主 Agent 调度 |
| Thread / 线程 | 一次多轮对话的容器（`conversations` 表一行，JSONB 存全部消息） |
| Session / 会话 | Thread 的别名层（部分前端概念沿用 sessions 命名，同一实体） |
| SSE 事件流 | `POST /api/chat/agent/{agent}` 返回的 `text/event-stream` |
| Checkpointer | LangGraph 线程状态持久化（backend=postgres） |
| Bridge / 桥接层 | `MessageStoreBridge`：统一存储访问，Redis 失败自动降级 memory |
| MessageStore | 轻量内存消息存储（`memory_store.py`，重启丢失，仅兜底） |

## 系统不是一个……

- **不是 RAG 问答机器人**：知识库是决策辅助之一，核心是工具链 + 决策闭环。
- **不是单体 CRUD**：新增功能优先考虑"Agent 能否用工具完成"，而不是加一堆
  管理接口（但任务/模型配置等管理面仍走传统 CRUD）。
- **前端不依赖消息时间戳渲染**：历史消息按数组顺序展示；时间戳用于溯源与
  排序，改动消息存储格式时注意保持兼容。

## 参考与沿革

项目脱胎于 DeepAgents/ScienceClaw 风格的 Agent 工程实践；仓库早期文档与日志
中的 "Yuxi" 命名是历史遗留，现已统一为 ShoppingClaw。
