# Jackal 工作区：构建说明书（持续更新）

目的：在 `Jackals_tools_statement/` 里记录“我在工作区内做了哪些模块改动、为什么做、入口在哪、如何验证”，便于你慢慢研究与回溯。

## 2026-05-12：合并新分支后收敛（Research 京东工具 + 统一模型入口）

- **Research 京东工具落点**：确认京东官方API+JustoneAPI 工具在 [research/tools.py](file:///d:/LFs-ShoppingClaw/src/agents/common/toolkits/research/tools.py)。
- **统一模型对外入口（兼容层）**：新增
  - [src/models/product.py](file:///d:/LFs-ShoppingClaw/src/models/product.py)
  - [src/models/state.py](file:///d:/LFs-ShoppingClaw/src/models/state.py)
  - [src/models/test_data.py](file:///d:/LFs-ShoppingClaw/src/models/test_data.py)
  让项目其他模块可以稳定使用 `src.models.*` 作为“导入入口”（减少导入路径漂移）。
- **Research 子Agent 输出收敛（候选商品列表）**：调整 `search_products` 让它返回 `products: List[Product]`（并且在没有官方SDK可用时，允许 Justone-only 产出候选集）。
- **工具层最小闭环恢复**：补齐 `src/tools/` 下的 compare/filter/search + crawler(base/mock)，保证确定性工作流/基础工具有可运行的最小实现。
- **toolkits 兼容层恢复**：新增 `src/agents/common/toolkits/shopping/`（search/filter/compare 三个工具封装），用于兼容现有测试与 MasterAgent 调用方式。
- **pytest 收集修复**：恢复 `pytest.ini`，避免误收集模板目录 `path/` 和 `test/` 下的脚本文件导致导入错误。
- **R1 输出契约（Research 搜索列表）**：把 `search_products` 的输出收敛为 `{"products": List[Product], "error": Optional[str]}`，并将京东 SDK 的 request 导入路径统一为 `src.jd.api.rest.*`，避免环境依赖导致运行失败；新增 research 搜索契约单测。
- **R1 输出契约（Research 全部入口）**：把 Research 目录下的官方/Justone 详情、图片、基础信息、批量规格等工具统一为 `{"products": List[Product], "error": Optional[str]}`；新增对应契约单测（不打真实网络）。

验证方式：
- `python -m pytest -q`（当前环境跑全量测试）

## 2026-05-14：Research 详情入口切到 internal enrich 模式

- **改动目标**：把 `Research` 内部的详情类工具从“每次重新造一个新 Product”改成“输入 `sku_id + 可选 existing_product`，在已有商品快照上做增量补全”，但对外仍保持统一返回契约 `{"products": List[Product], "error": Optional[str]}`。
- **改动位置**：
  - [research/schemas.py](file:///d:/LFs-ShoppingClaw/src/agents/common/toolkits/research/schemas.py)
  - [research/tools.py](file:///d:/LFs-ShoppingClaw/src/agents/common/toolkits/research/tools.py)
  - [product.py](file:///d:/LFs-ShoppingClaw/src/agents/common/model/product.py)
  - [test_research_other_contract.py](file:///d:/LFs-ShoppingClaw/tests/test_research_other_contract.py)
- **Research 内部 enrich 接线**：以下 4 个入口已经支持 `existing_product`，并统一走 `_enrich_product(...)`：
  - `jd_product_detail`
  - `jd_product_mobile_detail`
  - `get_product_full_detail`
  - `justone_product_full_detail`
- **这样做的原因**：
  - 搜索阶段已经拿到轻量 `Product`，详情阶段继续补充字段更符合 state 流转，不会丢失上游已确认字段。
  - Research 内部先落地 enrich，可以控制影响面，不会一口气扩散到 Analyst / Critic / 全项目。
  - 对外继续保留统一契约，现有调用方不需要重写。
- **本次补齐的模型兼容点**：
  - `Product` 新增兼容字段 `delivery_info`，并与 `express_info` 在 `model_post_init` 中双向同步。
  - 原因：Research 详情工具当前真实使用的是 `delivery_info` 语义，如果统一模型不承载，会在 enrich 时抛字段不存在错误。
- **本次新增测试重点**：
  - 旧字段保留：已有 `title / shop_name / specs / promo_tags` 不被详情阶段覆盖。
  - 新字段补全：详情阶段能补充 `specs / image_url / brand / category / after_sales_info / delivery_info / promo_info / rank_info`。
  - 外部契约不变：4 个详情入口依旧返回 `products + error`。

验证方式：
- `python -m pytest tests/test_research_other_contract.py -q`
- `python -m pytest -q`

## 2026-05-14：Master 主链路补 Evidence State Bridge

- **改动目标**：先不大改 MasterAgent 架构，只修掉多 Agent 主链路里的一个真实断点：`EvidenceCollector` 把 SubAgent 结果写到顶层标准字段，但 `SubAgentMiddleware` 在给 analyst / critic 注入前置证据时只读 `state["evidence"]`，导致上游结果可能传不到下游。
- **本次模块**：`middleware`
- **输入 state**：
  - 顶层标准字段：`research_data`、`analysis_report`、`risk_audit`、`user_profile`
  - 兼容旧结构：`evidence`
- **输出 state**：
  - 保持顶层标准字段继续存在
  - 同步维护统一的 `evidence` 视图，供 SubAgent 注入逻辑消费
- **改动位置**：
  - [evidence_collector.py](file:///d:/LFs-ShoppingClaw/src/agents/common/middleware/evidence_collector.py)
  - [subagents.py](file:///d:/LFs-ShoppingClaw/src/agents/common/middleware/subagents.py)
  - [test_evidence_bridge.py](file:///d:/LFs-ShoppingClaw/tests/test_evidence_bridge.py)
- **具体做法**：
  - `EvidenceCollectorMiddleware` 在收集 `product_list / comparison_matrix / risk_report / user_preference` 时，除了继续写顶层字段，也同步写入 `evidence[target_field]`
  - `SubAgentMiddleware` 新增统一 evidence view：优先读嵌套 `evidence`，如果没有，就从顶层标准字段动态补齐
- **为什么这样做**：
  - 改动面最小，不推翻你们当前 top-level state 设计
  - 兼容旧数据结构，降低对现有调用方的破坏
  - 先打通 `Research -> Analyst -> Critic` 的证据传递闭环，再决定要不要进一步统一 schema
- **本次测试重点**：
  - `EvidenceCollector` 能同时更新顶层字段和 `evidence`
  - `SubAgent` 注入逻辑在没有嵌套 `evidence` 时，仍能从顶层字段读取 `research_data / analysis_report`

验证方式：
- `python -m pytest tests/test_evidence_bridge.py -q`
- `python -m pytest -q`

## 2026-05-14：收口候选商品搜索入口（Unified Search Gateway）

- **改动目标**：把 `workflow / search_agent / shopping toolkit` 底层共用的候选商品搜索入口收口，不再让上层直接感知 `Research` 聚合搜索和 `crawler` fallback 的差异。
- **本次模块**：`tools`
- **输入**：
  - `query: str`
  - `platforms: List[PlatformCode] | None`
  - `limit: int`
- **输出**：
  - `List[Product]`
- **改动位置**：
  - [search_gateway.py](file:///d:/LFs-ShoppingClaw/src/tools/search_gateway.py)
  - [search.py](file:///d:/LFs-ShoppingClaw/src/tools/search.py)
  - [test_search_gateway.py](file:///d:/LFs-ShoppingClaw/tests/test_search_gateway.py)
- **具体做法**：
  - 新增 `src/tools/search_gateway.py`，内部负责统一路由：
    - `jd` 平台优先走 `Research` 的 `search_products`
    - 如果 `Research` 不可用、报错或无结果，再回退到现有 `crawler`
    - 非 `jd` 平台继续走现有 `crawler/mock`
  - `src/tools/search.py` 收薄为稳定对外入口，只保留：
    - 参数校验
    - 平台归一化
    - 调用 gateway
- **为什么这样做**：
  - 让 `search_agent` 和 `shopping_workflow` 先吃到更强的 JD 候选搜索能力
  - 不破坏现有 `Research` tool 契约，也不需要立刻重写 `jd_open_platform_client`
  - 后续如果要把真实 JD Open Platform 接成主路径，只需要替换 gateway 内部 provider，不必继续改上层节点
- **当前 fallback 策略**：
  - `jd`：Research 聚合搜索优先，失败时 crawler/mock 兜底
  - `taobao/pdd`：仍然走 crawler/mock
  - 结果在 gateway 中按 `Product.id` 去重
- **本次测试重点**：
  - `jd` 优先走 Research provider
  - Research 空结果时回退 crawler
  - 非 `jd` 平台不走 Research
  - 结果去重逻辑稳定

验证方式：
- `python -m pytest tests/test_search_gateway.py tests/test_search.py tests/test_search_tool.py tests/test_workflow.py -q`
- `python -m pytest -q`
