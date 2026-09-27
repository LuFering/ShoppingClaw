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
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import ToolMessage
from sqlalchemy import desc, func, select

from src.agents.independent.gift import stages as st
from src.agents.independent.common_llm import DeltaPump
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

    # ═══════════════════════════════════════════════════════════════════
    # 起始状态：先写一句「我还不了解 TA」
    # ═══════════════════════════════════════════════════════════════════
    # 学 Letta 的 `human` 记忆块 —— 它的初始内容不是空白，而是：
    #
    #     I haven't gotten to know this person yet.
    #     I'm curious about them - not just their preferences, but who they are.
    #     As we collaborate, I'll build up an understanding of how they think...
    #
    # 一句**诚实的自我陈述** + 一段「我打算怎么去了解」。这比空槽好：
    # 空槽只说明「这里没有东西」，而这句话说明「正在建立，而且我知道要建什么」。
    # 而且它给了中栏一个合理的**起点** —— 用户从第一秒就知道这块在干什么。
    #
    # 先发事件再起后台任务，保证它排在所有推演事件之前（seq 最小）。
    brief = f"{run.recipient or '对方'}的{run.occasion or '这次送礼'}"
    await emit(run_id, "opening", {
        "text": f"我还不了解{run.recipient or 'TA'}。",
        "sub": f"这次要给{brief}挑一份礼物（预算 ¥{budget or '—'}）。"
               f"我会从档案、检索与比价里逐步把该知道的补齐 —— "
               f"每得到一条就写进这里。",
        "name": run.recipient or "收礼人",
        "occasion": run.occasion or "",
        "budget": budget,
    })

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
    """跑**一次 ReAct 循环**。**永不抛异常**（失败落 run.error）。

    ═══════════════════════════════════════════════════════════════════
    2026-09-27：从「按六个写死的节点推进」改成「订阅模型的一次次决策」
    ═══════════════════════════════════════════════════════════════════

    用户的原话：「我感觉这个执行流是不是有点假了，为什么会执行这么快」。

    旧实现按 `STEPS` 顺序跑六个节点，service 知道每一步是什么、下一步去哪 ——
    因为那是写在代码里的。而且六步里**只有三处调模型**，另外三步是纯代码
    （查表 / 检索 / 比价），实测前四阶段只花 4.8 秒。那不是效率高，
    是**一半的步骤压根没有智能**。

    现在流程由模型定，service **不知道**它接下来要干什么 —— 只能订阅
    agent 的产出，把「模型决定调哪个工具」翻译成事件。与规划智能体完全同构。

    订阅 `stream_mode=["updates", "messages"]`：
      · `updates` —— 每个节点跑完的产出。模型节点的 `tool_calls` 就是
        「它决定了什么」，工具节点的 `ToolMessage` 就是「拿到了什么」。
      · `messages` —— **逐 token 的模型输出**，用来做实时推理流。
        这是 `create_agent` 自带的，不需要我们再往模型里塞回调。

    中断（ask_user）：工具写了 `question` 就落 awaiting 并停在这里。
    续跑时把用户的回答作为新消息喂回去，循环接着走。
    """
    phases: dict[str, float] = {}
    try:
        run = await get_run(run_id, user_id)
        if run is None:
            return

        agent = get_gift_graph()
        state = {
            "recipient": run.recipient, "occasion": run.occasion,
            "budget": run.budget, "signals": run.signals or [],
            "run_id": run.id, "user_id": run.user_id,
        }
        # 续跑：用户答过问，就把那条回答作为新消息接上 —— agent 是循环，
        # 多给一条输入它自己会接着判断，不需要我们算「从哪一步接」。
        history: list[dict] = list(run.messages or [])
        if not history:
            # build_goal 在 graph.py 里（与规划同构），不在 stages ——
            # stages 是纯函数（取数/组装），任务描述属于 agent 定义。
            from src.agents.independent.gift.graph import build_goal
            history = [{"role": "user", "content": build_goal(state)}]
        if run.answer_pick:
            history = history + [{"role": "user", "content": _answer_text(run)}]

        init = {"messages": history, **state}
        seen_tools: set[str] = set()
        # 跨步累积的产物（候选/排除/档案/礼盒）。`updates` 只给增量，
        # 得自己攒；攒出来的要落库，否则收尾生成交付物时读不到。
        acc: dict = _seed_acc(run)
        pump = DeltaPump(
            lambda text, kind: _emit_think_delta(run_id, text, kind),
            filter_reasoning_text=True,
        )

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
                stop = await _on_agent_step(run_id, chunk, seen_tools, acc, state, phases)
                if stop:
                    await pump.close()
                    await _close_all_phases(run_id, phases)
                    await _patch_run(run_id, messages=history,
                                     status="awaiting", question=stop)
                    await emit(run_id, "question", stop)
                    return
        finally:
            await pump.close()

        await _close_all_phases(run_id, phases)
        await _patch_run(run_id, messages=history)
        await _persist_products(run_id, acc)

        # 收尾：profile_head 是展示层字段，agent 不产出；这里补齐
        fresh = await get_run(run_id, user_id)
        if fresh is not None:
            # 用 acc 里的 profile（本轮最新），不用 fresh.profile ——
            # 后者是上一次 _patch_run 的快照，若本轮档案有更新会读到旧的。
            prof = acc.get("profile") or fresh.profile or []
            head = st.build_profile_head(
                {"recipient": fresh.recipient, "occasion": fresh.occasion,
                 "budget": fresh.budget},
                prof,
            )
            await _patch_run(run_id, profile_head=head, status="converged")
        await emit(run_id, "done", {})

    except Exception as e:
        logger.error(f"[gift] run {run_id} 推演失败: {e}", exc_info=True)
        try:
            await _close_all_phases(run_id, phases)
        except Exception:
            pass
        await _patch_run(run_id, status="failed", error=str(e)[:500])
        await emit(run_id, "done", {})


