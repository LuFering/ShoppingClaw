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
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import ToolMessage
from sqlalchemy import desc, func, select

from src.agents.independent.planning import stages as st
from src.agents.independent.common_llm import DeltaPump
from src.storage.postgres.manager import pg_manager
from src.agents.independent.planning.graph import get_planning_agent
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

# 每个阶段「正在做什么」。刻意不写「正在思考…」这种放之四海皆准的话：
# 写具体了，用户才知道它此刻是在等 MCP（慢）还是在等模型（慢），
# 而不是以为界面卡住了。
#
# 位置放在 STAGES 旁边（而不是用到的 _on_debug 旁）：建 run 时要用它给
# 全部阶段铺初始提示，两处引用同一份，别的地方改了这里不会漏。
RUNNING_HINT = {
    "intake": "把入口参数摊成可筛选的需求",
    "clarify": "查这个品类该看哪些维度",
    "search": "向淘宝检索真实商品",
    "filter": "按预算等硬约束筛选",
    "compare": "让模型逐条对比取舍",
    "risk": "查售后与风险政策",
    "deliver": "整理成待你拍板的问题",
}

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

    # 建 run 时就把**全部阶段**以「待办」下发。
    # ═══════════════════════════════════════════════════════════════════
    # 2026-09-25：为什么要先铺满
    # ═══════════════════════════════════════════════════════════════════
    # 原先阶段是一条条冒出来的，用户看不到还剩几步、也不知道总共要做什么。
    # 铺满之后是「7 步，正在第 3 步」—— 等待有了边界，焦虑感完全不同。
    # 每条的 state 由后续的 phase 事件就地改成 running / done。
    # 建 run 时**不铺阶段**了。
    # ═══════════════════════════════════════════════════════════════════
    # 2026-09-26：为什么撤掉「第 N / 7 步」
    # ═══════════════════════════════════════════════════════════════════
    # 旧实现按写死的七个阶段推进，所以能提前告诉用户「总共 7 步、现在第 3 步」。
    # 现在走法由模型定 —— 它可能搜三次、可能跳过风险排查、可能来回问两次。
    # 硬报「第 N / 7 步」就是编的：分母根本不存在。
    # 阶段名改成**归组标签**（见 _TOOL_META），界面按工具调用实时归类，
    # 不再有全局进度。宁可少一个进度条，也不给一个假的分母。

    # 后台推进：不阻塞本次请求。失败只记日志，run 会停在 failed 且带 error。
    asyncio.create_task(advance(run_id, user_id))

    fresh = await get_run(run_id, user_id)
    return fresh.to_dict() if fresh else {}


async def answer_question(run_id: str, user_id: str, key: str) -> dict | None:
    """用户回答待确认问题 → 收掉问题、把回答喂回 agent 续跑。

    ═══════════════════════════════════════════════════════════════════
    2026-09-26：续跑方式变了
    ═══════════════════════════════════════════════════════════════════
    旧实现要算「从提问阶段的**下一阶段**接上」—— 因为阶段是写死的链，
    从当前阶段重跑会让它再问一次（死循环）。

    现在没有阶段链了：agent 是一圈 ReAct 循环，用户的回答就是**新的输入**。
    把它接在历史消息后面重新跑一轮，模型自己会接着往下走。
    所以这里只需要把「历史 + 回答」存下来供 `advance` 拼输入。
    """
    run = await get_run(run_id, user_id)
    if run is None:
        return None
    q = run.question or {}
    label = next(
        (o.get("label") for o in (q.get("options") or []) if o.get("key") == key), key
    )
    await emit(run_id, "think", {
        "title": f"按你的选择「{label}」继续",
        "detail": "把这条回答交给 agent，它接着往下判断",
    })

    # 记下「回答了哪个选项」，advance 会把它转成一句话喂回模型。
    # 不存完整消息历史：run 表已经够宽了，而且历史可以从事件流重建。
    await _patch_run(run_id, question=None, answer_pick=key, status="running")

    asyncio.create_task(advance(run_id, user_id))

    fresh = await get_run(run_id, user_id)
    return fresh.to_dict() if fresh else None


# ══════════════════════════════════════════════════════════
# 推进
# ══════════════════════════════════════════════════════════


