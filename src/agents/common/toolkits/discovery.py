"""工具发现层 — 六层框架之「发现层」。

支持按标签、分类、关键词、语义检索动态筛选候选工具。
当前工具数量较少时以标签/分类过滤为主；工具量增长后可扩展 embedding 检索。
"""

from __future__ import annotations

import re
from typing import Any, Callable

from src.agents.common.toolkits.registry import (
    get_all_tool_instances,
    get_all_extra_metadata,
    ToolExtraMetadata,
)


def filter_tools(
    *,
    category: str | None = None,
    tags: list[str] | None = None,
    query: str | None = None,
    exclude: set[str] | None = None,
    match_all_tags: bool = False,
) -> list[Any]:
    """多条件过滤工具列表。

    Args:
        category: 按分类过滤（buildin / research / analyst / critic）
        tags: 按标签过滤
        query: 语义搜索词（当前用关键词匹配，后续可接 embedding）
        exclude: 排除的工具名称集合
        match_all_tags: True = 必须包含所有标签，False = 包含任一标签即可

    Returns:
        匹配的工具实例列表

    Example:
        # 获取所有搜索相关的工具
        tools = filter_tools(tags=["搜索", "官方API"])

        # 获取 Researcher 可用的工具
        tools = filter_tools(category="research")
    """
    all_tools = get_all_tool_instances()
    extra_meta = get_all_extra_metadata()

    result: list[Any] = []
    for tool in all_tools:
        meta = extra_meta.get(tool.name, ToolExtraMetadata())

        # ── 排除检查 ──
        if exclude and tool.name in exclude:
            continue

        # ── 分类过滤 ──
        if category is not None and meta.category != category:
            continue

        # ── 标签过滤 ──
        if tags:
            tool_tags = set(meta.tags or [])
            if match_all_tags:
                if not set(tags).issubset(tool_tags):
                    continue
            else:
                if not set(tags).intersection(tool_tags):
                    continue

        # ── 语义/关键词过滤 ──
        if query:
            if not _match_query(query, tool, meta):
                continue

        result.append(tool)

    return result


def _match_query(query: str, tool: Any, meta: ToolExtraMetadata) -> bool:
    """关键词匹配 — 在工具名、描述、标签中搜索。

    后续可替换为 embedding 相似度检索。
    """
    query_lower = query.lower()
    targets = [
        tool.name or "",
        tool.description or "",
        meta.display_name or "",
        " ".join(meta.tags or []),
    ]
    combined = " ".join(targets).lower()

    # 简单关键词匹配
    keywords = re.split(r"[\s,，]+", query_lower)
    return any(kw in combined for kw in keywords if kw)


def filter_by_agent(agent_name: str) -> list[Any]:
    """根据 Agent 名称返回其专用工具集。

    复用 subagents.yaml 中定义的绑定关系。
    """
    agent_tool_map: dict[str, list[str]] = {
        "researcher": ["search_products", "get_product_full_detail",
                       "get_products_specs_batch", "jd_deep_search",
                       "jd_product_detail", "jd_product_images",
                       "jd_product_basic", "jd_product_mobile_detail",
                       "justone_product_search"],
        "analyst": ["get_products_specs_extract", "filter_products_by_criteria",
                    "query_category_knowledge"],
        "critic": ["query_risk_policy"],
        "memory_manager": [],
    }

    tool_names = agent_tool_map.get(agent_name, [])
    if not tool_names:
        return []

    all_tools = get_all_tool_instances()
    return [t for t in all_tools if t.name in tool_names]


def get_discovery_info() -> dict[str, Any]:
    """获取工具发现层的统计信息（供调试/监控）。"""
    all_tools = get_all_tool_instances()
    extra_meta = get_all_extra_metadata()

    categories: dict[str, int] = {}
    all_tags: set[str] = set()

    for tool in all_tools:
        meta = extra_meta.get(tool.name, ToolExtraMetadata())
        categories[meta.category] = categories.get(meta.category, 0) + 1
        all_tags.update(meta.tags or [])

    return {
        "total_tools": len(all_tools),
        "categories": categories,
        "unique_tags": sorted(all_tags),
        "supports_semantic_search": False,
    }
