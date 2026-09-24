"""
任务执行器公共工具

所有执行器复用的 MCP 结果解析逻辑。

═══ 2026-09-23 修 B6：解析层完全不认识 MCP 真实返回 ═══
旧实现只在 dict 里找 data / items / results 三个键，而 taobao_mcp 的
`taobao.searchMaterial` 真实返回是：

    {
      "result_list": {"map_data": [ {item_basic_info, item_id,
                                     price_promotion_info, ...}, ... ]},
      "total_results": N,
      "request_id": "..."
    }

键名一个都对不上 → **恒返回 []** → 价格/库存/券/榜单/店铺 5 个执行器
全部拿不到数据（它们只认 `price` 字段，真实字段是
`price_promotion_info.zk_final_price`）。

为什么一直没暴露：`task_records` 长期为空表，这些执行器从未被真正跑过。

修法：解析层同时认识「真实淘宝结构」与「扁平结构」，并统一归一成
执行器消费的扁平商品 dict（title / price / original_price / coupon_amount
/ shop_name / item_id），单位统一为**分**（执行器与 PriceSnapshot 都用分）。
"""
import json
import logging

logger = logging.getLogger(__name__)


def _to_cents(value) -> int:
    """价格 → 分。淘宝返回的是元（可能是 '28' / 28 / 28.5）。"""
    try:
        return int(round(float(value) * 100))
    except (TypeError, ValueError):
        return 0


def _first(*values):
    """取第一个非空值 —— MCP 不同接口给的字段名不一致，按优先级兜。"""
    for v in values:
        if v not in (None, "", [], {}):
            return v
    return None


def _normalize_item(raw: dict) -> dict | None:
    """把一条 MCP 商品归一成执行器消费的扁平结构（价格单位：分）。"""
    if not isinstance(raw, dict):
        return None

    # ── 真实结构：基本信息在 item_basic_info，价格在 price_promotion_info ──
    basic = raw.get("item_basic_info")
    promo = raw.get("price_promotion_info")

    if isinstance(basic, dict) or isinstance(promo, dict):
        basic = basic or {}
        promo = promo or {}

        # 价格优先级：到手价(final_promotion_price) > 折扣价(zk_final_price) > 一口价(reserve_price)
        price_yuan = _first(
            promo.get("final_promotion_price"),
            promo.get("zk_final_price"),
            raw.get("price"),
            basic.get("price"),
        )
        original_yuan = _first(promo.get("reserve_price"), promo.get("zk_final_price"))

        price = _to_cents(price_yuan)
        original = _to_cents(original_yuan)
        coupon = max(0, original - price) if (original and price and original > price) else 0

        return {
            "item_id": str(_first(raw.get("item_id"), basic.get("item_id"), "") or ""),
            "title": str(_first(basic.get("title"), basic.get("short_title"), "")),
            "price": price,
            "original_price": original or None,
            "coupon_amount": coupon or None,
            "shop_name": str(_first(basic.get("shop_title"), basic.get("nick"), "")),
            "sales": _first(basic.get("volume"), basic.get("tk_total_sales"), 0) or 0,
            "pict_url": basic.get("pict_url") or "",
        }

    # ── 扁平结构（PDD / 其它 MCP server，或已经是归一过的）──
    price = raw.get("price")
    if price is None and raw.get("price_cents") is not None:
        price, original = raw.get("price_cents"), raw.get("original_price")
    else:
        price, original = _to_cents(price), _to_cents(raw.get("original_price"))

    return {
        "item_id": str(_first(raw.get("item_id"), raw.get("product_id"), raw.get("id"), "") or ""),
        "title": str(_first(raw.get("title"), raw.get("name"), "")),
        "price": price,
        "original_price": original or None,
        "coupon_amount": raw.get("coupon_amount") or raw.get("coupon_info") or None,
        "shop_name": str(_first(raw.get("shop_name"), raw.get("seller_nick"), "")),
        "sales": raw.get("sales") or raw.get("volume") or 0,
        "pict_url": raw.get("pict_url") or raw.get("white_image") or "",
    }


def parse_search_result(raw) -> list[dict]:
    """解析 MCP searchMaterial 返回的商品列表。

    统一出口：返回**归一后的扁平商品 dict**（价格单位：分），
    执行器不需要再关心 MCP 的嵌套结构。

    兼容形态：
    - 真实淘宝：{"result_list": {"map_data": [...]}}
    - JSON 字符串包裹上述任意一种
    - 已解析的 list
    - 旧扁平：{"data" | "items" | "results": [...]}
    """
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"[TaskExecutor] 无法解析 MCP 返回结果: {str(raw)[:200]}")
        return []

    if isinstance(data, dict):
        # ── 真实淘宝结构 ──
        rl = data.get("result_list")
        if isinstance(rl, dict):
            items = rl.get("map_data") or rl.get("data") or []
        elif isinstance(rl, list):
            items = rl
        else:
            # ── 旧/其它结构 ──
            items = data.get("data", data.get("items", data.get("results", [])))
    elif isinstance(data, list):
        items = data
    else:
        return []

    if not isinstance(items, list):
        return []

    out = []
    for it in items:
        norm = _normalize_item(it)
        if norm and norm.get("title") and norm.get("price"):
            out.append(norm)

    if items and not out:
        # 解析出了条目却全被丢掉 —— 大概率是 MCP 换了字段名，值得报警而不是静默
        logger.warning(
            f"[TaskExecutor] MCP 返回 {len(items)} 条但无一可用"
            f"（字段名可能变了）：{json.dumps(items[0], ensure_ascii=False)[:300]}"
        )
    return out
