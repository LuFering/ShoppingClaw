你说得对，`JointBERT` 是意图识别模型，不应该拿来做 Gap Detector。这个节点的 ML 任务本质不是“理解用户说了什么”，而是：

**给定当前 `intent + slots + evidence artifacts + subagent outputs`，判断证据链是否足够支撑最终推荐，并预测还缺哪些证据。**

我看了项目后，建议这样做。

**一、先定位它在当前架构里的真实位置**

你现在的主链路是：

`IntentDetectorMiddleware.before_agent`
→ `model`
→ `tools`
→ 回到 `model`
→ 最终结束

`src/agents/master_agent/factory.py` 里已经支持四类 middleware 节点：

- `before_agent`
- `before_model`
- `after_model`
- `after_agent`

而且 `after_model` 已经会被编进 graph：

```python
model -> xxx.after_model -> choose_model_to_tools_edge -> tools / END
```

所以 `gap_detector_node` 最自然的位置不是新开一个独立主图，而是做成：

```text
GapDetectorMiddleware.after_model
```

这样 LangGraph Studio 里会显示为：

```text
gap_detector.after_model
```

它的位置正好在模型输出之后、决定进入 tools 还是 END 之前。

**二、Gap Detector 不应该吃原始 prompt，而应该吃 State Feature**

这个节点的输入不能是单句 query。它必须把 state 压成结构化特征。

当前可用状态来自 [src/agents/master_agent/context.py](/abs/path/D:/ShoppingClaw/src/agents/master_agent/context.py)：

```python
intent
evidence_log
information_gaps
decision_confidence
research_data
analysis_report
risk_audit
user_profile
```

SubAgent 协议在 [src/agents/subagents/subagents.yaml](/abs/path/D:/ShoppingClaw/src/agents/subagents/subagents.yaml) 里已经规定了 `evidence_type`：

```json
{
  "evidence_type": "product_list | comparison_matrix | risk_report | user_preference",
  "data": {},
  "summary": ""
}
```

所以 Gap Detector 的 ML 输入应该是一个 `GapFeature`，而不是自然语言全文。

建议特征结构：

```json
{
  "intent_main": "product_recommend",
  "intent_sub": "single_product",
  "intent_confidence": 0.82,
  "missing_slots_count": 0,
  "slot_keys": ["category", "budget_max"],

  "has_user_profile": true,
  "has_product_list": true,
  "has_comparison_matrix": false,
  "has_risk_report": false,

  "product_count": 8,
  "valid_product_count": 5,
  "price_coverage": 0.8,
  "brand_diversity": 3,
  "platform_diversity": 2,

  "analysis_has_top_pick": false,
  "analysis_dimension_count": 0,

  "risk_red_count": 0,
  "risk_yellow_count": 0,

  "last_action": "researcher",
  "turn_index": 2
}
```

**三、模型任务定义**

不要做一个“单一分类器”。这个任务天然是多任务学习：

```text
输入：GapFeature
输出：
1. information_gaps: multi-label classification
2. decision_confidence: regression
3. next_action_hint: optional classification
```

标签空间建议固定：

```python
GAP_LABELS = [
    "human_input",
    "user_preference",
    "product_list",
    "price_or_stock",
    "comparison_matrix",
    "risk_audit",
    "evidence_quality",
    "no_gap",
]
```

输出格式：

```json
{
  "information_gaps": ["comparison_matrix", "risk_audit"],
  "gap_probs": {
    "comparison_matrix": 0.86,
    "risk_audit": 0.74
  },
  "decision_confidence": 0.63,
  "model_confidence": 0.81
}
```

注意区分：

- `decision_confidence`：当前证据是否足够做推荐
- `model_confidence`：Gap 模型自己对判断的把握

这两个不能混。

**四、推荐模型：GBDT / XGBoost / LightGBM，而不是 BERT**

这里不建议 Transformer。原因很具体：

1. Gap 判断主要依赖结构化证据是否存在、质量是否够、上下游依赖是否满足。
2. 当前 state 里的核心字段是 JSON/数值/枚举，不是长文本语义。
3. 线上节点会被频繁调用，BERT 类模型延迟和依赖都重。
4. `pyproject.toml` 里 `torch` 目前还是注释状态，但代码里已经隐式依赖了它，这是已有风险，不应该继续扩大。

我建议首版模型用：

```text
MultiOutputClassifier + GradientBoosting / RandomForest / XGBoost
Regressor + GradientBoostingRegressor
```

如果你接受新增依赖，优先：

```text
lightgbm
```

如果你想少引依赖，直接用：

```text
scikit-learn
```

但当前 `pyproject.toml` 还没有 `scikit-learn`，需要补。

推荐结构：

```text
src/services/gap/
  schema.py
  feature_extractor.py
  model.py
  service.py

models/gap_detector/
  label_config.json
  multilabel_model.joblib
  confidence_model.joblib
  calibrator.joblib

scripts/
  train_gap_detector.py
```

