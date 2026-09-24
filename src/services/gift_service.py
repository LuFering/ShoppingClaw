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
    """按 STEPS 顺序推演。**永不抛异常**（失败落 run.error）。"""
    try:
        run = await get_run(run_id, user_id)
        if run is None:
            return
        state = {
            "recipient": run.recipient, "occasion": run.occasion,
            "budget": run.budget, "signals": run.signals or [],
            "run_id": run.id, "user_id": run.user_id,
        }

        # ① 理解关系 —— 真读档案，中栏在这里被写活
        await emit(run_id, "stage", {"key": "understand"})
        await _step(run_id, "understand", "running")
        ctx = await st.read_recipient_context(state)
        profile = st.build_profile(state, ctx)
        head = st.build_profile_head(state, profile)
        await _patch_run(run_id, profile=profile, profile_head=head)
        for g in profile:
            await emit(run_id, "profile", {
                "key": g["key"], "state": g["state"],
                "text": g["text"], "note": g.get("note"),
            })
        await _say(run_id, "understand",
                   f"从档案里读到你与{run.recipient or '对方'}的关系与历史记录；"
                   f"{'命中 ' + str(len(ctx.get('history') or [])) + ' 条历史' if ctx.get('history') else '暂无历史记录，已如实标注'}。")
        await _step(run_id, "understand", "done",
                    evidence=f"读了 {len(ctx.get('history') or [])} 条历史决策、"
                             f"{len(ctx.get('prefs') or [])} 条偏好记录",
                    why="只取与本次送礼相关的字段，其余过滤掉")

        # ② 提取需求 —— 写下最终版「当前理解」
        await emit(run_id, "stage", {"key": "extract"})
        await _step(run_id, "extract", "running")
        understanding = st.build_understanding(state, profile)
        await _patch_run(run_id, understanding=understanding)
        await emit(run_id, "understanding", understanding)
        await _say(run_id, "extract", "把偏好翻译成一条可执行的挑选标准，后面的检索与排除都以它为准。")
        await _step(run_id, "extract", "done",
                    evidence=understanding["from"],
                    why="硬指标来自已确认项，不是通用祝福")

        # ③ 检索商品 —— 真调 MCP
        await emit(run_id, "stage", {"key": "search"})
        await _step(run_id, "search", "running")
        await emit(run_id, "deliverable", {"key": "compare", "state": "building"})
        kws = st.build_search_keywords(state)
        cands = await st.search_candidates(state)
        await _say(run_id, "search", f"用「{'、'.join(kws)}」这组品类词检索，命中 {len(cands)} 件。")
        await _step(run_id, "search", "done",
                    evidence=f"{len(kws)} 组品类词，命中 {len(cands)} 件",
                    why="关键词是品类词而不是「礼物」—— 后者只会搜出礼盒包装")

        # ④ 比价验货 + ⑤ 排除候选
        picked, excluded = st.verify_candidates(cands, state)
        compare = st.build_compare(picked, excluded)
        await _step(run_id, "verify", "running")
        await _say(run_id, "verify", f"按预算与商品类型核验，{len(picked)} 件入选、{len(excluded)} 件排除。")
        await _step(run_id, "verify", "done",
                    evidence=f"入选 {len(picked)} 件，排除 {len(excluded)} 件",
                    why="单价超预算 60% 的排除 —— 送礼要留组合空间")
        await emit(run_id, "deliverable", {"key": "compare", "state": "ready", "data": compare})

        await emit(run_id, "stage", {"key": "exclude"})
        await _step(run_id, "exclude", "running")
        for e in excluded:
            await emit(run_id, "excluded", {"name": e["name"], "why": e["why"]})
        await _say(run_id, "exclude", "被排除的保留理由、不删除 —— 否则无法回答「为什么最后只剩这几件」。")
        await _step(run_id, "exclude", "done",
                    evidence=f"排除 {len(excluded)} 件，理由已留档",
                    why="不删除、不隐藏")

        if not picked:
            # 没候选也要走完流程并如实说明，不能卡在中间
            await _say(run_id, "combine", "候选池是空的，这次凑不出方案 —— 不是失败，是数据没到位。")
            await _step(run_id, "combine", "skipped", evidence="无可用候选")
            await _step(run_id, "message", "skipped", evidence="无方案可写寄语")
            await _patch_run(run_id, status="converged")
            await emit(run_id, "done", {})
            return

        # ⑥ 组合礼盒
        await emit(run_id, "stage", {"key": "combine"})
        await _step(run_id, "combine", "running")
        await emit(run_id, "deliverable", {"key": "plan", "state": "building"})
        plan, budget_rows, order = st.combine(picked, state)
        await emit(run_id, "deliverable", {"key": "plan", "state": "ready", "data": plan})
        await emit(run_id, "deliverable", {"key": "budget", "state": "ready", "data": budget_rows})
        await _say(run_id, "combine", f"挑 {len(plan.get('items') or [])} 件凑成一个整体 —— 判据是「同时被用到」，不是各自最优。")
        await _step(run_id, "combine", "done",
                    evidence=f"合计 ¥{order.get('total')} / 预算 ¥{order.get('budget')}",
                    why="单件最优不等于组合最优")

        # ⑦ 生成寄语
        await emit(run_id, "stage", {"key": "message"})
        await _step(run_id, "message", "running")
        await emit(run_id, "deliverable", {"key": "message", "state": "building"})
        message = st.build_message(state, plan, understanding)
        supply = st.build_supply(picked, plan)
        await emit(run_id, "deliverable", {"key": "message", "state": "ready", "data": message})
        await emit(run_id, "deliverable", {"key": "supply", "state": "ready", "data": supply})
        await emit(run_id, "deliverable", {"key": "order", "state": "needs", "data": order})
        await _say(run_id, "message", "寄语的素材是前面每一步的判断，不是通用祝福。")
        await _step(run_id, "message", "done",
                    evidence="素材＝前面每一步的判断",
                    why="每一句都能指回上面某一步的依据")

        await _patch_run(run_id, status="converged")
        await emit(run_id, "done", {})

    except Exception as e:
        logger.error(f"[gift] run {run_id} 推演失败: {e}", exc_info=True)
        await _patch_run(run_id, status="failed", error=str(e)[:500])
        await emit(run_id, "done", {})


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
