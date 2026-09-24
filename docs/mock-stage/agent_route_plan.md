# /agent 路由改造方案（聚焦 MasterAgent 接入 · 扫描版）

> 范围：仅 `http://111.229.209.47/agent` 路由（通用聊天页 `/agent` ↔ `AgentView` → `AgentChatComponent`）。
> 状态：只扫描、只出方案，未改任何代码（按"先不着急"）。
> 事实来源：服务器 `/home/ubuntu/ShoppingClaw`（`src` bind-mount 到容器 `/app/src`，`server/` 为 FastAPI 入口），本轮已 scp 核对。
> 采购 / 代购工作台（`/proxy`、`/planning`）为独立 agent、需额外配置，**不在本范围**。

---

## 0. 结论先行

`/agent` **已经是 `MasterAgent` 的第一类（first-class）消费端**，前后端契约在扫描时完全对齐：REST 端点、SSE 事件类型、字段名、agent 命名（`id="MasterAgent"`）都已匹配。

本方案不是"重新接线"，而是：
1. 确认链路完整（附证据）；
2. 列出仍会削弱 `/agent` 体验的契约 / 功能缺口；
3. 给出优先级与改动点（仅 `/agent` 范围）。

---

## 1. 端到端链路（已验证）

```
/agent
 └─ AgentView.vue  (:single-mode="false")
     └─ AgentChatComponent.vue
         ├─ useAgentStore.initialize() → fetchAgents() / fetchDefaultAgent()
         └─ agentApi.sendAgentMessage(agentId, {query, config:{thread_id,model}, meta})
                │  POST /api/chat/agent/{agentId}
                ▼
         chat_rounter.chat_agent
                └─ services/chat_stream_service.py :: stream_agent_chat  (SSE 桥)
                     ├─ src.agents.agent_manager.get_agent(name)   ← 唯一注册 MasterAgent
                     ├─ agent.stream_messages(messages, input_context)
                     │    └─ master_agent/graph.py :: MasterAgent.get_graph()  (13 层中间件)
                     ├─ agent.sse_middleware.drain_events()  → SSEMonitoringMiddleware
                     └─ sse_session_manager.emit_nowait ─▶ GET /api/chat/sessions/{tid}/events (回放)
                │  text/event-stream
                ▼
         AgentChatComponent.handleSSEEvent(eventType, data)  → 渲染
```

逐点核对证据：

- **路由**：`router/index.js` 中 `/`→`/agent`（默认落地），`/agent` 与 `/agent/:agent_id` 均渲染 `AgentView`；`AgentView` 把 `route.params.agent_id` 同步到 `agentStore.selectAgent`。
- **Agent 命名（关键）**：`BaseAgent.get_info()` 返回 `id = __class__.__name__ = "MasterAgent"`；`agents/__init__.py` 以类名 `register_agent(MasterAgent)`（唯一注册），`agent_manager.get_agent("MasterAgent")` 命中。→ URL 的 `agentId` 与查找键一致，**可解析**（此前担心的 agentId 命名问题已确认无碍）。
- **REST 契约**：`GET /api/chat/agent`→`{agents:[{id,name,description,examples,has_checkpointer,capabilities}]}`（前端读 `response.agents`✓）；`GET /api/chat/default_agent`→`{default_agent_id}`✓；`/agent/{id}/history`、`/state`、线程 CRUD、`GET /api/chat/sessions/{tid}/events?last_event_id=` 全部与 `agent_api.js` / `threadApi` 一一对应（`main.py` 以 `prefix="/api"` 挂载 `chat` 路由）。
- **发送体**：前端发 `{query, config:{thread_id, model}, meta}`；`chat_agent` 形参恰为 `query, config, meta`（`image_content` 可选）。✓

---

## 2. SSE 事件契约对齐表

