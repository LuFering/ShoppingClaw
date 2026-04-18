from __future__ import annotations

import logging
from typing import List

from src.models.state import PlatformCode, ShoppingState
from src.tools.search import search

logger = logging.getLogger(__name__)


def search_agent(state: ShoppingState) -> dict:
    """
    搜索 Agent。

    职责：读取 state 中的 query / platform / search_limit，
         调用 search 工具获取商品列表，将结果写入 products。

    Args:
        state: LangGraph 工作流状态。

    Returns:
        {"products": List[Product]} 或 {"error": str}
    """
    query = state.get("query", "")
    platform = state.get("platform")

    if not str(query).strip():
        logger.error("search_agent.error platform=%s error=查询词为空", platform)
        return {"error": "查询词为空"}

    search_limit = int(state.get("search_limit", 10))  # type: ignore[arg-type]
    platforms: List[PlatformCode] | None = [platform] if platform else None

    try:
        logger.info(
            "search_agent.start query=%s platform=%s limit=%s",
            query, platform, search_limit,
        )
        products = search(query=query, platforms=platforms, limit=search_limit)

    except Exception as exc:
        logger.error(
            "search_agent.error query=%s platform=%s error=%s",
            query, platform, exc,
        )
        return {"error": str(exc)}

    logger.info(
        "search_agent.done query=%s platform=%s count=%s",
        query, platform, len(products),
    )

    if not products:
        logger.warning(
            "search_agent.empty_result query=%s platform=%s",
            query, platform,
        )

    return {"products": products}
