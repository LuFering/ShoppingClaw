"""采购规划 agent —— 服务层。

职责边界：
  · 只管**任务实例的生命周期**：建 run、订阅图的推进、写事件、维护决策图
    快照、收用户拍板。**不碰工具实现、不碰判断逻辑** —— 那些在
    `src/agents/independent/planning/stages.py`（纯函数）。
  · 阶段推进**由图驱动**（`graph.astream`），本模块只订阅它的逐节点产出。
    ⚠️ 2026-09-25 之前这里是一个自己串流程的 for 循环，而 `graph.py` 里的
    LangGraph **从未被执行过** —— 两份实现并存，改一处另一处不动。现在图是
    唯一推进路径：落事件、中断等用户这些 HTTP/DB 关注点通过 `_on_node` 挂在
    图的产出上，而不是另写一条流程。

与主动助理（assistant_service）的分工：
  · assistant 是**派生视图**，全部实时聚合、不落库
  · planning 是**任务实例**，状态必须落库 —— 图要能断点续跑、刷新要能恢复

两条铁律：
  1. 时间戳一律用列的默认值（`utc_now_naive`）；写 tz-aware 会直接
     asyncpg DataError（`task_router` 踩过）
  2. 用户口径统一 `str(users.id)`
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, func, select

from src.agents.independent.planning import stages as st
from src.storage.postgres.manager import pg_manager
from src.agents.independent.planning.graph import get_planning_graph
from src.storage.postgres.models_business import PlanningEvent, PlanningRun

logger = logging.getLogger(__name__)

# 阶段顺序 —— 流程骨架。改这里就等于改流程，不需要动图以外的代码。
STAGES: tuple[tuple[str, str], ...] = (
    ("intake", "理解需求"),
    ("clarify", "澄清约束"),
    ("search", "搜索候选"),
    ("filter", "筛选硬约束"),
    ("compare", "横向对比"),
    ("risk", "风险排查"),
    ("deliver", "生成交付"),
)
STAGE_LABEL = dict(STAGES)
STAGE_KEYS = [k for k, _ in STAGES]

# 交付物清单：收敛后逐个产出。state: waiting → running → ready
DELIVERABLE_SPEC = (
    ("d-plan", "采购方案.md", "含清单、顺序与依赖"),
    ("d-compare", "候选对比表", "按硬约束逐项横比"),
    ("d-budget", "预算分配表", "按类别拆分预算"),
)

MAX_EVENTS_PER_RUN = 2000   # 兜底：异常情况下不让单次 run 无限写事件


# ══════════════════════════════════════════════════════════
# 读
# ══════════════════════════════════════════════════════════

async def get_run(run_id: str, user_id: str) -> PlanningRun | None:
    """按 id 取 run，**带归属校验** —— 查不到与不属于你都返回 None。

    不区分「不存在」与「不是你的」：区分了就等于告诉调用方这个 id 存在。
    """
    async with pg_manager.get_async_session_context() as session:
        r = await session.execute(
            select(PlanningRun).where(
                PlanningRun.id == run_id, PlanningRun.user_id == user_id
            )
        )
        return r.scalar_one_or_none()


async def list_runs(user_id: str, limit: int = 20) -> list[dict]:
    """该用户的 run 列表（新的在前），供入口页显示「进行中 N 个」。"""
    async with pg_manager.get_async_session_context() as session:
        r = await session.execute(
            select(PlanningRun)
            .where(PlanningRun.user_id == user_id)
            .order_by(desc(PlanningRun.created_at))
            .limit(limit)
        )
        return [row.to_dict() for row in r.scalars().all()]


async def list_events(run_id: str, after_seq: int = 0, limit: int = 500) -> list[dict]:
    """按 seq 升序取事件 —— SSE 的续传读路径。"""
    async with pg_manager.get_async_session_context() as session:
        r = await session.execute(
            select(PlanningEvent)
            .where(PlanningEvent.run_id == run_id, PlanningEvent.seq > after_seq)
            .order_by(PlanningEvent.seq)
            .limit(limit)
        )
        return [row.to_dict() for row in r.scalars().all()]


# ══════════════════════════════════════════════════════════
# 写
# ══════════════════════════════════════════════════════════

async def emit(run_id: str, kind: str, payload: dict | None = None) -> None:
    """写一条事件。seq 在 run 内自增。

    **永不抛异常** —— 事件写失败不该中断图推进。
    并发安全：单进程内 asyncio 串行执行到 commit，且 run 的推进是单条
    后台任务链（answer 会等上一段结束），不会并发写同一 run。
    """
    try:
        async with pg_manager.get_async_session_context() as session:
            n = await session.execute(
                select(func.count()).select_from(PlanningEvent)
                .where(PlanningEvent.run_id == run_id)
            )
            if int(n.scalar() or 0) >= MAX_EVENTS_PER_RUN:
                logger.warning(f"[planning] run {run_id} 事件数达上限，停止写入")
                return
            mx = await session.execute(
                select(func.coalesce(func.max(PlanningEvent.seq), 0))
                .where(PlanningEvent.run_id == run_id)
            )
            session.add(PlanningEvent(
                run_id=run_id, seq=int(mx.scalar() or 0) + 1,
                kind=kind, payload=payload or {},
            ))
            await session.commit()
    except Exception as e:
        logger.warning(f"[planning] 写事件失败（忽略）: {e}")


async def _patch_run(run_id: str, **fields) -> None:
    """更新 run 的若干列。显式传 None 表示「置空」（如收掉 question）。"""
    try:
        async with pg_manager.get_async_session_context() as session:
            r = await session.execute(select(PlanningRun).where(PlanningRun.id == run_id))
            run = r.scalar_one_or_none()
            if run is None:
                return
            for k, v in fields.items():
                setattr(run, k, v)
            await session.commit()
    except Exception as e:
        logger.warning(f"[planning] 更新 run 失败（忽略）: {e}")


def _node(nid: str, name: str, ntype: str, importance: int, state: str,
          meta: dict | None = None) -> dict:
    return {"id": nid, "name": name, "type": ntype, "importance": importance,
            "state": state, "meta": meta or {}}


def _edge(src: str, dst: str, etype: str) -> dict:
    return {"source_id": src, "target_id": dst, "type": etype}


async def _merge_graph(run_id: str, new_nodes: list[dict], new_edges: list[dict]) -> None:
    """把增量并入 run.graph 快照，并发一条 graph 事件。

    合并后**下发整图**而不是增量：前端收到直接替换即可。
    「增量合并」的复杂度留在服务端一处，前端不做第二套。
    """
    async with pg_manager.get_async_session_context() as session:
        r = await session.execute(select(PlanningRun).where(PlanningRun.id == run_id))
        run = r.scalar_one_or_none()
        if run is None:
            return
        g = dict(run.graph or {})
        nodes = {n["id"]: n for n in (g.get("nodes") or [])}
        for n in new_nodes:
            nodes[n["id"]] = {**nodes.get(n["id"], {}), **n}
        edges = {(e.get("source_id"), e.get("target_id"), e.get("type")): e
                 for e in (g.get("edges") or [])}
        for e in new_edges:
            edges[(e.get("source_id"), e.get("target_id"), e.get("type"))] = e

        graph = {"nodes": list(nodes.values()), "edges": list(edges.values())}
        run.graph = graph
        meta = dict(run.meta or {})
        meta["totalExpected"] = len(graph["nodes"])
        meta["subject"] = run.subject or meta.get("subject") or ""
        meta["scene"] = run.scene or meta.get("scene") or ""
        run.meta = meta
        await session.commit()

    await emit(run_id, "graph", graph)


async def _current_nodes(run_id: str) -> list[dict]:
    """读 run 当前的图节点（供后续阶段使用）。"""
    try:
        async with pg_manager.get_async_session_context() as session:
            r = await session.execute(select(PlanningRun).where(PlanningRun.id == run_id))
            row = r.scalar_one_or_none()
            return ((row.graph or {}).get("nodes") or []) if row else []
    except Exception as e:
        logger.warning(f"[planning] 重读图节点失败: {e}")
        return []


# ══════════════════════════════════════════════════════════
# 建 / 答
# ══════════════════════════════════════════════════════════

async def create_run(user_id: str, params: dict) -> dict:
    """建一次规划任务。**立即返回**，不等图跑完。

    工作台是「看着它长出来」的界面 —— 若这里同步跑完再返回，前端只会
    看到一张已经画好的图，过程全丢。所以：建 run → 起后台任务推进 →
    立刻返回 run_id + 空图，前端接 SSE 看增量。
    """
    run_id = f"pr-{uuid.uuid4().hex[:12]}"
    run = PlanningRun(
        id=run_id,
        user_id=str(user_id),
        status="running",
        scene=str(params.get("scene") or ""),
        budget=str(params.get("budget") or ""),
        duration=str(params.get("duration") or ""),
        constraints=list(params.get("constraints") or []),
        subject=str(params.get("subject") or ""),
        graph={"nodes": [], "edges": []},
        meta={
            "scene": str(params.get("scene") or ""),
            "subject": str(params.get("subject") or ""),
            "totalExpected": 0,
        },
    )
    async with pg_manager.get_async_session_context() as session:
        session.add(run)
        await session.commit()

    # 后台推进：不阻塞本次请求。失败只记日志，run 会停在 failed 且带 error。
    asyncio.create_task(advance(run_id, user_id))

    fresh = await get_run(run_id, user_id)
    return fresh.to_dict() if fresh else {}


async def answer_question(run_id: str, user_id: str, key: str) -> dict | None:
    """用户回答待确认问题 → 收掉问题、记事件、从**下一阶段**续跑。"""
    run = await get_run(run_id, user_id)
    if run is None:
        return None
    q = run.question or {}
    label = next(
        (o.get("label") for o in (q.get("options") or []) if o.get("key") == key), key
    )
    await emit(run_id, "think", {
        "title": f"按你的选择「{label}」调整约束",
        "detail": "已更新决策图的「预算约束」节点",
    })
    await _patch_run(run_id, question=None, status="running")

    # 从**提问阶段的下一阶段**续跑，而不是从提问阶段本身 ——
    # 后者会让该阶段再问一次，陷入死循环（每个阶段都是「跑完才问」）。
    asked = q.get("phase")
    i = STAGE_KEYS.index(asked) if asked in STAGE_KEYS else len(STAGE_KEYS) - 1
    nxt = STAGE_KEYS[i + 1] if i + 1 < len(STAGE_KEYS) else None

    if nxt:
        asyncio.create_task(advance(run_id, user_id, start_at=nxt))
    else:
        asyncio.create_task(_finish(run_id, user_id))

    fresh = await get_run(run_id, user_id)
    return fresh.to_dict() if fresh else None


# ══════════════════════════════════════════════════════════
# 推进
# ══════════════════════════════════════════════════════════

async def advance(run_id: str, user_id: str, start_at: str = "intake") -> None:
    """推进这次 run。**永不抛异常**（失败落 run.error）。

    start_at 是**起始阶段本身**（包含），语义与 answer_question 的续跑一致。

    推进靠 `graph.astream()`：图的每个节点产出经 `_on_node` 转成事件与图变更，
    返回 question 就落 awaiting 并跳出 —— 这就是「等用户拍板」的中断点。
    流程本身只有图那一份定义，这里不再自己排阶段顺序。
    """
    try:
        run = await get_run(run_id, user_id)
        if run is None:
            return

        await _merge_graph(
            run_id,
            [_node("task", f"{run.scene}采购任务" if run.scene else "本次采购任务",
                    "核心任务", 5, "active", {"scene": run.scene})],
            [],
        )

        start_idx = STAGE_KEYS.index(start_at) if start_at in STAGE_KEYS else 0
        state = _state_of(run)

        # ═══ 跑图，而不是自己串流程 ═══
        # 2026-09-25 修正：这里原先是一个 for 循环调 `_run_stage`，
        # 而 `graph.py` 里的 LangGraph **从未被执行过** —— 两份实现并存。
        # 现在图是唯一推进路径，service 只订阅它的逐节点产出。
        #
        # 同时订阅 debug：只有它能给出「节点开始执行」的时点（见 _on_debug）。
        graph = get_planning_graph()
        await _patch_run(run_id, status="running")

        started: dict[str, float] = {}   # 节点名 → 开始时刻，用来算真实耗时

        async for mode, chunk in graph.astream(state, stream_mode=["updates", "debug"]):
            if await get_run(run_id, user_id) is None:
                return   # run 被删了

            if mode == "debug":
                await _on_debug(run_id, chunk, start_idx, started)
                continue

            for node, delta in (chunk or {}).items():
                # ⚠️ 必须自己累积。`stream_mode="updates"` 只给**本节点的增量**，
                # 不是累积状态 —— 早先直接把初始 `state` 传下去，于是
                # deliver 阶段看到的 selected/excluded 永远是空的
                # （问题文案据此编造，见 stages.deliver_question 的说明）。
                for k, v in (delta or {}).items():
                    if v is not None:
                        state[k] = v
                # 续跑时跳过 start_at 之前的节点（answer 之后从下一阶段接上）
                if node in STAGE_KEYS and STAGE_KEYS.index(node) < start_idx:
                    continue
                stop = await _on_node(run_id, node, delta or {}, state,
                                      started.pop(node, None))
                if stop:
                    await _patch_run(run_id, status="awaiting", question=stop)
                    await emit(run_id, "question", stop)
                    return

        await _finish(run_id, user_id)

    except Exception as e:
        logger.error(f"[planning] run {run_id} 推进失败: {e}", exc_info=True)
        await _patch_run(run_id, status="failed", error=str(e)[:500])
        await emit(run_id, "done", {"status": "failed", "error": str(e)[:200]})


# 每个阶段「正在做什么」。
# 刻意不写「正在思考…」这种放之四海皆准的话：写具体了，用户才知道它此刻
# 是在等 MCP（慢）还是在等模型（慢），而不是以为界面卡住了。
RUNNING_HINT = {
    "intake": "把入口参数摊成可筛选的需求",
    "clarify": "查这个品类该看哪些维度",
    "search": "向淘宝检索真实商品",
    "filter": "按预算等硬约束筛选",
    "compare": "让模型逐条对比取舍",
    "risk": "查售后与风险政策",
    "deliver": "整理成待你拍板的问题",
}


async def _on_debug(run_id: str, chunk: dict, start_idx: int,
                    started: dict[str, float]) -> None:
    """把图的 debug 事件翻译成「正在做什么」。

    ═══════════════════════════════════════════════════════════════════
    为什么非要用 debug 模式 —— 只用 updates 时「运行中」是不存在的状态
    ═══════════════════════════════════════════════════════════════════

    `updates` 只在节点**跑完之后**才 yield。所以节点开始时没有任何信号，
    等收到信号时活儿已经干完了 —— 界面上「进行中」那一行根本没有出现的
    机会（gift 那边就是这么写的：running 与 done 在同一瞬间发出）。

    实测最慢的两步是 MCP 检索（~9s）与模型取舍（~8s），这十几秒里界面
    一动不动，看起来像卡死。debug 模式的 `task` 事件在节点**开始执行前**
    发出，这是唯一能拿到「现在在干什么」的时点。

    耗时不用 `task_result`（它在 updates 之后才到）：直接用 updates 到达
    时刻减去 task 时刻。两者都在节点尾部，差值就是真实执行时长。
    """
    if (chunk or {}).get("type") != "task":
        return
    node = (chunk.get("payload") or {}).get("name") or ""
    if node not in STAGE_LABEL:
        return
    if node in STAGE_KEYS and STAGE_KEYS.index(node) < start_idx:
        return   # 续跑时跳过的阶段，不发「正在做」
    started[node] = time.monotonic()
    await emit(run_id, "phase", {
        "phase": node, "label": STAGE_LABEL[node],
        "state": "running", "hint": RUNNING_HINT.get(node, ""),
    })


def _state_of(run: PlanningRun) -> dict:
    return {
        "scene": run.scene, "budget": run.budget, "duration": run.duration,
        "constraints": run.constraints or [], "subject": run.subject,
        "run_id": run.id, "user_id": run.user_id,
    }


# 图节点名 → 阶段 key（与 STAGES 对齐）
async def _on_node(run_id: str, node: str, delta: dict, state: dict,
                   t_start: float | None = None) -> dict | None:
    """一个图节点跑完 → 落它的事件与图变更。

    返回非 None 表示「要停下来问用户」（值是 question 对象）。

    事件顺序跟着 `astream` 的逐节点产出走，不用自己排 ——
    这是把流程交给图的直接好处。

    t_start 是该节点开始执行的 `time.monotonic()`（由 `_on_debug` 记下）。
    有它就发一条带真实耗时的 phase；没有（比如续跑跳过了 debug）就不发，
    宁可没有时长也不编一个。
    """
    if node not in STAGE_LABEL:
        return None
    done_evt = {"phase": node, "label": STAGE_LABEL[node], "state": "done"}
    if t_start is not None:
        done_evt["ms"] = int((time.monotonic() - t_start) * 1000)
    await emit(run_id, "phase", done_evt)

    if node == "intake":
        needs = delta.get("needs") or []
        await emit(run_id, "think", {
            "title": f"解析需求：{state.get('scene') or '未指定场景'}"
                     + (f" · {state['budget']}" if state.get("budget") else ""),
            "detail": f"{len(needs)} 条约束待落到可筛选字段",
        })
        await _merge_graph(
            run_id,
            [_node(n["id"], n["name"], "需求", n["importance"], "candidate") for n in needs],
            [_edge("task", n["id"], "需要") for n in needs],
        )

    elif node == "clarify":
        dims = delta.get("dimensions") or []
        from_kb = delta.get("dims_from_kb")
        # 措辞必须跟着来源变：知识库真命中才说「命中 N 条」，
        # 否则如实说用的是通用维度 —— 不然「命中」二字会被读成
        # 「知识库里收录了这个品类」，而实际可能一条都没有。
        #
        # by 用 "kb" 而不是 "llm"：知识库命中是**检索**结果，不是模型判断。
        # 三种来源要能分辨：kb 知识库 / llm 模型 / rule 规则兜底。
        await emit(run_id, "retrieve", {
            "title": f"品类知识 · {state.get('subject') or state.get('scene') or '商品'}",
            "detail": (f"命中 {len(dims)} 条评估维度" if from_kb
                       else f"知识库未收录该品类，改用通用维度：{'、'.join(dims)}"),
            "by": "kb" if from_kb else "rule",
        })
        await _merge_graph(
            run_id,
            [_node(f"ev-{i}", d, "决策依据", 3, "candidate") for i, d in enumerate(dims)],
            [_edge("task", f"ev-{i}", "依据") for i in range(len(dims))],
        )

    elif node == "search":
        cands = delta.get("candidates") or []
        base = state.get("subject") or state.get("scene") or "好物"
        await emit(run_id, "call", {
            "title": f"搜索商品 ·「{base}」",
            "detail": f"返回 {len(cands)} 个真实 SKU" if cands else "无结果 —— 不中断流程",
        })
        if cands:
            await _merge_graph(
                run_id,
                [_node("obj-1", base, "采购对象", 5, "candidate")],
                [_edge("task", "obj-1", "拆解为")],
            )
            nodes = [_node(
                f"cand-{i}", str(c.get("title") or "未命名")[:40], "候选商品", 3, "candidate",
                {"price": st.yuan(c.get("price")), "item_id": c.get("item_id")},
            ) for i, c in enumerate(cands)]
            await _merge_graph(run_id, nodes, [_edge("obj-1", n["id"], "候选") for n in nodes])

    elif node == "filter":
        kept = delta.get("candidates") or []
        dropped = delta.get("excluded") or []
        await emit(run_id, "think", {
            "title": f"按硬约束筛选：保留 {len(kept)} 个"
                     + (f"，排除 {len(dropped)} 个" if dropped else ""),
            "detail": ("；".join(str(d.get("_reason") or "") for d in dropped[:2])
                       or "没有候选违反预算等硬约束"),
        })
        if dropped:
            nodes = [_node(
                f"drop-{i}", st.cand_name(d)[:40], "已排除", 2, "dropped",
                {"reason": d.get("_reason") or "", "price": st.yuan(d.get("price"))},
            ) for i, d in enumerate(dropped[:6])]
            await _merge_graph(run_id, nodes, [])

    elif node == "compare":
        best = delta.get("selected") or {}
        # 候选数从图上取（compare 节点只返回 selected，不带候选列表）
        cands = [n for n in await _current_nodes(run_id) if n.get("type") == "候选商品"]
        if best.get("name"):
            await emit(run_id, "think", {
                "title": f"对比 {len(cands) or '若干'} 款，选定「{str(best['name'])[:20]}」",
                "detail": str(best.get("why") or "")[:80],
                "by": best.get("by") or "rule",
            })
            nodes = await _current_nodes(run_id)
            target = next((n for n in nodes if n.get("name") == best.get("name")), None)
            if target:
                await _merge_graph(run_id, [{**target, "state": "selected"}], [])

    elif node == "risk":
        risks = delta.get("risks") or []
        from_kb = delta.get("risks_from_kb")
        await emit(run_id, "retrieve", {
            "title": "风险与售后政策",
            "detail": (f"命中 {len(risks)} 条待确认项" if from_kb
                       else "知识库未收录该品类，按通用项提示"),
            "by": "kb" if from_kb else "rule",
        })
        await _merge_graph(
            run_id,
            [_node(f"risk-{i}", t, "风险", 3, "candidate") for i, t in enumerate(risks)],
            [_edge("task", f"risk-{i}", "存在") for i in range(len(risks))],
        )

    elif node == "deliver":
        return delta.get("question")

    return None


async def _finish(run_id: str, user_id: str) -> None:
    """收尾：产出交付物 → 收敛。永不抛异常。"""
    try:
        if await get_run(run_id, user_id) is None:
            return
        for did, name, meta in DELIVERABLE_SPEC:
            await emit(run_id, "deliverable",
                       {"id": did, "name": name, "meta": meta, "state": "running", "progress": 0.5})
            await emit(run_id, "deliverable",
                       {"id": did, "name": name, "meta": meta, "state": "ready"})
        await _patch_run(run_id, status="converged")
        await emit(run_id, "done", {"status": "converged"})
    except Exception as e:
        logger.error(f"[planning] run {run_id} 收尾失败: {e}", exc_info=True)
        await _patch_run(run_id, status="failed", error=str(e)[:500])
        await emit(run_id, "done", {"status": "failed", "error": str(e)[:200]})


async def get_deliverable(run_id: str, user_id: str, did: str) -> dict | None:
    """生成交付物正文（Markdown）。查不到 run 或 id 非法返回 None。"""
    run = await get_run(run_id, user_id)
    if run is None:
        return None
    spec = next((s for s in DELIVERABLE_SPEC if s[0] == did), None)
    if spec is None:
        return None
    _, name, _ = spec
    nodes = (run.graph or {}).get("nodes") or []
    lines = [
        f"# {name}",
        "",
        f"- 场景：{run.scene or '—'}",
        f"- 预算：{run.budget or '—'}",
        f"- 周期：{run.duration or '—'}",
        f"- 生成时间：{datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 决策图节点",
        "",
    ]
    for n in nodes:
        meta = n.get("meta") or {}
        line = f"- [{n.get('type')}] {n.get('name')}（{n.get('state')}）"
        if meta.get("price"):
            line += f" · ¥{meta['price']}"
        if meta.get("pruneReason"):
            line += f" · 排除原因：{meta['pruneReason']}"
        lines.append(line)
    return {"name": name, "content": "\n".join(lines) + "\n"}
