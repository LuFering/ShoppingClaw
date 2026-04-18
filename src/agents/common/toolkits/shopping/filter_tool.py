import logging
from typing import Dict, Any

from src.agents.common.toolkits.registry import tool
from src.agents.common.toolkits.shopping.schemas import ProductFilterInput
from src.models.product import Product
from src.tools.filter import filter_products

logger = logging.getLogger(__name__)

# ==========================================
# 工具包装器 (Wrapper) - 骨架
# ==========================================
# 💡 解释：
# 和 search_tool 类似，我们在这里包装 filter_products。
# 为什么要再包一层？
# 1. 统一错误返回（`error` 字段）
# 2. 为 Agent 提供统一的中文 `display_name` 和分类标签。
# 3. 通过 args_schema = ProductFilterInput 强制类型校验。

@tool(
    category="shopping",
    tags=["过滤", "商品"],
    display_name="商品多条件过滤",
    icon="🔍",
    args_schema=ProductFilterInput,
)
def product_filter(
    products: list[Product],
    price_min: float | None = None,
    price_max: float | None = None,
    platforms: list[str] | None = None,
    min_rating: float | None = None,
    brands: list[str] | None = None,
    keywords: list[str] | None = None,
) -> Dict[str, Any]:
    """
    商品多条件过滤工具。
    
    职责：
    - 接收前置搜索结果（商品列表）
    - 校验价格区间等约束
    - 返回过滤后的字典结果 {"products": [...], "error": None}
    
    注意：
    这里的 products 通常是上一步搜索（或者 state 里存着）传过来的。
    如果产品列表为空，底层逻辑可能会直接报错，我们需要在这里提前判断或者用 try-except 捕获。
    """
    logger.info(f"[Tool] 执行商品过滤: products_count={len(products) if products else 0}")
    
    # 工程性防御 1：拦截空列表
    # 如果没商品，根本不需要调用底层逻辑，直接返回即可，省去不必要的计算。
    if not products:
        logger.warning("[Tool] 商品过滤: 传入的商品列表为空，直接返回空列表。")
        return {"products": [], "error": None}
    
    try:
        # 调用底层的过滤逻辑
        filtered_results = filter_products(
            products=products,
            price_min=price_min,
            price_max=price_max,
            platforms=platforms,
            min_rating=min_rating,
            brands=brands,
            keywords=keywords,
        )
        logger.info(f"[Tool] 商品过滤完成: 剩余数量={len(filtered_results)}")
        return {"products": filtered_results, "error": None}
        
    except ValueError as ve:
        # 工程性防御 2：拦截预期的业务异常
        # 底层 filter_products 会在 price_min > price_max 时抛出 ValueError
        error_msg = f"过滤条件有误: {str(ve)}"
        logger.warning(f"[Tool] 商品过滤参数错误: {error_msg}")
        return {"products": products, "error": error_msg} # 发生预期错误时，原样退回输入的商品，防止丢数据
        
    except Exception as e:
        # 工程性防御 3：拦截未知的崩溃异常
        error_msg = f"执行过滤时发生未知错误: {str(e)}"
        logger.error(f"[Tool] 商品过滤未知错误: {error_msg}", exc_info=True)
        return {"products": products, "error": error_msg} # 发生未知错误时，原样退回输入的商品
