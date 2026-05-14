import logging
from typing import Any, Dict, List

from src.agents.common.toolkits.registry import tool
from src.agents.common.toolkits.shopping.schemas import ProductCompareInput
from src.models.product import Product
from src.tools.compare import compare_products

logger = logging.getLogger(__name__)


@tool(
    category="shopping",
    tags=["对比", "商品", "推荐"],
    display_name="商品综合对比排序",
    icon="⚖️",
    args_schema=ProductCompareInput,
)
def product_compare(products: List[Product]) -> Dict[str, Any]:
    """对输入商品列表做综合对比排序，返回对比报告、排序后的商品列表和错误信息。

    适用于推荐前的候选商品比较场景。工具会基于底层 compare 逻辑输出
    可读报告，并给出按综合表现排序后的商品结果。
    """
    if not products:
        return {"report": "没有收到需要对比的商品，无法生成对比报告。", "ranked_products": [], "error": "商品列表为空"}
    try:
        result = compare_products(products=products)
        return {"report": result.report, "ranked_products": result.ranked_products, "error": None}
    except Exception as exc:
        return {"report": "生成对比报告时发生内部错误，无法提供对比结果。", "ranked_products": products, "error": str(exc)}