| 后端 EventType | 来源通道 | 前端 `handleSSEEvent` 分支 | 字段对齐 |
|---|---|---|---|
| `init` | legacy(`state=init`) | （无分支 → `default` 忽略） | 前端自建占位，无需 |
| `message_chunk` | legacy(`status=loading`, 有 content) | `message_chunk` | `content`, `message_id` ✓ |
| `thinking` | legacy(`event=thinking`) | `thinking` | `content` ✓ |
| `tool_start` | legacy(`event=tool_call`,calling) **+** SSEMonitoringMiddleware | `tool_start` | `tool_name`, `tool_call_id`, `arguments`, `meta{icon,category}`, `message_id`(仅 legacy) ✓ |
| `tool_complete` | legacy(`event=tool_result`) **+** SSEMonitoringMiddleware | `tool_complete` | `tool_name`, `tool_call_id`, `result_content`, `duration_ms`, `message_id`(仅 legacy) ✓ |
| `plan_update` | legacy(`event=plan_update` / `status=agent_state`) | `plan_update` | `steps` ✓ |
| `title` | 直接 emit | `title` | `thread_id`, `title` ✓ |
| `done` | 直接 emit | `done` | `statistics` ✓ |
| `error` | legacy(`status=error`) **+** SSEMonitoringMiddleware(工具失败) | `error`（对话级致命） | `message` / `error` ✓ |

结论：前端 `switch` 的每个分支后端都有产出。双通道（legacy + SSEMonitoringMiddleware）通过前端 `upsertToolCallIntoMessage` 跨条目去重 + `planShadowReconcile` 收敛，已解决"同工具重复 / 一直转圈"问题（组件内大量注释即为此类修复的佐证）。

---

## 3. 仍存在的缺口（按优先级）

### P0 — 功能性

**G1. ⚠️ SubAgent 工具解析 —— 已验证：analyst / critic 工具整包缺失（P0 坐实）。**
`MasterAgent.get_graph()` 经 `SubAgentMiddleware` 调 `load_subagent()` 加载 `subagents.yaml`，每个子 agent 的 `tools:` 列表经 `_get_tool_by_name(t)`（`graph.py:26`，精确匹配 `tool.name`）解析；匹配不到则返回 `None` → 该子 agent 拿 0 工具。

**验证动作（2026-09-16，只读扫描）**：
- `src/agents/common/toolkits/__init__.py::get_all_tool_instances()` 懒加载：`buildin.tools`（必加载）+ `research` / `analyst` / `critic.tools`（try 导入，失败仅 warning）。
- 实际 `toolkits/` 目录**只有 `buildin/` 与 `research/`**，**没有 `analyst/` 包、没有 `critic/` 包** → 后两个 import 静默失败，其工具永不注册。
- `subagents.yaml` 引用的 7 个工具名在 `src/agents/**` 全仓仅出现在 yaml 自身与 `discovery.py` 的映射里，**研究包之外无任何定义**。

**解析结果（结论）**：

| 子 agent | yaml 要求的工具 | 是否注册 | 结果 |
|---|---|---|---|
| researcher | `search_products`、`get_product_full_detail`、`get_products_specs_batch` | ✅ 在 `research/tools.py`，`@tool` 未传 `name` 故 `tool_obj.name == func.__name__`（`registry.py:124`） | 3/3 命中 |
| analyst | `get_products_specs_extract`、`filter_products_by_criteria`、`query_category_knowledge` | ❌ `toolkits/analyst/` 不存在 | **0/3（空工具）** |
| critic | `query_risk_policy` | ❌ `toolkits/critic/tools.py` 不存在 | **0/1（空工具）** |
| memory_manager | （无，yaml 即 `tools: []`） | — | 0（设计如此） |

**影响**：`/agent` 的 MasterAgent 仍会编排 analyst / critic，但这两个专家**没有任何工具**，只能凭模型参数"凭空"产出决策分析与风险评审 JSON —— 即用户最看重的"有对比 / 有风险评审"恰恰是最不可信的部分。**这是当前 `/agent` 产出好答案的头号阻断项。**
**修复方向**（待评审，不改代码）：① 补齐 `toolkits/analyst/`（3 工具）+ `toolkits/critic/tools.py`（`query_risk_policy`）并注册；或 ② 暂时从 `subagents.yaml` 摘掉 analyst / critic，仅留 researcher + memory_manager，避免"假专家"。

### P1 — 契约正确性

