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
from src.utils.datetime_utils import utc_now_naive

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
# ══════════════════════════════════════════════════════════════════════
# 产出物清单（artifacts）
# ══════════════════════════════════════════════════════════════════════
# 2026-09-27 重构：从「三份写得差不多的 Markdown」改成**按用途分的产出物**，
# 每份声明自己支持的格式。
#
# ⚠️ 元组第 4 位是**支持的格式**，不是装饰：
#   · 前端据此决定显示哪几个下载按钮 —— 而不是点了才发现 404
#   · 导出端点据此校验 —— 不支持的格式直接 404，不去猜怎么转
#
# 分工（这是重构的要点，不是「多加了几份」）：
#   report  读的：为什么这么买。有 PDF（可打印/转发）
#   list    用的：照着下单。有 CSV（进 Excel 做预算表）
#   compare 对的：横比表。明细附件
#   budget  算的：预算拆账。明细附件
ARTIFACT_SPEC = (
    {"id": "d-report", "name": "采购规划报告", "meta": "完整方案：结论、依据、预算与风险",
     "kind": "report", "formats": ("pdf", "md"), "primary": True,
     "desc": "读这一份就够：先讲清约束与结论，再逐项给推荐与理由，最后是风险。"},
    {"id": "d-list", "name": "采购清单", "meta": "照着下单：商品、数量、价格、item_id",
     "kind": "list", "formats": ("csv", "md"), "primary": False,
     "desc": "下单时用的那一份。含 item_id，可直接去淘宝搜同款；可导 CSV 做预算表。"},
    {"id": "d-compare", "name": "候选对比表", "meta": "按品类分组，入选与排除同表",
     "kind": "compare", "formats": ("md",), "primary": False,
     "desc": "每条候选为什么入选或排除，按品类分组逐项横比。"},
    {"id": "d-budget", "name": "预算分配表", "meta": "按品类拆分预算",
     "kind": "budget", "formats": ("md",), "primary": False,
     "desc": "钱花在哪一类上、占比与结余。"},
)