async def advance(run_id: str, user_id: str) -> None:
    """跑**一次 ReAct 循环**。**永不抛异常**（失败落 run.error）。

    ═══════════════════════════════════════════════════════════════════
    2026-09-26：从「按七个阶段推进」改成「订阅模型的一次次决策」
    ═══════════════════════════════════════════════════════════════════

    旧实现按 `STAGES` 顺序跑七个节点，service 知道每一步是什么、下一步去哪。
    现在流程由模型定，service **不知道**它接下来要干什么 —— 只能订阅
    agent 的产出，把「模型决定调哪个工具」翻译成事件。

    订阅 `stream_mode=["updates", "messages"]`：
      · `updates` —— 每个节点跑完的产出。模型节点的 `tool_calls` 就是
        「它决定了什么」，工具节点的 `ToolMessage` 就是「拿到了什么」。
      · `messages` —— **逐 token 的模型输出**，用来做实时推理流。
        这是 `create_agent` 自带的，不需要我们再往模型里塞回调。

    中断（ask_user）：工具写了 `question` 就落 awaiting 并停在这里。
    续跑时把用户的回答作为新消息喂回去，循环接着走。
    """
    try:
        run = await get_run(run_id, user_id)
        if run is None:
            return

        # 决策图：核心任务节点先立起来，后面每次搜索/排除往里加
        await _merge_graph(
            run_id,
            [_node("task", f"{run.scene}采购任务" if run.scene else "本次采购任务",
                    "核心任务", 5, "active", {"scene": run.scene})],
            [],
        )
        await _patch_run(run_id, status="running")

        agent = get_planning_agent()
        init = _agent_input(run)
        # 续跑：用户答过问，就把那条回答作为新消息接上 —— agent 是循环，
        # 多给一条输入它自己会接着判断，不需要我们算「从哪一步接」。
        if run.answer_pick:
            init["messages"] = init["messages"] + [
                {"role": "user", "content": _answer_text(run)}
            ]

        # 推理要过噪音过滤：agent 的推理通道会夹英文草稿与念任务要求的话，
        # 那些是「AI 味」的主要来源（详见 common_llm.filter_reasoning）。
        # 正文不过滤 —— 那是要读的内容，一个字都不能丢。
        pump = DeltaPump(
            lambda text, kind: _emit_think_delta(run_id, text, kind),
            filter_reasoning_text=True,
        )
        seen_tools: set[str] = set()
        # 跨步累积的产物（候选/排除/选中/风险/维度）。
        # `stream_mode="updates"` 只给增量，得自己攒；攒出来的要落库，
        # 否则收尾生成交付物时读不到（见 _persist_products 的说明）。
        acc: dict = {}

        try:
            async for mode, chunk in agent.astream(
                init, stream_mode=["updates", "messages"]
            ):
                if await get_run(run_id, user_id) is None:
                    return   # run 被删了

                if mode == "messages":
                    await _on_model_token(run_id, chunk, pump)
                    continue

                stop = await _on_agent_step(run_id, chunk, seen_tools, pump, acc)
                if stop:
                    await pump.close()
                    await _patch_run(run_id, status="awaiting", question=stop)
                    await emit(run_id, "question", stop)
                    return
        finally:
            await pump.close()

        # 收尾前把产物落库 —— `_finish` 生成交付物时要读它
        await _persist_products(run_id, acc)
        await _finish(run_id, user_id)

    except Exception as e:
        logger.error(f"[planning] run {run_id} 推进失败: {e}", exc_info=True)
        await _patch_run(run_id, status="failed", error=str(e)[:500])
        await emit(run_id, "done", {"status": "failed", "error": str(e)[:200]})


def _agent_input(run: PlanningRun) -> dict:
    """给 agent 的初始输入：任务描述 + 入口参数。"""
    from src.agents.independent.planning.graph import build_goal

    state = _state_of(run)
    return {
        "messages": [{"role": "user", "content": build_goal(state)}],
        **state,
    }


def _answer_text(run: PlanningRun) -> str:
    """用户对上一次提问的回答，转成一句话喂回模型。"""
    q = run.question or {}
    picked = run.answer_pick or ""
    label = next(
        (o.get("label") for o in (q.get("options") or []) if o.get("key") == picked),
        picked,
    )
    return f"关于「{q.get('text') or ''}」，我选：{label}。请据此继续。"


