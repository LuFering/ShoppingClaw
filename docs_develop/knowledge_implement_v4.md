我需要先查看 Yuxi-Know 项目的 knowledge 实现，然后结合两个设计文档给出融合方案。




**已查看目录** 9 个结果

**已查看文件** *base.py 1-100*

**已查看文件** *manager.py*

**已查看文件** *factory.py*


现在查看 ShoppingClaw 现有的 knowledge 结构：




**查看文件失败** *__init__.py*

**查看目录失败**

**已查看目录** 10 个结果


明白了，ShoppingClaw 项目目前**没有 knowledge 模块**。基于两个设计文档和 Yuxi-Know 的实现，我给出严谨的融合方案：

## ShoppingClaw Knowledge 模块融合方案

### 一、架构决策（基于 knowledge.md + knowledge_implement_v3.md）

#### 核心原则
1. **不照搬 Yuxi-Know 的文件管理逻辑**（那是给前端用的复杂知识库系统）
2. **采用 v3 的轻量级向量检索架构**（服务于 Agent 的知识增强）
3. **五类知识分轨存储**（knowledge.md 的核心洞见）

#### 技术选型
- **向量库**: ChromaDB（轻量、易部署，适合语义检索）
- **规则引擎**: 内存字典 + 精确匹配（平台规则/风控黑名单）
- **FAQ 库**: SQLite（精确优先+语义兜底）
- **不使用**: Milvus/LightRAG（过度工程化，ShoppingClaw 不需要多租户/文件上传功能）

---

### 二、目录结构设计

```
src/knowledge/
├── __init__.py                    # 初始化与导出
├── core/
│   ├── __init__.py
│   ├── models.py                  # KnowledgeItem, SourceType
│   └── retriever_base.py          # RetrieverBase 接口
├── stores/
│   ├── __init__.py
│   ├── vector_store.py            # ChromaDB 封装（frameworks/experiences）
│   ├── rule_engine.py             # 规则引擎（policies/risk_control）
│   └── faq_store.py               # FAQ 数据库（SQLite）
├── fusion/
│   ├── __init__.py
│   └── result_fuser.py            # 结果融合器（来源前缀注入）
├── indexers/
│   ├── __init__.py
│   └── markdown_indexer.py        # Markdown 分块索引器
├── lifecycle/
│   ├── __init__.py
│   ├── doc_manager.py             # 文档生命周期（删旧建新）
│   └── eval_monitor.py            # 质量监控（Hit Rate/Bad Case）
└── manager.py                     # 统一入口：query_knowledge()
```


---

### 三、实施步骤（TODOLIST）

#### Phase 1: 基础架构搭建（1-2天）

**Step 1.1: 添加依赖**
```toml
# pyproject.toml
dependencies = [
    "chromadb>=0.4.24",  # 向量检索
    # SQLite 是 Python 内置，无需额外安装
]
```


**Step 1.2: 创建核心数据模型**
- `core/models.py`: 
  - `SourceType` 枚举（POLICY/RISK_CONTROL/FRAMEWORK/EXPERIENCE/FAQ）
  - `KnowledgeItem` 数据类（content/source_type/doc_id/category/tags/metadata）
  
- `core/retriever_base.py`:
  - `RetrieverBase` 抽象基类（retrieve/add/delete 接口）

**Step 1.3: 实现三个存储后端**
1. `stores/vector_store.py`: ChromaDB 封装
   - 两个集合：`frameworks`（决策框架）、`experiences`（经验结论）
   - 支持 category 过滤、source_type 标记
   
2. `stores/rule_engine.py`: 规则引擎
   - 内存字典存储：`{category: {rule_id: rule_content}}`
   - 精确匹配方法：`match_rule(category, keywords)`
   - 支持生效日期/失效日期
   
3. `stores/faq_store.py`: FAQ 数据库
   - SQLite 表结构：`(id, question, answer, category, embedding)`
   - 两层检索：精确匹配 → 语义兜底

---

#### Phase 2: 检索与融合引擎（1天）

**Step 2.1: 实现结果融合器**
- `fusion/result_fuser.py`:
  - 按来源类型排序（POLICY > RISK_CONTROL > FRAMEWORK > FAQ > EXPERIENCE）
  - 注入来源前缀（【官方铁律】【风控警告】【决策标准】【常见问题】【历史反馈】）
  - 冲突检测（同一品类多条政策时标注版本差异）

**Step 2.2: 实现 Markdown 索引器**
- `indexers/markdown_indexer.py`:
  - 按标题分块（H1/H2/H3）
  - 自动提取元数据（category/tags/type）
  - 生成 chunk_id

---

#### Phase 3: 生命周期管理（1天）

**Step 3.1: 文档管理器**
- `lifecycle/doc_manager.py`:
  - `add_document()`: 先 delete_by_doc_id() 再 upsert
  - `delete_document()`: 清理所有相关 chunks
  - `batch_import()`: 从目录批量导入

**Step 3.2: 评估监控器**
- `lifecycle/eval_monitor.py`:
  - `log_retrieval()`: 记录每次检索（query/result_count/latency/hit_or_miss）
  - `log_bad_case()`: 人工标记错误案例
  - `generate_report()`: 生成 Hit Rate 统计报告

---

#### Phase 4: 统一入口集成（1天）

