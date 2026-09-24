# 主 Agent 改造 + 前端接入方案（扫描版 · 待评审）

> 范围：改造 `MasterAgent`，并让前端 API / 工作台接入主 agent。
> 状态：本轮**只扫描、只出方案**，未改动任何代码（按"先不着急"原则）。
> 事实来源：服务器 `~/ShoppingClaw`（bind-mount 到容器 `/app/src`），已重新 scp 核对。
> 阅读对象：后端 + 前端 + 你（决策阻塞项见第 5 节）。

---

> ⚠️ **范围更正（2026-09-16）**：本文件原 §4「前端接入方案」以**送礼 / 采购三栏工作台（`/proxy`、`/planning`）**为接入目标，但那是错误的——它们是**独立 agent、需额外配置，不在本次范围**。用户明确指定的接入目标是 **`/agent` 路由**（通用聊天页，`AgentView` → `AgentChatComponent`）。经重新扫描确认：**`/agent` 已经是 `MasterAgent` 的第一类消费端，前后端 SSE / REST 契约已对齐**，无需重写接线。聚焦 `/agent` 的方案见同目录 **`agent_route_plan.md`**。采购 / 代购工作台单列，不在本计划。

## 0. 一句话结论

后端 `MasterAgent` 是**唯一注册、可工作的 agent**，通过一套完整的 SSE 桥（`chat_rounter → chat_stream_service → EventType 协议 → session_manager 回放`）对外服务；但**前端三栏工作台（送礼 / 采购）目前完全吃 mock 流，没有任何 view 真正调用这个 agent**。要让"前端接入主 agent"，最小动作是**前端加一层 SSE 消费 + 三栏适配器**先把 GiftWorkbench 接到 `MasterAgent` 通用流；目标态是**注册专属 `GiftAgent` / `PurchaseAgent` 并让后端 emit 对齐三栏的领域事件**。两条路线都不破坏现有契约。

---

## 1. 当前链路全貌（已核对）

```
┌─ 前端 ───────────────────────────────────────────────────────────────┐
│ GiftWorkbenchView / PurchaseWorkbenchView                              │
│   └─ useGiftWorkbench / useXxx  composable                             │
│        └─ data/giftWorkbenchStream.js (createWorkbenchAgent · MOCK)    │
│        └─ data/giftAgentStream.js (createGiftAgent · MOCK)            │
│        └─ data/purchaseDemo.js (EXEC_STREAM · MOCK)                   │
│   ★ 没有任何 view 调用 agent_api.sendAgentMessage（仅 AgentManageView  │
│     用了 GET /api/chat/agent 列表接口）                                │
└───────────────────────────────────────────────────────────────────────┘
        │ （目标：替换为下面这条真实链路）
        ▼
┌─ 后端 ───────────────────────────────────────────────────────────────┐
│ POST /api/chat/agent/{agentId}                                        │
│   server/routers/chat_rounter.py :: chat_agent                        │
│     └─ services/chat_stream_service.py :: stream_agent_chat  (SSE 桥) │
│          ├─ src.agents.agent_manager.get_agent(name)   ← 只注册 MasterAgent │
│          ├─ agent.stream_messages(messages, input_context)            │
│          │    └─ master_agent/graph.py :: MasterAgent.get_graph()      │
│          │         └─ agent_demo.create_master_agent                  │
│          │              └─ master_agent/factory.py :: create_agent    │
│          │                 （68KB 6 层汇编器：model↔tools 循环 + 中间件）│
│          ├─ agent.sse_middleware.drain_events()  → SSEMonitoringMiddleware │
│          └─ sse_session_manager.emit_nowait ─▶ GET /api/chat/sessions/│
│                                                   {tid}/events  (回放)│
└──────────────────────────────────────────────────────────────────────┘
```

**已核实的文件与职责**