# 每个 run 当前处在哪个阶段 —— 用来判断「换阶段了」从而给上一个收尾。
_current_phase: dict[str, str] = {}

# run → {步骤 key: 这一批还有几个并行调用没返回}。
# 用于把并行的多个同类调用收成**一次** done（见 _close_phase）。
_pending: dict[str, dict[str, int]] = {}


async def _close_phase(run_id: str, tool: str, phases: dict) -> None:
    """某个工具跑完 → 给它的左栏步骤收尾（发 done + 真实耗时）。

    ⚠️ 收尾时机是这次改造的一个要点：旧实现按**图节点**收尾（节点跑完就
    done），现在没有固定节点了，只能按**工具跑完**来收。差别在于同一个步骤
    可能被调多次（模型搜了 4 轮）—— 那样不能每轮都 done，否则界面上
    「搜索候选」会闪四次完成。

    所以这里的规则是：**只有当模型不再有该步骤的待办调用时才收尾**。
    简化实现：等到它换到别的步骤（或 run 结束）时由 `_close_all_phases`
    统一收 —— 但那样又回到了「全挤在最后」。

    折中：工具跑完就收，前端按 key 聚合（同名步骤多次 done 只保留最后一次
    的耗时）。实测「搜索候选」被调 4 次、耗时相加才合理 —— 这个求和由
    前端做，后端只如实报每一次。
    """
    meta = _TOOL_META.get(tool)
    if not meta:
        return
    key = meta[0]

    # ═══════════════════════════════════════════════════════════════════
    # ⚠️ 模型会**并行**调多个同类工具（实测一次并行搜 2 个词、排除 3 批）
    # ═══════════════════════════════════════════════════════════════════
    # 并行时：多个 `call` 事件在同一瞬间发出（都只发一次 running），
    # 随后多个 `call_result` 依次到达，每次都调到这里。
    #
    # 如果每次都 done，界面会看到「搜索候选」闪好几次完成 —— 而那其实是
    # 同一批并行调用的各个返回。
    #
    # 正确做法：**等这一批全部返回再收尾**。用一个待返回计数器：
    # 发出 running 时记下这批有几个调用，每返回一个减一，减到 0 才 done。
    left = _pending.get(run_id) or {}
    n = left.get(key, 0)
    if n > 1:
        # 还有同批的没回来，先记账，不 done
        left[key] = n - 1
        _pending[run_id] = left
        return
    left.pop(key, None)
    _pending[run_id] = left

    t0 = phases.pop(key, None)
    if t0 is None:
        return
    _current_phase.pop(run_id, None)
    ms = int((time.monotonic() - t0) * 1000)
    # 同一批并行调用的耗时相加才是这步的真实总耗时（前端按 key 聚合）
    await emit(run_id, "step", {"key": key, "status": "done", "ms": ms})