# ── 工具名 → 展示用的事件 ────────────────────────────────────
# 事件不再是「第几阶段」，而是「模型决定做什么」。这张表把工具名翻成人话，
# 并决定归到哪个阶段标签下（标签只用于分组，不再代表流程顺序）。
_TOOL_META: dict[str, tuple[str, str]] = {
    # 工具名: (阶段标签, 动作措辞)
    "check_category_standards": ("澄清约束", "查品类标准"),
    "search_products": ("搜索候选", "搜索商品"),
    "check_risks": ("风险排查", "查风险与售后"),
    "drop_candidates": ("筛选硬约束", "排除不符合的"),
    "make_decision": ("横向对比", "定下选哪件"),
    "ask_user": ("生成交付", "向你确认"),
}


async def _on_model_token(run_id: str, chunk: Any, pump: DeltaPump) -> None:
    """模型逐 token 输出 → 喂进节流泵。

    `stream_mode="messages"` 给的是 `(message_chunk, metadata)`。只取正文与
    推理两种文本，工具调用的参数片段（JSON）不播 —— 那是程序不是思考。
    """
    from src.agents.independent.common_llm import _chunk_parts

    msg = chunk[0] if isinstance(chunk, (list, tuple)) else chunk
    content, reason = _chunk_parts(msg)
    if reason:
        pump.feed(reason, "reasoning")
    elif content:
        # 只在没有工具调用时才播正文（有 tool_calls 时正文往往是空转的说明）
        if not (getattr(msg, "tool_call_chunks", None) or []):
            pump.feed(content, "content")


async def _on_agent_step(
    run_id: str, chunk: dict, seen_tools: set[str], pump: DeltaPump,
    acc: dict,
) -> dict | None:
    """agent 跑完一步（模型节点或工具节点）→ 落事件、累积产物。

    `acc` 是**跨步累积**的产物字典（candidates/excluded/selected/risks/…）。
    ⚠️ 必须自己累积：`stream_mode="updates"` 只给**本步的增量**，不是完整
    状态。这些产物要落库（`_persist_products`），否则收尾生成交付物时
    读不到 —— 交付物会全是空的（实测踩过）。

    返回非 None 表示要停下来问用户。
    """
    for _node, delta in (chunk or {}).items():
        d = delta or {}
        # 累积工具写进 state 的产物（列表追加、标量后写覆盖，与图的 reducer 一致）
        for k in ("dimensions", "candidates", "excluded", "risks"):
            if d.get(k):
                acc.setdefault(k, [])
                acc[k] = acc[k] + list(d[k])
        for k in ("selected", "dims_from_kb", "risks_from_kb"):
            if d.get(k) is not None:
                acc[k] = d[k]

        for m in (d.get("messages") or []):
            # ── 模型决定调工具 ──
            for call in (getattr(m, "tool_calls", None) or []):
                name = call.get("name") or ""
                args = call.get("args") or {}
                # 同一个工具可能被调多次（多轮搜索），用「名字+参数」去重，
                # 只用来避免重复的 phase 事件；调用本身每次都发。
                key = f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
                first = key not in seen_tools
                seen_tools.add(key)
                await _emit_tool_call(run_id, name, args, first)

            # ── 工具返回 ──
            if isinstance(m, ToolMessage):
                await _emit_tool_result(run_id, m)

        # ── 工具写了 question → 停下来等用户 ──
        if d.get("question"):
            await _persist_products(run_id, acc)
            return d["question"]

    return None


async def _emit_tool_call(run_id: str, name: str, args: dict, first: bool) -> None:
    """模型决定调某个工具 → 一条事件。**带真实入参**。"""
    stage, verb = _TOOL_META.get(name, ("执行", name))
    if first:
        await emit(run_id, "phase", {
            "phase": stage, "label": stage, "state": "running",
            "hint": verb,
        })

    title, detail, sample = _describe_call(name, args)
    await emit(run_id, "call", {
        "title": title,
        "detail": detail,
        "args": args,
        "sample": sample,
        "tool": name,
        "stage": stage,
    })


def _describe_call(name: str, args: dict) -> tuple[str, str, list]:
    """把工具调用翻成人话。标题写模型**要做什么**，不是工具名。"""
    if name == "search_products":
        return (f"搜索「{args.get('keyword') or ''}」", "在淘宝找真实商品", [])
    if name == "check_category_standards":
        return (f"查「{args.get('category') or ''}」的选购标准", "看这个品类该比什么", [])
    if name == "check_risks":
        return (f"查「{args.get('subject') or ''}」的风险", "看售后与已知问题", [])
    if name == "drop_candidates":
        names = args.get("names") or []
        return (f"排除 {len(names)} 件", str(args.get("reason") or ""), [])
    if name == "make_decision":
        return (f"定下「{args.get('picked') or ''}」", str(args.get("why") or ""), [])
    if name == "ask_user":
        return ("向你确认一件事", str(args.get("question") or ""), [])
    return (name, "", [])