| 文件 | 角色 | 关键事实 |
|---|---|---|
| `src/agents/__init__.py` | agent 注册表 | `register_agent(MasterAgent)` **唯一**；`get_agent` 用**类名**作 key；`init_all_agents()` 导入即实例化 |
| `master_agent/graph.py` | MasterAgent 定义 | `get_graph()` 组装 13 层中间件；`self.sse_middleware` 手动挂 runtime lifecycle sink（hack） |
| `master_agent/agent_demo.py` | 汇编入口 | `create_master_agent` 仅拼接 `BASE_PROMPT.md` 后委托 `factory.create_agent`；`get_main_agent()` 供 LangGraph Studio |
| `master_agent/factory.py` | **真汇编器** | 68KB，`create_agent` + 大量 model_node/tool_node/chain 代码，疑似含 legacy/实验代码 |
| `master_agent/context.py` | MasterContext | 继承 BaseContext；含 `intent` 等**死字段**（路由中间件已禁用，无写入方） |
| `common/base.py` | BaseAgent | `stream_messages` 把 `input_context` 合入 context（`thread_id/user_id/model/agent_config`），`astream(stream_mode=["messages","updates","custom"])` |
| `common/context.py` | BaseContext | 定义 `thread_id/user_id/system_prompt/model/tools/mcps/skills` + `from_file/update` |
| `server/routers/chat_rounter.py` | 路由 | `POST /api/chat/agent/{name}`、`/sessions/{tid}/events` 回放、`/agent` 列表、`/default_agent`、`/models`、`/agent/{id}/state|history`、memory、stop |
| `services/chat_stream_service.py` | SSE 桥 | `stream_agent_chat` 是核心；make_chunk 同时写回放缓冲（**id 必须自增一致**） |
| `services/sse_protocol.py` | 事件枚举 | `EventType`：message_chunk/thinking/plan/plan_update/step_start/step_complete/tool_start/tool_complete/statistics/init/done/error/title |
| `services/sse_adapter.py` | 协议适配 | `legacy_chunk_to_events` + `format_sse_event`；含 `_coerce_plan_steps` 容错（plan 被序列化成了 str 的线上事故兜底） |
| `services/sse_session_manager.py` | 回放缓冲 | 进程内保留最近 1000 事件；`event_generator(last_event_id)` 续传；`deactivate_session` |
| `web-v2/src/apis/agent_api.js` | 前端 API | `sendAgentMessage(agentId,data)` → `POST /api/chat/agent/{agentId}`；`getDefaultAgent/getAgents/getAgentDetail/getAgentHistory/getAgentState` |
| `web-v2/src/views/GiftWorkbenchView.vue` | 送礼工作台 | 三栏：ExploreStream / ProfileCard / DeliverPanel；数据来自 `useGiftWorkbench`（**mock**） |
| `web-v2/src/data/giftWorkbenchStream.js` | mock 流 | `createWorkbenchAgent`，事件 `stage/step/live/profile/understanding/deliverable/excluded/done` |
| `web-v2/src/data/giftAgentStream.js` | mock 流 | `createGiftAgent`，事件 `think/stage/evidence/direction/element/why/risk/settle`；引用了不存在的 `gift_ideator` |
| `web-v2/src/views/PurchaseWorkbenchView.vue` | 采购工作台 | `EXEC_STREAM` from `purchaseDemo.js`（mock）+ `AgentExecStream` 组件 |

---

## 2. 契约冻结清单（改动不可破坏）

任何重构必须保证以下契约不变，否则会打断前端 / 回放 / 注册：

1. **注册与查找**：`agent_manager.get_agent(name)` 用**类名**作 key；`get_info()` 返回 `id = 类名`。前端 `agentId` 当前必须传 `"MasterAgent"`。
2. **流式入口**：`BaseAgent.stream_messages(messages, input_context)` 把 `input_context`（`thread_id/user_id/model/agent_config`）合入 context 后 `astream`。`input_context` 字段名是契约。
3. **SSE 协议**：`legacy_chunk_to_events` + `format_sse_event`；`make_chunk` **先 emit 再序列化**，回放缓冲的 `event_id` 与直播流的 `id` 必须同源（自增序号），否则前端 `last_event_id` 续传对不上（线上已踩过坑）。
4. **回放**：`GET /api/chat/sessions/{thread_id}/events?last_event_id=` 的语义不变。
5. **路由路径**：`POST /api/chat/agent/{name}`、`GET /api/chat/sessions/{tid}/events` 路径与 mount 方式（`main.py` 的 `prefix="/api"`）不变。

---

## 3. MasterAgent 后端改造目标

### 3.1 基座化：让 MasterAgent 成为"可配置的多实例"

当前 `MasterAgent` 是一个具体类。目标：抽出"通用 Master 能力"（图汇编、SSE 桥对接、subagent 调度、checkpointer），让 **GiftAgent / PurchaseAgent 作为配置化子类**：

- 差异只在于：`BASE_PROMPT` / `system_prompt`、`context_schema`（各自字段）、**工具子集**（buildin 分类 + 可选 MCP）、`subagents` 选择。
- 复用同一 `create_agent` 汇编器与同一个 SSE 桥（`stream_agent_chat` 不关心是哪个 agent，只 `get_agent(name)`）。
- 注册方式改为显式列表，避免"类名即 id"的隐式耦合（见 3.4）。

> 注意：`factory.py` 的 `create_agent` 是 6 层汇编器，本身**不需重写**即可支持多实例——只要 `graph.py` 的 `get_graph()` 把 middleware/context/tools 参数化。最小改动点就在 `MasterAgent.get_graph()`。

