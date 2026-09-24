"""主动助理聚合服务 —— `/api/assistant/overview` 的数据来源。

设计原则（与方案 §1.2 一致）：
  1. **不新建表、不缓存**。四个字段全部从 PG 实时聚合：
       feed    ← task_execution_logs join task_records
       todos   ← shopping_decisions（need / decided）+ 未完成 reminders
       brief   ← 当日事件聚合 + 三个统计数
       messages← 上述三者合成卡片序列
     数据是派生的，缓存只会带来"删了任务但卡片还在"这类一致性问题。

  2. **永不抛异常**。主动助理是装饰性界面，任一子查询失败都只让那一块为空，
     整体接口必须返回 200（与 home/suggestion_service 的降级哲学一致）。

  3. 用户口径统一 `str(users.id)`（与 decisions_router / task_router 同）。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from src.services import notify_service
from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_business import (
    ShoppingDecision,
    TaskExecutionLog,
    TaskRecord,
)

logger = logging.getLogger(__name__)

FEED_LIMIT = 20      # 情报流条数
MESSAGE_LIMIT = 30   # 左栏卡片数
BRIEF_POINT_LIMIT = 6
# 取日志时多取一些：忽略过滤发生在内存里，取满 FEED_LIMIT 条再筛会变少
FEED_SCAN = FEED_LIMIT * 3

# 执行日志状态 → 前端五态（与 task_api.js 的 mapLastResult 同语义）
LOG_RESULT_MAP = {
    "success": "ok",
    "failed": "fail",
    "timeout": "fail",
    "running": "run",
    "cancelled": "empty",
}


def _local_day_start() -> tuple[datetime, str]:
    """(本地日 00:00 对应的 naive UTC 时刻, 本地日期的显示文案)。

    库里存的是 naive UTC，而「今天」对用户来说是**本地日**。
    直接拿 UTC 日期切边界，会让 UTC+8 的用户在早上 8 点前把前一天的数据
    算进今天（反之亦然）。

    两个值都要返回：边界是 UTC 时刻（用于比较），显示文案是**本地**日期
    （用于卡片标题）。只返回前者再 strftime 会打印出 UTC 的日期 ——
    本地 9/24 早上 8 点前，UTC 边界落在 9/23，标题就会写成 09月23日。
    """
    local_now = datetime.now().astimezone()
    local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_midnight.astimezone(timezone.utc).replace(tzinfo=None), local_now.strftime("%m月%d日")


def _is_today(dt: datetime | None, day_start_utc: datetime) -> bool:
    """该时刻是否落在「今天」（本地日）。"""
    if not isinstance(dt, datetime):
        return False
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt >= day_start_utc


def _rel_time(dt: datetime | None) -> str:
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    secs = int(delta.total_seconds())
    if secs < 60:
        return "刚刚"
    if secs < 3600:
        return f"{secs // 60}分钟前"
    if secs < 86400:
        return f"{secs // 3600}小时前"
    days = secs // 86400
    return "昨天" if days == 1 else f"{days}天前"


def _clock(dt: datetime | None) -> str:
    """datetime → '今天 HH:MM'。库里是 naive UTC，需转本地。"""
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone()
    return f"今天 {local.hour:02d}:{local.minute:02d}"


def _summarize_log(result: dict | None, error: str | None) -> str:
    """执行结果 → 一行人话摘要。"""
    if error:
        return str(error)[:80]
    if not isinstance(result, dict):
        return ""
    for key in ("alert", "summary", "message"):
        if result.get(key):
            return str(result[key])[:80]

    status = str(result.get("status") or "")
    if status == "no_results":
        name = result.get("product_name") or result.get("keyword") or result.get("shop_name") or "目标"
        return f"{name}：暂时没搜到"
    if status == "no_match":
        return "没匹配到目标商品"
    if status == "ok":
        if result.get("response"):
            # agent 类型：取回复首行
            return str(result["response"]).splitlines()[0][:80]
        if result.get("current_price"):
            return f"当前 ¥{int(result['current_price']) / 100:.0f}"
        if result.get("with_coupons") is not None:
            return f"{result.get('with_coupons')} 件有券"
        return "已执行"
    return ""


# ══════════════════════════════════════════════════════════
# 四块数据
# ══════════════════════════════════════════════════════════

async def build_feed(user_id: str) -> list[dict]:
    """情报流：最近的执行日志（跨该用户所有任务）。

    忽略（dismiss）过滤在这里做：情报流的卡片 id 是 `log-{id}`，与事件流
    的 `ev-...` 共用同一个 Redis 忽略集合（见 notify_service.dismissed_ids）。
    不这么做的话，助理页的「忽略」按钮点了没有任何效果 —— 它和首页状态卡
    是同一批数据的两个出口，忽略语义必须一致。
    """
    try:
        dismissed = await notify_service.dismissed_ids(user_id)
    except Exception:
        dismissed = set()

    day_start = _local_day_start()[0]

    try:
        async with pg_manager.get_async_session_context() as session:
            rows = await session.execute(
                select(TaskExecutionLog, TaskRecord)
                .join(TaskRecord, TaskRecord.id == TaskExecutionLog.task_id)
                .where(TaskRecord.user_id == user_id)
                .order_by(TaskExecutionLog.started_at.desc())
                .limit(FEED_SCAN)
            )
            out = []
            for log, task in rows.all():
                if f"log-{log.id}" in dismissed:
                    continue
                result = log.result_data if isinstance(log.result_data, dict) else None
                # 「命中」是更有信息量的状态：执行器自己判定的 triggered
                res_state = LOG_RESULT_MAP.get(log.status, "empty")
                if result and result.get("triggered") and res_state == "ok":
                    res_state = "hit"
                out.append({
                    "id": f"log-{log.id}",
                    "result": res_state,
                    "product": task.name or "—",
                    "change": _summarize_log(result, log.error_message),
                    "time": _rel_time(log.started_at),
                    "taskId": task.id,
                    # 命中类型 = 任务类型，供卡片选语义色与文案。前端 hitLabel
                    # 的键恰好就是这 5 个（price/stock/coupon/rank/shop），所以
                    # 这里直接用原始 task_type，不走事件的类型收敛
                    # （notify_service 把 rank→price、shop→coupon 是因为事件流
                    # 的 statusTypeMeta 没有这两个语义，卡片这边有）。
                    # 原来前端把它写死成 price/stock 二选一，导致券、补货、
                    # 榜单类命中全都显示成「降价提醒」。
                    "hitType": str(task.task_type or ""),
                    # 供 build_brief 按「本地日」切分统计。放布尔而不是原始
                    # datetime：后者会被 FastAPI 序列化进响应，白白泄露一个
                    # 前端用不到的字段。
                    "today": _is_today(log.started_at, day_start),
                })
                if len(out) >= FEED_LIMIT:
                    break
            return out
    except Exception as e:
        logger.warning(f"[assistant] feed 聚合失败: {e}")
        return []


async def build_todos(user_id: str) -> list[dict]:
    """待办：购物档案里等待用户行动的记录 + 未完成的提醒。

    三类对应前端的 kindLabel：
      draft（待确认）← phase=need    —— AI 归档的草稿等用户确认
      buy  （该下单）← phase=decided —— 已选好等下单
      wait （继续等）← 使用中/已决策记录里未完成的提醒
    """
    todos: list[dict] = []
    try:
        async with pg_manager.get_async_session_context() as session:
            rows = await session.execute(
                select(ShoppingDecision).where(
                    ShoppingDecision.user_id == user_id,
                    ShoppingDecision.phase.in_(("need", "decided", "using")),
                )
            )
            for row in rows.scalars().all():
                data = row.data or {}
                target = str(data.get("target") or "未命名")
                phase = str(row.phase)

                if phase == "need":
                    note = str(data.get("aiSummary") or data.get("note") or "")[:60]
                    todos.append({
                        "id": f"todo-{row.id}",
                        "kind": "draft",
                        "kindLabel": "待确认",
                        "text": f"「{target}」草稿待确认",
                        "note": note or (f"预算 {data.get('budget')}" if data.get("budget") else "等待你补充需求"),
                    })
                elif phase == "decided":
                    todos.append({
                        "id": f"todo-{row.id}",
                        "kind": "buy",
                        "kindLabel": "该下单",
                        "text": f"{target} {data.get('bestPrice') or ''}".strip(),
                        "note": str(data.get("recReason") or data.get("aiRecommend") or "已选好，可下单")[:60],
                    })

                # 未完成的提醒 —— 归一化两种历史形状（同 B1）
                for rm in (data.get("reminders") or []):
                    if isinstance(rm, str):
                        text, at = rm.strip(), ""
                    elif isinstance(rm, dict):
                        if rm.get("done"):
                            continue
                        text = str(rm.get("text") or "").strip()
                        at = rm.get("at") or rm.get("due") or ""
                    else:
                        continue
                    if not text:
                        continue
                    todos.append({
                        "id": f"rem-{row.id}-{len(todos)}",
                        "kind": "wait",
                        "kindLabel": "继续等",
                        "text": text[:60],
                        "note": (f"{target} · {at}" if at else target)[:60],
                    })
            return todos
    except Exception as e:
        logger.warning(f"[assistant] todos 聚合失败: {e}")
        return todos


async def build_watching(user_id: str) -> list[dict]:
    """在盯的监控任务清单 —— 右栏「监控」tab 的数据（方案 §4 P4 / U2）。

    为什么单列一块：U2 的结论是「右栏放左栏没有的维度」——
    左栏（消息卡片）讲**现在发生了什么**（事件/命中），
    右栏讲**我在盯什么 / 我该做什么**（任务清单 + 待办）。
    简报从右栏撤掉（它已经是左栏第一张卡），避免同一条信息看两遍。

    只取 active/paused，已完成的没有「在盯」语义。
    """
    out: list[dict] = []
    try:
        async with pg_manager.get_async_session_context() as session:
            rows = await session.execute(
                select(TaskRecord)
                .where(
                    TaskRecord.user_id == user_id,
                    TaskRecord.status.in_(("active", "paused")),
                )
                .order_by(TaskRecord.created_at.desc())
            )
            for t in rows.scalars().all():
                params = t.task_params or {}
                out.append({
                    "id": t.id,
                    "name": t.name or "—",
                    "taskType": str(t.task_type or ""),
                    "active": t.status == "active",
                    "target": _describe_target(t.task_type, params),
                    "freq": _describe_freq(t.interval_seconds, t.cron_expression),
                    "nextAt": _rel_time_short(t.next_run_at),
                    "lastAt": _rel_time(t.last_run_at),
                    "runCount": t.run_count or 0,
                })
            return out
    except Exception as e:
        logger.warning(f"[assistant] watching 聚合失败: {e}")
        return out


def _describe_target(task_type: Any, params: dict) -> str:
    """监控对象 → 一行文案（与 task_api.js 的 describeTarget 同口径）。"""
    tt = str(task_type or "")
    if tt == "price":
        base = str(params.get("product_name") or params.get("keyword") or "")
        tp = params.get("target_price")
        return f"{base} · 目标 ¥{int(tp) / 100:.0f}" if tp else (base or "—")
    if tt == "coupon":
        base = str(params.get("keyword") or "")
        mc = params.get("min_coupon_amount")
        return f"{base} · ≥¥{int(mc) / 100:.0f}券" if mc else (base or "—")
    if tt == "rank":
        return str(params.get("keyword") or params.get("product_name") or "—")
    if tt == "shop":
        return str(params.get("shop_name") or "—")
    if tt == "stock":
        return str(params.get("product_name") or "—")
    if tt == "agent":
        return str(params.get("prompt") or "—")[:40]
    return "—"


def _describe_freq(interval_seconds: Any, cron: Any) -> str:
    """调度 → 人话（「每 6 小时」/「每天 09:00」）。

    cron 是标准五段 `分 时 日 月 周`（task_api.js buildSchedule 拼的是
    `${min} ${hour} * * ${dow}`），所以分钟在 p[0]、小时在 p[1]。
    """
    if interval_seconds:
        hours = max(1, int(interval_seconds) // 3600)
        return f"每 {hours} 小时" if hours < 24 else f"每 {hours // 24} 天"
    if cron:
        p = str(cron).split()
        if len(p) == 5:
            minute, hour, _, _, dow = p
            try:
                hm = f"{int(hour):02d}:{int(minute):02d}"
            except ValueError:
                return str(cron)
            return f"每天 {hm}" if dow == "*" else f"每周 {dow} {hm}"
    return "—"


def _rel_time_short(dt: datetime | None) -> str:
    """下次执行 → 「3 小时后」这类短文案（前端 fmtClock 口径的简化版）。"""
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = dt - datetime.now(timezone.utc)
    secs = int(delta.total_seconds())
    if secs <= 0:
        return "即将执行"
    if secs < 3600:
        return f"{secs // 60} 分钟后"
    if secs < 86400:
        return f"{secs // 3600} 小时后"
    return f"{secs // 86400} 天后"


async def build_brief(user_id: str, feed: list[dict], todos: list[dict]) -> dict:
    """每日简报：统计 + 要点。纯规则，不调 LLM（方案 §4 P2）。

    **口径修正（2026-09-24）**：原先 `hits` 统计的是 feed 里的命中条数，
    而 feed 是「最近 20 条执行日志」—— 跨越任意天数。卡片却写着
    「今天需要你知道的」，等于拿近 N 条冒充「今天」，任务一多就会把
    昨天的命中算进今天。
    现在改为按**本地日**切分：只统计今天 00:00 之后开始的执行。
    """
    # 边界已在 build_feed 按同一天算好并写进每条的 today 标记，
    # 这里只需取显示用的本地日期文案。
    _, today_label = _local_day_start()
    hits = sum(1 for f in feed if f.get("result") == "hit" and f.get("today"))
    drafts = sum(1 for t in todos if t.get("kind") == "draft")

    watching = 0
    try:
        async with pg_manager.get_async_session_context() as session:
            r = await session.execute(
                select(TaskRecord.id).where(
                    TaskRecord.user_id == user_id, TaskRecord.status == "active"
                )
            )
            watching = len(r.all())
    except Exception as e:
        logger.warning(f"[assistant] 在盯任务数统计失败: {e}")

    points: list[dict] = []

    # 命中事件最有信息量，优先展示（只取今天的）
    for f in feed:
        if f.get("result") != "hit" or not f.get("today"):
            continue
        points.append({"tone": "pos", "text": f"{f.get('product')} — {f.get('change')}"[:70]})
        if len(points) >= 3:
            break

    # 待办次之
    for t in [x for x in todos if x.get("kind") == "draft"][:2]:
        points.append({"tone": "accent", "text": f"{t.get('text')} — {t.get('note')}"[:70]})

    # 失败要报 —— 静默失败比不通知更糟（同样只报今天的）
    n_warn = 0
    for f in feed:
        if f.get("result") != "fail" or not f.get("today"):
            continue
        points.append({"tone": "warn", "text": f"{f.get('product')} 执行失败：{f.get('change')}"[:70]})
        n_warn += 1
        if n_warn >= 2:
            break

    if not points:
        # 空态也给一句有用的话，而不是留白
        if watching:
            points.append({"tone": "muted", "text": f"正在盯 {watching} 个任务，今天暂时没有新动静"})
        else:
            points.append({"tone": "muted", "text": "还没有监控任务 —— 在对话里说「帮我盯一下 XX 的价格」即可"})

    return {
        "stats": {
            "hits": hits,
            "drafts": drafts,
            "watching": watching,
            # 前端标题要用：显示**本地**日期，不是 UTC 边界日
            "date": today_label,
            "generated": bool(feed or todos),
        },
        "points": points[:BRIEF_POINT_LIMIT],
    }


def build_messages(brief: dict, feed: list[dict], todos: list[dict]) -> list[dict]:
    """左栏卡片序列：简报卡 + 命中卡 + 待办卡。

    不落库 —— 每次由聚合数据实时合成，刷新即恢复历史（修 U1）。
    """
    messages: list[dict] = []

    stats = brief.get("stats") or {}
    messages.append({
        "id": "msg-brief",
        "kind": "brief",
        # 这个 time 是**卡片合成时刻**（用户打开页面的时间），不是简报
        # 生成时刻 —— 简报是按需实时算的，没有独立的生成时间点。
        "time": _clock(datetime.now(timezone.utc)),
        "date": stats.get("date") or "",
        # 有数据才叫「今天需要你知道的」；一条数据都没有时如实说明，
        # 不要用一句空话冒充简报。
        "title": "今天需要你知道的" if stats.get("generated") else "还没有可汇总的动态",
        "points": brief.get("points") or [],
    })

    for f in feed:
        if f.get("result") not in ("hit", "fail"):
            continue
        messages.append({
            "id": f"msg-{f['id']}",
            "kind": "hit",
            # 命中类型来自 feed（由任务类型映射），不再写死 price/stock
            "hitType": f.get("hitType") or "decide",
            "time": f.get("time") or "",
            "product": f.get("product") or "",
            "change": f.get("change") or "",
            "source": f.get("taskId") or "",
            "result": f.get("result"),
        })

    for t in todos:
        if t.get("kind") != "draft":
            continue
        messages.append({
            "id": f"msg-{t['id']}",
            "kind": "draft",
            "time": "",
            "product": (t.get("text") or "").strip("「」").replace("」草稿待确认", ""),
            "summary": t.get("note") or "",
        })

    return messages[:MESSAGE_LIMIT]


async def get_overview(user_id: str) -> dict:
    """对外入口：永不抛异常。"""
    feed = await build_feed(user_id)
    todos = await build_todos(user_id)
    watching = await build_watching(user_id)
    brief = await build_brief(user_id, feed, todos)
    messages = build_messages(brief, feed, todos)
    return {
        "messages": messages,
        "brief": brief,
        "feed": feed,
        "todos": todos,
        "watching": watching,
    }


# ══════════════════════════════════════════════════════════
# 行动层：对话 → 真的建任务（方案 §4 P3）
# ══════════════════════════════════════════════════════════
#
# 设计选择（方案 §5 决策 #3 的方案 A）：**轻量 JSON，不嵌 AgentChat**。
# 助理页的价值在「看」不在「聊」，所以：
#   · 监控类意图 → 直接调 create_monitor_task 工具，一句话确认
#   · 其他意图   → 交给 MasterAgent 非流式 ainvoke，回一段文本
#
# 为什么不用 intent_service 做意图识别：那个 BERT 模型的权重文件
# （models/joint_intent_bert/）在当前部署里**不存在**，get_intent_service()
# 直接 FileNotFoundError。方案 §4 P3 写的「意图识别」在当前环境下无法落地，
# 这里改用保守的关键词快路径 —— 命中就建任务，不命中就交给 Agent 判断，
# 不会因为分类器缺失而误建任务。

# 监控意图的关键词。宁可漏判（交给 Agent 兜底）也不要误判
# —— 用户说「帮我看看这个」不该被建成监控任务。
_MONITOR_HINTS = ("盯", "监控", "降价", "降到", "提醒我", "到货", "补货", "有货", "降价告诉", "蹲")

# 任务类型关键词 → task_type（顺序即优先级：越具体的越靠前）
_TYPE_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("stock", ("补货", "到货", "有货", "上架")),
    ("coupon", ("券", "优惠", "满减")),
    ("rank", ("排名", "榜单", "排行")),
    ("shop", ("店铺", "旗舰店", "官方店")),
)

# 「降到 1800」「¥2999」「3000 元」→ 1800。**必须带显式价格标记**：
# 裸匹配数字会把商品名里的型号数字当成目标价 —— 「索尼XM5」→5、
# 「iPhone 16」→16、「戴森 V12」→12，建出来的任务全是错的。
_PRICE_RES = (
    re.compile(r"(?:降[到至]|目标价|低于|少于|不超过|≤|<=)\s*[¥￥]?\s*(\d+(?:\.\d+)?)", re.I),
    re.compile(r"[¥￥]\s*(\d+(?:\.\d+)?)"),
    re.compile(r"(\d+(?:\.\d+)?)\s*(?:元|块钱|块)"),
)


def _detect_task_type(text: str) -> str:
    """从文本判监控类型，默认 price（盯价是最常见诉求）。"""
    for task_type, hints in _TYPE_HINTS:
        if any(h in text for h in hints):
            return task_type
    return "price"


def _extract_target_price(text: str) -> str:
    """抽目标价（元）。抽不到返回空串 —— 工具会建一个不带阈值的监控。"""
    for rx in _PRICE_RES:
        m = rx.search(text)
        if m:
            return m.group(1)
    return ""


def _clean_target(text: str) -> str:
    """把「帮我盯一下索尼 XM5 的价格，降到 1800 告诉我」削成监控对象。

    削不干净也没关系 —— 搜索执行器用的是模糊匹配，留点噪音比误删关键词好。
    但要把**类型词**（补货/排名/券）剥掉，否则「科沃斯T80S补货」会拿整串
    去搜商品，搜不到。
    """
    t = text.strip()
    # 「帮我把洗碗机加进监控」→ 洗碗机（方案 §4 P4 举的就是这个例子）
    m = re.search(r"把(.+?)(?:加进|加入|放进|加到|挂上|设置|设成)(?:监控|提醒|关注|列表)", t)
    if m:
        return m.group(1).strip(" ，,。；;的")
    # 去掉开头的祈使句
    for prefix in ("帮我", "请", "麻烦", "给我", "我想", "我要", "能不能", "可以"):
        if t.startswith(prefix):
            t = t[len(prefix):]
    # 长前缀优先，避免「盯着」被「盯」截断成「着...」
    for prefix in ("盯一下", "盯住", "盯着", "盯", "监控一下", "监控", "关注一下", "关注", "蹲一下", "蹲"):
        if t.startswith(prefix):
            t = t[len(prefix):]
            break
    # 去掉尾部的说明性从句
    for sep in ("，", ",", "。", "；", ";", "降到", "降", "目标价", "低于", "告诉我", "提醒我", "通知我"):
        idx = t.find(sep)
        if idx > 0:
            t = t[:idx]
    # 去掉类型词与价格尾巴（「戴森 V12 价格 3000 元」→「戴森 V12」）
    t = re.split(r"[\s]*价格|[\s]*库存|[\s]*的券|[\s]*排名|[\s]*榜单|[\s]*活动", t)[0]
    for kw in ("补货", "到货", "有货", "上架", "降价", "优惠", "满减", "排行"):
        t = t.replace(kw, "")
    for suffix in ("的价格", "价格", "的库存", "库存", "的券", "的排名", "的活动"):
        if t.endswith(suffix):
            t = t[: -len(suffix)]
            break
    return t.strip(" ，,。；;的")


async def _try_monitor(text: str, user_id: str) -> dict | None:
    """命中监控意图就建任务，返回确认文案；不命中返回 None。"""
    if not any(h in text for h in _MONITOR_HINTS):
        return None

    target = _clean_target(text)
    if not target:
        return None

    task_type = _detect_task_type(text)
    try:
        from src.agents.common.middleware.user_scope import bind_user_id, with_user_id
        from src.agents.common.toolkits.buildin.monitor_tools import create_monitor_task

        # 两件事都不能少：
        #   1) with_user_id —— 包装工具，调用时从 contextvar 补齐 user_id。
        #      注册表只在导入时打了 `_sc_needs_user_id` 标记，真正包装发生在
        #      各个调用点（graph.py / subagents.py），这里必须自己做。
        #   2) bind_user_id —— 把当前用户写进 contextvar，供上一步读取。
        # 只传 kwarg 没用：user_id 不在 args_schema 里，会被 pydantic 丢掉。
        tool = with_user_id(create_monitor_task)
        with bind_user_id(user_id):
            raw = await tool.ainvoke({
                "task_type": task_type,
                "target": target,
                "target_price": _extract_target_price(text) if task_type == "price" else "",
            })
    except Exception as e:
        logger.warning(f"[assistant] 建监控任务失败: {e}")
        return {"reply": f"创建监控任务时出错：{e}", "created": False}

    # 工具失败时返回自然语言（「创建监控任务失败: ...」/「错误: ...」），
    # 成功时返回 JSON。**必须如实区分** —— 把失败当成功回「已帮你挂上」
    # 就是方案 §0 第 3 点批评的那种撒谎。
    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped.startswith(("错误", "创建监控任务失败")) or "工具执行失败" in stripped:
            return {"reply": stripped, "created": False}
        try:
            payload = json.loads(stripped)
        except (ValueError, TypeError):
            return {"reply": stripped, "created": False}
    elif isinstance(raw, dict):
        payload = raw
    else:
        return {"reply": f"创建监控任务返回了意外结果：{raw!r}"[:200], "created": False}

    if not payload.get("task_id"):
        return {"reply": str(payload.get("message") or raw)[:200], "created": False}

    label = {"price": "盯价", "stock": "盯补货", "coupon": "盯券", "rank": "盯排名", "shop": "盯店铺"}[task_type]
    price_note = ""
    if task_type == "price" and payload.get("target_price"):
        price_note = f"，到 ¥{int(payload['target_price']) / 100:.0f} 或以下就提醒你"
    return {
        "reply": f"已帮你挂上{label}任务：**{target}**{price_note}。命中后会出现在这里。",
        "created": True,
    }


async def send_message(text: str, user_id: str) -> dict:
    """助理页对话入口：先试监控快路径，再交给 MasterAgent。永不抛异常。"""
    text = (text or "").strip()
    if not text:
        return {"reply": "请说点什么～", "created": False}

    hit = await _try_monitor(text, user_id)
    if hit is not None:
        return hit

    # 非监控意图 → MasterAgent 非流式。会话隔离用独立 thread_id，
    # 不污染用户在 /agent 页的对话历史。
    try:
        import uuid

        from langchain_core.messages import AIMessage, HumanMessage

        from src.agents import agent_manager

        agent = agent_manager.get_agent("MasterAgent")
        if agent is None:
            return {"reply": "助理暂时不可用（MasterAgent 未注册）。", "created": False}

        graph = await agent.get_graph()
        thread_id = f"assistant_{user_id}_{uuid.uuid4().hex[:8]}"
        context = agent.context_schema()
        context.update({"user_id": user_id, "thread_id": thread_id})

        final_state = await graph.ainvoke(
            input={"messages": [HumanMessage(content=text)]},
            context=context,
            config={"configurable": {"thread_id": thread_id, "user_id": user_id}, "recursion_limit": 60},
        )

        reply = ""
        for msg in reversed(final_state.get("messages", [])):
            if isinstance(msg, AIMessage) and msg.content:
                reply = msg.content if isinstance(msg.content, str) else str(msg.content)
                break
        return {"reply": reply or "（没有生成回复）", "created": False}
    except Exception as e:
        logger.warning(f"[assistant] MasterAgent 回复失败: {e}")
        return {"reply": f"处理失败：{e}", "created": False}
