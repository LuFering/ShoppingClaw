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

    # 收集**真券**（title 含「券」的活动）。
    #
    # ⚠️ 不用 `p["coupon_amount"]` —— 那个字段是 `original_price - price`，
    # 即「已经减掉的差价」，不是可领的券。实测 10 件里 8 件拿它算
    # after_coupon 会归零，且 10/10 会命中「异常大额券」告警。
    coupon_products = []
    for p in products:
        for promo in (p.get("promotions") or []):
            kind = str(promo.get("title") or "")
            if "券" not in kind:
                continue                      # 补贴/秒杀/折扣不是券
            face = _parse_face(promo.get("desc"))
            if face <= 0 or face < min_coupon:
                continue
            coupon_products.append({
                "title": p.get("title", ""),
                "price": p.get("price", 0),        # 到手价（**已含**这张券）
                "coupon_kind": kind,               # 商品券 / 店铺券
                "coupon_desc": promo.get("desc"),  # 「满100减9」
                "coupon_face": face,               # 券面额（分）
                "ends_ms": promo.get("end_ms"),    # 券的结束时间
                # ⚠️ 刻意**不给** after_coupon：final_promotion_price 已是
                # 到手价（含券），再减一次就是双重扣减。前端要展示就说清
                # 「到手价已含该券」。
                "note": "到手价已含该券",
            })

    if not coupon_products:
        # 如实说没查到券 —— 不拿「差价」凑一个出来
        return {
            "status": "no_coupon",
            "keyword": keyword,
            "total_products": len(products),
            "with_coupons": 0,
            "triggered": False,
        }

    # 按面额排序，取最大的几张
    top = sorted(coupon_products, key=lambda x: x["coupon_face"], reverse=True)[:5]

    # 触发判据：**有券**（且面额 ≥ 门槛，上面已过滤）。
    # 旧判据「差价 > 半价」等于恒真 —— 差价本来就常超半价。
    return {
        "status": "ok",
        "keyword": keyword,
        "total_products": len(products),
        "with_coupons": len(coupon_products),
        "top_coupons": top,
        "triggered": True,
        "alert": f"发现 {len(coupon_products)} 张券，最大 {_yuan(top[0]['coupon_face'])}"
                 f"（{top[0]['coupon_desc']}）：{top[0]['title'][:24]}",
    }


def _parse_face(desc) -> int:
    """从「满100减9」这类描述里取**券面额**，返回分。

    取「减」后面那个数 —— 那是券能抵的钱。
    「满100减9」→ 900 分。解析不出来返回 0（上层据此跳过，不编一个数）。
    """
    import re
    m = re.search(r"减\s*([\d.]+)", str(desc or ""))
    if not m:
        return 0
    try:
        return int(round(float(m.group(1)) * 100))
    except (ValueError, TypeError):
        return 0


def _yuan(cents) -> str:
    try:
        return f"¥{int(cents) / 100:.0f}"
    except (TypeError, ValueError):
        return "—"