# 兼容旧名（事件与前端都还在按 id 取）
DELIVERABLE_SPEC = tuple(
    (a["id"], a["name"], a["meta"]) for a in ARTIFACT_SPEC
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
    """该用户的 run 列表（新的在前）。

    两个用途共用：入口页的「进行中 N 个」统计，以及**采购历史**那一栏。
    历史那一栏要显示每条的交付状态与规模，所以这里顺带把 run 的产物摘要
    一起算好 —— 前端不必为每一条再发一次请求（列表 20 条就是 20 个请求）。
    """
    async with pg_manager.get_async_session_context() as session:
        r = await session.execute(
            select(PlanningRun)
            .where(PlanningRun.user_id == user_id)
            .order_by(desc(PlanningRun.created_at))
            .limit(limit)
        )
        return [_with_summary(row) for row in r.scalars().all()]


def _with_summary(run: PlanningRun) -> dict:
    """补上历史列表要用的摘要：几个品类、多少钱。

    ⚠️ 从 `products.plan` 里读**已经算好的**值，不在这里重算 ——
    交付物那边是同一套 builder，两处各算一遍必然漂（这个项目里踩过多次）。
    方案还没定下来时如实留空，不编。
    """
    d = run.to_dict()
    plan = (run.products or {}).get("plan") or {}
    items = [i for i in (plan.get("items") or []) if isinstance(i, dict)]
    d["summary"] = {
        "categories": len(items),
        "total": plan.get("total"),
        # 报告里的总额以 total_estimate 为准时，plan.total 可能为空 —— 退回逐件求和
        "picked": len(items),
    }
    if d["summary"]["total"] is None and items:
        subs = [i.get("subtotal") for i in items]
        if subs and all(s is not None for s in subs):
            d["summary"]["total"] = round(sum(float(s) for s in subs), 2)
    return d


async def mark_delivered(run_id: str, user_id: str) -> dict | None:
    """标记这条采购已交付 —— 「生成交付」按钮的动作。

    ═══════════════════════════════════════════════════════════════════
    2026-09-27：这个动作原先**不存在**
    ═══════════════════════════════════════════════════════════════════
    页头那个「生成交付」按钮做的事其实是「把交付物正文再取一遍」——
    而正文在收尾时就已经算好并下发过了，所以点了之后**界面上什么都不会变**。
    用户的原话是「右侧的生成交付按钮无效」，准确。

    现在它是真的一个动作：记下交付时刻，历史列表据此把「待交付」变成
    「已交付」。产出物本身在收敛时就已生成，这一步交付的是**用户的确认**。

    只有收敛（converged）的 run 能交付 —— 还在跑或失败的任务没有可交付的
    东西，允许标记会让历史里出现「已交付但什么都没有」的记录。
    """
    async with pg_manager.get_async_session_context() as session:
        r = await session.execute(
            select(PlanningRun).where(
                PlanningRun.id == run_id, PlanningRun.user_id == user_id
            )
        )
        run = r.scalar_one_or_none()
        if run is None:
            return None
        if run.status != "converged":
            # 如实拒绝，并说清原因 —— 前端据此显示提示而不是静默失败
            return {"rejected": "not_converged", "status": run.status}
        # 幂等：重复点不该把时间刷成新的
        if run.delivered_at is None:
            run.delivered_at = utc_now_naive()
        await session.commit()
        await session.refresh(run)
        return _with_summary(run)


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


async def _merge_graph(run_id: str, new_nodes: list[dict], new_edges: list[dict],
                       prune_prefixes: tuple[str, ...] = ()) -> None:
    """把增量并入 run.graph 快照，并发一条 graph 事件。

    合并后**下发整图**而不是增量：前端收到直接替换即可。
    「增量合并」的复杂度留在服务端一处，前端不做第二套。

    `prune_prefixes`：合并前先删掉 id 以这些前缀开头、且**不在 `new_nodes`
    里**的旧节点。`_sync_graph` 是「从产物重建整图」，产物里没有的商品
    就是这一轮不再成立的 —— 不删的话它们会永远留在图上（见 `_sync_graph`
    末尾的说明）。默认空，即纯合并、不删任何东西。
    """
    async with pg_manager.get_async_session_context() as session:
        r = await session.execute(select(PlanningRun).where(PlanningRun.id == run_id))
        run = r.scalar_one_or_none()
        if run is None:
            return
        g = dict(run.graph or {})
        nodes = {n["id"]: n for n in (g.get("nodes") or [])}
        keep_ids = {n["id"] for n in new_nodes}
        if prune_prefixes:
            for nid in [k for k in nodes
                        if k.startswith(prune_prefixes) and k not in keep_ids]:
                del nodes[nid]
        for n in new_nodes:
            nodes[n["id"]] = {**nodes.get(n["id"], {}), **n}
        edges = {(e.get("source_id"), e.get("target_id"), e.get("type")): e
                 for e in (g.get("edges") or [])}
        if prune_prefixes:
            # 指向已删节点的边也要清掉，否则前端会画出一堆悬空的线
            edges = {k: e for k, e in edges.items()
                     if k[0] in nodes and k[1] in nodes}
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

    # ═══════════════════════════════════════════════════════════════════
    # ⚠️ 2026-09-27 修 bug：存的是**解析后的 label**，不是 key
    # ═══════════════════════════════════════════════════════════════════
    # 原先存 `answer_pick=key`（如 "opt0"），而 `advance` 要读 `run.question`
    # 才能把 key 翻回 label —— 但上一行刚把 question 置空，于是读到空对象，
    # 拼出的是「关于「」，我选：opt0。请据此继续」这种**没有意义的话**。
    #
    # 实测后果：模型收到这句废话后没按用户的选择走（用户选了「推隔音窗」，
    # 它却去查「隔音门」），整个方向跑偏。
    #
    # 顺带把问题原文也存下来：回答文本要能独立说清「在回答什么」，
    # 不能依赖另一张表里的字段还在。
    await _patch_run(
        run_id, question=None, status="running",
        answer_pick=key,
        answer_label=label,
        answer_question=str(q.get("text") or ""),
    )

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
    # ⚠️ 在 try **之前**定义：`except` 里要用它关阶段，而失败可能发生在
    # 赋值之前（那时会 NameError，把真正的错误盖掉）。实测踩过。
    phases: dict[str, float] = {}
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
        # 入口参数单独留一份：`_sync_graph` 重建图时要读它（需求节点、预算、
        # 采购对象名都从这儿来）。`init` 是喂给 agent 的输入，会被追加消息，
        # 不适合当「只读的入口参数」用。
        state = _state_of(run)
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
        # 阶段状态表（stage → 首次进入的时间戳）。换阶段时给上一个收尾，
        # 收尾/中断时全部关掉 —— 否则界面会永远停在「进行中」（见 _close_phase）。
        # 每次 advance 清空：续跑是新一轮循环，上一轮的阶段不该继续计。
        phases.clear()
        _current_phase.pop(run_id, None)
        # 跨步累积的产物（候选/排除/选中/风险/维度）。
        # `stream_mode="updates"` 只给增量，得自己攒；攒出来的要落库，
        # 否则收尾生成交付物时读不到（见 _persist_products 的说明）。
        #
        # ═══════════════════════════════════════════════════════════════
        # ⚠️ 2026-09-27：续跑必须**从上一轮的产物接着攒**
        # ═══════════════════════════════════════════════════════════════
        # 原先这里恒为 `{}`。中断续跑时，第二轮从空开始攒，收尾
        # `_persist_products` 拿它**覆盖** products —— 第一轮搜到的候选、
        # 排掉的商品全被丢掉。而图是 `_merge_graph` 按 id **合并**的，
        # 不会删节点 —— 于是图和产物越漂越远。
        #
        # 实测一次 run：图里 84 个商品节点、products 里只剩 45 个，
        # 54 个节点成了「数据已经不存在」的孤儿，界面上显示 98 个节点。
        # 用户看到的「候选商品这么多」有一半是这么来的。
        #
        # 同一个 bug 还有第二个后果：agent 的 state 也是空的，工具读
        # `state.get("candidates")` 得到空列表，`drop_candidates` 于是
        # 回「这些名字没在候选里找到，未生效」—— 界面上那句
        # 「候选里没找到你给的…」就是这么来的。
        acc: dict = _seed_acc(run)
        # 累积对话历史，跑完存进 `run.messages` —— 中断续跑时要用它，
        # 否则 agent 从零开始，把搜过的全重做一遍（见 _agent_input 的说明）。
        history: list[dict] = list(init.get("messages") or [])

        try:
            async for mode, chunk in agent.astream(
                init, stream_mode=["updates", "messages"]
            ):
                if await get_run(run_id, user_id) is None:
                    return   # run 被删了

                if mode == "messages":
                    await _on_model_token(run_id, chunk, pump)
                    continue

                _collect_messages(chunk, history)
                stop = await _on_agent_step(run_id, chunk, seen_tools, pump, acc,
                                            state, phases)
                if stop:
                    await pump.close()
                    # 关掉还开着的阶段：进程要停了，界面不能还显示「进行中」
                    await _close_all_phases(run_id, phases)
                    await _persist_history(run_id, history)
                    await _patch_run(run_id, status="awaiting", question=stop)
                    await emit(run_id, "question", stop)
                    return
        finally:
            await pump.close()

        # ═══════════════════════════════════════════════════════════════
        # 收尾前校验：模型**真的做出决定了吗**
        # ═══════════════════════════════════════════════════════════════
        # 2026-09-27：实测一次「装修 / 6万」的 run，模型搜了 42 件候选、
        # 排掉 4 件，然后 `astream` 就**正常结束了** —— 它从没调用
        # `make_decision`。而 `create_agent` 的循环「没有 tool_calls 就走向
        # END」是**正常路径**，不是异常，所以 advance 一路走到收尾，
        # 把空结果标成了 `converged`，报告上写着「本次未选出合适的商品」。
        #
        # 那是**静默失败**：用户看到的是一份"成功"的报告，只是里面没有结论。
        #
        # 判据用 `acc.plan.items` 而不是「有没有 tool_calls」：模型可能调了
        # make_decision 但名字对不上候选（工具会如实回报未生效），那种情况
        # 同样没有可交付的结论，也该续推。
        #
        # 复现验证：把那条 run 的历史原样喂回 agent，它会继续排除、搜索、
        # 最后调 ask_user —— 说明模型与历史都没坏，是那一轮模型调用被吞了
        # （上游限流/超时）。
        for attempt in range(MAX_DECISION_RETRIES):
            if _has_decision(acc):
                break
            logger.warning(
                "[planning] run %s 第 %d 次收尾校验：模型未做出决定（候选 %d 件），"
                "喂回历史让它继续", run_id, attempt + 1, len(acc.get("candidates") or [])
            )
            await emit(run_id, "think", {
                "title": "模型未给出结论，正在继续",
                "detail": "上游可能限流或超时，正在把上下文接回去让它接着推演",
                "by": "rule",
            })
            cont = await _continue_for_decision(run_id, user_id, history, acc, state, phases)
            if cont == "awaiting":
                # 它选择先问用户 —— 这是有效推进，直接停下等拍板
                await _persist_history(run_id, history)
                return

        # 收尾前把产物落库 + 最后一次重建图 —— `_finish` 生成交付物时要读它，
        # 界面也要看到「最终选中的那件」被标成 selected（而不是停在候选态）
        # 关掉最后一个阶段 —— 它后面没有「下一个阶段」来触发收尾
        await _close_all_phases(run_id, phases)
        await _persist_history(run_id, history)
        await _persist_products(run_id, acc)
        await _sync_graph(run_id, acc, state)

        if not _has_decision(acc):
            # 续推也没结果 —— **如实失败**，不产出「成功但没结论」的报告
            reason = (
                "模型在完成检索后没有给出采购结论（可能上游限流或超时）。"
                "候选已搜到 %d 件，可在入口页重新发起或稍后重试。" % len(acc.get("candidates") or [])
            )
            logger.error("[planning] run %s 续推 %d 次仍无决定，标为失败",
                         run_id, MAX_DECISION_RETRIES)
            await _patch_run(run_id, status="failed", error=reason)
            await emit(run_id, "done", {"status": "failed", "error": reason[:120]})
            return

        await _finish(run_id, user_id)

    except Exception as e:
        logger.error(f"[planning] run {run_id} 推进失败: {e}", exc_info=True)
        # 失败时同样要关阶段：否则界面显示「正在进行」，而进程已经停了
        try:
            await _close_all_phases(run_id, phases)
        except Exception:
            pass
        await _patch_run(run_id, status="failed", error=str(e)[:500])
        await emit(run_id, "done", {"status": "failed", "error": str(e)[:200]})


# 收尾校验最多续推几次。
# 2 次是权衡：一次多半能救回来（上游限流是瞬时的），再多就是反复撞同一堵墙
# —— 而且每次都要跑完整轮模型调用，用户等不起。
MAX_DECISION_RETRIES = 2


def _has_decision(acc: dict) -> bool:
    """这次推演**真的做出了决定**吗。

    判据是 `plan.items` 非空，而不是「有没有调过 make_decision」：

    ⚠️ 两者会不一致，而且以后者为准是错的。模型可能调了 make_decision，
    但给的商品名与候选对不上 —— 工具那时会如实回「没找到，请用原名」
    且**不写 plan**。这种情况下同样没有可交付的结论，也该续推。
    所以看结果（有没有定下东西），不看过程（有没有调那个工具）。
    """
    plan = acc.get("plan") or {}
    return bool([i for i in (plan.get("items") or []) if isinstance(i, dict)])


async def _continue_for_decision(run_id: str, user_id: str, history: list[dict],
                                 acc: dict, state: dict, phases: dict) -> str:
    """把历史接回去，让模型继续走完（直到它做出决定或提问）。

    返回 `"awaiting"` 表示它选择先问用户（这时该停下等拍板，不该算失败）。

    ═══════════════════════════════════════════════════════════════════
    为什么是「接回历史再跑一轮」而不是「单独问它选哪个」
    ═══════════════════════════════════════════════════════════════════
    最省事的做法是构造一句话「请从这些候选里选一件并调 make_decision」。
    但那等于把编排权拿回代码手里 —— 而这整个 agent 的设计前提是**走法由
    模型定**（它可能想再补搜一个品类、或者想先问用户）。给它完整上下文，
    它自己会接着判断，正如实测复现里它接着排除了 3 件、又补搜了一轮。

    `acc` 传进去而不是从 run 读：此刻还没落库（落库在收尾那一步），
    读库会拿到上一轮的旧产物。
    """
    run = await get_run(run_id, user_id)
    if run is None:
        return "gone"

    from src.agents.independent.planning.graph import get_planning_agent

    agent = get_planning_agent()
    # 把「轮到你了」明说一句：上一轮是以 tool 消息结尾的，
    # 模型收到的上下文里没有新的用户输入。补一句能让它明确知道要继续
    # （也是给上游一个非空的收尾回合）。
    resume = list(history) + [{
        "role": "user",
        "content": "请继续。如果信息已经足够，就定下最终要买的商品；"
                   "如果还需要我拍板，就向我提问。",
    }]
    init = {"messages": resume, **state, **_seed_acc(run)}
    # 用 acc 里更新的产物覆盖 _seed_acc（它读的是库里的旧值）
    init["candidates"] = acc.get("candidates") or init.get("candidates") or []
    init["excluded"] = acc.get("excluded") or init.get("excluded") or []
    init["plan"] = acc.get("plan") or {}

    stop = None
    try:
        async for mode, chunk in agent.astream(init, stream_mode=["updates"]):
            if mode != "updates":
                continue
            _collect_messages(chunk, history)
            # pump 传 None：`_on_agent_step` 的签名里虽然有它，但函数体
            # 从不使用（那是早期版本的残留）。续推这一轮也不播流式文字 ——
            # 它发生在收尾校验里，用户此刻看到的是「正在继续」那条事件。
            got = await _on_agent_step(run_id, chunk, set(), None,
                                       acc, state, phases)
            if got:
                stop = got
                break
    except Exception as e:
        # 续推失败不该让整条 run 崩 —— 调用方会按「仍无决定」如实收尾
        logger.warning("[planning] run %s 续推失败（忽略）: %s", run_id, e)
        return "failed"

    if stop:
        await _close_all_phases(run_id, phases)
        await _patch_run(run_id, status="awaiting", question=stop)
        await emit(run_id, "question", stop)
        return "awaiting"
    return "ok"


def _merge_plan(old: dict | None, new: dict | None) -> dict:
    """把新的一次 `make_decision` 并进已有的 plan：**同品类替换、新品类追加**。

    ═══════════════════════════════════════════════════════════════════
    为什么不能整体覆盖
    ═══════════════════════════════════════════════════════════════════
    模型在续跑时会**再调一次** `make_decision`，而第二次通常只列
    「这次新增的品类」（前一次定过的它认为已经生效 —— 这判断是对的）。
    整体替换就把上一轮的成果丢掉。实测一次七件套的 run：最终 plan 只剩
    书桌+餐桌两件，预算表显示「占 15%」，而模型的 `why` 里写的是
    「合计 ¥10034.7、占 83.6%」—— 卡片和理由又对不上，和用户最初
    报的那个毛病同源。

    按品类合并同时满足两种意图：
      · 「改主意换掉床」—— 床这一类被新值覆盖，旧的不会残留
      · 「这一轮只补书桌」—— 床、沙发等未被提及的品类原样保留

    品类取 `_category`；没有就退回商品名（单件采购时一个元素，等价于替换）。
    """
    old = old or {}
    new = new or {}
    new_items = [i for i in (new.get("items") or []) if isinstance(i, dict)]
    if not new_items:
        # 新的一次什么都没定下（全没匹配上）—— 保留旧的，别把成果清空
        return old

    def key(i: dict) -> str:
        return str(i.get("_category") or i.get("name") or "")

    merged: dict[str, dict] = {}
    for i in (old.get("items") or []):
        if isinstance(i, dict):
            merged[key(i)] = i
    for i in new_items:
        merged[key(i)] = i

    items = list(merged.values())
    # 总额：**每一件都有小计**时才算得准；缺任何一件就置空
    # （拿部分和冒充总额正是「28% vs 93%」那类错的来源，见 build_budget_doc）
    subs = [i.get("subtotal") for i in items]
    total = (round(sum(float(s) for s in subs), 2)
             if subs and all(s is not None for s in subs) else None)

    return {
        "items": items,
        # 理由用最新的（它反映这一轮的取舍逻辑）；没有就留旧的
        "why": new.get("why") or old.get("why") or "",
        "by": new.get("by") or old.get("by") or "llm",
        "total": total,
    }


def _collect_messages(chunk: dict, history: list[dict]) -> None:
    """把 agent 这一步产出的消息追加进历史（供续跑用）。

    只存**可序列化**的字段（role / content / tool_calls / tool_call_id）——
    LangChain 的 message 对象不能直接进 JSONB，且我们也不需要它的全部细节。
    """
    for _node, delta in (chunk or {}).items():
        for m in ((delta or {}).get("messages") or []):
            role = getattr(m, "type", None) or getattr(m, "role", "") or ""
            if role == "human":
                role = "user"
            elif role == "ai":
                role = "assistant"
            item: dict = {"role": role}
            content = getattr(m, "content", None)
            if isinstance(content, str):
                item["content"] = content
            elif content:
                item["content"] = str(content)
            calls = getattr(m, "tool_calls", None) or []
            if calls:
                # 只留能 JSON 化的三样；args 里可能有非基本类型，兜底转字符串
                item["tool_calls"] = [
                    {"id": c.get("id") or "", "name": c.get("name") or "",
                     "args": _safe_args(c.get("args"))}
                    for c in calls
                ]
            tid = getattr(m, "tool_call_id", None)
            if tid:
                item["tool_call_id"] = tid
            # 空消息（既无正文也无工具调用）不存 —— 只会让历史变长
            if item.get("content") or item.get("tool_calls"):
                history.append(item)


def _safe_args(args: Any) -> dict:
    """工具入参转成可 JSON 化的 dict。"""
    if not isinstance(args, dict):
        return {}
    out = {}
    for k, v in args.items():
        out[k] = v if isinstance(v, (str, int, float, bool, list, dict, type(None))) else str(v)
    return out


async def _persist_history(run_id: str, history: list[dict]) -> None:
    """把对话历史落库（续跑时要用）。

    ⚠️ 截断：一次运行的消息可能上百条，JSONB 会越写越大。留最后 60 条 ——
    足够让 agent 知道「搜过什么、排除了什么、选了什么」，又不至于把
    单行撑到几 MB。
    """
    try:
        await _patch_run(run_id, messages=history[-60:])
    except Exception as e:
        logger.warning(f"[planning] 落对话历史失败（忽略）: {e}")


def _seed_acc(run: PlanningRun) -> dict:
    """续跑时把上一轮的产物读回来，作为累积的起点。

    ⚠️ 这是「agent 自己记得自己做过什么」的一部分，和 `run.messages`
    （对话历史）配套：消息让它记得**说过什么**，产物让它记得**搜到了什么**。
    少了后者，`drop_candidates` 会在空池子里找名字，回一句
    「这些名字没在候选里找到，未生效」—— 模型据此以为自己搞错了，
    行为开始乱（实测踩过）。

    `plan` 也要带上：模型续跑时**只列这次新增的品类**（前一次定过的
    它认为已经生效），合并要有个底才能把旧的那些留住（见 `_merge_plan`）。
    """
    p = run.products or {}
    out: dict = {}
    for k in ("candidates", "excluded", "risks", "dimensions"):
        if p.get(k):
            out[k] = list(p[k])
    if p.get("plan"):
        out["plan"] = p["plan"]
    return out


def _agent_input(run: PlanningRun) -> dict:
    """给 agent 的初始输入：任务描述 + 入口参数 + **上一轮的对话历史**。

    ═══════════════════════════════════════════════════════════════════
    ⚠️ 2026-09-27 修 bug：续跑必须带上历史
    ═══════════════════════════════════════════════════════════════════
    原先只给「目标 + 一句回答」，agent 从零开始 —— 之前搜过的、排除过的
    全部作废，重头再来一遍。

    实测一次运行：用户在「推隔音窗还是静音门」处作答后续跑，agent 把前面
    6 次搜索**重做了一遍**（总计 12 次搜索），候选池因此从 ~20 膨胀到 42，
    决策图 82 个节点。用户看到的是「答完一句，它又开始从头搜」。

    现在把上一轮的消息历史（`run.messages`）接上，agent 接着走。
    """
    from src.agents.independent.planning.graph import build_goal

    state = _state_of(run)
    history = list(run.messages or [])
    if not history:
        # 首轮：只有任务描述
        history = [{"role": "user", "content": build_goal(state)}]
    # ⚠️ 续跑时把上一轮的**产物**也放进 agent 的 state —— 与 `_seed_acc`
    # 是同一件事的两面：那边管「落库时别丢」，这边管「工具读得到」。
    # 少了这边，`drop_candidates` 在空池子里找名字，回一句
    # 「这些名字没在候选里找到，未生效」，模型据此以为自己搞错了。
    # 图的 reducer 是追加语义，把旧的当底、新搜到的自然接在后面。
    seed = _seed_acc(run)
    return {"messages": history, **state, **seed}


def _answer_text(run: PlanningRun) -> str:
    """用户对上一次提问的回答，转成一句话喂回模型。

    ⚠️ 读的是 `answer_label` / `answer_question`（**存下来的副本**），
    不是 `run.question` —— 后者在用户点选项时就被清空了（见
    `answer_question` 的说明）。原先在这里读它，拼出来的是
    「关于「」，我选：opt0」，模型收到一句废话，方向直接跑偏。
    """
    picked = run.answer_pick or ""
    label = run.answer_label or picked
    asked = run.answer_question or ""
    if asked:
        return f"关于「{asked}」，我选：{label}。请据此继续。"
    return f"我选：{label}。请据此继续。"


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
    # ⚠️ 2026-09-27：从「生成交付」改成「向你确认」。
    # 它调的是 `ask_user` —— **提问**，不是交付。用「生成交付」这个名字有
    # 两个后果（用户直接看出来了）：
    #   · 模型常在**最开始**提问（需求不明确时先问），于是执行流的第一个
    #     阶段显示成「生成交付」—— 看着像流程倒着走。
    #   · 点开详情，里面是「已向用户提问，等待回答」，与「生成交付」
    #     这个标题对不上。
    # 真正的交付在收尾（`_finish` 生成产出物），与这个工具无关。
    "ask_user": ("向你确认", "向你确认"),
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
    acc: dict, state: dict, phases: dict,
) -> dict | None:
    """agent 跑完一步（模型节点或工具节点）→ 落事件、累积产物。

    `acc` 是**跨步累积**的产物字典（candidates/excluded/selected/risks/…）。
    ⚠️ 必须自己累积：`stream_mode="updates"` 只给**本步的增量**，不是完整
    状态。这些产物要落库（`_persist_products`），否则收尾生成交付物时
    读不到 —— 交付物会全是空的（实测踩过）。

    返回非 None 表示要停下来问用户。
    """
    changed = False
    for _node, delta in (chunk or {}).items():
        d = delta or {}
        # 累积工具写进 state 的产物（列表追加、标量后写覆盖，与图的 reducer 一致）
        for k in ("dimensions", "candidates", "excluded", "risks"):
            if d.get(k):
                acc.setdefault(k, [])
                acc[k] = acc[k] + list(d[k])
                changed = True
        for k in ("dims_from_kb", "risks_from_kb"):
            if d.get(k) is not None:
                acc[k] = d[k]
                changed = True

        # ⚠️ 2026-09-27：`plan` 要**按品类合并**，不能整体覆盖
        #
        # `make_decision` 是「收敛动作」，但模型在**续跑**时会再调一次 ——
        # 而它第二次只列**这次新增的品类**（前一次定过的它认为已经生效了，
        # 这判断没错）。`plan` 是后写覆盖语义，整体替换就把前一轮的 5 件
        # 换成这一轮的 2 件。实测：一次七件套的 run 最终只剩书桌+餐桌两件，
        # 预算表显示「占 15%」，而模型在 `why` 里写的是「合计 ¥10034.7、占 83.6%」
        # —— 又是同一个病：卡片和理由对不上。
        #
        # 合并规则：**同品类替换、新品类追加**。这样「改主意换掉床」仍然生效
        # （床这一类被新值覆盖），而「这一轮只补了书桌」不会把床弄丢。
        if d.get("plan") is not None:
            acc["plan"] = _merge_plan(acc.get("plan"), d["plan"])
            changed = True

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
                await _emit_tool_call(run_id, name, args, first,
                                      call.get("id") or "", phases)

            # ── 工具返回 ──
            if isinstance(m, ToolMessage):
                await _emit_tool_result(run_id, m)

        # ── 工具写了 question → 停下来等用户 ──
        if d.get("question"):
            await _persist_products(run_id, acc)
            await _sync_graph(run_id, acc, state)
            return d["question"]

    # 产物有变化才重建图 —— 模型节点（只出 tool_calls、不改产物）不该触发，
    # 否则每一步都重发一遍整图，白白刷屏。
    if changed:
        await _sync_graph(run_id, acc, state)
    return None