**Step 4.1: 实现 Manager**
- `manager.py`:
  ```python
  class KnowledgeManager:
      def __init__(self, work_dir: str):
          self.vector_store = VectorStore(work_dir)
          self.rule_engine = RuleEngine()
          self.faq_store = FAQStore(work_dir)
          self.doc_manager = DocManager(...)
          self.eval_monitor = EvalMonitor(...)
          self.result_fuser = ResultFuser()
      
      async def query_knowledge(
          self,
          query: str,
          category: str | None = None,
          source_types: list[str] | None = None,
          top_k: int = 5,
      ) -> str:
          # 1. 并行检索三个存储
          # 2. 合并结果并按优先级排序
          # 3. 融合为自然语言格式
          # 4. 记录检索日志
  ```


**Step 4.2: 注册到全局**
- `src/knowledge/__init__.py`:
  ```python
  from .manager import KnowledgeManager
  
  knowledge_manager = KnowledgeManager(work_dir="./data/knowledge")
  await knowledge_manager.initialize()
  ```


---

#### Phase 5: Agent 对接（1天）

**Step 5.1: 在 Analyst Prompt 中注入知识**
```python
# src/agents/subagents/analyst_agent.py

async def build_prompt(state: AnalystState):
    # 检索相关知识
    knowledge = await knowledge_manager.query_knowledge(
        query=state.user_query,
        category=state.category,
        source_types=["policy", "framework"],
    )
    
    prompt = f"""
你是购物分析专家。

【知识库上下文】
{knowledge}

【重要约束】
- 回答涉及政策问题时，必须引用【官方铁律】原文
- 严禁自行发挥或编造不存在的规则
- 如知识库为空，明确告知用户

用户问题：{state.user_query}
"""
```


**Step 5.2: 在 Critic 中注入风控知识**
```python
# src/agents/subagents/critic_agent.py

async def check_risks(state: CriticState):
    risks = await knowledge_manager.query_knowledge(
        query=f"{state.product_name} 风险检查",
        category=state.category,
        source_types=["risk_control"],
    )
    # 检测是否命中黑名单/高风险特征
```


---

### 四、关键设计细节

#### 1. 五类知识的存储映射

| 知识类型 | 存储后端 | 检索方式 | 示例 |
|---------|---------|---------|------|
| POLICY（平台规则） | RuleEngine（内存） | 精确匹配 | "7天无理由退货" |
| RISK_CONTROL（风控） | RuleEngine（内存） | 精确匹配 | "某品牌假货黑名单" |
| FRAMEWORK（决策框架） | VectorStore（ChromaDB） | 语义检索 | "学生党手机选购标准" |
| EXPERIENCE（经验结论） | VectorStore（ChromaDB） | 语义检索 | "小米售后难打通" |
| FAQ（高频问答） | FAQStore（SQLite） | 精确→语义 | "怎么申请退款" |

#### 2. 检索流程（全量并联）

```
用户查询："手机能退货吗？"
    ↓
并行检索：
  ├─ RuleEngine.match("退货", category="手机") → 【官方铁律】未激活支持7天退货
  ├─ VectorStore.retrieve("退货政策", category="手机") → 【历史反馈】部分用户反映...
  └─ FAQStore.search("怎么退货") → （未命中）
    ↓
ResultFuser 融合：
  【官方铁律】未激活商品支持7天无理由退货。
  【历史反馈】部分用户反映该品牌售后电话难打通。
    ↓
返回给 Analyst
```


#### 3. 数据来源规范

- **POLICY/RISK_CONTROL**: 运营团队手动录入（Markdown 文件或后台表单）
- **FRAMEWORK**: 基于行业研究 + LLM 辅助生成（需人工审核）
- **EXPERIENCE**: 从真实交易数据挖掘（好评/差评/退货原因统计）
- **FAQ**: 客服工单系统导出 + 人工整理

**严禁**: 直接用 LLM 生成经验结论并固化（knowledge.md 明确警告）

---

### 五、与 Yuxi-Know 的差异对比

| 维度 | Yuxi-Know | ShoppingClaw（本方案） |
|-----|-----------|---------------------|
| 定位 | 企业级知识库系统（带前端UI） | Agent 知识增强模块 |
| 复杂度 | 多租户/文件上传/权限管理 | 单应用/纯 API |
| 存储 | Milvus/LightRAG/Dify 多后端 | ChromaDB + SQLite + 内存 |
| 检索 | 文件级管理 + 向量检索 | 知识项级检索 |
| 适用场景 | 文档管理系统 | LLM Agent 上下文增强 |

**核心取舍**: 放弃 Yuxi-Know 的文件管理复杂性，聚焦于"快速检索 → 注入 Prompt"这一核心链路。

---

### 六、验证清单

开发完成后需验证：

1. ✅ 模糊查询能命中（"买错了咋整" → "退货政策"）
2. ✅ 品类过滤有效（查"手机"不返回"笔记本"的规则）
3. ✅ 来源前缀正确显示（【官方铁律】等）
4. ✅ 规则更新后立即可见（删旧建新策略）
5. ✅ Hit Rate 日志正常记录
6. ✅ Analyst 能正确引用知识库内容

---

这个方案结合了：
- **knowledge.md** 的五类知识分轨存储思想
- **knowledge_implement_v3.md** 的全量并联召回 + 文本前置标注
- **Yuxi-Know** 的工程化经验（但做了大幅简化）

是否需要我开始按这个方案编写代码？