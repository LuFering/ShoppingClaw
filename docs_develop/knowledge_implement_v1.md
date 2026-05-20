基于 `docs_develop/knowledge.md` 的核心原则（分层存储、分类检索、拒绝权重固化）以及现有的 `src/knowledge` 目录结构，我为你制定了以下深度改造方案。

### 一、 现状诊断与核心问题
目前的 `src/knowledge` 结构偏向于**通用 RAG 框架**（支持 LightRAG, Milvus, Dify），缺乏针对“电商导购”场景的**业务逻辑分层**。
*   **缺失点 1**：没有区分“精确匹配”（规则/FAQ）和“语义检索”（决策标准）。
*   **缺失点 2**：缺少结构化数据库（SQLite/PostgreSQL）的集成，无法处理硬性风控规则。
*   **缺失点 3**：`chunking` 模块过于通用，没有针对“品类决策框架”或“经验结论”进行专门的解析优化。

---

### 二、 目标架构设计：五层知识引擎
我们将知识库从单一的向量库升级为 **“混合知识引擎 (Hybrid Knowledge Engine)”**：

| 层级 | 知识类型 | 存储介质 | 检索策略 | 对应代码模块 |
| :--- | :--- | :--- | :--- | :--- |
| **L1** | 高频问答 (FAQ) | JSON / Redis | 字符串精确匹配 | `retrievers/exact_match.py` |
| **L2** | 平台规则/风控 | SQLite / PG | SQL 关键词过滤 | `stores/rule_store.py` |
| **L3** | 品类决策标准 | ChromaDB | 向量语义检索 | `stores/vector_store.py` |
| **L4** | 经验结论/评测 | ChromaDB | 向量语义检索 | `stores/vector_store.py` |
| **L5** | 实时商品数据 | API / Cache | 动态调用 | `tools/product_search.py` |

---

### 三、 目录结构重构方案
建议在 `src/knowledge` 下建立以下新结构：

```text
src/knowledge/
├── core/                  # 核心接口定义
│   ├── base_retriever.py  # 统一检索接口
│   └── knowledge_types.py # 定义五类知识的枚举
├── stores/                # 存储实现
│   ├── rule_store.py      # L2: 规则与风控 (SQLite)
│   ├── vector_store.py    # L3/L4: 决策标准与经验 (ChromaDB)
│   └── faq_store.py       # L1: 高频问答 (JSON/Memory)
├── retrievers/            # 检索器实现
│   ├── hybrid_retriever.py # 总调度器：路由到不同 Store
│   └── exact_match.py     # L1 精确匹配逻辑
├── indexers/              # 索引构建工具
│   ├── rule_importer.py   # 导入规则到 SQLite
│   └── doc_indexer.py     # 导入 Markdown 文档到向量库
├── chunking/              # 保持现有结构，增加电商专用解析器
│   └── ecommerce_parsers.py 
└── manager.py             # 对外暴露的统一入口
```


---

### 四、 详细改造逻辑说明

#### 1. 核心层 (`core/`)：定义“知识契约”
*   **优化点**：不再把所有东西都当作文本块。定义 `KnowledgeItem` 结构，包含 `type` (规则/决策/经验), `confidence` (置信度), 和 `source` (来源)。
*   **目的**：让 Analyst 知道它拿到的是“铁律”还是“参考建议”。

#### 2. 存储层 (`stores/`)：落实“分层存储”
*   **`rule_store.py` (L2)**：
    *   **逻辑**：使用 SQLAlchemy 操作 SQLite。
    *   **表结构**：`rules (id, category, keyword, content, strict_mode)`。
    *   **检索**：`SELECT content FROM rules WHERE keyword LIKE '%退货%'`。
*   **`vector_store.py` (L3/L4)**：
    *   **逻辑**：封装 ChromaDB。
    *   **优化**：引入 **Metadata Filtering**。例如查询时带上 `category="smartphone"`，防止搜手机决策标准时跳出冰箱的资料。
*   **`faq_store.py` (L1)**：
    *   **逻辑**：启动时加载 `faq.json` 到内存字典。
    *   **检索**：先做 Key 匹配，失败后计算 Levenshtein 距离找最相似的问法。

#### 3. 检索层 (`retrievers/`)：实现“智能路由”
*   **`hybrid_retriever.py`**：
    *   这是给 Agent 调用的唯一入口。
    *   **流程**：
        1.  接收 Query。
        2.  判断意图：如果是“怎么退款”，走 L1 (FAQ)；如果是“学生买什么手机”，走 L3 (向量)；如果是“某品牌是否假货”，走 L2 (规则)。
        3.  合并结果并标注来源。

#### 4. 索引层 (`indexers/`)：解决“数据来源”问题
*   **`doc_indexer.py`**：
    *   **逻辑**：读取 `docs/decision_frameworks/` 下的 Markdown 文件。
    *   **分块策略**：不按字符数切分，而是按 **Markdown 标题** 切分。确保“【手机-学生场景】”作为一个完整的语义块存入向量库。

---

### 五、 实施路线图 (TODOLIST)

1.  **第一阶段：基础设施搭建**
    *   [ ] 在 `src/knowledge/stores/` 下创建 `rule_store.py` 和 `faq_store.py`。
    *   [ ] 编写 `knowledge_base/rules.db` 的初始化脚本。
    *   [ ] 准备一份 `faq.json` 样例数据。

2.  **第二阶段：向量库专业化改造**
    *   [ ] 修改 `implementations/lightrag.py` 或新建 `chroma_impl.py`，增加 Metadata 过滤功能。
    *   [ ] 编写 `indexers/doc_indexer.py`，实现按标题分块的逻辑。

3.  **第三阶段：统一调度器开发**
    *   [ ] 实现 `hybrid_retriever.py`，完成从 Query 到不同 Store 的路由逻辑。
    *   [ ] 在 `manager.py` 中暴露 `query_knowledge(query, category)` 方法。

4.  **第四阶段：Agent 对接**
    *   [ ] 在 `subagents.yaml` 中为 Analyst 和 Critic 配置 `query_knowledge` 工具。
    *   [ ] 更新 Prompt，要求它们在回答时必须引用知识库的来源（如：“根据平台规则...”、“根据历史评测...”）。

### 六、 风险提示
*   **数据一致性**：规则库（L2）更新后，必须确保所有 Agent 能立即感知（建议使用内存缓存 + 定期刷新）。
*   **向量库噪音**：如果向量库内容太少，检索结果会很不准。初期建议先用 L1 和 L2 撑场面，L3/L4 随着文档积累再逐步开放。

这个方案是否符合你对“严谨、周密”的要求？如果确认，我们可以开始着手修改 `src/knowledge` 下的具体代码。