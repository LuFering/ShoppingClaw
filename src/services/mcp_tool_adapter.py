import logging
from typing import Any, Callable, Dict, List
import requests

from langchain.tools import BaseTool
from langchain.tools import tool as langchain_tool

logger = logging.getLogger(__name__)

def _create_mcp_executor(tool_spec: Dict[str, Any]) -> Callable[..., Any]:
    """
    创建一个闭包函数，用于实际执行 MCP 远程调用。
    
    在这个闭包里，大模型传过来的参数（**kwargs）会被打包成 JSON，
    通过 HTTP POST 发送给真实的 MCP Server 执行。
    """
    server_url = tool_spec.get("_mcp_server_url")
    tool_name = tool_spec.get("name")
    
    def executor(**kwargs: Any) -> Any:
        logger.info(f"[MCP Adapter] 准备执行远程工具: {tool_name}, 参数: {kwargs}")
        
        # 工程防御：如果没有配置 URL，说明是 Mock 的本地环境，直接返回假数据
        if not server_url or server_url.startswith("http://localhost:8080"):
            logger.info(f"[MCP Adapter] 触发 Mock 拦截，返回模拟结果。")
            if tool_name == "get_product_inventory":
                product_id = kwargs.get("product_id", "unknown")
                return {"status": "success", "stock": 99, "message": f"商品 {product_id} 库存充足。"}
            return {"status": "success", "message": "Mock execution completed."}
        
        # 真实环境下的 HTTP POST 调用
        try:
            # 构造标准的 MCP 协议请求体 (简化版)
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": kwargs
                },
                "id": 1
            }
            
            # 发起请求
            response = requests.post(server_url, json=payload, timeout=10)
            response.raise_for_status()
            
            # 假设服务器返回 JSON
            return response.json()
            
        except requests.RequestException as e:
            error_msg = f"调用远程 MCP 工具 {tool_name} 失败: {str(e)}"
            logger.error(error_msg)
            # 返回统一字典格式，防止 Agent 崩溃
            return {"error": error_msg}
            
    return executor

def convert_mcp_spec_to_langchain_tool(tool_spec: Dict[str, Any]) -> BaseTool:
    """
    将单个 MCP Tool Spec (JSON 描述) 转换为 LangChain 的 BaseTool。
    
    使用 @tool 装饰器动态创建工具，与项目其他工具保持一致。
    """
    # 提取基本信息
    name = tool_spec.get("name", "unknown_mcp_tool")
    description = tool_spec.get("description", "A remote MCP tool")
    
    # 创建执行器
    executor_func = _create_mcp_executor(tool_spec)
    
    # 使用 @tool 装饰器动态创建工具
    # 动态给执行器赋名字和文档，帮助大模型理解
    executor_func.__name__ = name
    executor_func.__doc__ = description
    
    # 使用 LangChain 原生 @tool 装饰器包装函数
    tool_obj = langchain_tool(
        description=description,
    )(executor_func)
    
    # 手动设置工具名称
    tool_obj.name = name
    
    return tool_obj

async def adapt_mcp_tools(tool_specs: List[Dict[str, Any]]) -> List[Callable[..., Any]]:
    """
    将一组 MCP Tool Specs 转换为一组可被 LangGraph 调用的 LangChain 工具。
    
    注意：此函数现在是异步的，以保持与 MCP 服务层的一致性。
    虽然工具转换本身是 CPU 密集型操作，但异步接口避免了混合调用模式。
    """
    langchain_tools = []
    for spec in tool_specs:
        try:
            tool = convert_mcp_spec_to_langchain_tool(spec)
            langchain_tools.append(tool)
        except Exception as e:
            logger.error(f"转换 MCP 工具 {spec.get('name')} 失败: {e}")
            
    return langchain_tools

def adapt_mcp_tools_sync(tool_specs: List[Dict[str, Any]]) -> List[Callable[..., Any]]:
    """
    同步版本的 MCP 工具转换函数，用于向后兼容。
    
    注意：在异步上下文中，请优先使用 adapt_mcp_tools()。
    警告：此函数可能在线程安全方面存在问题，建议在新代码中使用异步版本。
    """
    import asyncio
    
    # 线程安全检查：如果已有事件循环运行，使用线程安全方式调用
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 在已有事件循环的线程中，创建新的事件循环
            import asyncio
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(adapt_mcp_tools(tool_specs))
            finally:
                new_loop.close()
    except RuntimeError:
        # 没有事件循环，安全使用 asyncio.run
        pass
    
    # 默认使用 asyncio.run（线程安全）
    return asyncio.run(adapt_mcp_tools(tool_specs))