**五、训练数据怎么来**

不要手写少量规则样本糊弄。要从真实或模拟轨迹构造“状态快照”。

一条训练样本不是一条用户 query，而是一次 Agent 中间状态：

```json
{
  "state_snapshot": {
    "intent": {},
    "research_data": null,
    "analysis_report": null,
    "risk_audit": null,
    "user_profile": null,
    "evidence_log": []
  },
  "labels": {
    "information_gaps": ["product_list", "user_preference"],
    "decision_confidence": 0.28
  }
}
```

数据来源分三层：

1. **人工标注核心样本**
   每个主意图至少 100-200 条状态快照。

2. **合成轨迹样本**
   用现有 mock crawler 和 subagent 输出协议生成状态：
   - 无商品列表
   - 商品太少
   - 有商品但无对比
   - 有对比但无风控
   - 有完整证据
   - 意图低置信
   - slot 缺失

3. **线上日志回流**
   每轮把 `state -> gap output -> 用户是否追问/是否接受/是否完成购买` 记录下来，后面做再训练。

建议数据目录：

```text
data/gap_detector/train.jsonl
data/gap_detector/val.jsonl
data/gap_detector/test.jsonl
```

**六、集成方式**

新增 `GapDetectorMiddleware`：

```python
class GapDetectorState(AgentState):
    information_gaps: NotRequired[list[str]]
    decision_confidence: NotRequired[float]
    gap_debug: NotRequired[dict]
```

核心放在 `after_model`：

```python
class GapDetectorMiddleware(AgentMiddleware):
    name = "gap_detector"
    state_schema = GapDetectorState

    def after_model(self, state, runtime):
        result = get_gap_service().predict(state)

        update = {
            "information_gaps": result["information_gaps"],
            "decision_confidence": result["decision_confidence"],
            "gap_debug": result["debug"],
        }

        if result["decision_confidence"] < 0.7:
            update["jump_to"] = "model"

        return update
```

然后在 [src/agents/master_agent/graph.py](/abs/path/D:/ShoppingClaw/src/agents/master_agent/graph.py) 加入 middleware：

```python
GapDetectorMiddleware(),
```

位置建议放在 `PatchToolCallsMiddleware()` 之后、`ToolCallLimitMiddleware()` 之前或之后都可以；关键是它实现 `after_model`，实际 graph 顺序由 factory 的 after_model 逆序逻辑决定，最终要保证它在 `choose_model_to_tools_edge` 前执行。

**七、你当前项目里必须补的一块**

现在 SubAgent 返回结果主要作为 ToolMessage 回到 messages，项目里还没看到稳定的“解析 SubAgent JSON 并写入 `research_data / analysis_report / risk_audit / user_profile / evidence_log`”的 middleware。

这会直接影响 Gap ML，因为模型需要结构化 evidence。

所以 Gap Detector 前面要加一个：

```text
EvidenceCollectorMiddleware
```

职责：

- 从最近的 ToolMessage 解析 JSON
- 读取 `evidence_type`
- 写入对应 state 字段

映射：

```python
product_list -> research_data
comparison_matrix -> analysis_report
risk_report -> risk_audit
user_preference -> user_profile
```

同时 append：

```python
evidence_log.append({
  "type": evidence_type,
  "source": subagent_name,
  "content": summary,
  "timestamp": now
})
```

没有这个，Gap Detector 只能读 messages，模型输入会脏且不稳定。

**八、最终推荐架构**

```text
IntentDetectorMiddleware
  ↓
Model
  ↓
Tools / SubAgents
  ↓
EvidenceCollectorMiddleware.after_model
  ↓
GapDetectorMiddleware.after_model
  ↓
decision_confidence < 0.7 → 回 model 调度补证据
decision_confidence >= 0.7 → END / final response
```

**九、验收标准**

这个节点上线不能只看“能跑”。建议验收指标是：

- `information_gaps` multi-label F1 >= 0.82
- `critical_gap_recall >= 0.9`
- `decision_confidence` MAE <= 0.08
- 低证据状态误放行率 <= 5%
- 完整证据状态误拦截率 <= 10%
- 单次推理 P95 <= 30ms，GBDT 可以做到

**结论**

专业落地路线是：

1. 先补 `EvidenceCollectorMiddleware`，保证 state 结构化。
2. 新建独立 `gap_detector` ML service，不复用 JointBERT。
3. 模型用结构化特征的多标签分类 + 置信度回归，推荐 LightGBM/sklearn。
4. 用 `after_model` middleware 接入现有 LangGraph 工厂。
5. 让 `information_gaps` 成为 Master 调度 SubAgent 的硬输入，而不是 prompt 里的软建议。

这才是这个节点在你当前代码库里比较严谨的实现方式。