async def _emit_tool_result(run_id: str, m: ToolMessage) -> None:
    """工具返回 → 补一条事件，带**真实返回**（商品名+价格）。

    ⚠️ 这里要按 tool_call_id 找到对应那条 call 事件并**补全它**，而不是
    再发一条 —— 否则界面上「调用」和「返回」会分成两行，看着像调了两次。
    """
    content = str(getattr(m, "content", "") or "")
    await emit(run_id, "call_result", {
        "tool_call_id": getattr(m, "tool_call_id", "") or "",
        "text": content[:600],
    })


async def _finish(run_id: str, user_id: str) -> None:
    """收尾：产出交付物 → 收敛。永不抛异常。

    ⚠️ 2026-09-25 之前这里只把状态从 running 翻成 ready，**什么内容都没生成**
    —— 交付物是「空的」，正文要等用户点预览时才现算，而且三份算出的是同一段
    文字。现在真正把内容算出来，随事件一起下发：前端拿到就能直接渲染，
    刷新后也能从事件流里恢复。

    算不出来（state 不全）也照发 ready，但 data 为 None —— 前端会显示
    「无可交付内容」而不是假装成功。
    """
    try:
        run = await get_run(run_id, user_id)
        if run is None:
            return

        state = _state_from_run(run)
        for did, name, meta in DELIVERABLE_SPEC:
            await emit(run_id, "deliverable",
                       {"id": did, "name": name, "meta": meta, "state": "running", "progress": 0.5})
            try:
                doc = st.build_deliverable(state, did)
            except Exception as e:
                logger.warning(f"[planning] 交付物 {did} 生成失败: {e}")
                doc = None
            await emit(run_id, "deliverable",
                       {"id": did, "name": name, "meta": meta,
                        "state": "ready" if doc else "empty", "data": doc})

        await _patch_run(run_id, status="converged")
        await emit(run_id, "done", {"status": "converged"})
    except Exception as e:
        logger.error(f"[planning] run {run_id} 收尾失败: {e}", exc_info=True)
        await _patch_run(run_id, status="failed", error=str(e)[:500])
        await emit(run_id, "done", {"status": "failed", "error": str(e)[:200]})


def _state_of(run: PlanningRun) -> dict:
    """run 的入口参数 → agent 的初始 state。"""
    return {
        "scene": run.scene or "",
        "budget": run.budget or "",
        "duration": run.duration or "",
        "constraints": run.constraints or [],
        "subject": run.subject or "",
        "run_id": run.id,
        "user_id": run.user_id,
    }


async def _persist_products(run_id: str, acc: dict) -> None:
    """把 agent 累积的产物落进 `run.products`。

    ═══════════════════════════════════════════════════════════════════
    2026-09-26：为什么需要它
    ═══════════════════════════════════════════════════════════════════
    旧实现从 `run.graph` 的节点反推候选与选中项 —— 因为那时流程固定，
    图里必然有「候选商品」节点。

    现在走法由模型定：它可能搜了 3 轮、排除了 4 件、选了 1 件，这些都在
    **agent state** 里，不在图上（图只记关键节点）。收尾生成交付物时
    agent 早跑完了、state 也没了 —— 所以必须边跑边落库。

    落的是 `run.products`（JSONB），收尾时 `_state_from_run` 优先读它。
    """
    try:
        await _patch_run(run_id, products=acc)
    except Exception as e:
        logger.warning(f"[planning] 落产物失败（忽略）: {e}")


async def _emit_think_delta(run_id: str, text: str, kind: str = "content") -> None:
    """把模型推理的一段增量发出去。

    ⚠️ 单独一种事件（而不是复用 `think`）：前端要把这些片段**追加到同一行**，
    而 `think` 是「新起一条」。两者语义不同，混用会让每次增量都变成新条目。

    带上 `phase` 让前端知道这段推理属于哪一步；带 `kind` 让前端区分
    「它在想」（reasoning）与「它的结论」（content）—— 两者观感不同，
    前者该弱化成过程，后者才是要读的内容。
    """
    await emit(run_id, "think_delta", {"phase": "compare", "text": text, "kind": kind})


