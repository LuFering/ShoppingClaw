"""硬编码工具集 - ShoppingClaw Agent 核心能力"""
from src.agents.common.toolkits.registry import (
    tool,
    ToolExtraMetadata,
    get_all_tool_instances,
    get_extra_metadata,
    get_all_extra_metadata,
)
from src.agents.common.toolkits.utils import gen_tool_info

# ==============================================================
# 💡 解释：在这里导入 shopping 模块，
# 这样在加载 registry.py 时，@tool 装饰器就会自动触发，
# 把 search_tool, filter_tool, compare_tool 注册进系统的可用工具表。
# 如果不在这里 import，那这些工具就像放在抽屉里没打开一样。
# ==============================================================
import src.agents.common.toolkits.shopping

__all__ = [
    "tool",
    "ToolExtraMetadata",
    "get_all_tool_instances",
    "get_extra_metadata",
    "get_all_extra_metadata",
    "gen_tool_info",
]

