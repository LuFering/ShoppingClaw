# ShoppingClaw Agent 设计原则与架构指南 (v2.1)

## 1. 核心定位：决策执行引擎 (Decision Execution Engine)
本项目是一个**以决策为中心的智能体系统**。所有组件必须服务于"从模糊意图到结构化决策"的闭环。
- **拒绝线性流**：严禁使用 `Step 1 -> Step 2` 的硬编码流水线。
- **拥抱动态循环**：必须实现基于 `ReAct` 和 `Information Gap` 的状态机循环。

## 2. 架构模式：分层主从式协作 (Hierarchical Master-Worker)
- **主智能体 (Master Agent)**：唯一的"决策大脑"。维护全局 `MasterContext`（DecisionState），负责识别缺口并调度工具。
- **子智能体 (Worker Agents)**：领域专家（Researcher, Critic, Analyst, Memory）。它们**不是**主图中的平行节点，而是被封装为 **LangChain Tools** 的黑盒执行器。
- **交互方式**：Master Agent 通过 `SubAgentMiddleware` 以 `tool_calls` 启动子 Agent，子 Agent 执行完毕后返回结构化结果。

## 3. 主智能体中间件链设计

主图基于 `factory.py` 的 `create_master_agent` 构建，通过 13 层中间件实现完整的决策闭环：

```
SSEMonitoringMiddleware          # 1. 工具调用监控（捕获所有调用供 SSE 推送）
  → ContentGuardMiddleware       # 2. 内容安全审查
  → PatchToolCallsMiddleware     # 3. 修复工具调用格式
  → ToolResultOffloadMiddleware  # 4. 大型结果卸载到文件系统
  → ToolCallLimitMiddleware      # 5. 调用次数限制（run=10, thread=20）
  → TodoListMiddleware           # 6. 任务拆解
  → FilesystemMiddleware         # 7. 文件读写能力
  → SubAgentMiddleware           # 8. 子智能体调度（核心）
  → ThinkingProcessMiddleware    # 9. 思考过程提取（前端可视化）
```

### A. Gap Detector（按需启用）
- **触发时机**：在意图识别后，分析 `evidence_log` 与 `intent` 的匹配度。
- **职责**：更新 `information_gaps` 列表，评估 `decision_confidence`。
- **技术植入点**：此处是植入 LightGBM 模型的评估节点。

### B. 动态路由逻辑
- **IF** `decision_confidence < 0.7` **THEN** 继续搜索/计算。
- **IF** `information_gaps` 包含 "human_input" **THEN** 触发 `interrupt`（人机协同）。
- **ELSE** 路由至 `END`（输出最终决策报告）。

## 4. 显式决策状态 (MasterContext)

定义在 `src/agents/master_agent/context.py` 中：

| 字段 | 类型 | 说明 |
|------|------|------|
| `intent` | `IntentState` | 意图识别结果 |
| `current_intent_type` | `str` | 如 COMPLEX_PURCHASE / SIMPLE_QUERY |
| `intent_confidence` | `float` | 意图分类置信度 (0.0-1.0) |
| `routing_reasoning` | `str` | 调用子 Agent 的逻辑依据 |
| `evidence_log` | `list[dict]` | 已收集证据（type/source/content/timestamp） |
| `information_gaps` | `list[str]` | 待填补信息缺口 |
| `decision_confidence` | `float` | 决策置信度（<0.7 触发补充收集） |
| `research_data` | `list[dict]` | Researcher 产出 |
| `analysis_report` | `dict` | Analyst 产出 |
| `risk_audit` | `dict` | Critic 产出 |
| `user_profile` | `dict` | Memory 产出 |

## 5. 工具与子智能体开发规范

### A. 原子化工具 (Atomic Tools)
- **落点**：`src/agents/common/toolkits/buildin/`
- **示例**：`execute_python_code`（代码解释器），`save_user_preference`（记忆存储）。

### B. 子智能体工具化 (Sub-agent as Tool)
子 Agent 在 `subagents.yaml` 中声明，由 `SubAgentMiddleware` 自动封装为 Tool：
```yaml
# src/agents/subagents/subagents.yaml
Researcher:
  description: "跨平台商品搜索专家"
  tools: ["jd_search", "jd_product_detail"]
  system_prompt: "你是商品搜索专家..."

Critic:
  description: "搜索结果质量评估专家"
  tools: ["evaluate_search_result", "detect_bias"]
  system_prompt: "你是质量评估专家..."
```

Master Agent 通过 `tool_calls` 调用子 Agent，子 Agent 内部可拥有独立的工具链和模型配置。

## 6. 混合智能增强 (Hybrid AI Integration Points)
- **JointBERT**：意图识别，多标签分类（search_product / compare_price / ask_recommend）
- **LightGBM**：Gap Detector 置信度评估，客观评估证据质量

## 7. 开发红线 (Red Lines)
- **禁止平行节点**：不要将 Researcher/Analyst 作为 `add_node` 添加到主图并与 Model 平行。
- **禁止隐式状态**：所有决策依据（缺口、信心）必须存在于 `MasterContext` 中，不能仅靠 LLM 上下文记忆。
- **禁止无据决策**：最终输出应可追溯每一步调用的理由。

## 8. 目录结构指引
- `src/agents/master_agent/factory.py`：通用 ReAct 引擎（通常不改动）。
- `src/agents/master_agent/graph.py`：**核心开发文件**，定义中间件链和子 Agent 加载。
- `src/agents/master_agent/context.py`：MasterContext 决策状态定义。
- `src/agents/common/toolkits/`：五大工具包（research / critic / analyst / memory / buildin）。
- `src/agents/subagents/subagents.yaml`：子 Agent 配置与工具映射。
