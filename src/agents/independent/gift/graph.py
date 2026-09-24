"""送礼推演的状态图。

形态：**单图 + 七步**（与 planning 同一套骨架，阶段内容不同）。

    understand → extract → search → verify → combine → message → END
                                                 (exclude 与 verify 同批算)

设计取舍与 planning 一致：不用 LLM 分诊（步骤顺序由送礼这件事本身决定），
不在图里 interrupt（推演在后台跑，用户拍板走 HTTP 打进来）。

本文件是**声明式骨架**：节点函数复用 stages.py 的纯函数，
与 service 的推进共用同一份逻辑，不会分叉成两份实现。
"""
from __future__ import annotations

import logging
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

logger = logging.getLogger(__name__)


class GiftState(TypedDict, total=False):
    recipient: str
    occasion: str
    budget: int
    signals: list[str]
    run_id: str
    user_id: str

    profile: list[dict]
    understanding: dict
    picked: list[dict]
    excluded: list[dict]
    plan: dict


def _keep(old, new):
    """列表/字典用「后写覆盖」，允许显式置空。"""
    return new if new is not None else old


def build_gift_graph():
    from src.agents.independent.gift import stages as st

    async def n_understand(state: GiftState) -> dict:
        return {"profile": st.build_profile(state, await st.read_recipient_context(state))}

    async def n_extract(state: GiftState) -> dict:
        return {"understanding": st.build_understanding(state, state.get("profile") or [])}

    async def n_search(state: GiftState) -> dict:
        return {"picked": await st.search_candidates(state)}

    async def n_verify(state: GiftState) -> dict:
        picked, excluded = st.verify_candidates(state.get("picked") or [], state)
        return {"picked": picked, "excluded": excluded}

    async def n_combine(state: GiftState) -> dict:
        plan, _rows, _order = st.combine(state.get("picked") or [], state)
        return {"plan": plan}

    async def n_message(state: GiftState) -> dict:
        # 寄语依赖 combine 的产物；本轮只做存在性占位，正文由 service 生成
        return {}

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
