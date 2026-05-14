"""硬编码工具集 - ShoppingClaw Agent 核心能力"""
from src.agents.common.toolkits.registry import (
    tool,
    ToolExtraMetadata,
    get_extra_metadata,
    get_all_extra_metadata,
)

# 延迟导入：research 和 analyst 工具包在首次调用时才加载，
# 避免服务启动时引入 jd/sqlalchemy/torch 等重量级依赖。
_tools_loaded = False

def _ensure_tools_loaded():
    global _tools_loaded
    if _tools_loaded:
        return
    import src.agents.common.toolkits.buildin.tools  # 注册内置工具
    try:
        import src.agents.common.toolkits.shopping  # 注册购物工具
    except Exception:
        pass
    try:
        import src.agents.common.toolkits.research  # 注册爬虫工具
    except Exception:
        pass
    try:
        import src.agents.common.toolkits.analyst  # 注册分析工具
    except Exception:
        pass
    try:
        import src.agents.common.toolkits.critic.tools  # 注册审查工具
    except Exception:
        pass
    _tools_loaded = True

def get_all_tool_instances() -> list:
    _ensure_tools_loaded()
    from src.agents.common.toolkits.registry import get_all_tool_instances as _get
    return _get()

from src.agents.common.toolkits.utils import gen_tool_info

__all__ = [
    "tool",
    "ToolExtraMetadata",
    "get_all_tool_instances",
    "get_extra_metadata",
    "get_all_extra_metadata",
    "gen_tool_info",
]
