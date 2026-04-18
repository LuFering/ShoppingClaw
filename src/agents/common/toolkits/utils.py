"""工具辅助函数"""
import traceback
from typing import Any

import logging

logger = logging.getLogger(__name__)


def gen_tool_info(tools: list) -> list[dict[str, Any]]:
    """提取所有工具的结构化信息（用于前端展示或调试）
    
    Args:
        tools: 工具实例列表
        
    Returns:
        工具信息字典列表，包含 name, description, args 等
    """
    tools_info = []

    for tool_obj in tools:
        try:
            metadata = getattr(tool_obj, "metadata", {}) or {}
            info = {
                "id": tool_obj.name,
                "name": metadata.get("display_name", tool_obj.name),
                "description": tool_obj.description,
                "category": metadata.get("category", "unknown"),
                "tags": metadata.get("tags", []),
                "args": [],
            }

            # 解析参数 schema
            if hasattr(tool_obj, "args_schema") and tool_obj.args_schema:
                schema = (
                    tool_obj.args_schema 
                    if isinstance(tool_obj.args_schema, dict)
                    else tool_obj.args_schema.model_schema() if hasattr(tool_obj.args_schema, 'model_schema') else tool_obj.args_schema.schema()
                )

                for arg_name, arg_info in schema.get("properties", {}).items():
                    info["args"].append({
                        "name": arg_name,
                        "type": arg_info.get("type", arg_info.get("$ref", "any")),
                        "description": arg_info.get("description", ""),
                        "required": arg_name in schema.get("required", []),
                    })

            tools_info.append(info)

        except Exception as e:
            logger.error(f"解析工具 {getattr(tool_obj, 'name', 'unknown')} 信息失败: {e}")
            continue

    logger.info(f"成功提取 {len(tools_info)} 个工具的信息")
    return tools_info