async def _close_all_phases(run_id: str, phases: dict) -> None:
    """给还开着的阶段收尾（发 done + 真实耗时）。

    ⚠️ 必须有：run 的最后一个阶段不会有「下一个阶段」来触发收尾，
    不显式关就会一直挂在「进行中」—— 实测过，界面显示正在跑而进程已经停了。
    """
    for key in list(phases.keys()):
        t0 = phases.pop(key)
        _current_phase.pop(run_id, None)
        ms = int((time.monotonic() - t0) * 1000)
        await emit(run_id, "step", {"key": key, "status": "done", "ms": ms})


def _seed_acc(run: GiftRun) -> dict:
    """续跑时把上一轮的产物读回来，作为累积的起点。

    与 `run.messages`（对话历史）配套：消息让它记得**说过什么**，
    产物让它记得**搜到了什么**。少了后者，`screen_candidates` 会在空池子里
    找名字，回一句「这些名字没在候选里找到」，模型据此以为自己搞错了。
    """
    return {
        "profile": list(run.profile or []),
        "picked": list((run.data or {}).get("picked") or []) if hasattr(run, "data") else [],
        "excluded": list((run.products or {}).get("excluded") or []),
        "plan": (run.products or {}).get("plan") or {},
        **(run.products or {}),
    }


async def _persist_products(run_id: str, acc: dict) -> None:
    """把 agent 累积的产物落进 run.products —— 收尾生成交付物时要读它。"""
    try:
        await _patch_run(run_id, products=acc)
    except Exception as e:
        logger.warning(f"[gift] 落产物失败（忽略）: {e}")


async def _emit_think_delta(run_id: str, text: str, kind: str = "content") -> None:
    """把模型推理的一段增量发出去。

    ⚠️ 单独一种事件（而不是复用 `live`）：前端要把这些片段**追加到同一行**，
    而 `live` 是「新起一条」。两者语义不同，混用会让每次增量都变成新条目。
    """
    await emit(run_id, "think_delta", {"text": text, "kind": kind})


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
        if not (getattr(msg, "tool_call_chunks", None) or []):
            pump.feed(content, "content")


# 工具名 → （左栏步骤 key，中文名，正在做什么）
#
# ⚠️ 与旧的 `_NODE_META` 不同：那是**图的节点名**，这是**工具名**。
# 现在走法由模型定，service 只能按它调的工具归类。
# 同一个步骤可能被调多次（多轮搜索）—— 前端按 key 聚合成一个块。
_TOOL_META: dict[str, tuple[str, str, str]] = {
    "read_recipient": ("understand", "理解关系", "读收礼人的档案"),
    "search_gifts": ("search", "检索商品", "用品类词搜真实商品"),
    "screen_candidates": ("verify", "比价验货", "排除不合适的"),
    "compose_gift": ("combine", "组合礼盒", "让模型决定这几件如何构成一体"),
    "write_note": ("message", "生成寄语", "写一段指回依据的话"),
    "ask_user": ("ask", "向你确认", "需要你拍板"),
}

