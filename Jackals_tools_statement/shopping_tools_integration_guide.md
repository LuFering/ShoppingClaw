# MasterAgent 工具极简接入指南

这篇指南帮助你用两行代码，把本地工具和远程 MCP 工具无缝接入 `MasterAgent`。

## 1. 接入代码示例

你可以在 `MasterAgent.get_graph` 或者你的初始化函数中运行以下逻辑：

```python
import asyncio
from src.agents.common.toolkits import get_all_tool_instances
from src.services.mcp_service import get_tools_from_all_servers
from src.services.mcp_tool_adapter import adapt_mcp_tools_sync

# 1. 拿到所有本地注册的工具（包含搜索、过滤、对比）
local_tools = get_all_tool_instances()

# 2. 从远端拉取 MCP 工具描述，并转换为 LangChain 工具（包含库存查询等）
# 这里为了方便直接集成到现有的同步构图中，提供了一个同步的 adapt 接口
mcp_specs = asyncio.run(get_tools_from_all_servers())
mcp_tools = adapt_mcp_tools_sync(mcp_specs)

# 3. 合并所有工具
all_available_tools = local_tools + mcp_tools
```

## 2. 你的实际接入点

在 `src/agents/master_agent/graph.py` 的第 96 行左右：

```python
    async def get_graph(self, **kwargs):
        # ... 前面的代码 ...
        
        # ⚠️ 新增：拉取 MCP 工具并合并本地工具
        from src.services.mcp_service import get_tools_from_all_servers
        from src.services.mcp_tool_adapter import adapt_mcp_tools_sync
        
        mcp_specs = await get_tools_from_all_servers()
        all_tools = await self.get_tools() + adapt_mcp_tools_sync(mcp_specs)
        
        # 调用工厂函数创建 graph
        graph = create_master_agent(
            model=model,
            tools=all_tools,  # ⚠️ 解开注释，传入 all_tools
            # middleware=[... 其他中间件先不管 ...]
        )
        
        return graph
```

## 3. 注意事项
- 所有工具内部已经做了容错处理（不抛异常，而是返回带 `error` 的 `dict`）。
- 发生错误时，大模型会拿到异常信息并自动重试或告知用户，无需你在图节点外部做额外拦截。
