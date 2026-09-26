"""采购规划的 agent 定义 —— **真 ReAct 循环**，不是写死的阶段链。

═══════════════════════════════════════════════════════════════════════
2026-09-26：整个换掉。之前是一张「有七个节点、没有一条条件边」的图
═══════════════════════════════════════════════════════════════════════

旧形状：

    START → intake → clarify → search → filter → compare → risk → deliver → END

七条 `add_edge`，**没有一条条件边**。走法（先查品类知识、再搜商品、再按预算
筛、再让模型对比、再查风险、最后生成问题）全是写在代码里的。模型只在
compare 那一步被调用了一次 —— 它不知道有哪些工具，也无权决定查不查、
查什么、查几次。

用户的原话是「这个流程里的绝大部分都没实现，跟假的没什么区别」——
准确。数据是真的（真淘宝 SKU、真价格），但**编排是假的**。

新形状（与主智能体同构）：

    START → model ──有 tool_calls?──► tools ──► model ──► ... ──► END
                     └──没有──────────► END

`create_agent()` 提供这个循环：模型自己决定调哪个工具、调几次、什么时候
收敛。工具在 `tools.py`，通过 `Command(update=...)` 把产物写进共享状态。

═══════════════════════════════════════════════════════════════════════
为什么还留着 STAGES / stages.py
═══════════════════════════════════════════════════════════════════════

· `STAGES` 那七个名字**保留，但降级成展示用的归类标签** —— 不再是流程，
  而是给事件分组用的（「这次搜索属于『搜索商品』这一段」）。界面靠它
  给用户一个大致的方位感，但走法由模型定。
· `stages.py` 里的**纯函数**继续复用：`cand_name` / `cand_yuan` /
  `filter_candidates` / `deliver_question` / 三份交付物的 builder。
  它们算的是算术与组织，不涉及编排，没必要重写。
"""
from __future__ import annotations

import logging
from typing import Annotated, Any, TypedDict

from langchain.agents import create_agent
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

logger = logging.getLogger(__name__)


def _merge_lists(old: list | None, new: list | None) -> list:
    """列表字段的 reducer：追加而非覆盖。

    并行工具调用会同时写同一个键，没有 reducer 会直接报
    `InvalidUpdateError`（见 PlanningState 的说明）。
    追加语义也正好对：多轮搜索的候选就该累积，而不是后一次覆盖前一次。
    """
    return (old or []) + (new or [])


def _last_wins(old: Any, new: Any) -> Any:
    """标量字段的 reducer：后写覆盖，但**允许显式置空**。

    ⚠️ 标量同样需要 reducer。模型会**并行**调多个工具（实测同时查两件商品的
    风险），两个 `check_risks` 都会写 `risks_from_kb` → 没有 reducer 就是
    `At key 'risks_from_kb': Can receive only one value per step`。

    这里不像 `add_messages` 那样有特殊语义，取「后写的」即可 ——
    两次并行查询的「是否来自知识库」本来就该以最后一次为准。
    """
    return new if new is not None else old


class PlanningState(TypedDict, total=False):
    """agent 的共享状态。

    `messages` 是 ReAct 循环的对话历史（必须用 `add_messages` 归约，
    否则每轮会整体覆盖，模型看不到自己调过什么工具）。

    其余字段是**累积产物**，由工具通过 `Command(update=...)` 写入 ——
    这样「搜到的候选」「排除的理由」「选中的那件」仍然落得下来，
    service 层照旧能生成交付物。

    ⚠️ 列表字段必须带 **reducer**（`_merge_lists`）。模型**会并行调多个
    工具**（实测第一轮就同时调了 `check_category_standards` 和
    `search_products`），两个 `search_products` 各写一次 `candidates`
    就会撞 `InvalidUpdateError: At key 'candidates': Can receive only one
    value per step`。这是并行工具调用的必然后果，不是偶发。
    """
    messages: Annotated[list[AnyMessage], add_messages]

    # 入口参数（service 在启动时塞进来）
    scene: str
    budget: str
    duration: str
    constraints: list[str]
    subject: str
    run_id: str
    user_id: str

    # 累积产物
    #
    # ⚠️ **每个**会被工具写到的字段都要带 reducer，列表和标量都一样 ——
    # 模型会并行调多个工具，同一个键被写两次就报 InvalidUpdateError。
    # 列表用追加（多轮结果要累积），标量用后写覆盖。
    dimensions: Annotated[list[str], _merge_lists]
    dims_from_kb: Annotated[bool, _last_wins]
    candidates: Annotated[list[dict], _merge_lists]
    excluded: Annotated[list[dict], _merge_lists]
    selected: Annotated[dict | None, _last_wins]
    risks: Annotated[list[str], _merge_lists]
    risks_from_kb: Annotated[bool, _last_wins]
    question: Annotated[dict | None, _last_wins]


