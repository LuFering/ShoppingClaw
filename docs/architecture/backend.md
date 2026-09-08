# 后端架构

## 1. 应用入口与生命周期

`server/main.py` 创建 FastAPI 应用并挂载：CORS → RequestID → Audit 中间件。

启动 `lifespan` 按阶段进行（**快速就绪优先，重活后台化**）：

| 阶段 | 内容 | 失败策略 |
| --- | --- | --- |
| Phase 1 | PostgreSQL 初始化 + 建业务表（`pg_manager.create_business_tables`） | warning，不阻塞启动 |
| Phase 1.3 | **Redis 连接预热**（serve loop 内建池，杜绝跨 loop） | warning，缓存降级 |
| Phase 1.5 | 知识库初始化（LlamaIndex + Chroma + Embedding） | warning |
| Phase 2 | 后台加载 ML 模型（意图识别等，`asyncio.to_thread`） | 异步，不阻塞就绪 |
| Phase 3 | 定时任务调度器启动 | warning |
| Phase 4 | SSE 会话清理任务（每小时清理不活跃会话） | — |
| shutdown | 反向：调度器停 → 清理任务取消 → Redis 断连 | — |

> 约定：新增重活一律后台化/延迟化，不得拖慢 `/api/system/health` 就绪。

## 2. 分层与模块地图

```
server/                          # FastAPI 应用
├── main.py                      # 入口 + lifespan + 系统端点
├── routers/                     # 路由层
│   ├── __init__.py              # 聚合 chat（→ /api/chat/*）
│   ├── auth_router.py           # /api/auth/*
│   ├── chat_rounter.py          # /api/chat/*（对话/线程/记忆/历史/统计）
│   ├── models_router.py         # /api/models/*（模型配置）
│   └── task_router.py           # /api/tasks/*（定时任务）
├── middleware/                  # audit（审计日志）等
└── utils/                       # auth_middleware（get_required_user/get_current_user/get_admin_user）、速率限制等

src/                             # 业务核心（容器 /app/src）
├── agents/
│   ├── master_agent/            # context.py(MasterContext) · graph.py(主图) · factory.py
│   ├── subagents/               # factory.py + subagents.yaml（子 Agent 声明式配置）
│   └── common/                  # 中间件链 / backends(沙盒) / toolkits / model 数据类
├── services/                    # SSE 协议与会话 · chat_stream_service(对话编排与持久化)
│                                 # redis_store(桥接) · redis_cache · memory_store · cache_decorator
│                                 # conversation_service · history_* · user_memory · intent/gap
│                                 # mcp_service · tool_registry · scheduler_service
│                                 # task_executors/(price/stock/coupon/rank/shop)
│                                 # comparison · recommend · home/suggestion
├── repositories/                # conversation_repository / operation_log_repository …（单表读写）
├── storage/postgres/            # manager.py(会话) · models_business.py(全部表定义)
├── knowledge/                   # Chroma RAG（文档加载/索引/检索）
├── jd/                          # 京东 SDK 封装（搜索/详情/价格等 REST）
├── config/ · models/ · utils/ · plugins/
```

依赖方向：`routers → services → (repositories/storage)`，Agent 图是
`services` 的下游消费者；`routers` 不得直接碰 ORM 细节。

## 3. Agent 系统

### 结构

- **Master Agent**（id=`MasterAgent`）：`graph.py` 构建决策状态机，`factory.py`
  装配 13 层中间件链与工具集；`context.py` 维护全局 `MasterContext`/DecisionState。
- **SubAgents**：`subagents.yaml` 声明（Researcher/Critic/Analyst/Memory…），
  `factory.py` 按声明实例化；它们是**封装为 LangChain Tool 的黑盒执行器**，
  通过 `SubAgentMiddleware` 以 `tool_calls` 启动，返回结构化结果。
- 主图 13 层中间件（顺序即配置顺序）大致为：SSE 监控 → 内容守卫 → 工具调用
  修复 → 工具结果卸载 → 调用次数限制 → 任务拆解（TodoList）→ 文件系统 →
  **子 Agent 调度** → 思考过程提取 … 详见
  `src/agents/master_agent/factory.py` 的装配注释（以代码为准）。

### 决策循环（Information Gap 驱动）

```
识别意图 → 收集证据(搜索/工具) → 评估 decision_confidence
  ├─ confidence < 阈值 → 继续检索（最多 N 轮）
  ├─ information_gaps 含 human_input → interrupt 人机协同
  └─ 满足 → 输出最终决策报告
```

历史设计文档中的 LightGBM Gap Detector 属按需启用项，当前意图识别走
`src/services/intent_service.py` 本地模型，勿假设 LightGBM 已部署。

## 4. SSE 与对话服务

- 协议定义：`src/services/sse_protocol.py`（EventType 枚举，唯一事实来源）
- 会话管理：`sse_session_manager.py`（同线程并发互斥 + 心跳 + 清理）
- 对话编排与持久化：`chat_stream_service.py`（保存时序见
  [存储文档](storage.md#3-写入时序一次对话)）
- 详细事件清单与报文：见 [API/SSE 事件协议](../api/chat.md#sse-事件协议)

## 5. 定时任务

`src/services/scheduler_service.py`：基于 APScheduler 风格调度（cron /
interval），`task_executors/` 提供 price/stock/coupon/rank/shop 执行器；
任务元数据落 `task_records`，执行过程写 `task_execution_logs`，
价签快照落 `price_snapshots`。对外接口见 [tasks API](../api/tasks.md)。

## 6. 认证与审计

- JWT 签发：`POST /api/auth/token`（OAuth2 password form）；依赖注入
  `get_required_user`（强制）/ `get_current_user`（可选）/ `get_admin_user`。
- 审计：`AuditMiddleware` 将写操作落 `operation_logs`（含 user_id 外键，
  删用户前先删其审计日志）。
- 速率限制：`server/middleware/rate_limiter.py`（滑动窗口，Redis 键
  `chat:user:{uid}`，默认 20 次/分）。
