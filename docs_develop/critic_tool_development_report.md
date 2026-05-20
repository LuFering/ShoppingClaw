# Critic Agent 知识库工具开发完成报告

## 一、已完成工作

### 1.1 工具层开发

**文件结构**：
```
src/agents/common/toolkits/critic/
├── __init__.py          # 导出query_risk_policy
├── schemas.py           # QueryRiskPolicyInput输入模型
└── tools.py             # query_risk_policy工具实现
```

**核心工具**：`query_risk_policy`

**功能特性**：
- ✅ 支持4种风险类型检索：authenticity（正品）、after_sales（售后）、price_fraud（价格欺诈）、quality（质量）
- ✅ 自动映射英文风险类型为中文查询词，提高检索精准度
- ✅ 只检索高优先级知识源：policy（官方政策）+ risk_control（风控规则）
- ✅ 完整的日志记录和错误处理
- ✅ Pydantic Schema验证输入参数

**代码位置**：
- 工具定义：`src/agents/common/toolkits/critic/tools.py:18-63`
- 输入Schema：`src/agents/common/toolkits/critic/schemas.py:5-18`

### 1.2 SubAgent配置更新

**文件**：`src/agents/subagents/subagents.yaml`

**修改内容**：
1. 为critic添加tools列表：`tools: [query_risk_policy]`
2. 在system_prompt中新增"## 可用工具"章节（第356-370行）
   - 说明工具参数和返回值
   - 列出4种使用场景
   - 明确调用原则（客观规则用工具，主观判断靠经验）

### 1.3 工具注册集成

**文件**：`src/agents/master_agent/graph.py`

**修改内容**：
- 第23-24行：导入analyst和critic工具模块，触发@tool装饰器注册
```python
import src.agents.common.toolkits.analyst.tools
import src.agents.common.toolkits.critic.tools
```

**修复问题**：
- 修正`src/agents/common/toolkits/analyst/__init__.py`的导出函数名（原导出名称与实际不符）

### 1.4 验证测试

**测试脚本**：`test/test_critic_simple.py`

**验证结果**：✅ 全部通过
- ✅ 文件存在性：3个文件全部创建
- ✅ 工具定义：包含完整函数、装饰器、category标记
- ✅ 知识库集成：调用knowledge_manager，source_types正确
- ✅ YAML配置：tools列表和Prompt说明已添加
- ✅ Graph导入：critic和analyst工具均已导入

---

## 二、技术实现细节

### 2.1 工具设计思路

**与Analyst工具的对比**：

| 维度 | Analyst (query_category_knowledge) | Critic (query_risk_policy) |
|------|-----------------------------------|---------------------------|
| **知识类型** | framework + experience（决策标准+经验结论） | policy + risk_control（官方政策+风控规则） |
| **检索目标** | "专家级建议"：选购维度、避坑指南 | "铁律"：硬性规则、黑名单、保修条款 |
| **查询构造** | `{category} 选购标准 {focus_area}` | `{product_name} {category} {risk_type映射}` |
| **使用场景** | 横向对比时的专业依据 | 风险评估时的客观证据 |

**关键设计点**：
1. **风险类型映射**：将英文枚举值转换为中文查询词，提升向量检索命中率
   ```python
   risk_type_map = {
       "authenticity": "正品 真假 翻新",
       "after_sales": "售后 退换货 保修",
       ...
   }
   ```

2. **严格过滤来源**：只查`["policy", "risk_control"]`，避免FAQ噪音干扰风控判断

3. **容错处理**：知识库无结果时返回友好提示，引导Critic基于经验推理

### 2.2 输出格式约定

工具返回的是纯文本字符串（知识库检索结果），Critic需要在自己的输出JSON中引用：

```json
{
  "evidence_type": "risk_report",
  "data": {
    "risks": [
      {
        "item_id": "SKU_12345",
        "dimension": "售后可行性",
        "level": "yellow",
        "description": "该商品不支持7天无理由退货（来源：query_risk_policy返回的平台规则第2条）",
        "basis": "evidence_based",
        "source": "query_risk_policy"  // 可选：标注数据来源
      }
    ],
    ...
  }
}
```

---

## 三、后续待办事项

### 3.1 GapDetector增强（优先级：高）

**文件**：`src/services/gap/service.py`

**任务**：增加Critic触发规则

```python
# 建议在detect_gaps方法中添加：

# 规则1：高价商品强制审核
if research_data and any(p.get("price", 0) > 5000 for p in research_data):
    if not evidence.get("risk_audit"):
        gaps.append("risk_audit")

# 规则2：用户询问可靠性
if any(kw in user_query for kw in ["靠谱", "真假", "正品", "翻新"]):
    if not evidence.get("risk_audit"):
        gaps.append("authenticity_check")

# 规则3：售后类意图（已有）
if intent_type == "after_sales":
    if not evidence.get("risk_audit"):
        gaps.append("risk_audit")
```

### 3.2 单元测试（优先级：中）

**文件**：`tests/test_critic_tool.py`

**测试用例**：
1. 工具注册验证（已通过简单脚本验证）
2. Mock知识库返回，测试query_risk_policy的输出格式
3. 测试不同risk_type参数的查询词构造逻辑
4. 测试知识库为空时的降级处理