# 每个 run 当前处在哪个阶段 —— 用来判断「换阶段了」从而给上一个收尾。
# 进程内即可：单进程跑后台任务，run 的推进是单条任务链，不会并发。
_current_phase: dict[str, str] = {}


async def _close_phase(run_id: str, stage: str, phases: dict) -> None:
    """给一个阶段收尾：发 state=done + **真实耗时**。

    ═══════════════════════════════════════════════════════════════════
    2026-09-27：为什么必须补这一步
    ═══════════════════════════════════════════════════════════════════
    原先只发 `state="running"`，**从不发改 done** —— 于是界面上每个阶段
    都永远停在「进行中」（实测五个阶段全是 is-running、耗时全是 0ms），
    run 跑完了左栏还在转。用户说的「有始有终」缺的就是这一半。

    耗时按「首次进入 → 离开」的时间差算，是**真实**的墙上时间。它包含了
    模型在这阶段里的思考时间，所以不是「工具执行耗时」而是「这一阶段
    耗时」—— 那正是用户想知道的（哪一步慢）。
    """
    t0 = phases.pop(stage, None)
    _current_phase.pop(run_id, None)
    if t0 is None:
        return
    ms = int((time.time() - t0) * 1000)
    await emit(run_id, "phase", {
        "phase": stage, "label": stage, "state": "done", "ms": ms,
    })


