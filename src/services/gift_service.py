"""送礼智能体（gift）—— 服务层。

与 `planning_service` 同一套骨架（建 run → 后台推进 → 事件流水 + 快照），
但阶段内容完全不同 —— 这是刻意的：两个 agent 是**并列**的独立实现，
共用的是服务模式而不是业务逻辑。

  采购 = 决策收敛：7 阶段（理解需求→…→生成交付），核心产物是决策图
  送礼 = 意义建构：7 步（理解关系→…→生成寄语），核心产物是人物档案

铁律同 planning：时间戳用列默认值（naive UTC）、用户口径 str(users.id)。
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import desc, func, select

from src.agents.independent.gift import stages as st
from src.storage.postgres.manager import pg_manager
from src.agents.independent.gift.graph import get_gift_graph
from src.storage.postgres.models_business import GiftEvent, GiftRun

logger = logging.getLogger(__name__)

# 左栏七步的顺序 —— 前端 ExploreStream 按这个顺序渲染
STEP_KEYS = [k for k, _ in st.STEPS]
STEP_LABEL = st.STEP_LABELS

MAX_EVENTS_PER_RUN = 3000


# ══════════════════════════════════════════════════════════
# 读
# ══════════════════════════════════════════════════════════

async def get_run(run_id: str, user_id: str) -> GiftRun | None:
    """取 run + 归属校验。查不到与不属于你都返回 None。"""
    async with pg_manager.get_async_session_context() as session:
        r = await session.execute(
            select(GiftRun).where(GiftRun.id == run_id, GiftRun.user_id == user_id)
        )
        return r.scalar_one_or_none()


async def list_runs(user_id: str, limit: int = 20) -> list[dict]:
    async with pg_manager.get_async_session_context() as session:
        r = await session.execute(
            select(GiftRun).where(GiftRun.user_id == user_id)
            .order_by(desc(GiftRun.created_at)).limit(limit)
        )
        return [row.to_dict() for row in r.scalars().all()]


async def list_events(run_id: str, after_seq: int = 0, limit: int = 1000) -> list[dict]:
    async with pg_manager.get_async_session_context() as session:
        r = await session.execute(
            select(GiftEvent)
            .where(GiftEvent.run_id == run_id, GiftEvent.seq > after_seq)
            .order_by(GiftEvent.seq).limit(limit)
        )
        return [row.to_dict() for row in r.scalars().all()]


# ══════════════════════════════════════════════════════════
# 写
# ══════════════════════════════════════════════════════════

async def emit(run_id: str, kind: str, payload: dict | None = None) -> None:
    """写一条事件。**永不抛异常** —— 事件写失败不该中断推演。"""
    try:
        async with pg_manager.get_async_session_context() as session:
            n = await session.execute(
                select(func.count()).select_from(GiftEvent).where(GiftEvent.run_id == run_id)
            )
            if int(n.scalar() or 0) >= MAX_EVENTS_PER_RUN:
                logger.warning(f"[gift] run {run_id} 事件数达上限，停止写入")
                return
            mx = await session.execute(
                select(func.coalesce(func.max(GiftEvent.seq), 0)).where(GiftEvent.run_id == run_id)
            )
            session.add(GiftEvent(
                run_id=run_id, seq=int(mx.scalar() or 0) + 1,
                kind=kind, payload=payload or {},
            ))
            await session.commit()
    except Exception as e:
        logger.warning(f"[gift] 写事件失败（忽略）: {e}")


async def _patch_run(run_id: str, **fields) -> None:
    try:
        async with pg_manager.get_async_session_context() as session:
            r = await session.execute(select(GiftRun).where(GiftRun.id == run_id))
            run = r.scalar_one_or_none()
            if run is None:
                return
            for k, v in fields.items():
                setattr(run, k, v)
            await session.commit()
    except Exception as e:
        logger.warning(f"[gift] 更新 run 失败（忽略）: {e}")


# ══════════════════════════════════════════════════════════
# 建
# ══════════════════════════════════════════════════════════

async def create_run(user_id: str, params: dict) -> dict:
    """建一次送礼推演。**立即返回**，推演在后台跑。

    与 planning 同理：工作台是「看着它长出来」的界面，
    同步跑完再返回就只剩一张已经画好的档案卡。
    """
    run_id = f"gr-{uuid.uuid4().hex[:12]}"
    try:
        budget = int(params.get("budget") or 0)
    except (TypeError, ValueError):
        budget = 0

    run = GiftRun(
        id=run_id,
        user_id=str(user_id),
        status="running",
        recipient=str(params.get("recipient") or ""),
        occasion=str(params.get("occasion") or ""),
        budget=budget,
        signals=list(params.get("signals") or []),
        profile=[],
        understanding={},
        profile_head={},
    )
    async with pg_manager.get_async_session_context() as session:
        session.add(run)
        await session.commit()

    asyncio.create_task(advance(run_id, user_id))

    fresh = await get_run(run_id, user_id)
    return fresh.to_dict() if fresh else {}


# ══════════════════════════════════════════════════════════
# 推进
# ══════════════════════════════════════════════════════════

async def _say(run_id: str, key: str, text: str) -> None:
    """发一段「实时描述」—— 前端按 more=true 累积成打字机效果。

    这里整段一次发（more=False）：片段化是**前端**的表现层需求，
    后端没必要为了视觉效果把一句话切碎再发很多条事件。
    """
    await emit(run_id, "live", {"key": key, "text": text, "more": False})


async def _step(run_id: str, key: str, status: str, **extra) -> None:
    await emit(run_id, "step", {"key": key, "status": status, **extra})


async def advance(run_id: str, user_id: str) -> None:
    """跑**图**推进这次推演。**永不抛异常**（失败落 run.error）。

    ═══════════════════════════════════════════════════════════════
    2026-09-25 修正：这里之前是一个 for 循环自己串流程
    ═══════════════════════════════════════════════════════════════
    那时 `graph.py` 里的 LangGraph **从未被执行过** —— 两份实现并存，
    读者会以为跑的是图。现在图是**唯一**推进路径。

    用什么方式订阅：`astream(stream_mode="updates")`。
    节点只管算状态，service 按「哪个节点产出了什么」翻译成事件 ——
    这样事件顺序天然跟着图的执行顺序，不需要往里塞回调
    （塞回调还要处理同步/异步转换，顺序反而不好保证）。
    """
    try:
        run = await get_run(run_id, user_id)
        if run is None:
            return

        state = {
            "recipient": run.recipient, "occasion": run.occasion,
            "budget": run.budget, "signals": run.signals or [],
            "run_id": run.id, "user_id": run.user_id,
        }

        graph = get_gift_graph()
        async for chunk in graph.astream(state, stream_mode="updates"):
            # chunk 形如 {"节点名": 该节点返回的 state 增量}
            for node, delta in (chunk or {}).items():
                await _on_node(run_id, node, delta or {})

        # 收尾：profile_head 是展示层字段，图不产出；这里补齐
        fresh = await get_run(run_id, user_id)
        if fresh is not None:
            head = st.build_profile_head(
                {"recipient": fresh.recipient, "occasion": fresh.occasion,
                 "budget": fresh.budget},
                fresh.profile or [],
            )
            await _patch_run(run_id, profile_head=head, status="converged")
        await emit(run_id, "done", {})

    except Exception as e:
        logger.error(f"[gift] run {run_id} 推演失败: {e}", exc_info=True)
        await _patch_run(run_id, status="failed", error=str(e)[:500])
        await emit(run_id, "done", {})


# 节点名 → 左栏那一步的 key / 中文名（与 STEPS 对齐）
_NODE_META = {
    "understand": ("understand", "理解关系"),
    "extract": ("extract", "提取需求"),
    "search": ("search", "检索商品"),
    "verify": ("verify", "比价验货"),
    "combine": ("combine", "组合礼盒"),
    "message": ("message", "生成寄语"),
}


async def _on_node(run_id: str, node: str, delta: dict) -> None:
    """一个节点跑完 → 落它对应的过程事件与产物事件。

    事件顺序跟着图走（astream 逐节点 yield），不用自己排。
    """
    if node not in _NODE_META:
        return
    key, label = _NODE_META[node]
    await emit(run_id, "stage", {"key": key})
    await _step(run_id, key, "running")

    try:
        if node == "understand":
            profile = delta.get("profile") or []
            ctx = delta.get("context") or {}
            await _patch_run(run_id, profile=profile)
            for g in profile:
                await emit(run_id, "profile", {
                    "key": g["key"], "state": g["state"],
                    "text": g["text"], "note": g.get("note"),
                })
            await _step(run_id, "understand", "done",
                        evidence=f"读了 {len(ctx.get('history') or [])} 条历史、"
                                 f"{len(ctx.get('prefs') or [])} 条偏好")
            await _say(run_id, "understand",
                       "从档案取到与本次送礼相关的字段，其余过滤掉。")

        elif node == "extract":
            u = delta.get("understanding") or {}
            await _patch_run(run_id, understanding=u)
            await emit(run_id, "understanding", u)
            await _step(run_id, "extract", "done",
                        evidence=u.get("from") or "",
                        why="由模型归纳自真实档案项" if u.get("by") == "llm"
                            else "规则兜底（模型不可用）")
            await _say(run_id, "extract", "把偏好归纳成一条判断，后面的取舍以它为准。")

        elif node == "search":
            picked = delta.get("picked") or []
            await emit(run_id, "deliverable", {"key": "compare", "state": "building"})
            await _step(run_id, "search", "done",
                        evidence=f"检索到 {len(picked)} 个真实候选")
            await _say(run_id, "search", "用品类词检索（不是「礼物」——那只会搜出礼盒包装）。")

        elif node == "verify":
            excluded = delta.get("excluded") or []
            picked = delta.get("picked") or []
            for e in excluded:
                await emit(run_id, "excluded", {"name": e["name"], "why": e["why"]})
            await emit(run_id, "deliverable",
                       {"key": "compare", "state": "ready",
                        "data": st.build_compare(picked, excluded)})
            await _step(run_id, "verify", "done",
                        evidence=f"{len(picked)} 件入选、{len(excluded)} 件排除")
            await _say(run_id, "verify", "排除的保留理由、不删除 —— 否则答不出「为什么只剩这几件」。")

        elif node == "combine":
            plan = delta.get("plan") or {}
            rows = delta.get("budget_rows") or []
            await emit(run_id, "deliverable", {"key": "plan", "state": "ready", "data": plan})
            await emit(run_id, "deliverable", {"key": "budget", "state": "ready", "data": rows})
            by_llm = plan.get("by") == "llm"
            await _step(run_id, "combine", "done",
                        evidence=f"{len(plan.get('items') or [])} 件，由模型挑选并给出理由"
                                 if by_llm else "按品类轮流取（模型不可用，已降级）")
            await _say(run_id, "combine",
                       "组合由模型决策（判据是「同时被用到」），预算与品类去重由代码校验。"
                       if by_llm else "模型不可用，已降级为规则选件。")

        elif node == "message":
            msg = delta.get("message") or {}
            supply = delta.get("supply") or []
            await emit(run_id, "deliverable", {"key": "message", "state": "ready", "data": msg})
            await emit(run_id, "deliverable", {"key": "supply", "state": "ready", "data": supply})
            await emit(run_id, "deliverable",
                       {"key": "order", "state": "needs", "data": {}})
            by_llm = msg.get("by") == "llm"
            await _step(run_id, "message", "done",
                        evidence="由模型生成，素材指回前面的判断" if by_llm
                                 else "模板兜底（模型不可用）")
            await _say(run_id, "message", "寄语里的每句都指回上面某一步的依据。")
    except Exception as e:
        logger.warning(f"[gift] 节点 {node} 事件落库失败（忽略）: {e}")


async def get_deliverable(run_id: str, user_id: str, key: str) -> dict | None:
    """取某个交付物的当前内容（从事件流里找最后一次 ready/building）。"""
    run = await get_run(run_id, user_id)
    if run is None:
        return None
    if key not in st.DELIVERABLE_KEYS:
        return None
    events = await list_events(run_id, after_seq=0)
    data = None
    for ev in events:
        if ev["kind"] == "deliverable" and (ev["payload"] or {}).get("key") == key:
            p = ev["payload"]
            if p.get("data") is not None:
                data = p["data"]
    return {
        "key": key,
        "label": st.DELIVERABLE_LABELS.get(key, key),
        "data": data,
        "generated_at": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M"),
    }
