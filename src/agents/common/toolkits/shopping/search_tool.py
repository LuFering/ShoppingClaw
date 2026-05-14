import logging
from typing import Any, Dict

from src.agents.common.toolkits.registry import tool
from src.agents.common.toolkits.shopping.schemas import ProductSearchInput
from src.tools.search import search

logger = logging.getLogger(__name__)


@tool(
    category="shopping",
    tags=["搜索", "商品"],
    display_name="跨平台商品搜索",
    icon="🔍",
    args_schema=ProductSearchInput,
)
def product_search(query: str, platforms: list[str] | None = None, limit: int = 10) -> Dict[str, Any]:
    """按查询词执行跨平台商品搜索，返回候选商品列表和错误信息。

    适用于购物场景中的候选集召回。工具会调用统一搜索入口，根据平台参数
    在指定平台或全平台范围内检索商品，并输出结构化 `Product` 列表。
    """
    try:
        results = search(query=query, platforms=platforms, limit=limit)
        return {"products": results, "error": None}
    except Exception as exc:
        return {"products": [], "error": str(exc)}