### 3.2 清理 `factory.py`（68KB，低风险收敛）

- `factory.py` 含大量 model_node / tool_node / chain 代码，部分疑似 ScienceClaw 遗留 / 实验代码。
- **建议**：先抽到 `common/builder.py`（你此前 `common_refactor_guide.md` 的 P1 已规划），`master_agent/factory.py` 仅留 `create_master_agent` 薄壳；核心链路**暂不动**，避免引入回归。
- 列为**低优先**，不阻塞前端接入。

### 3.3 清死字段 + 修 SSE hack

- `MasterContext` 中 `intent / intent_confidence / routing_reasoning / evidence_log / information_gaps / decision_confidence / research_data / analysis_report / risk_audit / user_profile` 全是无写入方的死字段（`IntentDetectorMiddleware` / `EvidenceCollectorMiddleware` / `GapDetectorMiddleware` 已注释禁用）。
  - **动作**：保留 `intent: Optional[dict]`（为将来路由中间件预留），其余决策状态机字段移出 `MasterContext`（或整组删，待你确认是否彻底弃用"决策状态机"思路）。
- `graph.py` 里 `self.sse_middleware` 通过闭包 `_sse_sink` 挂 `lifecycle_handler` 是 hack，且 `get_graph` 重复调用会叠加 sink。
  - **动作**：改为正式 middleware 或在 `configure_runtime()` 里注册一次性 sink；`get_graph` 加"已注册则跳过"守卫。

### 3.4 agentId 命名（待决策 c）

- 现状：前端硬编码 `"MasterAgent"`（类名）。
- 建议：注册表用**语义 id**（`master` / `gift` / `purchase`），`get_info().id` 返回语义 id；`/api/chat/default_agent` 与前端默认值同步。避免"改类名就崩前端"。

---

## 4. 前端接入方案（把工作台接到主 agent）

### 4.1 现状痛点

- 三栏工作台吃 mock，**演示态 ≠ 真实态**；`gift_ideator` 等后端根本不存在。
- mock 事件 schema（`stage/step/profile/understanding/deliverable` / `think/direction/element/why/risk`）与真实 `EventType`（`message_chunk/thinking/plan_update/tool_start/tool_complete/done`）**不一一对应**。注释里"换 EventSource 界面不改"是**乐观估计**——字段需一层映射。

### 4.2 两条接入路线

**路线 ①（最小闭环，推荐先落地）**
- 前端加 `useAgentStream(agentId, threadId)` composable：`fetch(POST /api/chat/agent/{agentId})` + `ReadableStream` 读 SSE，解析 `EventType`，维护 `last_event_id` 游标。
- 加一个**三栏适配器**：把 `message_chunk→左栏 live 正文`、`thinking→左栏推理`、`tool_start/tool_complete→左栏步骤+依据`、`plan_update→左栏计划/中栏待确认`、`done→右栏收敛`。
- 复用 `GET /api/chat/sessions/{tid}/events` 做刷新续传。
- **优点**：不动后端、不依赖 SubAgent 复苏，先打通"前端→主agent"端到端。
- **代价**：MasterAgent 通用流没有"送礼领域语义"，三栏只能吃到"通用推理 + 工具调用"，右栏交付物需前端按工具结果二次组织。

**路线 ②（目标态）**
- 后端注册 `GiftAgent` / `PurchaseAgent`（各自 system_prompt + 工具 + 可选 subagents）。
- 后端在这两个 agent 里 emit **对齐三栏的领域事件**：`profile`（中栏档案）/ `direction`（方向）/ `element`（候选）/ `why`（依据）/ `risk`（风险）/ `deliverable`（右栏）。可复用 `custom` 流模式（中间件 `get_stream_writer()` 已支持）。
- 前端把 mock 的 `createWorkbenchAgent` 换成 `useAgentStream`，**事件字段几乎一一对应，界面层零/低改造**（mock 注释里的设想成立）。
- **代价**：依赖 Phase 2 基座化 + Phase 4 SubAgent/工具复苏。

### 4.3 事件协议对齐表（路线 ② 的映射契约，建议落 `docs/api-contracts.md`）

| 三栏落点 | mock 事件 | 后端应 emit | 真实 EventType 承载方式 |
|---|---|---|---|
| 左·探索流 | `stage` / `step` / `live` | 计划步骤 + 增量正文 | `plan_update` + `message_chunk` |
| 左·步骤依据 | `step.evidence` | 工具结果 preview | `tool_complete.result_preview` |
| 中·人物档案 | `profile` / `understanding` | 用户画像卡 | `custom: profile` / `custom: understanding` |
| 中·待确认 | `profile.state` | 推断信号 | `custom: profile`（state 字段） |
| 右·交付物 | `deliverable` | 方案/对比/预算/寄语/订单 | `custom: deliverable` |
| 全局 | `done` | 收敛 | `EventType.DONE` + statistics |

