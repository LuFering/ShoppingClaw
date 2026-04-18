"""工具注册表 - 基于 LangChain 的拓展装饰器"""
from dataclasses import dataclass, field
from typing import Callable

from langchain.tools import tool as langchain_tool


@dataclass
class ToolExtraMetadata:
    """工具附加元数据（用于分类和前端展示）"""
    category: str = "buildin"  # 分类：buildin, subagent, mcp
    tags: list[str] = field(default_factory=list)  # 标签：["记忆", "计算"]
    display_name: str = ""  # 显示名称（给人看的中文名）
    icon: str = ""  # 图标标识


# 全局注册表：tool_name -> ToolExtraMetadata
_extra_registry: dict[str, ToolExtraMetadata] = {}

# 全局工具实例列表（由 @tool 装饰器自动收集）
_all_tool_instances: list = []


def get_extra_metadata(tool_name: str) -> ToolExtraMetadata | None:
    """获取指定工具的附加元数据"""
    return _extra_registry.get(tool_name)


def get_all_extra_metadata() -> dict[str, ToolExtraMetadata]:
    """获取所有工具的附加元数据"""
    return _extra_registry.copy()


def get_all_tool_instances() -> list:
    """获取所有已注册的工具实例（直接用于 Agent 注入）"""
    return _all_tool_instances.copy()


def tool(
    category: str = "buildin",
    tags: list[str] = None,
    display_name: str = "",
    icon: str = "",
    name: str | None = None,
    description: str | None = None,
    args_schema: type | None = None,
    return_direct: bool = False,
):
    """基于 LangChain 的拓展装饰器，同时注册元数据
    
    使用示例:
        @tool(category="buildin", tags=["记忆"], display_name="保存偏好")
        def save_user_preference(key: str, value: str) -> str:
            ...
    """
    def decorator(func: Callable) -> Callable:
        # 1. 应用 LangChain 原生装饰器
        tool_obj = langchain_tool(
            description=description or func.__doc__ or "",
            args_schema=args_schema,
            return_direct=return_direct,
        )(func)

        # 2. 如果指定了 name，手动覆盖工具名称
        if name:
            tool_obj.name = name

        # 3. 注册附加元数据
        tool_name = tool_obj.name
        _extra_registry[tool_name] = ToolExtraMetadata(
            category=category,
            tags=tags or [],
            display_name=display_name or tool_name,
            icon=icon,
        )

        # 4. 自动收集工具实例
        _all_tool_instances.append(tool_obj)

        return tool_obj

    return decorator
