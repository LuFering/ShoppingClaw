"""送礼规划的 agent 定义 —— **真 ReAct 循环**，不是写死的节点链。

═══════════════════════════════════════════════════════════════════════
2026-09-27：整个换掉。之前是一张「有六个节点、没有一条条件边」的图
═══════════════════════════════════════════════════════════════════════

用户的原话：「我感觉这个执行流是不是有点假了，为什么会执行这么快」。

量下来确实如此。旧形状：

    START → understand → extract → search → verify → combine → message → END

六条 `add_edge`，**没有一条条件边**。而且六步里**只有三处调模型**
（`build_understanding` / `combine` / `build_message`），另外三步是纯代码：

    read_history / read_preferences   一次查表
    search_candidates                 一次 HTTP 检索
    verify_candidates                 一次 for 循环比价

实测前四个阶段总共 **4.8 秒**（检索 0.8s、比价 0.02s）—— 那不是效率高，
是**一半的步骤压根没有智能**。

新形状（与规划智能体同构）：

    START → model ──有 tool_calls?──► tools ──► model ──► ... ──► END
                     └──没有──────────► END

`create_agent()` 提供这个循环：模型自己决定调哪个工具、调几次、什么时候
收敛。工具在 `tools.py`，通过 `Command(update=...)` 把产物写进共享状态。

═══════════════════════════════════════════════════════════════════════
一处与规划不同的地方：**零幻觉红线更硬**
═══════════════════════════════════════════════════════════════════════

送礼场景编错代价最高 —— 编一个「她喜欢香水」而实际过敏，这份礼物就废了。
所以提示词里反复强调：读不到档案就如实说没有、不要假装了解对方；
只能从搜索结果里挑商品，不许虚构。

（旧流程里这条红线靠代码保证；改成模型自主后，只能靠提示词 + 工具的
如实回报。工具会把「没找到」原样告诉模型，让它自己纠正。）
"""
from __future__ import annotations

import logging
from typing import Annotated, Any, TypedDict

from langchain.agents import create_agent
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from src.agents.independent.gift.context import GIFT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def _merge_lists(old: list | None, new: list | None) -> list:
    """列表字段的 reducer：追加而非覆盖。

    模型会**并行调多个工具**，没有 reducer 会直接报 `InvalidUpdateError`。
    追加语义也正好对：多轮搜索的候选就该累积。
    """
    return (old or []) + (new or [])


def _last_wins(old: Any, new: Any) -> Any:
    """标量字段的 reducer：后写覆盖，但**允许显式置空**。

    ⚠️ 标量同样需要 reducer。模型会并行调工具，两个工具都写同一个标量键
    就会报 `At key 'plan': Can receive only one value per step`。
    """
    return new if new is not None else old


# ⚠️ `profile` 在 state 里存的是 **op 日志**，不是条目列表。
#
# 2026-09-28 的一轮弯路值得记下来：为了让 update/drop 能表达，先把
# reducer 换成「整表替换」，让工具自己算全量列表再写回。结果自测抓到
# 真 bug —— 模型**并行**调两次 write_profile 时（实测同一条消息里两个
# call），两次都基于同一份旧 state 算 id，后写的把先写的**整个丢掉**。
# id 实证：p2 先被写成「送礼往来」，随后被并行那次顶成「行情锚点」，
# 整条送礼往来消失，而且没有任何 drop 事件。
#
# 现在改成「追加 op + 折叠」（见 stages.fold_profile）：
#   · 工具只 `Command(update={"profile": [一条 op]})`
#   · reducer 用 _merge_lists（追加）—— 并行各追加各的，**不会互相覆盖**
#   · 当前档案由 fold_profile(ops) 纯函数折出，确定性、可重放
#
# 三个词别混：state 里是 **ops**，折出来的是 **entries**，前端看到的是
# 差集事件（add/update/drop）。


class GiftState(TypedDict, total=False):
    """agent 的共享状态。

    ⚠️ **每个**会被工具写到的字段都要带 reducer，列表和标量都一样 ——
    模型会并行调多个工具，同一个键被写两次就报 `InvalidUpdateError`。
    """
    messages: Annotated[list[AnyMessage], add_messages]

    # 入口参数（service 在启动时塞进来）
    recipient: str
    occasion: str
    budget: int
    signals: list[str]
    run_id: str
    user_id: str

    # 累积产物
    context: Annotated[dict, _last_wins]        # 读到的档案
    # 中栏档案的 **op 日志**（不是条目列表！）—— 见上面那段说明。
    # 追加语义是必须的：并行调用不能互相覆盖。当前值 = fold_profile(它)。
    profile: Annotated[list[dict], _merge_lists]
    understanding: Annotated[dict, _last_wins]  # 当前理解
    picked: Annotated[list[dict], _merge_lists]   # 搜到的候选
    excluded: Annotated[list[dict], _merge_lists]  # 排除的候选（带理由）
    searched: Annotated[list[str], _merge_lists]  # 搜过的关键词
    plan: Annotated[dict, _last_wins]           # 组好的礼盒
    message: Annotated[dict, _last_wins]        # 寄语
    question: Annotated[dict | None, _last_wins]


def build_gift_agent():
    """编译送礼 agent（ReAct 循环）。

    `create_agent` 返回的就是个已编译的图：model ↔ tools 之间用条件边
    循环，模型不再产生 tool_calls 时走向 END。
    """
    from src.agents.independent.common_llm import get_model
    from src.agents.independent.gift.tools import GIFT_TOOLS

    return create_agent(
        get_model(),
        tools=GIFT_TOOLS,
        system_prompt=GIFT_SYSTEM_PROMPT,
        state_schema=GiftState,
        name="gift",
    )


_compiled = None


def get_gift_agent():
    """进程内单例。编译一次即可 —— 无状态，可并发跑多个 run。"""
    global _compiled
    if _compiled is None:
        _compiled = build_gift_agent()
    return _compiled


# ══════════════════════════════════════════════════════════════════════
# 兼容旧名
# ══════════════════════════════════════════════════════════════════════
# `get_gift_graph` 是改 ReAct 之前的入口名，有两处调用方：
#   · gift_service.advance（推演主路径）
#   · gift/agent.py（BaseAgent 的 get_graph）
# 保留这个别名，两处都不用改 —— 减少一次改动就少一次出错的機會。
# 名字里的 "graph" 现在其实是个已编译的 ReAct agent，但**不改名**：
# 改名的收益只是措辞好看，代价是同时动两处调用点。
get_gift_graph = get_gift_agent


def build_goal(state: dict) -> str:
    """把入口参数拼成给模型的第一句话。

    这是**任务描述**，不是流程指令 —— 只讲「送给谁、什么场合、多少预算」，
    不讲「先做什么再做什么」（那是模型自己的事）。
    """
    parts = ["帮我挑一份礼物。"]
    if state.get("recipient"):
        parts.append(f"送给：{state['recipient']}。")
    if state.get("occasion"):
        parts.append(f"场合：{state['occasion']}。")
    if state.get("budget"):
        parts.append(f"预算：¥{state['budget']}。")
    signals = state.get("signals") or []
    if signals:
        parts.append(f"用户更在意：{'、'.join(str(s) for s in signals)}。")
    parts.append("请给出你的建议。")
    return "".join(parts)
