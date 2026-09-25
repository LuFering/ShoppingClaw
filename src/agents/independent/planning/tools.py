"""采购规划 agent 的工具集 —— **模型自己决定调哪个、调几次**。

═══════════════════════════════════════════════════════════════════════
2026-09-26：从「七个写死的阶段」改成「一组工具 + 真 ReAct 循环」
═══════════════════════════════════════════════════════════════════════

之前是这个形状：

    START → intake → clarify → search → filter → compare → risk → deliver → END

七条 `add_edge`，**一条条件边都没有**。也就是说「先查品类知识、再搜商品、
再按预算筛、再让模型对比」这个顺序是写在代码里的，模型只被调用了一次
（compare 那一步）。数据是真的（真淘宝 SKU、真价格），但**推理是假的** ——
模型不知道有哪些工具可用，也无权决定要不要查、查什么、查几次。

主智能体不是这样的：它是 `create_agent()` 起的真 ReAct 循环，模型自己决定
调哪个工具、什么时候收敛。差距就在这里。

现在改成同样的形状：

    model ──条件边──► tools ──条件边──► model ──► ... ──► END

每个工具是 `@tool`，模型在 system prompt 里看到说明后自己编排。工具通过
返回 `Command(update={...})` 把产物写进共享状态 —— 这样「搜到的候选」
「排除的理由」「选中的那件」仍然会累积，service 层照旧能落库、能生成交付物。

工具本身**不做事件写入**（那是 service 的职责）：service 从每次工具调用里
生成事件，带上真实入参和真实返回。

═══════════════════════════════════════════════════════════════════════
两个实现上的硬约束（都踩过）
═══════════════════════════════════════════════════════════════════════

1. **工具必须回一条 `ToolMessage`，且带上 `tool_call_id`。**
   返回 `Command` 的工具如果不带匹配的 ToolMessage，LangGraph 会报
   「Every tool call MUST have a corresponding ToolMessage」直接失败。
   `tool_call_id` 靠 `Annotated[str, InjectedToolCallId]` 注入 ——
   注意它在 `langchain_core.tools`，**不在** `langgraph.prebuilt`。

2. **不能自己造 message role。** 一开始我写了 `{"role": "tool_result_note"}`，
   想给模型一段「给人看的说明」，结果 `convert_to_messages` 直接
   `ValueError: Unexpected message type`。只认 human/ai/system/tool 那几种。
"""
from __future__ import annotations

import logging
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

logger = logging.getLogger(__name__)


def _note(text: str, tool_call_id: str) -> ToolMessage:
    """工具给模型的回话。必须带 tool_call_id，否则 LangGraph 配对失败。"""
    return ToolMessage(content=text, tool_call_id=tool_call_id)


# ══════════════════════════════════════════════════════════════
# 取数类工具
# ══════════════════════════════════════════════════════════════

