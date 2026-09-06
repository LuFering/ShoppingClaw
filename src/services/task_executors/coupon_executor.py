"""
优惠券监控执行器

搜索关键词 → 检测优惠券 → 按力度过滤 → 异常大额券告警
"""
import logging

from src.storage.postgres.models_business import TaskRecord
from src.services.mcp_service import call_stdio_tool_async, MCP_SERVERS
from src.services.task_executors.common import parse_search_result

logger = logging.getLogger(__name__)


async def execute(task: TaskRecord) -> dict:
    """
    task_params:
        {
            "keyword": "蓝牙耳机",
            "min_coupon_amount": 1000,    # 最低优惠券面额（分）
            "platform": "taobao"
        }
    """
    params = task.task_params or {}
    keyword = params.get("keyword", "")
    platform = params.get("platform", "taobao")
    min_coupon = params.get("min_coupon_amount", 0)

    if not keyword:
        return {"error": "缺少 keyword 参数"}

    raw = await call_stdio_tool_async(
        "taobao_mcp", MCP_SERVERS.get("taobao_mcp", {}),
        "taobao.searchMaterial",
        {"q": keyword, "page_size": 10}
    )

    products = parse_search_result(raw)
    if not products:
        return {"status": "no_results", "keyword": keyword}

    # 筛选有优惠券的商品
    coupon_products = []
    for p in products:
        coupon = _extract_coupon(p)
        if coupon and coupon >= min_coupon:
            coupon_products.append({
                "title": p.get("title", ""),
                "price": p.get("price", 0),
                "coupon_amount": coupon,
                "after_coupon": max(0, int(p.get("price", 0)) - coupon),
            })

    # 标记异常大额券（超过商品原价50%的券）
    alerts = []
    for cp in coupon_products:
        if cp["price"] > 0 and cp["coupon_amount"] > cp["price"] * 0.5:
            alerts.append(cp)

    return {
        "status": "ok",
        "keyword": keyword,
        "total_products": len(products),
        "with_coupons": len(coupon_products),
        "top_coupons": sorted(coupon_products, key=lambda x: x["coupon_amount"], reverse=True)[:5],
        "alerts": alerts,
        "triggered": len(alerts) > 0,
    }


def _extract_coupon(product: dict) -> int:
    """提取优惠券面额（分）"""
    coupon = product.get("coupon_amount", product.get("coupon_info", 0))
    try:
        return int(coupon)
    except (ValueError, TypeError):
        return 0
