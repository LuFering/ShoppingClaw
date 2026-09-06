"""
价格监控执行器

定时搜索商品 → 比对价格 → 保存快照 → 返回变化摘要
"""
from datetime import datetime, timezone

from sqlalchemy import select

from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_business import TaskRecord, PriceSnapshot
from src.services.mcp_service import call_stdio_tool_async, MCP_SERVERS

from src.services.task_executors.common import parse_search_result


async def execute(task: TaskRecord) -> dict:
    """
    执行价格监控任务。

    task_params 结构:
        {
            "product_name": "iPhone 15 Pro",
            "target_price": 5000,       # 目标价（分），可选
            "platform": "taobao"        # taobao/pdd
        }

    执行流程:
        1. 调用 MCP 搜索商品
        2. 解析价格、优惠券
        3. 保存 PriceSnapshot
        4. 返回变化摘要
    """
    params = task.task_params or {}
    product_name = params.get("product_name", "")
    target_price = params.get("target_price")  # 可选
    platform = params.get("platform", "taobao")

    if not product_name:
        return {"error": "缺少 product_name 参数"}

    # 1. 调用 MCP 搜索
    server_name = "taobao_mcp"
    server_config = MCP_SERVERS.get(server_name, {})
    raw = await call_stdio_tool_async(
        server_name, server_config,
        "taobao.searchMaterial",
        {"q": product_name, "page_size": 5}
    )

    # 2. 解析结果
    products = parse_search_result(raw)
    if not products:
        return {"status": "no_results", "product_name": product_name, "count": 0}

    # 3. 查找匹配商品 + 保存快照
    matched = _find_best_match(products, product_name)
    if not matched:
        return {"status": "no_match", "product_name": product_name, "candidates": len(products)}

    snapshot = await _save_snapshot(matched, platform)

    # 4. 与目标价比对
    current_price = matched.get("price", 0)
    result = {
        "status": "ok",
        "product_name": matched.get("title", product_name),
        "product_id": snapshot.product_id,
        "current_price": current_price,
        "original_price": matched.get("original_price"),
        "coupon_amount": matched.get("coupon_amount"),
        "shop_name": matched.get("shop_name"),
    }

    if target_price and current_price <= target_price:
        result["alert"] = f"已降至目标价 {target_price/100:.2f} 以下！当前 {current_price/100:.2f}"
        result["triggered"] = True
    else:
        result["triggered"] = False

    # 5. 查历史趋势（最近7天）
    history = await _get_price_history(snapshot.product_id, days=7)
    if len(history) >= 2:
        result["trend"] = _calc_trend(history)

    return result


# ── 辅助函数 ──

def _find_best_match(products: list[dict], query: str) -> dict | None:
    """在搜索结果中按关键词匹配最佳商品"""
    if not products:
        return None
    # 简单关键词匹配
    query_lower = query.lower()
    for p in products:
        title = str(p.get("title", p.get("name", ""))).lower()
        if query_lower in title:
            return p
    # 没精确匹配，返回第一个
    return products[0]


async def _save_snapshot(product: dict, platform: str) -> PriceSnapshot:
    """保存价格快照到数据库"""
    product_id = str(product.get("item_id", product.get("product_id", product.get("id", ""))))
    snapshot = PriceSnapshot(
        product_id=product_id,
        product_name=str(product.get("title", product.get("name", "")))[:500],
        platform=platform,
        price=int(product.get("price", 0)),
        original_price=product.get("original_price"),
        coupon_amount=product.get("coupon_amount"),
        stock_status="in_stock",
        shop_name=str(product.get("shop_name", product.get("seller_nick", "")))[:200],
        snapshot_at=datetime.now(timezone.utc),
    )
    async with pg_manager.get_async_session_context() as session:
        session.add(snapshot)
        await session.commit()
    return snapshot


async def _get_price_history(product_id: str, days: int = 7) -> list[PriceSnapshot]:
    """获取商品最近 N 天的价格历史"""
    from datetime import timedelta
    since = datetime.now(timezone.utc) - timedelta(days=days)
    async with pg_manager.get_async_session_context() as session:
        result = await session.execute(
            select(PriceSnapshot)
            .where(PriceSnapshot.product_id == product_id, PriceSnapshot.snapshot_at >= since)
            .order_by(PriceSnapshot.snapshot_at.asc())
        )
        return list(result.scalars().all())


def _calc_trend(history: list[PriceSnapshot]) -> dict:
    """计算价格趋势"""
    prices = [s.price for s in history if s.price]
    if len(prices) < 2:
        return {"direction": "flat"}
    first_price = prices[0]
    last_price = prices[-1]
    change_pct = (last_price - first_price) / first_price * 100 if first_price else 0
    return {
        "direction": "down" if change_pct < -1 else ("up" if change_pct > 1 else "flat"),
        "change_pct": round(change_pct, 1),
        "first_price": first_price,
        "last_price": last_price,
        "snapshots": len(prices),
    }