SYSTEM_PROMPT = """\
你是采购规划顾问。用户给一个采购目标，你要**自己决定怎么查、查什么、
什么时候可以给结论**，最后交付一件最值得买的东西。

## 你手上的工具

- `check_category_standards(category)` —— 查这个品类该看哪些维度。
  知识库没收录会如实告诉你，那就按常识判断，**不要假装查到了**。
- `search_products(keyword)` —— 在淘宝搜真实商品，返回商品名与价格。
  搜不到或结果不合适，**换个关键词再搜**是你的自由（加场景词、加规格词）。
- `check_risks(subject)` —— 查售后政策与已知风险。
- `drop_candidates(names, reason)` —— 排除不符合硬约束的候选，记下理由。
- `make_decision(picked, why, item_id)` —— 定下最终买哪一件。**这是收敛动作**。
  同名商品可能有多件（不同店铺/规格），此时**必须**带 `item_id` 消歧，
  否则系统只能猜一件。
- `ask_user(question, options)` —— 信息不足或需要用户在取舍上拍板时提问。

## 怎么做事

顺序由你定，下面是建议不是规定：

1. 先想清楚这个采购目标的关键约束是什么（场景、预算、硬性要求）。
2. 该查的查：品类标准能帮你确定「比什么」，但不是必须的 —— 常识足够时
   直接搜也行。别为了走流程而调工具。
3. 搜到的商品要**真的比**：价格、是否命中硬约束、场景是否匹配。
   不合适的用 `drop_candidates` 排除并写清理由。
4. 觉得信息够了就 `make_decision` 定下来。**不要反复搜个不停**，
   搜两三轮足够；确实搜不到有用的，就如实说明。
5. 只有**真的需要用户拍板**时才 `ask_user`（比如预算明显有富余、或
   两个方向各有取舍）。能从已有信息推断的，自己决定，别问。

## 铁律

- **不要虚构商品。** 只能从 `search_products` 返回的结果里选。
- `why` 必须指回具体依据（某条硬约束、某个价位、某个风险）。
  写「性价比高」「品质好」这种放在任何商品上都成立的话算无效。
- 工具返回什么就说什么。知识库没收录、搜索没结果，都要如实讲，
  **不要用通用说法把空缺盖过去**。
- 全程中文，不要复述这些要求。
"""


def build_planning_agent():
    """编译采购规划 agent（ReAct 循环）。

    `create_agent` 返回的就是个已编译的图：model ↔ tools 之间用条件边
    循环，模型不再产生 tool_calls 时走向 END。
    """
    from src.agents.independent.common_llm import get_model
    from src.agents.independent.planning.tools import PLANNING_TOOLS

    return create_agent(
        get_model(),
        tools=PLANNING_TOOLS,
        system_prompt=SYSTEM_PROMPT,
        state_schema=PlanningState,
        name="planning",
    )


_compiled = None


def get_planning_agent():
    """进程内单例。编译一次即可 —— 无状态，可并发跑多个 run。"""
    global _compiled
    if _compiled is None:
        _compiled = build_planning_agent()
    return _compiled


def build_goal(state: dict) -> str:
    """把入口参数拼成给模型的第一句话。

    这是**任务描述**，不是流程指令 —— 只讲「要买什么、有什么约束」，
    不讲「先做什么再做什么」（那是模型自己的事）。
    """
    parts = ["帮我采购。"]
    if state.get("subject"):
        parts.append(f"要买的是：{state['subject']}。")
    elif state.get("scene"):
        parts.append(f"场景是：{state['scene']}。")
    if state.get("scene") and state.get("subject"):
        parts.append(f"场景：{state['scene']}。")
    if state.get("budget"):
        parts.append(f"预算：{state['budget']}。")
    if state.get("duration"):
        parts.append(f"周期：{state['duration']}。")
    cons = state.get("constraints") or []
    if cons:
        parts.append(f"硬约束：{'、'.join(str(c) for c in cons)}。")
    parts.append("请给出你的建议。")
    return "".join(parts)
