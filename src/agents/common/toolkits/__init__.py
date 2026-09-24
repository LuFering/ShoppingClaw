"""硬编码工具集 - ShoppingClaw Agent 核心能力。

六层框架入口：
- registry  : 注册层（@tool 装饰器 + 元数据绑定）
- discovery : 发现层（标签/分类/语义筛选）
- runtime   : 执行层 + 生命周期层（Handler Chain + 事件）
- result    : 结果层（ToolResult 统一协议）
"""

from src.agents.common.toolkits.registry import (
    tool,
    ToolExtraMetadata,
    get_extra_metadata,
    get_all_extra_metadata,
)

from src.agents.common.toolkits.result import ToolResult, ToolStatus
from src.agents.common.toolkits.discovery import (
    filter_tools,
    filter_by_agent,
    get_discovery_info,
)

from src.agents.common.toolkits.utils import gen_tool_info

# 延迟导入：research 和 analyst 工具包在首次调用时才加载，
# 避免服务启动时引入 jd/sqlalchemy/torch 等重量级依赖。
_tools_loaded = False


def _ensure_tools_loaded():
    global _tools_loaded
    if _tools_loaded:
        return
    # Always load buildin tools first (required for agent core functionality)
    import src.agents.common.toolkits.buildin.tools
    # 购物档案工具（购后助手专属：归档 / 阶段 / 提醒 / 复盘）
    # @tool 装饰器在 import 时完成注册，故必须显式导入。
    import src.agents.common.toolkits.buildin.archive_tools
    # 编排层工具（主智能体专属：路由目录 / 编排 SOP / 档案查询）
    import src.agents.common.toolkits.buildin.orchestration_tools
    # 监控任务工具（购后助手专属：建监控 / 看监控）—— 补「对话说了真的算」
    import src.agents.common.toolkits.buildin.monitor_tools
    # Optional toolkits: failure should not block buildin tools
    for mod_path, label in [
        ("src.agents.common.toolkits.research", "research"),
        ("src.agents.common.toolkits.analyst", "analyst"),
        ("src.agents.common.toolkits.critic.tools", "critic"),
    ]:
        try:
            import importlib
            importlib.import_module(mod_path)
        except Exception as e:
            import logging
            logging.warning("[Toolkit] Failed to load %s toolkit: %s", label, e)
    _tools_loaded = True


def get_all_tool_instances() -> list:
    _ensure_tools_loaded()
    from src.agents.common.toolkits.registry import get_all_tool_instances as _get
    return _get()


__all__ = [
    # 注册层
    "tool",
    "ToolExtraMetadata",
    "get_extra_metadata",
    "get_all_extra_metadata",
    # 结果层
    "ToolResult",
    "ToolStatus",
    # 发现层
    "filter_tools",
    "filter_by_agent",
    "get_discovery_info",
    # 工具
    "get_all_tool_instances",
    "gen_tool_info",
]