_STEP_ORDER = ("understand", "search", "verify", "combine", "message", "ask")


async def _on_agent_step(run_id: str, chunk: dict, seen_tools: set[str],
                         acc: dict, state: dict, phases: dict) -> dict | None:
    """agent 跑完一步（模型节点或工具节点）→ 落事件、累积产物。

    返回非 None 表示要停下来问用户。

    ⚠️ `acc` 是**跨步累积**的：`updates` 只给本步增量，不是完整状态。
    """
    changed = False
    for _node, delta in (chunk or {}).items():
        d = delta or {}
        # 累积工具写进 state 的产物（列表追加、标量后写覆盖，与 reducer 一致）
        for k in ("profile", "picked", "excluded", "searched"):
            if d.get(k):
                acc[k] = list(acc.get(k) or []) + list(d[k])
                changed = True
        for k in ("context", "understanding", "plan", "message"):
            if d.get(k) is not None:
                acc[k] = d[k]
                changed = True

        for m in (d.get("messages") or []):
            # ── 模型决定调工具 ──
            for call in (getattr(m, "tool_calls", None) or []):
                name = call.get("name") or ""
                args = call.get("args") or {}
                meta = _TOOL_META.get(name)
                if meta:
                    key = meta[0]
                    # 第一次进入这个步骤 → 发 running（并记开始时刻算真实耗时）
                    if key not in phases:
                        phases[key] = time.monotonic()
                        _current_phase[run_id] = key
                        # 这一批有几个并行调用？同一批 call 事件在同一瞬间
                        # 发出，所以这里累加即可（见 _close_phase 的说明）
                        left = _pending.setdefault(run_id, {})
                        left[key] = (left.get(key) or 0) + 1
                        await emit(run_id, "step", {
                            "key": key, "status": "running",
                            "label": meta[1], "hint": meta[2],
                        })
                    else:
                        # 同批的第二个并行调用：只加计数，不重发 running
                        left = _pending.setdefault(run_id, {})
                        left[key] = (left.get(key) or 0) + 1
                await _emit_tool_call(run_id, name, args)

            # ── 工具返回 ──
            #
            # ⚠️ 工具**跑完**才发交付物与「推演所得」：这一步才知道它产出了
            # 什么。旧实现按图节点发（`_on_node` 的六个 if/elif），现在没有
            # 固定节点了，只能按工具名对应。
            if isinstance(m, ToolMessage):
                await _emit_tool_result(run_id, m)
                name = getattr(m, "name", "") or ""
                await _after_tool(run_id, name, acc, phases)

        # ── 工具写了 question → 停下来等用户 ──
        if d.get("question"):
            await _persist_products(run_id, acc)
            return d["question"]

    if changed:
        # 每一步都把产物落库：收尾要用，中途刷新也读得到
        await _persist_products(run_id, acc)
    return None


async def _emit_tool_call(run_id: str, name: str, args: dict) -> None:
    """模型决定调某个工具 → 一条事件。**带真实入参**。"""
    title, detail, sample = _describe_call(name, args)
    meta = _TOOL_META.get(name)
    await emit(run_id, "call", {
        "title": title, "detail": detail, "args": args, "sample": sample,
        "tool": name, "stage": meta[0] if meta else "执行",
    })


def _describe_call(name: str, args: dict) -> tuple[str, str, list]:
    """把工具调用翻成人话。标题写模型**要做什么**，不是工具名。"""
    if name == "search_gifts":
        return (f"搜「{args.get('keyword') or ''}」", "找真实商品", [])
    if name == "read_recipient":
        return ("读收礼人的档案", "看历史决策与长期偏好", [])
    if name == "screen_candidates":
        names = args.get("names") or []
        return (f"排除 {len(names)} 件", str(args.get("reason") or ""), [])
    if name == "compose_gift":
        return (f"组礼盒「{args.get('title') or ''}」", str(args.get("thesis") or ""), [])
    if name == "write_note":
        return ("写寄语", "每句指回前面的依据", [])
    if name == "ask_user":
        return ("向你确认一件事", str(args.get("question") or ""), [])
    return (name, "", [])


