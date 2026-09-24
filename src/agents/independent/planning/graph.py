"""采购规划的状态图。

形态：**单图 + 阶段**（方案 §3.5 定稿）。

    intake → clarify → search → filter → compare → risk → deliver → END

设计取舍：
  · **不用 LLM 分诊**：阶段顺序是业务决定的（先搜才能筛，先比才能排风险），
    让模型每轮猜下一个阶段既慢又会跑偏。编排这层由代码定，
    模型只在阶段内部做判断（取舍、措辞、风险分级）。
  · **不在图里 interrupt**：阶段推进由 planning_service 在后台任务里跑，
    用户拍板是 HTTP 请求打进来的（POST /answer），两者不在同一次调用里。
    用 LangGraph 的 interrupt 需要长连接挂住整个 run —— 工作台刷新一次就断了。
    所以「停下来等用户」落在 run.status=awaiting 上，服务层据此中断循环。

这个文件目前是**声明式骨架**：节点函数直接复用 stages.py 的实现
（与 planning_service._invoke_stage 同一套），保证「图描述的流程」与
「服务层跑的流程」不会分叉成两份。
"""
from __future__ import annotations

import logging
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

logger = logging.getLogger(__name__)


class PlanningState(TypedDict, total=False):
    """图的状态。

    total=False：阶段是逐步填的，不要求每个节点都返回全部字段。
    """
    # 入口参数
    scene: str
    budget: str
    duration: str
    constraints: list[str]
    subject: str
    run_id: str
    user_id: str

    # 累积产物
    needs: list[dict]
    dimensions: list[str]
    candidates: list[dict]
    selected: dict | None
    risks: list[str]
    question: dict | None


def _merge_list(old: list | None, new: list | None) -> list:
    """列表字段的 reducer：追加而非覆盖（多个阶段都会往 candidates 里写）。"""
    return (old or []) + (new or [])


def _merge_questions(old, new):
    """question 用「后写覆盖」，且允许显式置空（None）。"""
    return new if new is not None else old


def build_planning_graph():
    """编译采购规划的图。

    注意：节点内**不做事件写入**（那是 service 的职责），只算状态。
    这样图可以脱离 DB 单独测试，也避免「一次执行写两遍事件」。
    """
    from src.agents.independent.planning import stages as st

    async def n_intake(state: PlanningState) -> dict:
        return {"needs": st.build_needs(state)}

    async def n_clarify(state: PlanningState) -> dict:
        return {"dimensions": await st.retrieve_dimensions(state.get("subject") or state.get("scene") or "商品")}

    async def n_search(state: PlanningState) -> dict:
        return {"candidates": await st.search_candidates(state)}

    async def n_filter(state: PlanningState) -> dict:
        # 本轮不真过滤（需 LLM 判断），原样透传以保持图与阶段数一致
        return {"candidates": state.get("candidates") or []}

    async def n_compare(state: PlanningState) -> dict:
        return {"selected": st.pick_best(state.get("candidates") or [])}

    async def n_risk(state: PlanningState) -> dict:
        return {"risks": await st.retrieve_risks(state.get("subject") or state.get("scene") or "商品")}

    async def n_deliver(state: PlanningState) -> dict:
        return {"question": st.deliver_question(state)}

    g = StateGraph(PlanningState)
    g.add_node("intake", n_intake)
    g.add_node("clarify", n_clarify)
    g.add_node("search", n_search)
    g.add_node("filter", n_filter)
    g.add_node("compare", n_compare)
    g.add_node("risk", n_risk)
    g.add_node("deliver", n_deliver)

    g.add_edge(START, "intake")
    for a, b in (
        ("intake", "clarify"),
        ("clarify", "search"),
        ("search", "filter"),
        ("filter", "compare"),
        ("compare", "risk"),
        ("risk", "deliver"),
    ):
        g.add_edge(a, b)
    g.add_edge("deliver", END)
    return g.compile()


_compiled = None


def get_planning_graph():
    """进程内单例。编译一次即可 —— 无状态，可并发跑多个 run。"""
    global _compiled
    if _compiled is None:
        _compiled = build_planning_graph()
    return _compiled