### 3.3 端到端测试（优先级：中）

**文件**：`tests/test_workflow_with_critic.py`

**测试场景**：
```python
def test_critic_identifies_after_sales_risk():
    """测试Critic能识别售后风险"""
    # 构造场景：用户询问iPhone 15，知识库中有"不支持7天退货"的规则
    # 验证Critic输出中包含yellow或red级别的售后风险
```

### 3.4 监控与日志（优先级：低）

**任务**：
- 统计Critic调用频率
- 记录工具调用次数（避免过度调用）
- 统计红灯风险触发率

---

## 四、架构一致性验证

### 4.1 符合设计规范

✅ **职责边界清晰**：
- Critic不搜索商品（Researcher的职责）
- Critic不做推荐替换（Analyst的职责）
- Critic只指出风险，由MasterAgent决定是否采纳

✅ **工具隔离原则**：
- Critic工具category="critic"，不会被MasterAgent直接调用
- 只能通过SubAgentMiddleware调度给critic子智能体

✅ **输出协议统一**：
- 遵循`{evidence_type, data, summary}`三段式结构
- EvidenceCollector能正确映射到state.risk_audit

### 4.2 与现有模块协调

✅ **知识库复用**：
- 共用`knowledge_manager.query_knowledge()`接口
- 通过source_types参数区分不同Agent的知识需求

✅ **GapDetector集成**：
- FeatureExtractor已支持统计红灯数量（第77-80行）
- service.py已有售后类意图的risk_audit缺口检测（第108-111行）

✅ **State字段完备**：
- context.py第73行已定义`risk_audit: Optional[Dict]`
- EvidenceCollector第61行已映射`"risk_report": "risk_audit"`

---

## 五、验收标准达成情况

| 验收项 | 状态 | 说明 |
|--------|------|------|
| 工具代码实现 | ✅ 完成 | query_risk_policy完整实现 |
| Schema定义 | ✅ 完成 | QueryRiskPolicyInput含完整字段描述 |
| YAML配置 | ✅ 完成 | tools列表和Prompt说明已添加 |
| 工具注册 | ✅ 完成 | graph.py已导入，@tool装饰器生效 |
| 知识库集成 | ✅ 完成 | 调用knowledge_manager，source_types正确 |
| 文件结构 | ✅ 完成 | critic目录结构与analyst一致 |
| 验证测试 | ✅ 完成 | test_critic_simple.py全部通过 |
| GapDetector扩展 | ⏳ 待办 | 需增加高价商品和关键词触发规则 |
| 单元测试 | ⏳ 待办 | 需编写pytest测试用例 |
| 端到端测试 | ⏳ 待办 | 需构造完整工作流测试场景 |

---

## 六、关键技术决策记录

### 决策1：为什么只查policy和risk_control？

**理由**：
- Critic需要的是"铁律"，不是"建议"
- FAQ和experience可能互相矛盾，不适合作为风控依据
- policy和risk_control是平台官方规则，具有强制性

**影响**：
- 如果知识库中某品类缺少policy数据，Critic会收到空结果
- 此时Critic应基于经验推理，并标注`basis="experience_based"`

### 决策2：为什么risk_type是Optional？

**理由**：
- 有时Critic只需要通用风控信息，不指定具体类型
- 保持灵活性，让LLM根据上下文决定是否需要细化

**示例**：
- `risk_type=None` → 查询"iPhone 15 智能手机"的所有一般规则
- `risk_type="after_sales"` → 精准查询"iPhone 15 智能手机 售后 退换货 保修"

### 决策3：为什么不直接在Prompt中硬编码规则？

**理由**：
- 规则会频繁更新（如平台政策调整）
- 硬编码会导致每次更新都要改Prompt并重新部署
- 知识库可以动态更新，Agent无需重启

**优势**：
- 解耦业务规则和Agent逻辑
- 支持A/B测试不同规则版本
- 便于审计和追溯规则变更历史

---

## 七、下一步行动建议

**立即执行**（今天）：
1. ✅ 已完成工具开发和基础验证
2. ⏳ 在PyCharm中运行完整应用，验证Critic能否成功调用工具
3. ⏳ 准备一些测试数据（policy/risk_control类型的知识条目）

**本周内完成**：
1. 实现GapDetector增强规则（约0.3天）
2. 编写单元测试（约0.5天）
3. 手动测试3-5个典型场景（约0.5天）

**下周计划**：
1. 端到端集成测试
2. 性能监控和日志完善
3. 根据测试结果优化Prompt和工具调用策略

---

## 八、总结

Critic Agent的知识库工具开发已按方案完成，核心成果：

1. **工具层**：实现了`query_risk_policy`，支持4种风险类型检索
2. **配置层**：更新了subagents.yaml，添加了工具说明和调用指引
3. **集成层**：在graph.py中完成工具注册，确保启动时可用
4. **验证层**：通过自动化脚本验证所有配置项正确

当前状态：**可进入测试阶段**

下一步重点：补充GapDetector规则和编写测试用例，确保上线后稳定运行。
