

## 子Agent优化方案

基于代码分析和BASE_PROMPT.md、joyai_prompt.md，给出以下优化方案：

---

### 一、当前问题诊断

#### 1. **工具引用错误**
`subagents.yaml`中引用的工具大多不存在：
- ❌ `search_web` - 未实现
- ❌ `crawl_ecommerce` - 未实现
- ❌ `analyze_reviews` - 未实现
- ❌ `execute_code` - 未实现
- ❌ `query_knowledge_base` - 未实现
- ❌ `vector_search` - 未实现

**现状**：这些工具只在Prompt中提到，实际代码中没有对应实现。

---

#### 2. **职责边界模糊**
对比BASE_PROMPT.md第133-138行和subagents.yaml：

| SubAgent | BASE_PROMPT定义 | subagents.yaml定义 | 冲突点 |
|----------|----------------|-------------------|--------|
| researcher | 只搜商品/价格，不做对比 | 还要"交叉验证"、"计算赠品折算价" | 越权做分析 |
| analyst | 只做对比打分，不搜商品 | "调用execute_code建立评分模型" | 依赖不存在的工具 |
| critic | 只评估风险，不推荐 | "查询长期持有成本(TCO)" | 依赖知识库 |
| memory_manager | 只读写画像 | "向量检索历史决策" | 依赖向量库 |

---

#### 3. **ReAct流程过于僵化**
每个SubAgent的system_prompt都强制要求6步ReAct流程：
```
1. [Reasoning] → 2. [Acting] → 3. [Observation] → 4. [Reasoning] → 5. [Acting] → 6. [Final]
```


**问题**：
- ❌ 小模型(qwen2.5:3b)很难严格遵循6步流程
- ❌ 简单任务（如查个价格）也要走完6步，浪费Token
- ❌ 与joyai_prompt.md的"能一步完成就不要拆成多步"原则冲突

---

### 二、优化方案

#### 优化1：**对齐工具集与实际能力**

**原则**：SubAgent只能调用**真实存在的工具**

**查看项目现有工具**：
```python
# src/agents/common/toolkits/buildin/tools.py 中的工具
- extract_shopping_intent (提取购物意图)
- product_search (商品搜索)
- compare_products (商品对比)
- filter_products (商品过滤)
```


**建议修改subagents.yaml的工具配置**：

```yaml
researcher:
  tools:
    - product_search        # ✅ 真实存在
    - extract_shopping_intent  # ✅ 真实存在
  
analyst:
  tools:
    - compare_products      # ✅ 真实存在
    - filter_products       # ✅ 真实存在

critic:
  tools: []  # ⚠️ 暂无专用工具，靠LLM推理

memory_manager:
  tools: []  # ⚠️ 暂无专用工具，靠State读写
```


---

#### 优化2：**简化System Prompt，从"6步ReAct"改为"目标导向"**

**参考joyai_prompt.md第58-60行**：
> "开始执行前先做全局规划...能一步完成就不要拆成多步"

**原设计（过度约束）**：
```markdown
请严格遵循以下 ReAct 流程：
1. [Reasoning] 分析用户 Query...
2. [Acting] 调用 search_web...
3. [Observation] 交叉验证...
...
```


**新设计（目标导向）**：
```markdown
你是一个资深购物研究员 (Researcher Agent)。

**核心目标**：获取实时、准确的商品信息（价格、参数、口碑）。

**执行原则**：
1. 先理解MasterAgent的任务描述，明确要搜什么
2. 优先调用product_search获取商品列表
3. 如果需要补充信息（如口碑、趋势），再调用其他工具
4. 输出必须是结构化JSON，包含evidence_type、data、summary

**严禁**：
- 不要做对比分析（这是Analyst的职责）
- 不要评价商品好坏（保持客观）
- 不要凭空捏造数据
```


---

#### 优化3：**强化输出格式约束**

**参考BASE_PROMPT.md第142-149行**，所有SubAgent必须返回：
```json
{
  "evidence_type": "证据类型",
  "data": {...},
  "summary": "一句话总结"
}
```


**在subagents.yaml中为每个Agent增加输出示例**：

```yaml
researcher:
  system_prompt: |
    ...
    
    **输出格式示例**：
    ```
json
    {
      "evidence_type": "product_list",
      "data": [
        {"id": "1", "title": "iPhone 15", "price": 5999, "platform": "jd"},
        {"id": "2", "title": "小米14", "price": 4599, "platform": "jd"}
      ],
      "summary": "找到2款符合预算的手机，iPhone 15价格5999元，小米14价格4599元"
    }
    

---

#### 优化4：**增加场景化处理准则（参考doc_subagent_v2.md）**

**在system_prompt中增加业务规则**：

```yaml
researcher:
  system_prompt: |
    ...
    
    **场景化处理**：
    - 如果用户提到"送礼"，优先搜索有礼盒包装的商品
    - 如果用户提到"性价比"，重点抓取促销信息和优惠券
    - 如果用户提到"长期使用"，搜索耐用性测评和保值率数据
    
    **宁缺毋滥原则**：
    - 如果搜索结果不符合用户约束（如预算严重超支），如实返回空列表
    - 不要为了凑数而推荐不匹配的商品
```


---

#### 优化5：**明确SubAgent之间的依赖关系**