**G2. 工具失败事件类型冲突（会腰斩整轮）。**
`SSEMonitoringMiddleware.wrap_tool_call` 在工具抛异常时 `emit({"type": EventType.ERROR, tool_name, tool_call_id, error})`——复用 `error` 类型。但前端 `case 'error'` 把**任意** error 当作整轮对话致命错误并 `throw` → 外层 catch 标记整条失败。前端虽有专用 `case 'tool_error'`，但 `EventType` 枚举根本无 `TOOL_ERROR`、legacy 也不映射，后端**从不发 `tool_error`**，该分支是死的。
结果：单个工具失败可能把整条 MasterAgent 回复流腰斩，而非仅把该工具标红。
修复：中间件对"工具级失败"改发 `tool_error`（带 `tool_name`/`tool_call_id`/`error`），前端已就绪；仅对话级致命错误发 `error`。

**G3. `agent_state` 的 `todos` 被压平丢失。**
`legacy_chunk_to_events` 在 `status="agent_state"` 时只转成 `plan_update.steps`，从不发 `agent_state` 类型；SSEMiddleware 也不发。前端 `case 'agent_state'`，（读 `data.todos`）是死分支，状态面板"待办 / 文件" richness 丢失（仅 plan 步骤可见）。`GET /api/chat/agent/{id}/state` 仍返回完整 `agent_state.todos`，前端 refresh 能用。
可选：后端补发 `agent_state` 事件（带 `todos`/`files`），或前端以 `plan_update` 为唯一来源并删死分支。

### P2 — 丰富度 / 健壮性

**G4. 商品卡片端到端确认。**
`render_product_card` 是 buildin 工具（`tools.py:396`），`MasterAgent.get_tools()` 含全部 buildin 工具 → 工具可用；后端在 `ToolMessage.name == "render_product_card"` 时持久化 `productCards`，前端 `tool_complete` 分支解析 `{type:"product_card",data}` 或 `{cards:[...]}` 渲染。
需确认：① LLM 实际会调用该工具；② 卡片结构兼容前端两种格式；③ 历史回读 `get_agent_history` 的 `productCards` 不被 `syncThreadHistory` 的"条数 / 卡片数不更差"规则丢弃。

**G5. `store.toolMetadata` / `availableTools` 永不填充。**
`stores/agent.js` 声明但从不写入（注释：SC 后端不下发工具清单，渲染回退前端 `TOOL_NAME_MAP`）。若要服务端驱动的工具元数据 / 图标，需 `GET /api/chat/agent` 或新端点返回 `tools` 并在 `initialize` 写入。当前不影响功能。

**G6. 鉴权前置条件。**
所有 `/api/chat/*` 路由 `Depends(get_required_user)`；前端 `agentApi` 带 `getAuthHeaders()`。未登录访问 `/agent` 时 `GET /api/chat/agent` 返 401 → `initialize()` 失败 → `selectedAgentId` 为 null → 输入框 disabled、提示"智能体尚未就绪"。即 `/agent` 需已登录会话才可用（演示 / 测试备好账号或放开 dev 分支）。

---

## 4. 建议执行顺序（仅 `/agent`，扫描已完成，待评审）

1. **G1 已验证 = analyst / critic 工具整包缺失**（见 §3 G1 表格）—— 最高优先，决定 `/agent` 是否有用。二选一：补工具包，或先摘掉这两个"假专家"。
2. **修 G2**（`tool_error` 类型）—— 小改动，避免单工具失败腰斩整轮。
3. **确认 / 补 G3**（`agent_state` todos）—— 状态面板 richness。
4. **端到端走查 G4**（商品卡）—— 用真实 query 验证卡片渲染与历史回读。
5. 视需要 G5 / G6。

---

## 5. 明确不在本范围

- `/proxy`（代购 / 礼物工作台）、`/planning`（采购工作台）：独立 agent，需单独配置。
- 后端 `MasterAgent` 13 层中间件重构、`factory.py` 收敛、`common/` 基座化：属"主 agent 改造"后端部分，可单列；但 `/agent` 页面本身不依赖它们即可工作。