async def _close_all_phases(run_id: str, phases: dict) -> None:
    """收尾时把还开着的阶段全部关掉。

    ⚠️ 必须有：run 的最后一个阶段不会有「下一个阶段」来触发收尾，
    不显式关就会一直挂在「进行中」。中断（等用户拍板）与失败路径也要关 ——
    否则界面显示「正在进行」，而实际上进程已经停了。
    """
    for stage in list(phases.keys()):
        await _close_phase(run_id, stage, phases)


async def _emit_tool_call(run_id: str, name: str, args: dict, first: bool,
                          tool_call_id: str = "",
                          phases: dict | None = None) -> None:
    """模型决定调某个工具 → 一条事件。**带真实入参**。

    ⚠️ 带上 `tool_call_id`：模型会**并行**调多个工具，返回时要用它精确配对
    到是哪一次调用。前端靠「最后一条还没返回的 call」去猜是错的 ——
    并行时返回顺序不保证，会把 A 的结果挂到 B 上（实测踩过：搜索关键词和
    返回的商品对不上）。

    `phases`：阶段状态表（stage → 首次进入的时间戳）。传入时这里负责
    **阶段的生命周期** —— 换阶段就把上一个阶段收尾（发 state=done + 真实
    耗时）。不传则只发 running（测试与旧调用方）。
    """
    stage, verb = _TOOL_META.get(name, ("执行", name))
    if phases is not None:
        prev = _current_phase.get(run_id)
        if prev and prev != stage:
            await _close_phase(run_id, prev, phases)
        if stage not in phases:
            phases[stage] = time.time()
            _current_phase[run_id] = stage
            await emit(run_id, "phase", {
                "phase": stage, "label": stage, "state": "running",
                "hint": verb,
            })
    elif first:
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
        "tool_call_id": tool_call_id,
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
        picks = args.get("picks") or []
        if isinstance(picks, list) and picks:
            names = [str(p.get("picked") or "") for p in picks if isinstance(p, dict)]
            names = [n for n in names if n]
            title = (f"定下「{names[0]}」" if len(names) == 1
                     else f"定下 {len(names)} 件：{'、'.join(n[:12] for n in names[:3])}")
        else:
            # 兼容旧事件回放里的单件形状
            title = f"定下「{args.get('picked') or ''}」"
        return (title, str(args.get("why") or ""), [])
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
        # 记下报告那份 doc —— 通知要用它的 headline（件数/总价）。
        # 复用它而不是另算一遍：两次 build_deliverable 结果可能不一致。
        report_doc = None
        for a in ARTIFACT_SPEC:
            did, name, meta = a["id"], a["name"], a["meta"]
            await emit(run_id, "deliverable",
                       {"id": did, "name": name, "meta": meta, "state": "running", "progress": 0.5})
            try:
                doc = st.build_deliverable(state, did)
            except Exception as e:
                logger.warning(f"[planning] 交付物 {did} 生成失败: {e}")
                doc = None
            if did == "d-report":
                report_doc = doc
            await emit(run_id, "deliverable",
                       {"id": did, "name": name, "meta": meta,
                        "state": "ready" if doc else "empty", "data": doc,
                        # 产出物元信息：支持的格式、是否主件、一句话说明。
                        # 前端据此决定显示几个下载按钮、哪个默认展开 ——
                        # 而不是点了才发现 404（见 ARTIFACT_SPEC 的说明）
                        "formats": list(a["formats"]),
                        "primary": a["primary"],
                        "desc": a["desc"]})

        await _patch_run(run_id, status="converged")
        await emit(run_id, "done", {"status": "converged"})

        # 通知：让「规划收敛了」出现在主页状态卡与助理页。
        # ⚠️ 通知失败绝不能影响推演 —— 内部已全包，这里再兜一层。
        try:
            from src.services import notify_service
            await notify_service.notify_run_once(
                user_id, run_id,
                notify_service.from_planning_run(
                    await get_run(run_id, user_id), report_doc),
            )
        except Exception as notify_err:
            logger.warning(f"[planning] 发通知失败（忽略）: {notify_err}")
    except Exception as e:
        logger.error(f"[planning] run {run_id} 收尾失败: {e}", exc_info=True)
        await _patch_run(run_id, status="failed", error=str(e)[:500])
        await emit(run_id, "done", {"status": "failed", "error": str(e)[:200]})
        # 失败也要告知 —— 悄悄失败比推一条更糟
        try:
            from src.services import notify_service
            await notify_service.notify_run_once(
                user_id, run_id,
                notify_service.from_planning_run(await get_run(run_id, user_id)),
            )
        except Exception as notify_err:
            logger.warning(f"[planning] 发失败通知出错（忽略）: {notify_err}")


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


