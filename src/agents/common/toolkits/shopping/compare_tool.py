import logging
from typing import Dict, Any

from src.agents.common.toolkits.registry import tool
from src.agents.common.toolkits.shopping.schemas import ProductCompareInput
from src.models.product import Product
from src.tools.compare import compare_products

logger = logging.getLogger(__name__)

# ==========================================
# 工具包装器 (Wrapper) - 骨架
# ==========================================
# 💡 解释：
# 这是一个相对复杂的工具，因为它的输出不仅有商品列表，还有一份“对比报告文本”。
# 如果我们把这个文本写回 Agent 的 State，Agent 就能直接把它回答给用户。
# 它的返回字典结构是：{"report": str, "ranked_products": [...], "error": None}

@tool(
    category="shopping",
    tags=["对比", "商品", "推荐"],
    display_name="商品综合对比排序",
    icon="⚖️",
    args_schema=ProductCompareInput,
)
def product_compare(products: list[Product]) -> Dict[str, Any]:
    """
    商品对比排序工具。
    
    职责：
    - 接收多个商品对象
    - 根据预设权重（价格、评分、销量）计算综合得分
    - 生成对比报告，并按得分从高到低返回商品
    
    注意：
    大模型可能会一次传好几个商品进来，我们需要保证这个函数不会因为某一个商品缺了属性（比如没评分）就崩溃。
    """
    logger.info(f"[Tool] 执行商品对比: products_count={len(products) if products else 0}")
    
    # 工程性防御 1：拦截空列表
    if not products:
        logger.warning("[Tool] 商品对比: 传入的商品列表为空，无法进行对比。")
        return {
            "report": "没有收到需要对比的商品，无法生成对比报告。",
            "ranked_products": [],
            "error": "商品列表为空"
        }
        
    # 工程性防御 2：单商品拦截已移至底层 compare_products 函数处理
    # 这里不再重复处理，保持逻辑一致性
    
    try:
        # 调用底层业务逻辑
        # compare_products 返回的是 ComparisonResult 对象 (包含 report 和 ranked_products 属性)
        result = compare_products(products=products)
        
        logger.info("[Tool] 商品对比完成，已生成报告和排序列表。")
        
        # 将 Pydantic 对象转换为字典，确保序列化安全
        # 使用 model_dump() 而不是直接访问属性，避免序列化问题
        result_dict = result.model_dump()
        result_dict["error"] = None
        return result_dict
        
    except Exception as e:
        # 工程性防御 3：拦截所有未知计算异常（比如除零错误、属性缺失等）
        error_msg = f"执行对比计算时发生异常: {str(e)}"
        logger.error(f"[Tool] 商品对比崩溃: {error_msg}", exc_info=True)
        
        # 出错时兜底：退回原列表，不中断对话
        return {
            "report": "生成对比报告时发生内部错误，无法提供对比结果。",
            "ranked_products": products,
            "error": error_msg
        }