def _state_from_run(run: PlanningRun) -> dict:
    """把 run 还原成 stages 需要的 state。

    ═══════════════════════════════════════════════════════════════════
    2026-09-26：主数据源从「图」改成「run.products」
    ═══════════════════════════════════════════════════════════════════

    旧实现从 `run.graph` 的节点反推候选与选中项 —— 那时流程固定，
    图里必然有「候选商品」「已排除」这些节点。

    现在走法由模型定，候选/排除/选中都在 **agent state** 里，图只记关键
    节点。agent 跑完 state 就没了，所以推演过程中边跑边落进 `run.products`
    （见 `_persist_products`），这里优先读它。

    图仍然有用：它是给**界面**看的决策图。两者分工不同 ——
    products 是「结论的数据」，graph 是「过程的可视化」。
    读不到 products 时（旧 run）回退到从图反推。
    """
    p = run.products or {}
    if p.get("candidates") or p.get("selected"):
        cands = _dedup(p.get("candidates") or [])
        excluded = p.get("excluded") or []
        out_names = {st.cand_name(e) for e in excluded}
        return {
            "scene": run.scene, "budget": run.budget, "duration": run.duration,
            "constraints": run.constraints or [], "subject": run.subject,
            "run_id": run.id, "user_id": run.user_id,
            # 已排除的从候选里剔掉 —— 排除工具只往 excluded 里追加，
            # 不回头改 candidates（改了会让候选翻倍，见 tools._to_stage_state）
            "candidates": [c for c in cands if st.cand_name(c) not in out_names],
            "excluded": excluded,
            "selected": p.get("selected") or {},
            "risks": p.get("risks") or [],
            "dimensions": p.get("dimensions") or [],
            "needs": [],
        }

    # ── 回退：从图反推（2026-09-26 之前建的 run）──
    nodes = (run.graph or {}).get("nodes") or []
    candidates, excluded = [], []
    for n in nodes:
        meta = n.get("meta") or {}
        if n.get("type") == "候选商品":
            candidates.append({
                "name": n.get("name"),
                "price_yuan": meta.get("price"),
                "item_id": meta.get("item_id"),
                "why": meta.get("why") or "",
                "by": meta.get("by") or "",
                "_selected": n.get("state") == "selected",
            })
        elif n.get("type") == "已排除":
            excluded.append({
                "name": n.get("name"),
                "price_yuan": meta.get("price"),
                "_reason": meta.get("reason") or "",
            })

    selected = next((c for c in candidates if c.pop("_selected", False)), None) or {}

    return {
        "scene": run.scene, "budget": run.budget, "duration": run.duration,
        "constraints": run.constraints or [], "subject": run.subject,
        "run_id": run.id, "user_id": run.user_id,
        "candidates": candidates, "excluded": excluded, "selected": selected,
        "risks": [n.get("name") for n in nodes if n.get("type") == "风险"],
        "dimensions": [n.get("name") for n in nodes if n.get("type") == "决策依据"],
        "needs": [n.get("name") for n in nodes if n.get("type") == "需求"],
    }


def _dedup(items: list[dict]) -> list[dict]:
    """按 item_id / 名字去重 —— 模型会多轮搜索，同一件可能出现多次。"""
    seen, out = set(), []
    for c in items:
        key = str(c.get("item_id") or st.cand_name(c))
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


async def get_deliverable(run_id: str, user_id: str, did: str) -> dict | None:
    """取一份交付物：结构化 data（前端渲染）+ markdown（下载）。

    ⚠️ 之前这里无论 `did` 是什么都返回**同一段「决策图节点」罗列**，
    只有标题不同 —— 点开「候选对比表」看到的其实是一张节点清单。
    现在按 did 分别生成，与收尾时下发的是同一套 builder，不会漂。
    """
    run = await get_run(run_id, user_id)
    if run is None:
        return None
    spec = next((s for s in DELIVERABLE_SPEC if s[0] == did), None)
    if spec is None:
        return None
    _, name, meta = spec

    state = _state_from_run(run)
    try:
        doc = st.build_deliverable(state, did)
    except Exception as e:
        logger.warning(f"[planning] 交付物 {did} 生成失败: {e}")
        doc = None

    return {
        "id": did,
        "name": name,
        "meta": meta,
        "data": doc,
        "content": st.deliverable_markdown(doc, name) if doc else "",
        "generated_at": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M"),
    }
