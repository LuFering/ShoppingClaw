# ShoppingClaw Agent 设计原则与架构指南 (v2.0)

## 1. 核心定位：决策执行引擎 (Decision Execution Engine)
本项目是一个**以决策为中心的智能体系统**。所有组件必须服务于“从模糊意图到结构化决策”的闭环。
- **拒绝线性流**：严禁使用 `Step 1 -> Step 2` 的硬编码流水线。
- **拥抱动态循环**：必须实现基于 `ReAct` 和 `Information Gap` 的状态机循环。

## 2. 架构模式：分层主从式协作 (Hierarchical Master-Worker)
- **主智能体 (Master Agent)**：唯一的“决策大脑”。它维护全局 `DecisionState`，负责识别缺口并调度工具。
- **子智能体 (Worker Agents)**：领域专家（如 Researcher, Analyst）。它们**不是**主图中的平行节点，而是被封装为 **LangChain Tools** 的黑盒执行器。
- **交互方式**：主 Agent 通过 `tool_calls` 启动子 Agent，子 Agent 内部可拥有独立的微型 Graph，执行完毕后返回结构化字符串给主 Agent。

## 3. 主智能体图设计方案 (Main Graph Blueprint)
主图基于 `factory.py` 提供的 `create_agent` 引擎构建，并通过 `graph.py` 进行决策层扩展：

### A. 核心节点 (Nodes)
1.  **Model Node (内置)**：由 `factory.py` 提供，负责 LLM 推理和 Tool Calling。
2.  **Tool Node (内置)**：由 `factory.py` 提供，负责执行原子化工具或子智能体工具。
3.  **Gap Detector Node (自定义扩展)**：
    - **触发时机**：在 Model Node 输出后、进入下一轮循环前。
    - **职责**：分析 `evidence_log` 与 `intent` 的匹配度，更新 `information_gaps` 列表。
    - **技术植入点**：此处是植入 ML/DL 模型（如 BERT 评分）的核心位置。

### B. 动态路由逻辑 (Conditional Edges)
在 `graph.py` 中通过 `add_conditional_edges` 实现：
- **IF** `confidence_score < 0.7` **THEN** 路由回 `model` (强制继续搜索/计算)。
- **IF** `information_gaps` 包含 "human_input" **THEN** 触发 `interrupt` (人机协同)。
- **ELSE** 路由至 `END` (输出最终决策报告)。

## 4. 显式决策状态 (Explicit Decision State)
必须在 `src/agents/mainagent/context.py` 中定义 `DecisionState`，包含以下关键字段：
- `messages`: 对话历史 (List[AnyMessage])。
- `intent`: 用户原始意图 (str)。
- `constraints`: 预算、品牌偏好等约束 (dict)。
- `evidence_log`: 已收集的证据摘要列表 (List[str])。
- `information_gaps`: 待填补的信息缺口 (List[str], e.g., ["price_missing", "review_missing"])。
- `confidence_score`: 当前决策置信度 (float, 0.0-1.0)。
- `decision_path`: 决策轨迹日志 (List[str])，用于前端可视化回放。

## 5. 工具与子智能体开发规范
### A. 原子化工具 (Atomic Tools)
- **落点**：`src/agents/mainagent/tools/atomic_tools.py`
- **示例**：`execute_python_code` (代码解释器), `save_user_preference` (记忆存储)。

### B. 子智能体工具化 (Sub-agent as Tool)
- **落点**：`src/agents/researcher/graph.py` (子图) -> `src/agents/mainagent/tools/expert_tools.py` (封装)。
- **封装范式**：
  ```python
  @tool
  def deep_research_tool(query: str) -> str:
      """当需要跨平台深度调研时调用。"""
      sub_graph = create_researcher_graph().compile()
      return sub_graph.invoke({"query": query})['summary']
  ```

## 6. 混合智能增强 (Hybrid AI Integration Points)
- **DL 评估器**：在 `Gap Detector Node` 中运行轻量级判别模型，客观评估证据质量。
- **RL 调度器**：在 `Tool Node` 执行前，利用 Bandit 算法根据历史成功率优化工具选择。

## 7. 开发红线 (Red Lines)
- **禁止平行节点**：不要将 Researcher/Analyst 作为 `add_node` 添加到主图并与 Model 平行。
- **禁止隐式状态**：所有决策依据（缺口、信心）必须存在于 `State` 中，不能仅靠 LLM 上下文记忆。
- **禁止无据决策**：最终输出必须附带 `decision_path`，证明每一步调用都有对应的 `information_gap` 支撑。

## 8. 目录结构指引
- `src/agents/mainagent/factory.py`: 通用 ReAct 引擎（通常不改动）。
- `src/agents/mainagent/graph.py`: **核心开发文件**，负责定义 DecisionState 和扩展决策节点。
- `src/agents/mainagent/tools/`: 存放所有原子工具和子智能体封装。
- `src/agents/{subagent_name}/`: 存放各子智能体的独立 Graph 实现。
