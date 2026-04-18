# ShoppingClaw - Tools & MCP 模块构建总结 (By Jackal)

本文档汇总了 `Tools & MCP` 模块的全部构建成果。该模块已完全解耦，具备高容错性，并 100% 覆盖了单元测试。

## 1. 整体架构与产出清单

### 本地购物工具 (Shopping Tools)
所有本地工具已封装在 `src/agents/common/toolkits/shopping/` 目录下，均配置了严格的 Pydantic 输入校验与 `try-except` 兜底（异常统一返回 `error` 字段，不导致大模型崩溃）。

- **`product_search`**: 跨平台商品搜索（基于 MockCrawler）
- **`product_filter`**: 多条件商品过滤（内置空列表拦截与原值退回机制）
- **`product_compare`**: 综合商品对比排序（输出带自然语言的对比报告）

### 外部扩展工具 (MCP Service)
MCP 服务用于连接外部系统工具（如库存、物流），相关代码位于 `src/services/` 下。

- **`mcp_service.py`**: 维护 `MCP_SERVERS` 注册表，实现 `get_tools_from_all_servers()`，通过 HTTP 获取远端工具的 JSON 描述（Tool Spec），内置故障服务器隔离防御。
- **`mcp_tool_adapter.py`**: 实现适配器逻辑。将拉取到的 JSON 描述通过闭包与 `StructuredTool.from_function`，动态转换为 LangChain 可直接调用的 `@tool`。

## 2. 核心设计原则

1. **防呆与容错**: 大模型传参可能出错。底层异常被拦截并转换为带有 `error` 的 `dict` 返回，Agent 会根据 `error` 自我纠正。
2. **数据防丢失**: 像 `filter` 和 `compare` 工具，如果发生计算崩溃，包装层会将输入的原商品列表退回，保证大模型的上下文不丢数据。
3. **单一职责隔离**: 本地工具的封装、MCP 的拉取、MCP 的动态转换，三者物理隔离。其中任何一部分出现网络或逻辑问题，都不会阻塞其他模块的加载。

## 3. 测试覆盖
测试代码位于 `tests/` 目录下，可直接运行验证：
- `test_search_tool.py`
- `test_filter_tool.py`
- `test_compare_tool.py`
- `test_mcp_service.py`
- `test_mcp_adapter.py`









    
