async def _sync_graph(run_id: str, acc: dict, state: dict) -> None:
    """把累积产物**重建成决策图**并下发。

    ═══════════════════════════════════════════════════════════════════
    2026-09-26：补上漏掉的一步 —— 决策图之前根本不长
    ═══════════════════════════════════════════════════════════════════

    改成 ReAct 之后，我只保留了「核心任务」那一个节点就再没动过图 ——
    界面上永远是「1 / 1 节点」（实测截图可见）。原因是旧实现的建图代码
    写在 `_on_node` 里，那个函数在重写时被整个替换掉了，而我没有把建图
    这部分补回来。

    现在改成**从产物重建整图**，而不是逐节点增量拼。理由：
      · 产物本来就是完整的（候选/排除/选中/风险/维度都在 `acc` 里）
      · 增量拼要处理「候选被排除后类型要变」这类状态迁移，容易拼出重复节点
      · 重建成整图后 `_merge_graph` 按 id 覆盖，天然幂等

    节点 id 用 **item_id**（不是下标）：同一件商品从「候选商品」变成
    「已排除」时 id 不变，`_merge_graph` 就地把类型与状态改掉，
    不会留下一个旧节点。
    """
    nodes: list[dict] = []
    edges: list[dict] = []

    subject = state.get("subject") or state.get("scene") or "本次采购"

    # 需求：把入口参数摊成依据节点（这些是模型的判据来源）
    for i, c in enumerate(state.get("constraints") or []):
        nodes.append(_node(f"need-{i}", str(c), "需求", 4, "candidate"))
        edges.append(_edge("task", f"need-{i}", "需要"))
    if state.get("budget"):
        nodes.append(_node("need-budget", f"预算 {state['budget']}", "需求", 5, "candidate"))
        edges.append(_edge("task", "need-budget", "需要"))

    # 采购对象：搜到东西之后才立
    cands = acc.get("candidates") or []
    if cands:
        nodes.append(_node("obj-1", subject, "采购对象", 5, "candidate"))
        edges.append(_edge("task", "obj-1", "拆解为"))

    # 品类标准（模型查到的评估维度）
    for i, d in enumerate((acc.get("dimensions") or [])[:6]):
        nodes.append(_node(f"ev-{i}", str(d), "决策依据", 3, "candidate"))
        edges.append(_edge("task", f"ev-{i}", "依据"))

    # 候选商品：被排除的用**同一个 id** 覆盖成「已排除」
    # ⚠️ 用 effective_excluded：剔掉已经被选中的那些。模型会改主意 ——
    # 先排掉、后又选回来，同一件就会同时挂在两个名单上。不剔掉的话，
    # 图里它会先画成「已排除」再被候选循环覆盖，看起来忽明忽暗。
    plan = acc.get("plan") or {}
    plan_items = [i for i in (plan.get("items") or []) if isinstance(i, dict)]
    if not plan_items:
        # 兼容旧的单件形状
        sel = acc.get("selected") or {}
        if sel.get("name"):
            plan_items = [sel]
    excluded = st.effective_excluded({
        "excluded": acc.get("excluded") or [],
        "plan": {**plan, "items": plan_items},
    })
    out_names = {st.cand_name(e) for e in excluded}
    sel_ids = {str(i.get("item_id") or "") for i in plan_items if i.get("item_id")}
    sel_names = {str(i.get("name") or "") for i in plan_items}
    # 每件入选的**同类理由** —— 图里点开节点要看到「为什么是它」
    why_by_id = {
        str(i.get("item_id") or ""): str(i.get("why") or "")
        for i in plan_items if i.get("item_id")
    }
    why_by_name = {str(i.get("name") or ""): str(i.get("why") or "") for i in plan_items}

    def _cid(c: dict) -> str:
        raw = c.get("item_id") or st.cand_name(c)
        # 去掉可能出现在 id 里的特殊字符，图 id 要能安全当 key 用
        return "cand-" + "".join(ch for ch in str(raw) if ch.isalnum() or ch in "-_")[:40]

    def _is_selected(c: dict) -> bool:
        """是不是这次买下的那件。

        ⚠️ 优先按 **item_id** 比。同名商品可能有**多件**（不同店铺/规格），
        只按名字比会把它们全标成「已采纳」—— 实测一次运行里 4 件同名商品
        都被标上了。模型没给 item_id 时才退回按名字（此时只能接受歧义）。
        """
        iid = str(c.get("item_id") or "")
        if iid and sel_ids:
            return iid in sel_ids
        return bool(sel_names) and st.cand_name(c) in sel_names

    # ═══════════════════════════════════════════════════════════════════
    # 采购对象 → 品类 → 商品：候选不再直接挂在中心点上
    # ═══════════════════════════════════════════════════════════════════
    # 用户的原话：「候选节点会有这么多节点，这很不合理…全是点」。
    #
    # 根因是**所有候选都从同一个中心点射出去**。一次采购 6 个品类、几十件
    # 商品，星形辐射的结果就是中心一圈密密麻麻的点，读不出任何结构 ——
    # 看不出「这是床那组、那是沙发那组」，也看不出每组收敛到了哪一件。
    #
    # 现在加一层**品类节点**：
    #
    #     采购对象 ─┬─ 床   ─┬─ 候选…
    #               ├─ 沙发 ─┼─ 候选…
    #               └─ 衣柜 ─┴─ ★入选
    #
    # 每个品类自己收着自己的候选，星形变成三级树。好处不只是好看：
    # 品类节点本身就是**归纳**，一眼能看出这次要买几类、每类几件、
    # 哪一类还没定下来。
    #
    # 画布容量也跟着降：原先每个品类留 6 件（共 36 个点），现在 4 件。
    # 排序保证该露的在前面：入选的 > 有价格的 > 原顺序，所以被截掉的
    # 一定是同类里排在后面的备选。
    MAX_PER_CAT = 4

    def _rank(c: dict) -> tuple:
        return (0 if _is_selected(c) else 1,
                0 if st.cand_yuan(c) is not None else 1)

    by_cat: dict[str, list[dict]] = {}
    for c in cands:
        by_cat.setdefault(st.item_category(c), []).append(c)

    # 品类节点的 id。⚠️ 用**品类名清洗后**的 slug，不用 hash() ——
    # Python 字符串 hash 每进程不同（PYTHONHASHSEED 随机），
    # 重启一次 id 就变，旧节点留在图上删不掉。
    def _catid(cat: str) -> str:
        slug = "".join(ch for ch in str(cat) if ch.isalnum())[:16] or "x"
        return f"cat-{slug}"

    for cat, group in by_cat.items():
        ordered = sorted(group, key=_rank)
        picked_in_cat = [c for c in ordered if _is_selected(c)]
        # 品类节点带「本类几件 / 已选哪件」—— 它是归纳，本身就该有信息量
        if picked_in_cat:
            sub = f"已选 {st.cand_name(picked_in_cat[0])[:12]}"
        else:
            sub = f"{len(ordered)} 件候选"
        nodes.append(_node(_catid(cat), f"{cat}（{len(ordered)}）", "采购品类", 4,
                           "selected" if picked_in_cat else "candidate",
                           {"category": cat, "count": len(ordered),
                            "picked": st.cand_name(picked_in_cat[0]) if picked_in_cat else "",
                            "sub": sub}))
        edges.append(_edge("obj-1", _catid(cat), "拆解为"))

        for c in ordered[:MAX_PER_CAT]:
            n = st.cand_name(c)
            iid = str(c.get("item_id") or "")
            state_key = "selected" if _is_selected(c) else "candidate"
            why = why_by_id.get(iid) or why_by_name.get(n) or ""
            nodes.append(_node(_cid(c), n[:40], "候选商品", 3, state_key,
                               {"price": st.yuan(c.get("price")), "item_id": c.get("item_id"),
                                # 图里点开节点要能看到选它的理由
                                "why": why if state_key == "selected" else "",
                                "category": cat}))
            edges.append(_edge(_catid(cat), _cid(c), "候选"))

        # 截断必须**看得见**：悄悄少画几件，用户会以为搜索只返回了这些
        # （那是在骗人）；明说「还有 N 件没画」，他才知道图是摘要、
        # 全量在候选对比表里。
        extra = len(ordered) - MAX_PER_CAT
        if extra > 0:
            hid = f"more-{_catid(cat)[4:]}"
            nodes.append(_node(hid, f"还有 {extra} 件", "候选商品", 1, "candidate",
                               {"category": cat, "collapsed": extra}))
            edges.append(_edge(_catid(cat), hid, "候选"))

    # 排除的同样只画前几件：全画出来又是一面墙。理由已在对比表里逐条列出。
    for e in excluded[:MAX_PER_CAT * 2]:
        price = st.cand_yuan(e)
        nodes.append(_node(_cid(e), st.cand_name(e)[:40], "已排除", 2, "pruned",
                           {"price": st.yuan(e.get("price")), "item_id": e.get("item_id"),
                            "reason": e.get("_reason") or "",
                            # 前端详情条读的是 pruneReason
                            "pruneReason": e.get("_reason") or ""}))
    if len(excluded) > MAX_PER_CAT * 2:
        rest = len(excluded) - MAX_PER_CAT * 2
        nodes.append(_node("more-excluded", f"另有 {rest} 件已排除", "已排除", 1, "pruned",
                           {"reason": "见图表与交付物中的完整排除清单"}))

    # 风险
    for i, r in enumerate((acc.get("risks") or [])[:6]):
        nodes.append(_node(f"risk-{i}", str(r), "风险", 3, "candidate"))
        edges.append(_edge("task", f"risk-{i}", "存在"))

    if not nodes:
        return
    # ⚠️ `_merge_graph` 只按 id 合并、**从不删节点**。而 `_sync_graph` 是
    # 「从产物重建整图」—— 产物里没有的，就是这一轮不再成立的节点。
    # 不显式删掉的话，上一轮搜到、这一轮已被丢弃的商品会永远留在图上，
    # 越积越多（实测一次 run 攒到 98 个节点，其中 54 个是孤儿）。
    #
    # 所以把这次重建出的**商品类节点 id 全集**传下去，让合并时清掉
    # 不在其中的旧商品节点。前缀要包含 `more-`（品类的「还有 N 件」汇总
    # 节点）—— 那个数字随搜索变化，旧的要跟着走。
    # 只清商品类 —— 需求/依据/风险这些是按位置编号的，删了会连累其它节点。
    await _merge_graph(run_id, nodes, edges, prune_prefixes=("cand-", "more-", "cat-"))


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
    if p.get("candidates") or p.get("selected") or p.get("plan"):
        cands = _dedup(p.get("candidates") or [])
        # ⚠️ 用 effective_excluded：它会剔掉**已经被选中的**那些。
        # 模型会改主意 —— 实测它先以「超预算」排掉雅兰床垫，用户答
        # 「升级品质」后又选了回来，于是同一件同时挂在候选与排除两个名单上。
        # 不剔掉的话，下面这行会把它从候选里删掉，对比表就标不出它入选。
        state_for_ex = {"excluded": p.get("excluded") or [],
                        "plan": p.get("plan") or {},
                        "selected": p.get("selected") or {}}
        excluded = st.effective_excluded(state_for_ex)
        out_names = {st.cand_name(e) for e in excluded}
        return {
            "scene": run.scene, "budget": run.budget, "duration": run.duration,
            "constraints": run.constraints or [], "subject": run.subject,
            "run_id": run.id, "user_id": run.user_id,
            # 已排除的从候选里剔掉 —— 排除工具只往 excluded 里追加，
            # 不回头改 candidates（改了会让候选翻倍，见 tools._to_stage_state）
            "candidates": [c for c in cands if st.cand_name(c) not in out_names],
            "excluded": excluded,
            "plan": p.get("plan") or {},
            # 兼容旧 run：单件形状仍然读得出来，刷新后不会突然变空
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

    # 回退路径也按「可能有多件」来读 —— 2026-09-27 之后图上可以有多件 selected
    # （买一套时每件都标），所以收集全部，不再只取第一件。
    picked = [c for c in candidates if c.pop("_selected", False)]
    plan = {
        "items": [{
            "name": c.get("name"), "item_id": c.get("item_id"),
            "price_yuan": c.get("price_yuan"), "quantity": None,
            "quantity_basis": "", "subtotal": None, "why": c.get("why") or "",
        } for c in picked],
        "why": "", "by": "kb",
        "total": (sum(c["price_yuan"] for c in picked)
                  if picked and all(c.get("price_yuan") for c in picked) else None),
    }

    return {
        "scene": run.scene, "budget": run.budget, "duration": run.duration,
        "constraints": run.constraints or [], "subject": run.subject,
        "run_id": run.id, "user_id": run.user_id,
        "candidates": candidates, "excluded": excluded,
        "plan": plan,
        "selected": picked[0] if picked else {},
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
    spec = next((a for a in ARTIFACT_SPEC if a["id"] == did), None)
    if spec is None:
        return None
    name, meta = spec["name"], spec["meta"]

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
        # 支持的导出格式。前端据此显示按钮、路由据此校验 ——
        # 一份产出物能导什么，由**它的类型**决定，不由调用方猜。
        "formats": list(spec["formats"]) if doc else [],
        "primary": spec["primary"],
        "desc": spec["desc"],
        "generated_at": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M"),
    }


# ══════════════════════════════════════════════════════════════════════
# 导出：按格式分派
# ══════════════════════════════════════════════════════════════════════
# 每种格式只做**渲染**，不重算任何业务数字 —— 数据来自与 `get_deliverable`
# 同一套 builder，两者不会漂。
#
# ⚠️ 格式支持由产出物**自己声明**（ARTIFACT_SPEC 的 formats），
# 不在这里按 did 写 if/else。加一种产出物时只改那一处。
_EXT = {"pdf": "pdf", "csv": "csv", "md": "md"}
_MIME = {
    "pdf": "application/pdf",
    # ⚠️ CSV 带 BOM 才是给人用的（Excel 中文不乱码），见 st.list_csv 的说明
    "csv": "text/csv; charset=utf-8",
    "md": "text/markdown; charset=utf-8",
}


async def export_deliverable(run_id: str, user_id: str, did: str,
                             fmt: str) -> tuple[bytes, str, str] | None:
    """导出产出物。返回 `(字节, 文件名, MIME)`；不支持则 None（路由层 404）。

    支持格式以 `ARTIFACT_SPEC` 的声明为准 —— 声明了 md 但没有专门的渲染器时
    走 `deliverable_markdown`（所有类型都有），所以 md 是天然兜底。
    """
    spec = next((a for a in ARTIFACT_SPEC if a["id"] == did), None)
    if spec is None or fmt not in spec["formats"]:
        return None

    run = await get_run(run_id, user_id)
    if run is None:
        return None

    state = _state_from_run(run)
    try:
        doc = st.build_deliverable(state, did)
    except Exception as e:
        logger.warning(f"[planning] 导出前置失败 {did}: {e}")
        return None
    if not doc:
        return None

    name = spec["name"]
    try:
        if fmt == "pdf":
            from src.agents.independent.planning.pdf_export import build_report_pdf
            data = build_report_pdf(doc)
            if not data:
                return None
        elif fmt == "csv":
            data = st.list_csv(doc).encode("utf-8-sig")
        else:  # md
            data = st.deliverable_markdown(doc, name).encode("utf-8")
    except Exception as e:
        logger.error(f"[planning] 导出 {did}.{fmt} 失败: {e}", exc_info=True)
        return None

    return data, f"{name}.{_EXT.get(fmt, fmt)}", _MIME.get(fmt, "application/octet-stream")
