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
from src.agents.independent.planning.context import PLANNING_SYSTEM_PROMPT

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
    risks: Annotated[list[str], _merge_lists]
    risks_from_kb: Annotated[bool, _last_wins]
    question: Annotated[dict | None, _last_wins]

    # ⚠️ 2026-09-27：`selected`（单件）换成 `plan`（整套）。
    #
    # 原先一次采购只能定下**一件**商品，因为 `make_decision(picked, ...)`
    # 收的是单数。这对「买一台洗地机」没问题，对「搬家买家具」则是错的 ——
    # 实测一次 run 里模型算了整套 5 件的账（¥11163，占预算 93%），
    # 却只能交出一件（床 ¥3401），于是预算表显示「占 28%」，
    # 和它自己写的理由差了 3 倍。**是工具签名在逼模型迁就一个错误的接口。**
    #
    # `plan` 的形状：
    #   {"items": [{name, item_id, price_yuan, quantity,
    #               quantity_basis, subtotal, why}],
    #    "why": "整套的取舍逻辑", "by": "llm", "total": 11163.0}
    plan: Annotated[dict | None, _last_wins]


def build_planning_agent():
    """编译采购规划 agent（ReAct 循环）。

    `create_agent` 返回的就是个已编译的图：model ↔ tools 之间用条件边
    循环，模型不再产生 tool_calls 时走向 END。
    """
    from pathlib import Path

    from src.agents.common.backends import (
        CompositeBackend,
        FilesystemBackend,
        ReadOnlyBackend,
        StateBackend,
    )
    from src.agents.common.middleware.filesystem import FilesystemMiddleware
    from src.agents.common.middleware.skills import SkillsMiddleware
    from src.agents.independent.common_llm import get_model
    from src.agents.independent.planning.tools import PLANNING_TOOLS

    skills_dir = Path(__file__).parent / "skills"

    def _fs_backend(runtime):
        # 技能目录(/skills/) → 真实磁盘；其余(工具结果卸载等) → 虚拟状态，避免写进源码目录
        return CompositeBackend(
            default=StateBackend(runtime),
            routes={
                # 技能目录只读：防止模型（或被注入的第三方数据）改写源码里的 SKILL.md
                "/skills/": ReadOnlyBackend(
                    FilesystemBackend(root_dir=str(skills_dir), virtual_mode=True)
                ),
            },
        )

    return create_agent(
        get_model(),
        tools=PLANNING_TOOLS,
        system_prompt=PLANNING_SYSTEM_PROMPT,
        state_schema=PlanningState,
        middleware=[
            FilesystemMiddleware(backend=_fs_backend),                    # 文件工具在前（对齐 mainagent 约定）
            SkillsMiddleware(backend=_fs_backend, sources=["/skills/"]),  # 技能清单在后
        ],
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
