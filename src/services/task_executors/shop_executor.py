"""
店铺活动监控执行器

搜索店铺商品 → 检测上新/活动 → 变化告警
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
            "shop_name": "小米官方旗舰店",
            "platform": "taobao"
        }
    """
    params = task.task_params or {}
    shop_name = params.get("shop_name", "")
    platform = params.get("platform", "taobao")

    if not shop_name:
        return {"error": "缺少 shop_name 参数"}

    raw = await call_stdio_tool_async(
        "taobao_mcp", MCP_SERVERS.get("taobao_mcp", {}),
        "taobao.searchMaterial",
        {"q": shop_name, "page_size": 10}
    )

    products = parse_search_result(raw)
    if not products:
        return {"status": "no_results", "shop_name": shop_name}

    # 筛选该店铺的商品
    shop_products = []
    for p in products:
        seller = str(p.get("shop_name", p.get("seller_nick", ""))).lower()
        if shop_name.lower() in seller:
            shop_products.append({
                "title": p.get("title", ""),
                "price": p.get("price", 0),
                "original_price": p.get("original_price"),
                "coupon_amount": p.get("coupon_amount", 0),
                "sales": p.get("sales", p.get("volume", 0)),
            })

    # 统计: 平均价格、折扣商品数、优惠券覆盖率
    prices = [p["price"] for p in shop_products if p["price"] > 0]
    coupons = [p for p in shop_products if p["coupon_amount"] > 0]
    discounted = [p for p in shop_products if p["original_price"] and p["price"] < p["original_price"]]

    result = {
        "status": "ok",
        "shop_name": shop_name,
        "total_visible": len(shop_products),
        "avg_price": round(sum(prices) / len(prices)) if prices else 0,
        "with_coupons": len(coupons),
        "discounted_count": len(discounted),
        "price_range": {
            "min": min(prices) if prices else 0,
            "max": max(prices) if prices else 0,
        },
    }

    # 折扣率 > 30% 的商品标记为活动预警
    deep_discounts = []
    for p in shop_products:
        if p["original_price"] and p["original_price"] > 0:
            discount_rate = (p["original_price"] - p["price"]) / p["original_price"]
            if discount_rate > 0.3:
                deep_discounts.append({
                    "title": p["title"],
                    "discount": f"{discount_rate*100:.0f}%",
                    "price": p["price"],
                })

    if deep_discounts:
        result["deep_discounts"] = deep_discounts[:5]
        result["triggered"] = True
    else:
        result["triggered"] = False

    return result