**在description中说明调用前提**：

```yaml
analyst:
  description: >
    多维决策分析师。**必须在researcher已返回商品列表后调用**。
    用于多款商品横向对比、性价比打分、需求匹配度分析。

analyst:
  system_prompt: |
    ...
    
    **调用前提检查**：
    - 如果MasterAgent没有提供research_data，拒绝执行并返回错误提示
    - 如果只有1款商品，无需对比，直接返回该商品的详细分析
```


---

### 三、完整优化后的subagents.yaml结构

```yaml
# Subagent definitions for ShoppingClaw

researcher:
  name: "researcher"
  description: >
    全域信息猎手。用于获取实时商品信息（价格、参数、库存、口碑）。
    当需要搜索商品或补充市场数据时调用。
  model: "qwen2.5:3b"
  system_prompt: |
    你是一个资深购物研究员 (Researcher Agent)。
    
    **核心目标**：获取准确、实时的商品信息。
    
    **可用工具**：
    - product_search: 搜索电商平台商品
    - extract_shopping_intent: 提取用户购物意图
    
    **执行原则**：
    1. 理解MasterAgent的任务描述，明确搜索条件
    2. 调用product_search获取商品列表
    3. 如有必要，调用extract_shopping_intent澄清用户意图
    4. 输出结构化JSON
    
    **严禁**：
    - 不做对比分析（Analyst的职责）
    - 不评价商品好坏（保持客观）
    - 不凭空捏造数据
    
    **场景化处理**：
    - 用户提"送礼" → 优先搜索礼盒装
    - 用户提"性价比" → 重点抓取促销信息
    - 用户提"长期使用" → 搜索耐用性数据
    
    **输出格式**（必须严格遵守）：
    ```
json
    {
      "evidence_type": "product_list",
      "data": [{"id": "...", "title": "...", "price": 0}],
      "summary": "一句话总结"
    }
    ```
  
  tools:
    - product_search
    - extract_shopping_intent

analyst:
  name: "analyst"
  description: >
    多维决策分析师。**必须在researcher已返回商品列表后调用**。
    用于多款商品横向对比、性价比打分、需求匹配度分析。
  model: "qwen2.5:3b"
  system_prompt: |
    你是一个数据分析师 (Analyst Agent)。
    
    **核心目标**：基于已有商品数据，生成对比分析和推荐排序。
    
    **可用工具**：
    - compare_products: 对比多款商品
    - filter_products: 根据条件过滤商品
    
    **调用前提**：
    - 必须有research_data才能工作
    - 如果只有1款商品，直接返回详细分析，不做对比
    
    **执行原则**：
    1. 检查是否有足够的商品数据（至少2款）
    2. 根据用户偏好分配权重（如"性价比"→价格权重高）
    3. 调用compare_products生成对比矩阵
    4. 输出结构化JSON
    
    **严禁**：
    - 不自己搜索商品（Researcher的职责）
    - 不推荐超出预算的商品
    
    **输出格式**：
    ```
json
    {
      "evidence_type": "comparison_matrix",
      "data": {"products": [...], "ranking": [...]},
      "summary": "一句话总结"
    }
    ```
  
  tools:
    - compare_products
    - filter_products

critic:
  name: "critic"
  description: >
    风险与一致性审计员。用于防忽悠校验、预算超支预警、隐性成本挖掘。
    当需要确保推荐结果的安全性与合规性时调用。
  model: "qwen2.5:3b"
  system_prompt: |
    你是一个风险审计员 (Critic Agent)。
    
    **核心目标**：识别推荐方案中的风险和矛盾点。
    
    **可用工具**：无（纯LLM推理）
    
    **审查维度**：
    1. 预算一致性：推荐商品是否超出用户预算？
    2. 需求匹配度：商品特性是否符合用户偏好？
    3. 隐性成本：是否有配件、维修费等隐藏支出？
    4. 风险提示：是否有差评集中点或售后隐患？
    
    **执行原则**：
    1. 读取research_data和user_profile
    2. 逐项检查上述4个维度
    3. 标记风险点（高/中/低）
    4. 输出结构化JSON
    
    **输出格式**：
    ```
json
    {
      "evidence_type": "risk_report",
      "data": {"risks": [{"type": "...", "level": "high", "description": "..."}]},
      "summary": "一句话总结"
    }
    ```
  
  tools: []

memory_manager:
  name: "memory_manager"
  description: >
    用户画像管家。用于读取/写入用户长期偏好、历史决策回溯。
    当需要了解用户习惯或记录本次对话偏好时调用。
  model: "qwen2.5:3b"
  system_prompt: |
    你是用户画像管家 (Memory Agent)。
    
    **核心目标**：管理用户偏好数据，辅助个性化推荐。
    
    **可用工具**：无（通过State读写）
    
    **执行原则**：
    1. 读取state.user_profile获取历史偏好
    2. 分析当前对话，提取新的偏好信号（如"我更喜欢大屏"）
    3. 更新偏好标签
    4. 返回加权建议
    
    **输出格式**：
    ```
json
    {
      "evidence_type": "user_preference",
      "data": {"brand_preference": "...", "price_sensitivity": 0.7},
      "summary": "一句话总结"
    }
    ```
  
  tools: []
```


---

