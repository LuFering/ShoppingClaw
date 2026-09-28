"""
优惠到期监控执行器

搜索商品 → 取出所有**带结束时间的活动**（券/补贴/秒杀）→ 按剩余时间排序
→ 快到期时提醒。

═══ 为什么是它替换了「补货监控」 ═══
2026-09-29：补货监控被移除 —— 导购 MCP 的 26 个工具**没有任何库存字段**
（逐个查过：searchMaterial / getItemInfo / pdd.goods.detail / unified_tags
/ 商品详情页 / 官方文档，零命中）。改代码修不了，是缺数据源。

实测覆盖率之后选了「优惠到期」：
    活动窗口   23/23 件商品都有   ← 选它
    国家补贴   13/35 件
    销量       100% 但是累计值，单次快照看不出「突增」

而且它正好补上补货留下的空位 —— 用户担心的本来就是**错过优惠**。
"""
import logging
from datetime import datetime, timezone

from src.storage.postgres.models_business import TaskRecord
from src.services.mcp_service import call_stdio_tool_async, MCP_SERVERS
from src.services.task_executors.common import parse_search_result

logger = logging.getLogger(__name__)

# 多久算「快到期」—— 默认 24 小时
DEFAULT_SOON_HOURS = 24


async def execute(task: TaskRecord) -> dict:
    """
    task_params:
        {
            "product_name": "戴森 V12",     # 监控对象（商品名/关键词）
            "soon_hours": 24,               # 剩余多少小时内算「快到期」，默认 24
            "min_discount": 0,              # 只关心力度 ≥ 这个值的（分），可选
            "platform": "taobao"
        }
    """
    params = task.task_params or {}
    product_name = params.get("product_name", "")
    soon_hours = int(params.get("soon_hours") or DEFAULT_SOON_HOURS)
    min_discount = int(params.get("min_discount") or 0)

    if not product_name:
        return {"error": "缺少 product_name 参数"}

    raw = await call_stdio_tool_async(
        "taobao_mcp", MCP_SERVERS.get("taobao_mcp", {}),
        "taobao.searchMaterial",
        {"q": product_name, "page_size": 10}
    )
    products = parse_search_result(raw)
    if not products:
        return {"status": "no_results", "product_name": product_name}

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 收集所有**尚未结束**的活动
    deals = []
    for p in products:
        for promo in (p.get("promotions") or []):
            end_ms = promo.get("end_ms") or 0
            if end_ms <= now_ms:
                continue                     # 已结束的不报
            hours = (end_ms - now_ms) / 3_600_000
            deals.append({
                "product": str(p.get("title") or "")[:60],
                "product_id": p.get("stable_id") or p.get("item_id") or "",
                "price": p.get("price") or 0,
                "kind": promo.get("title") or "优惠",
                "desc": promo.get("desc") or "",
                "ends_in_hours": round(hours, 1),
                "ends_at": datetime.fromtimestamp(end_ms / 1000, timezone.utc).isoformat(),
            })

    if not deals:
        # 如实说「没查到活动」—— 不编一个出来。补货那版最坏的地方就是
        # 永远返回 ok + triggered:false，看着像在跑其实什么都没做。
        return {
            "status": "no_promotion",
            "product_name": product_name,
            "scanned": len(products),
            "triggered": False,
        }

    deals.sort(key=lambda d: d["ends_in_hours"])
    soon = [d for d in deals if d["ends_in_hours"] <= soon_hours]

    result = {
        "status": "ok",
        "product_name": product_name,
        "scanned": len(products),
        "total_deals": len(deals),
        "soonest": deals[0],
        "soon_count": len(soon),
        "deals": deals[:5],
        # 触发判据：有活动在 soon_hours 内到期
        "triggered": bool(soon),
    }
    if soon:
        d = soon[0]
        result["alert"] = (
            f"「{d['kind']}」{d['ends_in_hours']:.0f} 小时后结束"
            f"：{d['product']}"
            + (f"（{d['desc']}）" if d["desc"] else "")
        )
    return result
