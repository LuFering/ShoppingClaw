from __future__ import annotations

import logging
from typing import List

from src.models.product import Product
from src.models.state import ShoppingState
from src.tools.compare import compare_products

logger = logging.getLogger(__name__)


def recommendation_agent(state: ShoppingState) -> dict:
    """
    Recommendation Agent

    职责：作为工作流的最后一环，读取 products 和 analysis_report，
         调用底层对比算法得出排名，生成推荐列表和最终回复。
    输入：ShoppingState（包含 query, products, analysis_report）
    输出：dict（包含 recommendations, answer, 可选的 error）
    """
    query = state.get("query", "未知商品")
    products: List[Product] = state.get("products", [])
    analysis_report = state.get("analysis_report", "")

    logger.info("recommendation_agent.start query=%s products_count=%s", query, len(products))

    # 工程防御 1：没有商品时直接返回安慰性话术
    if not products:
        logger.warning("recommendation_agent.empty_products")
        return {
            "recommendations": [],
            "answer": f"抱歉，关于您搜索的“{query}”，未能找到符合要求的商品。\n\n【市场分析】\n{analysis_report}"
        }

    # 工程防御 2：只有一个商品时，直接推荐，不走对比算法
    if len(products) == 1:
        single_product = products[0]
        logger.info("recommendation_agent.single_product")
        return {
            "recommendations": products,
            "answer": f"为您找到了一款关于“{query}”的商品：\n\n"
                      f"【推荐商品】 {single_product.title} (价格: ¥{single_product.price})\n\n"
                      f"【市场分析】\n{analysis_report}"
        }

    try:
        # 核心逻辑：调用底层对比算法
        logger.info("recommendation_agent.comparing_products")
        compare_result = compare_products(products=products)
        
        # 提取排序结果，为了不让用户看花眼，我们只推荐 Top 3
        top_n = 3
        ranked_products = compare_result.ranked_products
        recommendations = ranked_products[:top_n]
        
        # 组装给用户的最终答案 (answer)
        # 融合了用户的需求、对比工具的专业报告、以及上一个节点的大盘分析
        answer_parts = [
            f"根据您的需求“{query}”，我为您挑选并对比了多款商品，以下是综合推荐：\n",
            "【对比分析报告】",
            compare_result.report,
            "\n【大盘市场分析】",
            analysis_report
        ]
        
        logger.info("recommendation_agent.done recommendations_count=%s", len(recommendations))
        return {
            "recommendations": recommendations,
            "answer": "\n".join(answer_parts)
        }
        
    except Exception as exc:
        # 工程防御 3：算法崩溃兜底
        error_msg = f"recommendation failed: {str(exc)}"
        logger.error("recommendation_agent.error %s", error_msg, exc_info=True)
        
        # 降级处理：不抛异常中断，而是原样返回商品列表作为推荐
        return {
            "recommendations": products[:3],  # 随便取前三个凑数
            "answer": f"在为您生成“{query}”的推荐报告时遇到了一些问题，但我依然为您找到了一些相关商品供您参考。\n\n【市场分析】\n{analysis_report}",
            "error": error_msg
        }