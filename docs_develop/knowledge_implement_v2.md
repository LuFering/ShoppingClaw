基于 `knowledge_update_v1.md` 的深度反馈，我们将方案从“理论分层”升级为**“企业级混合检索引擎”**。核心转变在于：从**串行路由**转向**并联召回 + 来源加权**，并补全了**写入侧（Write-side）**的生命周期管理。

以下是严谨、周密的二次优化方案：

### 一、 架构范式转变：并联召回模型 (Parallel Recall Model)

不再让 `hybrid_retriever` 猜用户意图，而是采用 **“广撒网、精筛选”** 策略：
1.  **Query 分发**：收到请求后，同时向 L1(FAQ)、L2(Rules)、L3/L4(Vector) 发起查询。
2.  **结果标准化**：所有 Store 返回统一的 `KnowledgeItem` 结构。
3.  **Rerank/融合**：根据来源类型（铁律 > FAQ > 经验）和语义相关性进行排序。
4.  **LLM 综合**：将 Top-K 结果作为 Context 喂给 Analyst/Critic。

---

### 二、 深度改造后的目录结构与职责

```text
src/knowledge/
├── core/
│   ├── models.py          # 定义 KnowledgeItem (含 source_type, validity_period)
│   └── retriever_base.py  # 统一检索接口 (async def retrieve)
├── stores/
│   ├── faq_store.py       # L1: 内存字典 + Embedding 兜底 (弃用 Levenshtein)
│   ├── rule_engine.py     # L2: 结构化字段匹配 (弃用 SQL LIKE)
│   └── vector_store.py    # L3/L4: ChromaDB + Metadata Filtering
├── fusion/
│   └── result_fuser.py    # 负责多路结果的冲突检测与优先级排序
├── lifecycle/             # 【新增】写入侧管理
│   ├── version_manager.py # 规则版本控制与失效处理
│   └── index_updater.py   # 向量库的增量更新 (Upsert/Delete)
└── manager.py             # 对外暴露的唯一入口
```


---

### 三、 关键模块优化逻辑

#### 1. 核心数据契约 (`core/models.py`)
用 `source_type` 替代模糊的 `confidence`：
*   `OFFICIAL_POLICY`: 平台官方规则（权重最高，不可篡改）。
*   `OPERATIONAL_RULE`: 运营配置的风控/黑名单（权重高）。
*   `DECISION_FRAMEWORK`: 品类决策标准文档（权重中，供参考）。
*   `USER_EXPERIENCE`: 真实数据沉淀的经验（权重中低，需标注“基于历史数据”）。

#### 2. L2 规则引擎重构 (`stores/rule_engine.py`)
**问题**：SQL LIKE 无法处理条件分支和用语多样性。
**方案**：结构化存储 + 逻辑匹配。
*   **表结构**：`rules (trigger_keywords[], applicable_category, condition_logic, action_content)`
*   **检索逻辑**：
    1.  先通过 `applicable_category` 过滤。
    2.  检查 Query 是否命中 `trigger_keywords` 集合。
    3.  如果命中，返回结构化的 `action_content`（如：`{"limit": "7天", "condition": "未激活"}`），而不是大段文本。

#### 3. L1 FAQ 中文适配 (`stores/faq_store.py`)
**问题**：Levenshtein 距离在中文下失效。
**方案**：**双层检索**。
*   **第一层**：精确 Key 匹配（速度最快）。
*   **第二层**：使用轻量级 Embedding 模型（如 `bge-m3` 或 Ollama 的 `nomic-embed-text`）计算余弦相似度。
*   **阈值判定**：只有相似度 > 0.85 才认为是有效匹配，否则返回空。

#### 4. 写入侧生命周期 (`lifecycle/`)
这是企业级系统的灵魂：
*   **版本管理**：每条规则增加 `version_id` 和 `is_active` 标记。更新时不是覆盖，而是插入新版本并将旧版本标记为 `inactive`。
*   **增量索引**：`index_updater.py` 提供 `upsert_document(doc_id, content)` 方法。当 Markdown 文档修改时，自动计算 Chunk 差异，只更新变化的向量块，避免全量重建。

---

### 四、 实施路线图 (TODOLIST - 修正版)

#### Phase 1: 接口定义与基础存储 (Foundation)
*   [ ] 定义 `KnowledgeItem` 数据类，明确 `source_type` 枚举。
*   [ ] 实现 `rule_engine.py`，完成结构化规则的增删改查。
*   [ ] 实现 `faq_store.py`，集成 Embedding 模型进行语义兜底。

#### Phase 2: 并联召回与融合 (Fusion Engine)
*   [ ] 开发 `result_fuser.py`：实现多路结果的合并逻辑。
    *   *逻辑示例*：如果 L2 返回了“禁止退货”的铁律，则直接丢弃 L3 中关于“如何退货”的建议。
*   [ ] 完善 `manager.py`，实现 `query_knowledge(query, category)` 的并联调用。

#### Phase 3: 向量库专业化与写入侧 (Vector & Lifecycle)
*   [ ] 优化 `vector_store.py`，实现按 Markdown 标题分块的 Indexer。
*   [ ] 编写 `lifecycle/index_updater.py`，实现向量库的 Upsert 功能。
*   [ ] 建立 `docs/decision_frameworks/` 目录，录入第一批品类决策标准。

#### Phase 4: Agent 联调 (Integration)
*   [ ] 在 `subagents.yaml` 中配置工具。
*   [ ] **Prompt 注入**：在 Analyst 的 Prompt 中增加：“你必须优先遵循 `source_type: OFFICIAL_POLICY` 的内容；对于 `USER_EXPERIENCE`，请在回复中注明‘根据过往用户反馈’。”

---

### 五、 风险提示与应对

1.  **冲突处理**：当 FAQ 说“可以退”，规则库说“不能退”时怎么办？
    *   *应对*：在 `result_fuser.py` 中硬编码优先级：`OFFICIAL_POLICY > OPERATIONAL_RULE > FAQ`。
2.  **Embedding 成本**：每次查 FAQ 都跑 Embedding 会慢吗？
    *   *应对*：FAQ 数量通常在几百条以内，内存计算余弦相似度极快。如果量大，可对 FAQ 预先计算好向量存入 Redis。
3.  **冷启动问题**：刚开始没有经验结论怎么办？
    *   *应对*：在 Prompt 中引导 Agent：“如果知识库中没有相关经验结论，请基于通用逻辑推理，并诚实告知用户缺乏历史数据支撑。”

这个方案修正了路由过于理想化、中文适配差、写入侧缺失等致命伤，符合企业级开发的稳健性要求。是否需要我针对某个具体模块（如 `rule_engine` 的结构化设计）给出代码片段？