import logging
from typing import Any, Dict, List

from src.agents.common.toolkits.registry import tool
from src.agents.common.toolkits.shopping.schemas import ProductFilterInput
from src.models.product import PlatformCode, Product
from src.tools.filter import filter_products

logger = logging.getLogger(__name__)


@tool(
    category="shopping",
    tags=["过滤", "商品"],
    display_name="商品多条件过滤",
    icon="🧹",
    args_schema=ProductFilterInput,
)
def product_filter(
    products: List[Product],
    price_min: float | None = None,
    price_max: float | None = None,
    platforms: list[PlatformCode] | None = None,
    min_rating: float | None = None,
    brands: list[str] | None = None,
    keywords: list[str] | None = None,
) -> Dict[str, Any]:
    """按价格、平台、评分、品牌和关键词等条件过滤候选商品列表。

    适用于商品召回之后的二次筛选场景。工具会基于传入的结构化商品列表
    执行多条件过滤，并返回过滤后的商品结果或过滤条件错误信息。
    """
    try:
        results = filter_products(
            products,
            price_min=price_min,
            price_max=price_max,
            platforms=platforms,
            min_rating=min_rating,
            brands=brands,
            keywords=keywords,
        )
        return {"products": results, "error": None}
    except Exception as exc:
        return {"products": products or [], "error": f"过滤条件有误: {exc}"}