@tool
async def check_category_standards(
    category: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """查这个品类的选购标准：该看哪些维度、行业公认的判据。

    需要知道「买这类东西应该比什么」时调用。知识库没收录会如实告诉你是空的
    —— 那就按常识判断，不要假装查到了。

    Args:
        category: 品类名，如「隔音材料」「洗地机」
    """
    from src.agents.independent.planning import stages as st

    dims, from_kb = await st.retrieve_dimensions(category)
    body = f"评估维度：{'、'.join(dims)}\n" + (
        "（来自知识库）" if from_kb
        else "（知识库未收录这个品类，以上是通用维度 —— 请按常识判断，不要当作专业依据）"
    )
    return Command(update={
        "dimensions": dims,
        "dims_from_kb": from_kb,
        "messages": [_note(body, tool_call_id)],
    })


@tool
async def search_products(
    keyword: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """在淘宝搜真实商品，返回商品名与价格。

    搜不到或结果不合适时，**换个关键词再搜**是你的自由 —— 加场景词、加规格词。
    不要一次搜不到就放弃。

    Args:
        keyword: 搜索关键词。用**品类词**，不要用「礼物」「推荐」这类词
    """
    from src.agents.independent.planning import stages as st

    found = await st.search_candidates(_to_stage_state(state), keyword=keyword)

    if found:
        lines = []
        for c in found[:5]:
            p = st.cand_yuan(c)
            lines.append(f"- {st.cand_name(c)}" + (f" ¥{p:g}" if p is not None else ""))
        body = f"关键词「{keyword}」返回 {len(found)} 件：\n" + "\n".join(lines)
    else:
        body = f"关键词「{keyword}」没有返回结果，换个词试试"

    # 只交**本次**搜到的：state 的 candidates 带 reducer（追加），
    # 这里再合并一遍会让结果翻倍。去重交给 reducer 之后的读取方
    # （`_state_from_run` 与交付物 builder 都按 item_id/名字去过重）。
    return Command(update={
        "candidates": found,
        "messages": [_note(body, tool_call_id)],
    })


@tool
async def check_risks(
    subject: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """查这类东西的售后政策与已知风险（退换、保修、质量缺陷、长期成本）。

    知识库没收录时会如实说明，此时应基于常识提示风险，并说明是常识判断。

    Args:
        subject: 商品或品类名
    """
    from src.agents.independent.planning import stages as st

    risks, from_kb = await st.retrieve_risks(subject)
    body = f"风险项：{'、'.join(risks)}\n" + (
        "（来自知识库）" if from_kb else "（知识库未收录，以上是通用提示）"
    )
    return Command(update={
        "risks": risks,
        "risks_from_kb": from_kb,
        "messages": [_note(body, tool_call_id)],
    })


# ══════════════════════════════════════════════════════════════
# 判断类工具
# ══════════════════════════════════════════════════════════════

@tool
def drop_candidates(
    names: Annotated[list[str], "要排除的商品名（必须与搜索结果里的名字一致）"],
    reason: Annotated[str, "排除理由，要具体（哪条硬约束不满足）"],
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """把不符合硬约束的候选排除掉，并记下理由。

    排除的项**不会从图上消失**，会标上理由保留 —— 用户要能看到
    「这些被排除了、为什么」。理由要写具体，不要写「不合适」。

    Args:
        names: 要排除的商品名列表
        reason: 排除理由
    """
    from src.agents.independent.planning import stages as st

    cands = state.get("candidates") or []
    by_name = {st.cand_name(c): c for c in cands}
    dropped = [
        {**by_name[n], "_reason": reason}
        for n in names if n in by_name
    ]

    # 名字对不上要如实说 —— 不能让模型以为排除了、实际没动
    missed = [n for n in names if n not in by_name]
    body = f"已排除 {len(dropped)} 件：{reason}"
    if missed:
        body += f"\n⚠️ 这些名字没在候选里找到，未生效：{missed[:3]}"

    # ⚠️ 只写**被排除的**，不动 candidates —— 两个字段都带 reducer（追加），
    # 回写「保留下来的全部」会让候选每排除一次就翻一倍。
    # 「候选里哪些还留着」由读取端按 excluded 里的名字过滤得出
    # （见 `_to_stage_state`）。
    return Command(update={
        "excluded": dropped,
        "messages": [_note(body, tool_call_id)],
    })


@tool
def make_decision(
    picked: Annotated[str, "选中的商品名（必须与候选里的名字完全一致）"],
    why: Annotated[str, "为什么是它。要指回具体依据：某条硬约束、某个价位、某个风险"],
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """定下最终买哪一件，并说明理由。

    **这是收敛动作**：调完之后应当准备给用户交代，不要再搜新商品。
    理由必须指回具体依据，写「性价比高」「品质好」这种放在任何商品上都
    成立的话算无效。

    Args:
        picked: 选中的商品名
        why: 选它的理由
    """
    from src.agents.independent.planning import stages as st

    pool = (state.get("candidates") or []) + (state.get("excluded") or [])
    hit = next((c for c in pool if st.cand_name(c) == picked), None)
    if hit is None:
        return Command(update={
            "messages": [_note(
                f"⚠️ 候选里没有叫「{picked}」的商品，请用搜索结果里的原名。",
                tool_call_id,
            )],
        })

    price = st.cand_yuan(hit)
    # ⚠️ 把**价格一起存进 selected**。交付物的预算表要算「花了多少」，
    # 而收尾时只能从落库的 products 读 —— 只存 name/why 的话预算永远是 0
    # （实测踩过：预算分配表显示「本次花费 ¥0」，而实际选中了 ¥165 的东西）。
    return Command(update={
        "selected": {
            "name": picked,
            "why": why,
            "by": "llm",
            "price_yuan": price,
            "item_id": hit.get("item_id"),
        },
        "messages": [_note(
            f"已定：{picked}" + (f"（¥{price:g}）" if price is not None else "")
            + f"\n理由：{why}",
            tool_call_id,
        )],
    })


@tool
def ask_user(
    question: Annotated[str, "要问用户的问题。要具体，基于你这次实际拿到的结果"],
    options: Annotated[list[str], "2~4 个选项，让用户能一键回答"],
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """当信息不足以继续、或需要用户在取舍上拍板时，向用户提问。

    问之前先想清楚：这个问题是不是必须用户回答？能从已有信息推断的就别问。
    问题要基于你**这次实际拿到的结果**（比如「有 2 件因超预算被排除了，
    要把预算放宽到 ¥315 吗」），不要问放之四海皆准的话。

    Args:
        question: 问题文本
        options: 候选答案
    """
    return Command(update={
        "question": {
            "text": question,
            "options": [
                {"key": f"opt{i}", "label": str(o), "primary": i == 0}
                for i, o in enumerate(options or [])
            ],
        },
        "messages": [_note("已向用户提问，等待回答。", tool_call_id)],
    })


# ══════════════════════════════════════════════════════════════
# 辅助
# ══════════════════════════════════════════════════════════════

def _to_stage_state(state: dict) -> dict:
    """把 agent 的 state 转成 stages 纯函数期望的形状。

    ═══════════════════════════════════════════════════════════════════
    两处必须在这里收口（因为 state 的列表字段是**追加**语义）
    ═══════════════════════════════════════════════════════════════════

    1. **去重**：模型会多轮搜索、还会并行搜，同一个商品可能出现多次。
       reducer 只负责追加，不管重复。
    2. **剔除已排除的**：`drop_candidates` 只往 `excluded` 里追加，
       不回头改 `candidates`（改了会让候选翻倍）。所以「还留着的候选」
       要在这里按名字差集算出来。

    stages 里的纯函数（filter_candidates / 交付物 builder）拿到的是
    收口后的干净数据，不必各自再处理这两件事。
    """
    from src.agents.independent.planning import stages as st

    seen, cands = set(), []
    for c in state.get("candidates") or []:
        key = str(c.get("item_id") or st.cand_name(c))
        if key in seen:
            continue
        seen.add(key)
        cands.append(c)

    excluded = list(state.get("excluded") or [])
    out_names = {st.cand_name(e) for e in excluded}
    cands = [c for c in cands if st.cand_name(c) not in out_names]

    return {
        "scene": state.get("scene") or "",
        "budget": state.get("budget") or "",
        "duration": state.get("duration") or "",
        "constraints": state.get("constraints") or [],
        "subject": state.get("subject") or "",
        "candidates": cands,
        "excluded": excluded,
        "selected": state.get("selected") or {},
        "risks": state.get("risks") or [],
        "dimensions": state.get("dimensions") or [],
        "run_id": state.get("run_id") or "",
        "user_id": state.get("user_id") or "",
    }


PLANNING_TOOLS = [
    check_category_standards,
    search_products,
    check_risks,
    drop_candidates,
    make_decision,
    ask_user,
]
