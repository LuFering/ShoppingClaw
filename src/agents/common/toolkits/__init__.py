"""硬编码工具集 - ShoppingClaw Agent 核心能力"""
from src.agents.common.toolkits.registry import (
    tool,
    ToolExtraMetadata,
    get_all_tool_instances,
    get_extra_metadata,
    get_all_extra_metadata,
)
from src.agents.common.toolkits.utils import gen_tool_info

__all__ = [
    "tool",
    "ToolExtraMetadata",
    "get_all_tool_instances",
    "get_extra_metadata",
    "get_all_extra_metadata",
    "gen_tool_info",
]
