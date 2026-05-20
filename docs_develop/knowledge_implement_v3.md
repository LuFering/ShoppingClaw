基于 `knowledge_update_v2.md` 的深度反馈，我们进入**企业级落地版（v3）**。这一版的核心在于：**放弃过度工程化的“智能路由”，转向“全量并联 + 语义增强 + 文本前置标注”**，并补全了**质量评估闭环**。

以下是严谨、周密的最终优化方案：

### 一、 架构范式：全量并联召回 (Full Parallel Recall)
不再区分 L1/L2/L3 的检索路径差异，统一采用 **“向量化底座 + 来源加权”** 模式。

*   **逻辑转变**：所有的知识（FAQ、规则、决策标准）都存入向量库，但通过 `source_type` 和 `metadata` 进行物理或逻辑隔离。
*   **优势**：彻底解决关键词匹配漏词、中文编辑距离失效的问题。用户说“买错了咋整”也能精准命中“退货政策”。

---

### 二、 深度改造后的目录结构

```text
src/knowledge/
├── core/
│   ├── models.py          # KnowledgeItem: content, source_type, doc_id, tags
│   └── retriever_base.py  # 定义 retrieve(query, filter_meta) 接口
├── stores/
│   ├── unified_vector_store.py # 核心存储：ChromaDB，支持多集合管理
│   └── rule_validator.py  # 【新增】规则一致性校验工具（离线运行）
├── fusion/
│   └── result_fuser.py    # 负责冲突标记与自然语言前缀注入
├── lifecycle/
│   ├── doc_manager.py     # 文档版本控制与按文档粒度的全量重建
│   └── eval_monitor.py    # 【新增】检索质量监控（命中率/Bad Case记录）
├── indexers/
│   └── markdown_indexer.py # 按标题分块，自动提取 category metadata
└── manager.py             # 唯一入口：query_knowledge(query, category)
```


---

### 三、 关键模块优化逻辑 (v3 核心)

#### 1. 统一向量存储 (`stores/unified_vector_store.py`)
**设计原则**：所有知识入库时强制携带 `source_type`。
*   **Collection 划分**：
    *   `policies`: 存平台规则、风控黑名单（权重最高）。
    *   `frameworks`: 存品类决策标准（权重中）。
    *   `experiences`: 存用户经验结论（权重低）。
*   **检索逻辑**：
    ```python
    def retrieve(query, category=None, top_k=5):
        # 1. 并行查询不同 Collection
        policy_res = policies_col.query(query, filter={"category": category})
        framework_res = frameworks_col.query(query, filter={"category": category})
        
        # 2. 合并结果并按 source_type 排序
        return merge_and_rank([policy_res, framework_res])
    ```


#### 2. 融合器自然语言化 (`fusion/result_fuser.py`)
**解决 v2 痛点**：LLM 忽略元数据字段。
*   **实现逻辑**：在返回给 Agent 之前，将结构化数据转为带前缀的文本块。
*   **输出示例**：
    > “【官方铁律】未激活商品支持7天无理由退货。  
    > 【历史反馈】部分用户反映该品牌售后电话难打通，建议优先使用在线客服。”

#### 3. 写入侧：按文档全量重建 (`lifecycle/doc_manager.py`)
**解决 v2 痛点**：增量索引复杂度太高。
*   **流程**：
    1.  监测到 `docs/policies/return_policy.md` 修改。
    2.  调用 `delete_by_doc_id("return_policy")` 清除旧 Chunk。
    3.  重新分块并 `upsert` 新 Chunk。
*   **优势**：代码量少，不会出现“边界偏移”导致的脏数据。

#### 4. 质量评估机制 (`lifecycle/eval_monitor.py`)
**企业级必选项**：
*   **Hit Rate 监控**：记录每次检索是否有有效返回。
*   **Bad Case 收集**：提供一个简单的 API，允许人工标记“某次回答错误是因为知识库没查到”。
*   **定期审计**：每月运行一次脚本，检查 `policies` 集合中是否存在过期的 `is_active=False` 条目。

---

### 四、 实施路线图 (TODOLIST - 最终版)

#### Phase 1: 统一底座搭建 (Foundation)
*   [ ] 实现 `unified_vector_store.py`，完成 ChromaDB 的多集合初始化。
*   [ ] 编写 `markdown_indexer.py`，实现按标题分块并自动提取 `category`。
*   [ ] 录入第一批数据：5条 FAQ、3条退货规则、2个手机品类决策框架。

#### Phase 2: 检索与融合引擎 (Retrieval & Fusion)
*   [ ] 开发 `result_fuser.py`，实现“来源前缀注入”逻辑。
*   [ ] 完善 `manager.py`，实现并联召回与结果合并。
*   [ ] **联调测试**：输入模糊 Query（如“这玩意儿能退吗”），验证是否能命中规则库。

#### Phase 3: 写入侧与生命周期 (Lifecycle)
*   [ ] 实现 `doc_manager.py` 的“删旧建新”逻辑。
*   [ ] 建立 `docs/` 目录规范，明确不同知识类型的存放位置。

#### Phase 4: 评估与 Agent 对接 (Eval & Integration)
*   [ ] 部署 `eval_monitor.py`，开始记录检索日志。
*   [ ] 更新 Analyst/Critic 的 Prompt，强调对“【官方铁律】”的绝对服从。
*   [ ] 进行 Bad Case 专项测试，优化分块策略。

---

### 五、 风险提示与应对

1.  **向量库噪音**：如果 Query 太短（如“手机”），可能召回大量无关内容。
    *   *应对*：在 `manager.py` 中增加**重排序（Rerank）**环节，或者要求 Agent 在调用工具时必须提供 `category` 过滤条件。
2.  **规则冲突**：当两条官方政策矛盾时怎么办？
    *   *应对*：在 `doc_manager.py` 中引入 `effective_date`（生效日期）。融合器优先返回生效日期最新的条目，并将旧条目作为背景信息附带。
3.  **Agent 幻觉**：即使有前缀，LLM 仍可能瞎编。
    *   *应对*：在 Prompt 中加入**思维链约束**：“在回答任何涉及政策的问题前，必须先引用检索到的【官方铁律】原文，严禁自行发挥。”

这个方案修正了规则匹配的脆弱性，简化了写入侧的工程负担，并补全了质量监控，是目前最符合企业开发思路且具备高可行性的版本。是否需要我针对 `unified_vector_store.py` 给出基础的类结构设计？