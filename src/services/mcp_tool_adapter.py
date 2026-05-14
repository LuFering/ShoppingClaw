import logging
from typing import Any, Dict, List

import requests
from langchain.tools import BaseTool
from langchain.tools import tool as langchain_tool
from pydantic import BaseModel, Field, create_model

logger = logging.getLogger(__name__)


def _build_args_schema(input_schema: dict | None) -> type[BaseModel]:
    if not isinstance(input_schema, dict):
        return create_model("McpToolArgs", __base__=BaseModel)

    props = input_schema.get("properties") or {}
    required = set(input_schema.get("required") or [])
    fields: dict[str, tuple[Any, Any]] = {}

    for name, spec in props.items():
        desc = ""
        if isinstance(spec, dict):
            desc = str(spec.get("description") or "")
        default = ... if name in required else None
        fields[name] = (Any, Field(default=default, description=desc))

    return create_model("McpToolArgs", __base__=BaseModel, **fields)


def _create_mcp_executor(tool_spec: Dict[str, Any]):
    server_url = tool_spec.get("_mcp_server_url")
    tool_name = tool_spec.get("name")

    def executor(**kwargs: Any) -> Any:
        if not tool_name:
            return {"error": "MCP tool name missing"}

        if not server_url or str(server_url).startswith("http://localhost:8080"):
            if tool_name == "get_product_inventory":
                product_id = kwargs.get("product_id", "unknown")
                return {"status": "success", "stock": 99, "message": f"商品 {product_id} 库存充足。"}
            return {"status": "success", "message": "Mock execution completed."}

        try:
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": kwargs},
                "id": 1,
            }
            response = requests.post(server_url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            error_msg = f"调用远程 MCP 工具 {tool_name} 失败: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg}

    return executor


def convert_mcp_spec_to_langchain_tool(tool_spec: Dict[str, Any]) -> BaseTool:
    name = tool_spec.get("name", "unknown_mcp_tool")
    description = tool_spec.get("description", "A remote MCP tool")
    args_schema = _build_args_schema(tool_spec.get("inputSchema"))

    executor_func = _create_mcp_executor(tool_spec)
    executor_func.__name__ = name
    executor_func.__doc__ = description

    tool_obj = langchain_tool(description=description, args_schema=args_schema)(executor_func)
    tool_obj.name = name
    return tool_obj


def adapt_mcp_tools(tool_specs: List[Dict[str, Any]]) -> List[BaseTool]:
    langchain_tools: List[BaseTool] = []
    for spec in tool_specs:
        try:
            langchain_tools.append(convert_mcp_spec_to_langchain_tool(spec))
        except Exception as e:
            logger.error(f"转换 MCP 工具 {spec.get('name')} 失败: {e}")
    return langchain_tools
