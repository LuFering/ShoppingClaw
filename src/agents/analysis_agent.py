from __future__ import annotations

import logging
from statistics import mean, median
from typing import Iterable

from src.models.product import Product
from src.models.state import ShoppingState

logger = logging.getLogger(__name__)


def _safe_prices(products: Iterable[Product]) -> list[float]:
    prices: list[float] = []
    for p in products:
        try:
            prices.append(float(p.price))
        except Exception:
            continue
    return [x for x in prices if x > 0]


def analysis_agent(state: ShoppingState) -> dict:
    """
    Analysis Agent

    职责：读取 products，产出一段可复用的市场分析文本（analysis_report）。
    输入：ShoppingState（包含 products，可选 query/platform）
    输出：dict（包含 analysis_report，可选 error）
    """
    query = state.get("query", "未知商品")
    products: list[Product] = state.get("products", [])

    logger.info("analysis_agent.start query=%s products_count=%s", query, len(products))

    if not products:
        return {
            "analysis_report": (
                f"关于“{query}”的市场分析：\n"
                "- 当前候选商品为空，建议放宽检索条件或更换平台后重试。"
            )
        }

    try:
        prices = _safe_prices(products)
        if not prices:
            return {
                "analysis_report": (
                    f"关于“{query}”的市场分析：\n"
                    "- 已获取候选商品，但价格字段缺失或不可解析，建议检查数据源映射。"
                )
            }

        min_price = min(prices)
        max_price = max(prices)
        avg_price = mean(prices)
        med_price = median(prices)

        platform_count: dict[str, int] = {}
        brand_count: dict[str, int] = {}
        for p in products:
            platform_count[p.platform] = platform_count.get(p.platform, 0) + 1
            if p.brand:
                brand_count[p.brand] = brand_count.get(p.brand, 0) + 1

        platform_line = ", ".join(f"{k}:{v}" for k, v in sorted(platform_count.items()))
        top_brands = sorted(brand_count.items(), key=lambda kv: kv[1], reverse=True)[:5]
        brand_line = "、".join(f"{b}({c})" for b, c in top_brands) if top_brands else "无"

        report = (
            f"关于“{query}”的市场分析：\n"
            f"- 样本数：{len(products)}（平台分布：{platform_line}）\n"
            f"- 价格区间：¥{min_price:.2f} ~ ¥{max_price:.2f}\n"
            f"- 均价/中位数：¥{avg_price:.2f} / ¥{med_price:.2f}\n"
            f"- 主要品牌（Top）：{brand_line}\n"
            f"- 建议：优先关注接近中位数价位且评价/店铺信息更完整的商品。"
        )

        logger.info("analysis_agent.done query=%s", query)
        return {"analysis_report": report}

    except Exception as exc:
        error_msg = f"analysis failed: {exc}"
        logger.error("analysis_agent.error %s", error_msg, exc_info=True)
        return {
            "analysis_report": (
                f"关于“{query}”的市场分析：\n"
                "- 分析阶段发生异常，建议稍后重试或减少候选商品数量。"
            ),
            "error": error_msg,
        }

