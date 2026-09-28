"""通知事件服务 —— 打通「定时任务执行完 → 用户能看到」这段断链。

背景（2026-09-23 实读）：
  `TaskRecord.notify_enabled` / `notify_channels` 两个字段**全仓没有任何
  消费方**（grep 排除字段定义与前端表单后为空）。任务跑完只写进
  `task_execution_logs`，用户永远不知道 —— 主动助理页面上的"命中提醒"
  因此只能是演示数据。

设计约束（与项目铁律一致）：
  1. **不新建表**。通知是 `task_execution_logs` 的**派生视图**，不是事实。
     建表会立刻面临"任务删了通知还在"这类一致性问题。事件从执行结果现算。
  2. **PG 是主真相**：这里只做"最近事件的快速出口"，用 Redis List 兜住
     最近 200 条；要回溯更久直接查 `task_execution_logs`。
  3. **永不抛异常**。通知失败绝不能影响任务执行本身 —— 所有公开函数
     内部 try/except 全包，失败只记 warning。
  4. **时间戳统一** `datetime.now(timezone.utc).isoformat()`（AGENTS.md 铁律 #3）。

存储结构：
  user:{uid}:events             List  —— 最近事件（LPUSH + LTRIM 200），7 天 TTL
  user:{uid}:events:dismissed   Set   —— 用户已忽略/已处理的事件 id

事件契约（前端 home_api.js / assistant_api.js 已声明，此处一字不差对齐）：
  {id, type, main, sub, time}
  type ∈ price | coupon | deal | decide | fav | prefer | care | review
        （语义表见 AgentChatComponent.vue 的 statusTypeMeta，不发明新类型）
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from src.services.redis_cache import get_redis_cache

logger = logging.getLogger(__name__)

# ── Redis key 约定 ──
EVENTS_KEY = "user:{}:events"
DISMISSED_KEY = "user:{}:events:dismissed"
# 已通知过的 run id —— 同一个 run 只发一次（见 notify_run_once）
NOTIFIED_KEY = "user:{}:events:notified"

MAX_EVENTS = 200          # 每个用户最多保留的事件数
EVENTS_TTL = 7 * 86400    # 7 天，过期自然清理，避免 Redis 无限增长

# ── 事件类型（与前端 statusTypeMeta 对齐，不新增）──
TASK_TYPE_TO_EVENT = {
    "price": "price",
    "deal": "deal",
    "coupon": "coupon",
    "rank": "price",    # 排名异动本质是价格竞争信号，复用「盯价」语义
    "shop": "coupon",   # 店铺活动展示的也是券/满减，复用「券」语义
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    """事件 id：时间前缀保证有序，短随机后缀防撞。"""
    return f"ev-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"


def _money(cents: Any) -> str:
    """分 → '¥2899'。执行器里的价格单位是分。"""
    try:
        value = int(cents or 0)
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""
    yuan = value / 100
    return f"¥{yuan:.0f}" if yuan == int(yuan) else f"¥{yuan:.2f}"


def _rel_time(iso_ts: str | None) -> str:
    """ISO 时间 → 前端用的相对文案（'2小时前'）。

    前端 fmtAgo 在 task_api.js 里是对 ISO 处理的；事件流这边只给
    相对文案即可，省得前端再引一次工具函数。
    """
    if not iso_ts:
        return ""
    try:
        raw = iso_ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
    except (ValueError, AttributeError):
        return ""

    secs = int(delta.total_seconds())
    if secs < 60:
        return "刚刚"
    if secs < 3600:
        return f"{secs // 60}分钟前"
    if secs < 86400:
        return f"{secs // 3600}小时前"
    days = secs // 86400
    return "昨天" if days == 1 else f"{days}天前"


# ══════════════════════════════════════════════════════════
# 执行结果 → 事件
# ══════════════════════════════════════════════════════════

def from_task_result(task: Any, result: Any) -> dict | None:
    """把一次任务执行结果转成事件；没有值得打扰用户的内容时返回 None。

    「值得打扰」的判定很关键 —— 每次都推送"价格没变"会把通知变成噪音，
    用户很快就会全部忽略。所以：
      · status 不是 ok           → 不打扰（no_results / no_match 是常态）
      · triggered 明确为 False   → 不打扰（执行器自己判定没到阈值）
      · agent 类型完成任务        → 打扰（每小时简报/汇总属于用户主动要的）
      · 其余 ok 且有实质内容      → 打扰
    """
    if not isinstance(result, dict):
        return None

    status = str(result.get("status") or "").lower()
    task_type = str(getattr(task, "task_type", "") or "")
    task_name = str(getattr(task, "name", "") or "")
    event_type = TASK_TYPE_TO_EVENT.get(task_type, "decide")

    # 失败要告知 —— 用户配了监控却悄悄不跑了，比不推更糟
    if status in ("failed", "error") or result.get("error"):
        reason = str(result.get("error") or "执行失败")
        return _mk(
            event_type="review",
            main=f"「{task_name}」执行失败",
            sub=reason[:80],
            task=task,
        )

    # agent 定时任务：prompt 的结果本身就是产物，无条件上报
    if task_type == "agent" and status == "ok":
        summary = str(result.get("response") or "").strip()
        first = summary.splitlines()[0][:60] if summary else "已完成"
        return _mk(
            event_type="decide",
            main=f"{task_name}：{first}",
            sub=(summary[60:140] if len(summary) > 60 else "点击查看完整汇总"),
            task=task,
        )

    if status != "ok":
        return None

    if task_type == "price":
        return _price_event(task, result, event_type)
    if task_type == "deal":
        return _deal_event(task, result, event_type)
    if task_type == "coupon":
        return _coupon_event(task, result, event_type)
    if task_type == "rank":
        return _rank_event(task, result, event_type)
    if task_type == "shop":
        return _shop_event(task, result, event_type)

    # 未知类型但有 alert：给个通用卡，别丢信息
    alert = result.get("alert")
    if alert:
        return _mk(event_type=event_type, main=str(alert)[:60], sub=task_name, task=task)
    return None


# ══════════════════════════════════════════════════════════════════
# 送礼 / 采购 run 的通知
# ══════════════════════════════════════════════════════════════════
# 2026-09-29：这两个 agent 跑完原本**不发任何通知** —— `emit()` 的调用方
# 只有 scheduler_service 一处。用户在主页状态卡与助理页都看不到提示，
# 而它们恰恰是用户会离开页面等一两分钟的长任务。
#
# 事件类型复用已有的（`decide` / `review`），前端不用改 —— 见文件顶部
# 「不发明新类型」的约定。

async def notify_run_once(user_id: str, run_id: str, event: dict | None) -> bool:
    """把 run 的结果作为事件发出去，**同一个 run 只发一次**。

    返回是否真的发了（去重命中或 event 为空都返回 False）。

    ⚠️ 为什么需要去重：`advance()` 的正常收尾与 except 分支都可能走到
    「收敛/失败」，用户重试、`mark_delivered` 也可能再触发同一路径。
    不去重就是同一件事刷好几条通知。

    用 Redis Set 记录已通知的 run_id，**不新建 PG 表** —— 通知是派生视图
    不是事实（见文件顶部约束 #1）。TTL 与事件流一致（7 天）。
    """
    if not user_id or not run_id or not isinstance(event, dict):
        return False
    try:
        cache = get_redis_cache()
        if not cache._connected or cache._redis is None:
            await cache.connect()
        key = NOTIFIED_KEY.format(user_id)
        # SADD 返回 1 = 新加入（首次），0 = 已存在（重复）
        added = await cache._redis.sadd(key, str(run_id))
        if not added:
            return False
        await cache._redis.expire(key, EVENTS_TTL)
    except Exception as e:
        # ⚠️ 去重表读不到时**宁可发**（用户看到重复好过什么都没看到），
        # 但要留痕 —— 静默吞掉会让「为什么发了三条」无从查起。
        logger.warning(f"[notify] 去重检查失败，仍发送: {e}")

    await emit(user_id, event)
    return True


def _g(run: Any, key: str, default=None):
    """从 run（ORM 对象或 dict）取字段 —— 两种形状都要支持。"""
    if run is None:
        return default
    if isinstance(run, dict):
        return run.get(key, default)
    return getattr(run, key, default)


def from_gift_run(run: Any) -> dict | None:
    """送礼推演收敛/失败 → 事件。没有可用内容时返回 None。

    字段依据实测的 GiftRun 列（不是猜的）：
      recipient / occasion / budget / profile / products
    """
    if run is None:
        return None

    status = str(_g(run, "status") or "")
    recipient = str(_g(run, "recipient") or "对方")
    occasion = str(_g(run, "occasion") or "")

    if status == "failed":
        return _mk(
            event_type="review",
            main=f"「给{recipient}的{occasion or '送礼'}推演」执行失败",
            sub=str(_g(run, "error") or "未给出原因")[:80],
            task=None,
        )
    if status != "converged":
        return None

    # 内容取自档案与礼盒 —— 与中栏/右栏同源，不另算一套。
    # ⚠️ `products.plan` 里的 price 单位是**元**（送礼侧的口径），
    # 与执行器的「分」不同，所以这里不再乘 100。
    prof = _g(run, "profile") or []
    plan = (_g(run, "products") or {}).get("plan") or {}
    items = plan.get("items") or []

    # 没方案也没档案 = 跑完了但没产出，不值得打扰
    if not items and not prof:
        return None

    parts = []
    if occasion:
        parts.append(occasion)
    if items:
        parts.append(f"{len(items)} 件")
        total = sum(int(i.get("price") or 0) for i in items)
        if total:
            parts.append(f"¥{total:,}")
    elif prof:
        parts.append(f"档案 {len(prof)} 条")

    title = str(plan.get("title") or "").strip()
    return _mk(
        event_type="decide",
        main=(f"{recipient}的礼物方案已生成" + (f"：{title}" if title else "")),
        sub=" · ".join(parts) or "点击查看",
        task=None,
    )


def from_planning_run(run: Any, report: dict | None = None) -> dict | None:
    """采购规划收敛/失败 → 事件。没有可用内容时返回 None。

    字段依据实测的 PlanningRun 列：
      scene / subject / budget / products

    ⚠️ 报告摘要**不在 run 上** —— 它由 `st.build_deliverable` 按 state 现算。
    调用方已经为发 `deliverable` 事件算过一次，把结果传进来即可
    （`report`），避免这里再算一遍（两次结果可能不一致）。
    """
    if run is None:
        return None

    status = str(_g(run, "status") or "")
    if status == "failed":
        return _mk(
            event_type="review",
            main="「采购规划」执行失败",
            sub=str(_g(run, "error") or "未给出原因")[:80],
            task=None,
        )
    if status != "converged":
        return None

    subject = str(_g(run, "subject") or "")
    scene = str(_g(run, "scene") or "")

    # headline 的位置（实测）：get_deliverable() → {id, name, data:{headline:{...}}}
    # 也容忍调用方直接传 data，或直接传 headline。
    head: dict = {}
    if isinstance(report, dict):
        for cand in (report.get("data"), report):
            if isinstance(cand, dict) and isinstance(cand.get("headline"), dict):
                head = cand["headline"]
                break

    parts = []
    if head.get("categories"):
        parts.append(f"{head['categories']} 个品类")
    if head.get("total") is not None:
        parts.append(f"¥{int(head['total']):,}")
    if not parts:
        parts.append("点击查看")

    label = subject or scene or "采购规划"
    return _mk(
        event_type="decide",
        main="采购规划已收敛，等你确认",
        sub=f"{label[:24]} · " + " · ".join(parts),
        task=None,
    )


def _mk(*, event_type: str, main: str, sub: str, task: Any) -> dict:
    return {
        "id": _new_id(),
        "type": event_type,
        "main": main[:80],
        "sub": sub[:120],
        "time": _rel_time(_now_iso()) or "刚刚",
        "task_id": str(getattr(task, "id", "") or ""),
        "task_name": str(getattr(task, "name", "") or ""),
        "created_at": _now_iso(),
    }


def _price_event(task: Any, r: dict, event_type: str) -> dict | None:
    """价格监控：只在真触发（到目标价）或明显降价时打扰。"""
    title = str(r.get("product_name") or r.get("product_name") or "").strip()
    price = _money(r.get("current_price"))
    target = r.get("target_price")

    if r.get("triggered") and r.get("alert"):
        return _mk(event_type=event_type, main=str(r["alert"])[:60],
                   sub=f"{title} · 当前 {price}".strip(" ·"), task=task)

    # 没触发但有趋势下跌 —— 值得看一眼，但不做"命中"处理
    trend = r.get("trend") or {}
    if trend.get("direction") == "down" and abs(trend.get("change_pct") or 0) >= 5:
        return _mk(
            event_type=event_type,
            main=f"{title} 近 7 天降了 {abs(trend['change_pct'])}%",
            sub=f"当前 {price}" + (f" · 目标 {_money(target)}" if target else ""),
            task=task,
        )

    return None


def _deal_event(task: Any, r: dict, event_type: str) -> dict | None:
    """优惠到期：只在**真的有活动快结束**时打扰。

    ⚠️ 取代了原来的 `_stock_event`（2026-09-29）。补货监控已下线 ——
    导购 MCP 不提供库存数据，那个执行器恒返回 triggered:false，
    永远不会走到这里。
    """
    if not r.get("triggered"):
        return None
    d = r.get("soonest") or {}
    hours = d.get("ends_in_hours")
    main = str(r.get("alert") or "优惠即将结束")[:60]
    if hours is not None and not r.get("alert"):
        main = f"{str(d.get('kind') or '优惠')} {hours:.0f} 小时后结束"
    return _mk(
        event_type=event_type,
        main=main,
        sub=str(d.get("desc") or d.get("product") or r.get("product_name") or "")[:120],
        task=task,
    )


def _coupon_event(task: Any, r: dict, event_type: str) -> dict | None:
    """优惠券：报面额最大的那张。

    ⚠️ 2026-09-29 跟着执行器改：不再读 `alerts` / `after_coupon` ——
    前者是「差价 > 半价」的假告警（10/10 恒命中），后者是双重扣减
    （final_promotion_price 已是到手价，再减一次归零）。
    现在读执行器新给的 `top_coupons`（真券，面额从「满X减Y」解析）。
    """
    tops = r.get("top_coupons") or []
    if not tops:
        return None
    best = max(tops, key=lambda x: x.get("coupon_face") or 0)
    amount = _money(best.get("coupon_face"))
    kind = str(best.get("coupon_kind") or "券")
    return _mk(
        event_type=event_type,
        main=f"发现 {amount} {kind}：{str(best.get('title') or '')[:30]}",
        # 到手价已含该券 —— 不报「券后价」，那会误导（实测归零）
        sub=str(best.get("coupon_desc") or r.get("keyword") or ""),
        task=task,
    )


def _rank_event(task: Any, r: dict, event_type: str) -> dict | None:
    """排名：执行器已用 triggered 表达「变动 ≥3 位」，直接采信。"""
    if not r.get("triggered") or not r.get("alert"):
        return None
    return _mk(
        event_type=event_type,
        main=str(r["alert"])[:60],
        sub=f"{r.get('keyword') or ''} · 当前第 {r.get('current_rank') or '—'} 位",
        task=task,
    )


def _shop_event(task: Any, r: dict, event_type: str) -> dict | None:
    """店铺活动：只报深度折扣（执行器阈值 30%）。"""
    deep = r.get("deep_discounts") or []
    if not deep:
        return None
    best = max(deep, key=lambda x: x.get("price") or 0)
    return _mk(
        event_type=event_type,
        main=f"{r.get('shop_name') or '店铺'}：{str(best.get('title') or '')[:28]} 直降 {best.get('discount')}",
        sub=f"现价 {_money(best.get('price'))}",
        task=task,
    )


# ══════════════════════════════════════════════════════════
# 存取
# ══════════════════════════════════════════════════════════

async def emit(user_id: str, event: dict | None) -> None:
    """写入事件 + 尽力实时推送。**永不抛异常。**

    推送走 SSE 会话 `notify:{user_id}` —— 前端打开主动助理页时订阅，
    关掉就收不到，这正是想要的语义（离线事件仍在 Redis 里，下次进页面
    拉 `/api/events/recent` 补上）。
    """
    if not user_id or not isinstance(event, dict):
        return

    try:
        cache = get_redis_cache()
        if not cache._connected or cache._redis is None:
            await cache.connect()

        key = EVENTS_KEY.format(user_id)
        await cache._redis.lpush(key, json.dumps(event, ensure_ascii=False))
        await cache._redis.ltrim(key, 0, MAX_EVENTS - 1)
        await cache._redis.expire(key, EVENTS_TTL)
    except Exception as e:
        logger.warning(f"[notify] 写入事件失败（忽略）: {e}")

    # 实时推送：失败不影响主流程
    try:
        from src.services.sse_session_manager import get_session_manager

        mgr = get_session_manager()
        sid = f"notify:{user_id}"
        session = getattr(mgr, "_sessions", {}).get(sid)
        if session is not None and session.is_active:
            mgr.emit_nowait(sid, {"type": "notify_event", "event": event})
    except Exception as e:
        logger.debug(f"[notify] 实时推送失败（忽略）: {e}")


async def dismissed_ids(user_id: str) -> set[str]:
    """取用户已忽略/已处理的 id 集合。永不抛异常（失败返回空集）。

    调用方不止事件流：助理页的情报流卡片来自 task_execution_logs
    （id 形如 `log-12`），与事件流的 `ev-...` 共用同一个忽略集合 ——
    忽略是「用户不想再看这条」的语义，与它从哪个出口来无关。
    """
    if not user_id:
        return set()
    try:
        cache = get_redis_cache()
        if not cache._connected or cache._redis is None:
            await cache.connect()

        raw = await cache._redis.smembers(DISMISSED_KEY.format(user_id))
        return {x.decode() if isinstance(x, bytes) else str(x) for x in (raw or [])}
    except Exception as e:
        logger.warning(f"[notify] 读取已忽略集合失败（返回空）: {e}")
        return set()


async def recent(user_id: str, limit: int = 8) -> list[dict]:
    """取最近事件（新的在前），过滤掉用户已忽略的。永不抛异常。"""
    if not user_id:
        return []
    try:
        cache = get_redis_cache()
        if not cache._connected or cache._redis is None:
            await cache.connect()

        raw = await cache._redis.lrange(EVENTS_KEY.format(user_id), 0, max(limit * 3, limit) - 1)
        dismissed = await dismissed_ids(user_id)

        out: list[dict] = []
        for item in raw:
            try:
                ev = json.loads(item)
            except (json.JSONDecodeError, TypeError):
                continue
            if ev.get("id") in dismissed:
                continue
            # 时间按取出时刻重算，避免存进去的"刚刚"永远不变
            ev["time"] = _rel_time(ev.get("created_at")) or ev.get("time") or ""
            out.append(ev)
            if len(out) >= limit:
                break
        return out
    except Exception as e:
        logger.warning(f"[notify] 读取事件失败（返回空）: {e}")
        return []


async def dismiss(user_id: str, event_id: str) -> bool:
    """标记事件已忽略/已处理。永不抛异常。"""
    if not user_id or not event_id:
        return False
    try:
        cache = get_redis_cache()
        if not cache._connected or cache._redis is None:
            await cache.connect()

        key = DISMISSED_KEY.format(user_id)
        await cache._redis.sadd(key, event_id)
        await cache._redis.expire(key, EVENTS_TTL)
        return True
    except Exception as e:
        logger.warning(f"[notify] 忽略事件失败: {e}")
        return False
