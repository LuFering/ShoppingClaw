import logging
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)

# ==========================================
# MCP Server Registry (MCP服务器注册表)
# ==========================================
# 这里存放所有已配置的 MCP 服务器信息。
# 现阶段我们做最小闭环（MVP），直接在内存里写死几个配置用于测试。
# 未来这些配置应该从 config.yaml 或数据库中加载。
MCP_SERVERS: Dict[str, Dict[str, Any]] = {
    # 这是一个用于本地开发的 Mock MCP 服务器配置
    "mock_inventory_mcp": {
        "url": "http://localhost:8080/mcp",
        "description": "提供商品库存和物流查询相关工具的 Mock MCP 服务",
        "type": "http", # 预留字段，标记连接类型
    }
}

def get_mcp_serve_names() -> List[str]:
    """
    获取所有已注册的 MCP 服务器名称。
    
    返回:
        服务器名称列表，例如 ["mock_inventory_mcp"]
    """
    return list(MCP_SERVERS.keys())

async def _fetch_tools_from_server(server_name: str, server_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    从单个 MCP 服务器拉取工具列表的 spec（元数据描述）。
    
    说明：
    这是一个内部辅助函数。在真实场景下，它会发起 HTTP/SSE 请求去 MCP Server 拉取工具描述。
    当前作为 MVP，我们如果遇到 `mock_inventory_mcp`，就直接返回一组假的工具描述（Mock）。
    """
    logger.info(f"正在从 MCP 服务器拉取工具: {server_name}")
    
    if server_name == "mock_inventory_mcp":
        # 返回假装从远端拉回来的工具描述 (Tool Spec)
        return [
            {
                "name": "get_product_inventory",
                "description": "获取指定商品的实时库存情况",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "string", "description": "商品ID，例如 'jd_mock_001'"},
                        "region": {"type": "string", "description": "发货区域，如 '北京'"}
                    },
                    "required": ["product_id"]
                },
                "_mcp_server_name": server_name, # 注入来源标识，方便追踪
                "_mcp_server_url": server_config.get("url")
            }
        ]
    
    # 其他未实现的服务器暂返回空列表
    logger.warning(f"MCP 服务器 {server_name} 尚未实现真实的拉取逻辑。")
    return []

async def get_tools_from_all_servers() -> List[Dict[str, Any]]:
    """
    从所有注册的 MCP 服务器拉取并聚合工具。
    
    注意：
    这里返回的不是可执行的 Callable 函数，而是工具的描述字典 (Tool Spec)。
    Day 6 的 `mcp_tool_adapter` 会负责把这些字典转换为 LangChain 可用的 Tool 对象。
    
    返回:
        聚合后的所有工具描述列表
    """
    all_tools_specs: List[Dict[str, Any]] = []
    
    for server_name, server_config in MCP_SERVERS.items():
        try:
            # 获取该服务器下的所有工具描述
            tools_specs = await _fetch_tools_from_server(server_name, server_config)
            all_tools_specs.extend(tools_specs)
            logger.info(f"成功从 {server_name} 加载了 {len(tools_specs)} 个工具。")
        except Exception as e:
            # 工程性防御：一个 MCP Server 挂了，不能影响其他 Server 的工具加载
            logger.error(f"从 MCP 服务器 {server_name} 拉取工具失败: {e}", exc_info=True)
            continue
            
    return all_tools_specs