async def _emit_tool_result(run_id: str, m: ToolMessage) -> None:
    """工具返回 → 补一条事件，带**真实返回**。"""
    content = str(getattr(m, "content", "") or "")
    await emit(run_id, "call_result", {
        "tool_call_id": getattr(m, "tool_call_id", "") or "",
        "text": content[:600],
    })


def _answer_text(run: GiftRun) -> str:
    """用户对上一次提问的回答，转成一句话喂回模型。

    ⚠️ 读的是 `answer_label` / `answer_question`（**存下来的副本**）——
    提问字段在用户点选项时就被清空了。
    """
    label = str(getattr(run, "answer_label", "") or "")
    q = str(getattr(run, "answer_question", "") or "")
    if q and label:
        return f"关于「{q}」，我选：{label}"
    if label:
        return f"我选：{label}"
    return "按你的判断继续。"


def _collect_messages(chunk: dict, history: list[dict]) -> None:
    """把 agent 这一步产出的消息追加进历史（供续跑用）。

    只存**可序列化**的字段（role / content / tool_calls / tool_call_id）——
    LangChain 的 message 对象不能直接进 JSONB。
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
            tc = getattr(m, "tool_calls", None)
            if tc:
                item["tool_calls"] = [
                    {"name": c.get("name"), "args": c.get("args"),
                     "id": c.get("id")}
                    for c in tc
                ]
            tcid = getattr(m, "tool_call_id", None)
            if tcid:
                item["tool_call_id"] = tcid
            history.append(item)


# ══════════════════════════════════════════════════════════════════════
# 交付物：由**工具完成**驱动，而不是节点
# ══════════════════════════════════════════════════════════════════════
# 旧实现按图节点名发交付物事件（`_on_node` 里 if/elif 六个分支）。现在走法
# 由模型定、没有固定节点了，只能按「哪个工具跑完了」来发。
#
# 六份交付物与工具的对应：
#   screen_candidates 跑完 → 候选对比表
#   compose_gift      跑完 → 礼盒方案 + 预算分配
#   write_note        跑完 → 寄语文案 + 货源与配送 + 送礼订单
# 与旧的节点版本一一对应（verify→compare、combine→plan/budget、
# message→message/supply/order），只是触发点从节点换成了工具。
async def _emit_finding(run_id: str, key: str, **kw) -> None:
    """把这一阶段**真实产生**的信息回流到中栏的「推演所得」。

    ⚠️ 与「人物档案」是两类东西，用不同的事件 kind（`finding` 而不是
    `profile`）：前者的主语是收礼人（她喜欢什么），后者的主语是这次推演
    （我们查了什么、排除了什么、怎么搭的）。混用会让前端把它们排进同一组，
    「已知喜好：颈椎按摩仪」看起来就成了她的喜好 —— 那其实是我们的检索词。

    没有真实内容时 `build_run_finding` 返回 None，这里直接不发 ——
    宁可中栏少一块，也不编一块出来。
    """
    f = st.build_run_finding(key, **kw)
    if f:
        await emit(run_id, "finding", f)


async def _after_tool(run_id: str, tool: str, acc: dict,
                       phases: dict | None = None) -> None:
    """工具跑完 → 收尾该阶段、产出交付物与「推演所得」。

    三件事都在这里做，因为它们的数据源相同（工具写进 acc 的产物），
    分成三处会各读一遍、容易漂。
    """
    # ⚠️ **每个工具跑完就收尾它那一步**，而不是等 run 结束。
    # 原先只在换阶段和收尾时关，于是五个步骤的 done 全挤在最后一秒 ——
    # 界面上看不到「这一步做完了」，观感就是「一直在跑、突然全绿」。
    # 实测 83 秒的 run 里，5 个 done 全落在最后 1 秒。
    if phases:
        await _close_phase(run_id, tool, phases)

    await _emit_deliverables_for(run_id, tool, acc)

    # 「推演所得」—— 回流到中栏。与「人物档案」语义分开：前者主语是这次推演
    # （我们查了什么、排除了什么），后者主语是收礼人（她喜欢什么）。
    #
    # ⚠️ `searched` / `excluded` 是**累加型**，只在**这一批全部返回后**发一次。
    # 模型并行搜 3 个词时，三次返回各发一次的话中栏会闪三条「搜过的方向」，
    # 每条都比上一条长（实测就是这个现象）。判据与 `_close_phase` 同一套 ——
    # 都是「还有同批的没回来就等」。
    left = _pending.get(run_id) or {}
    meta = _TOOL_META.get(tool)
    if meta and left.get(meta[0], 0) > 0:
        return   # 同批还有未返回的，等最后一个回来时一起发

    if tool == "read_recipient":
        # ⚠️ 档案必须在这里**发事件 + 落库** —— 旧流程里这是 `_on_node`
        # 的 understand 分支干的事，改成 ReAct 后我漏掉了，后果是中栏五组
        # 全是「尚未读到…」、完整度显示 0/0，而左栏却写着「读到母亲 · 52 岁」
        #（左栏读的是工具返回文本，中栏读的是 profile 事件 —— 两条路）。
        profile = acc.get("profile") or []
        if profile:
            await _patch_run(run_id, profile=profile)
            for g in profile:
                await emit(run_id, "profile", {
                    "key": g["key"], "state": g["state"],
                    "text": g["text"], "note": g.get("note"),
                    "source": g.get("source"),
                })

    elif tool == "search_gifts":
        await _emit_finding(run_id, "searched",
                            keywords=acc.get("searched") or [])
    elif tool == "screen_candidates":
        await _emit_finding(run_id, "excluded",
                            excluded=acc.get("excluded") or [])
    elif tool == "compose_gift":
        await _emit_finding(run_id, "pairing", plan=acc.get("plan") or {})


async def _emit_deliverables_for(run_id: str, tool: str, acc: dict) -> None:
    """某个工具跑完后，产出它对应的交付物。没有内容就不发 —— 不编。"""
    try:
        if tool == "screen_candidates":
            picked = acc.get("picked") or []
            excluded = acc.get("excluded") or []
            if not picked and not excluded:
                return
            await emit(run_id, "deliverable",
                       {"key": "compare", "state": "ready",
                        "data": st.build_compare(picked, excluded)})

        elif tool == "compose_gift":
            plan = acc.get("plan") or {}
            if not plan.get("items"):
                return
            await emit(run_id, "deliverable",
                       {"key": "plan", "state": "ready", "data": plan})
            # 预算分配：礼盒里每件的金额
            rows = [
                {"label": i.get("role") or "一件", "name": i.get("name"),
                 "amount": i.get("price") or 0}
                for i in (plan.get("items") or [])
            ]
            await emit(run_id, "deliverable",
                       {"key": "budget", "state": "ready", "data": rows})

        elif tool == "write_note":
            msg = acc.get("message") or {}
            picked = acc.get("picked") or []
            plan = acc.get("plan") or {}
            if msg:
                await emit(run_id, "deliverable",
                           {"key": "message", "state": "ready", "data": msg})
            supply = st.build_supply(picked, plan)
            if supply:
                await emit(run_id, "deliverable",
                           {"key": "supply", "state": "ready", "data": supply})
            await emit(run_id, "deliverable",
                       {"key": "order", "state": "needs", "data": {}})
    except Exception as e:
        logger.warning(f"[gift] 交付物 {tool} 事件失败（忽略）: {e}")


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
