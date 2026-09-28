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


def stable_item_id(item_id) -> str:
    """商品主键 —— 淘宝 item_id 的**稳定段**。

    ⚠️ 淘宝的 item_id 形如 `<随机会话前缀>-<稳定商品标识>`，
    **前缀每次搜索都重新生成**（实测 4 次调用 12 个 id 零重复）。

    直接拿完整 item_id 当主键的后果：同一个商品每次存成一条新的
    price_snapshot，`_get_price_history(product_id)` 永远查不到历史，
    trend 永远算不出 —— 盯价实际上从没盯过任何东西。
    （这个 bug 长期没暴露，因为 task_records 一直是空表，执行器没被真跑过。）

    实测聚合对照：
        完整 item_id：3 次调用 → 18 个「商品」，出现≥2次的 0 个
        稳定段：      4 次调用 →  6 个商品，   每个都出现 4 次

    ⚠️ 没有 '-' 时原样返回 —— PDD 的 goods_id 是纯数字且本身稳定，
    走不到这里；但万一上游换了形状，返回原文比返回空串安全。
    """
    s = str(item_id or "")
    tail = s.partition("-")[2]
    return tail or s


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

        iid = str(_first(raw.get("item_id"), basic.get("item_id"), "") or "")
        # 活动窗口（券/补贴/秒杀的**结束时间**）—— 实测 23/23 件商品都有。
        # deal 执行器靠它做「优惠即将到期」提醒；补货做不了之后，
        # 这是数据覆盖最完整的替代信号。
        promos = []
        for pth in ((promo.get("final_promotion_path_list") or {})
                    .get("final_promotion_path_map_data") or []):
            if not isinstance(pth, dict):
                continue
            end_ms = pth.get("promotion_end_time")
            try:
                end_ms = int(end_ms) if end_ms else 0
            except (TypeError, ValueError):
                end_ms = 0
            if not end_ms:
                continue
            promos.append({
                "title": str(pth.get("promotion_title") or ""),
                "desc": str(pth.get("promotion_desc") or ""),
                "end_ms": end_ms,
            })
        return {
            "item_id": iid,
            "promotions": promos,
            # 跨会话稳定的主键 —— 见 stable_item_id 的说明。
            # item_id 的会话前缀每次搜索都变，凡是**跨调用**要用它当主键的
            # 地方（价格快照、任务去重）都必须用这个。
            "stable_id": stable_item_id(iid),
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

    iid = str(_first(raw.get("item_id"), raw.get("product_id"), raw.get("id"), "") or "")
    return {
        "item_id": iid,
        "stable_id": stable_item_id(iid),      # 见上
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