> 关键：领域语义走 `custom` 模式（`EventType` 已有的扩展通道），通用通道（message_chunk/thinking/tool_*/done）保持原样供通用聊天视图复用。

### 4.4 具体改动点（前端，路线 ①）

| 文件 | 改动 |
|---|---|
| `web-v2/src/composables/useAgentStream.js` | **新增**：fetch + ReadableStream 消费 SSE，解析 EventType，暴露 `events`/`lastEventId`/`abort` |
| `web-v2/src/composables/useGiftWorkbench.js` | 把 `createWorkbenchAgent().run()` 换成 `useAgentStream('MasterAgent', tid)` + 适配器 |
| `web-v2/src/views/GiftWorkbenchView.vue` | `onMounted(start)` 不变；`start` 内部从 mock 切真实流 |
| `web-v2/src/apis/agent_api.js` | 已具备 `sendAgentMessage`；补 `getSessionEvents(tid, lastEventId)` 封装回放 |
| `web-v2/src/router` / `task` 透传 | 确保 `thread_id` 由前端生成并写 localStorage（回放需要） |

---

## 5. 待你决策的阻塞项

| # | 问题 | 选项 | 影响 |
|---|---|---|---|
| (a) | **jd / SubAgent 工具回归** | ①恢复 `jd` 模块 ②裁剪 `subagents.yaml` 只留可用工具 ③用现有 MCP 工具替代 | 决定 researcher/analyst/critic 能否真产出（Phase 4） |
| (b) | **现在就注册专属 agent？** | ①先全走 MasterAgent（路线①） ②直接做 GiftAgent/PurchaseAgent（路线②） | 决定前端先接通用流还是等领域事件 |
| (c) | **agentId 命名** | ①保持类名 `MasterAgent` ②语义 id `master/gift/purchase` | 影响注册表与前端默认值耦合度 |
| (d) | **factory.py 是否重构** | ①只收敛到 `common/builder.py` 薄壳 ②暂不动 | 低风险，不阻塞接入 |

> 你此前说"先不着急"——(a) 暂挂起，先推 (b)=① + 路线① 打通最小闭环最稳。

---

## 6. 实施阶段（建议顺序）

- **Phase 0（已完成）**：P0 import 修复，保证 `import src.agents` 与 `MasterAgent.get_graph()` 可编译（前轮已落地 + 验证）。
- **Phase 1（最小闭环，不依赖后端改 agent）**：前端 `useAgentStream` + 三栏适配器，GiftWorkbench 先接 `MasterAgent` 通用流，打通"前端→主agent"端到端。验证：`/proxy` 能跑出真实推理流 + 刷新续传可用。
- **Phase 2（后端基座化）**：MasterAgent 配置化子类；`common/builder.py` 收敛 `factory`；清 `MasterContext` 死字段；SSE middleware 正规化；(c) 命名落地。
- **Phase 3（专属 agent + 领域事件）**：注册 `GiftAgent` / `PurchaseAgent`；后端 emit 对齐三栏的领域事件（走 `custom`）；前端切路线②（零/低改造）。
- **Phase 4（SubAgent 复苏）**：(a) 决策后恢复 researcher/analyst/critic 真产出，让领域事件有真实内容。

---

## 7. 回归红线（每次改动后必须验证）

1. `python -c "import src.agents"` → 成功（前轮已修，勿再引入 dangling import）。
2. `MasterAgent().get_graph()` → `CompiledStateGraph`（编译 OK）。
3. `POST /api/chat/agent/MasterAgent` 能流式返回 + `GET /api/chat/sessions/{tid}/events` 回放 OK。
4. 现有 mock 视图在接入前**保持可演示**（不破坏 `GiftWorkbenchView` 现有 UI）。
5. 前端 `useAgentStream` 异常时不让流断裂（`chat_stream_service` 已有 `try/except` 兜底，前端需对齐）。

---

## 8. 本机 shell 环境坑（备查）

Git Bash 在本环境 PATH 缺失 coreutils（`mkdir/ssh/scp/ls` 找不到）。修复：每条 Bash 前置
`export PATH="/c/Users/25153/.workbuddy/binaries/PortableGit/versions/1.2.0/usr/bin:/c/Users/25153/.workbuddy/binaries/PortableGit/versions/1.2.0/bin:$PATH"`
并加 `dangerouslyDisableSandbox:true`；scp 远端路径用**绝对路径**（`/home/ubuntu/...`），`~/` 不被 scp 展开。
