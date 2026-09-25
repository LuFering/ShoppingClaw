"""送礼推演的状态图。

形态：**单图 + 七步**。

    understand → extract → search → verify → combine → message → END

═══════════════════════════════════════════════════════════════════════
2026-09-25 修正：这张图此前**从未被执行过**
═══════════════════════════════════════════════════════════════════════

初版把图写在这儿，然后在 `gift_service.advance()` 里另写了一个 for 循环
真跑 —— 两份实现，读者会以为跑的是图。现在图是**唯一**的推进路径：
service 只负责订阅图的事件、落库、处理中断，不再自己串流程。

分工：
  · 图          —— 流程定义 + 每一步的判断（节点里真调模型/工具）
  · gift_service —— 订阅 stream、写事件、维护快照、等用户拍板

事件由节点通过 `emit` 回调发出（defer=True 的 run 才需要）；
service 把回调塞进 config，图不认识 DB。
"""
from __future__ import annotations

import logging
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

logger = logging.getLogger(__name__)


def _keep(old, new):
    """列表/字典用「后写覆盖」，允许显式置空。"""
    return new if new is not None else old


class GiftState(TypedDict, total=False):
    # 入口参数
    recipient: str
    occasion: str
    budget: int
    signals: list[str]
    run_id: str
    user_id: str

    # 累积产物
    context: dict          # 读到的档案
    profile: list[dict]    # 中栏五组
    understanding: dict
    picked: list[dict]
    excluded: list[dict]
    plan: dict
    budget_rows: list[dict]
    order: dict
    message: dict
    supply: list[dict]
    compare: list[dict]
    question: dict | None


def build_gift_graph():
    """编译送礼图。

    节点从 config 里取 `emit` 回调（service 注入）。图本身不碰 DB ——
    这样它可以脱离服务单独跑测试，也避免「一次执行写两遍事件」。
    """
    from src.agents.independent.gift import stages as st

    def _emit(config, kind: str, payload: dict) -> None:
        fn = (config or {}).get("configurable", {}).get("emit")
        if callable(fn):
            try:
                fn(kind, payload)
            except Exception as e:  # 事件写失败不该中断推演
                logger.warning(f"[gift] emit 失败（忽略）: {e}")

    async def n_understand(state: GiftState, config=None) -> dict:
        ctx = await st.read_recipient_context(state)
        profile = st.build_profile(state, ctx)
        _emit(config, "profile_batch", {"profile": profile, "ctx": ctx})
        return {"context": ctx, "profile": profile}

    async def n_extract(state: GiftState, config=None) -> dict:
        u = await st.build_understanding(state, state.get("profile") or [], state.get("context") or {})
        _emit(config, "understanding", u)
        return {"understanding": u}

    async def n_search(state: GiftState, config=None) -> dict:
        _emit(config, "deliverable", {"key": "compare", "state": "building"})
        picked = await st.search_candidates(state)
        return {"picked": picked}

    async def n_verify(state: GiftState, config=None) -> dict:
        p, e = st.verify_candidates(state.get("picked") or [], state)
        _emit(config, "deliverable", {"key": "compare", "state": "ready",
                                      "data": st.build_compare(p, e)})
        return {"picked": p, "excluded": e}

    async def n_combine(state: GiftState, config=None) -> dict:
        _emit(config, "deliverable", {"key": "plan", "state": "building"})
        plan, rows, order = await st.combine(
            state.get("picked") or [],
            {**state, "_profile": state.get("profile") or []},
            state.get("understanding") or {},
        )
        _emit(config, "deliverable", {"key": "plan", "state": "ready", "data": plan})
        _emit(config, "deliverable", {"key": "budget", "state": "ready", "data": rows})
        return {"plan": plan, "budget_rows": rows, "order": order}

    async def n_message(state: GiftState, config=None) -> dict:
        _emit(config, "deliverable", {"key": "message", "state": "building"})
        msg = await st.build_message(state, state.get("plan") or {},
                                     state.get("understanding") or {})
        supply = st.build_supply(state.get("picked") or [], state.get("plan") or {})
        _emit(config, "deliverable", {"key": "message", "state": "ready", "data": msg})
        _emit(config, "deliverable", {"key": "supply", "state": "ready", "data": supply})
        _emit(config, "deliverable", {"key": "order", "state": "needs",
                                      "data": state.get("order") or {}})
        return {"message": msg, "supply": supply}

    g = StateGraph(GiftState)
    for name, fn in (
        ("understand", n_understand), ("extract", n_extract),
        ("search", n_search), ("verify", n_verify),
        ("combine", n_combine), ("message", n_message),
    ):
        g.add_node(name, fn)

    g.add_edge(START, "understand")
    for a, b in (
        ("understand", "extract"), ("extract", "search"), ("search", "verify"),
        ("verify", "combine"), ("combine", "message"),
    ):
        g.add_edge(a, b)
    g.add_edge("message", END)
    return g.compile()


_compiled = None


def get_gift_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_gift_graph()
    return _compiled
