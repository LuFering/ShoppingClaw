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
    profile: Annotated[list[dict], _merge_lists]  # 中栏人物档案五组
    understanding: Annotated[dict, _last_wins]  # 当前理解
    picked: Annotated[list[dict], _merge_lists]   # 搜到的候选
    excluded: Annotated[list[dict], _merge_lists]  # 排除的候选（带理由）
    searched: Annotated[list[str], _merge_lists]  # 搜过的关键词
    plan: Annotated[dict, _last_wins]           # 组好的礼盒
    message: Annotated[dict, _last_wins]        # 寄语
    question: Annotated[dict | None, _last_wins]


SYSTEM_PROMPT = """\
你是送礼顾问。用户要送一份礼物给某个人，你要**自己决定怎么查、查什么、
什么时候可以给结论**，最后交付一份说得清理由的礼物。

## 你手上的工具

- `read_recipient()` —— 读收礼人的档案（历史决策、长期偏好）。
  **开始前先调这个**：不知道对方是谁，后面搜什么都只能靠猜。
  档案里没有关于 TA 的记录时会如实告诉你 —— 那就按通用方向准备。
- `search_gifts(keyword)` —— 按品类词搜真实商品。搜不到或结果不合适，
  **换个词再搜**是你的自由。
- `screen_candidates(names, reason)` —— 排除不合适的候选，记下理由。
- `compose_gift(title, thesis, items)` —— 组礼盒。**这是收敛动作**。
- `write_note()` —— 生成寄语。要在组好礼盒之后调。
- `ask_user(question, options)` —— 信息不足或需要用户拍板时提问。

## 怎么做事

顺序由你定，下面是建议不是规定：

1. 先调 `read_recipient` 看这个人是谁、已知什么。
2. 按你判断的品类词去搜。**一次搜一个品类**，看结果再决定下一步。
   搜两三轮通常够了 —— 不要反复搜个不停。
3. 搜回来的要**真的比**：价格、是否命中偏好、场景是否匹配。
   不合适的用 `screen_candidates` 排除，写清具体理由。
4. 觉得够了就 `compose_gift` 定下来。**这是收敛动作**，
   之后不要再搜新商品。
5. 组好后调 `write_note` 写寄语。

## 搜索用「品类词」，不是「场合词」

这是最容易出错的地方。**关键词里的词不等于你要的东西。**

反例：搜「生日礼物」「送妈妈」—— 淘宝只会返回礼盒包装、贺卡、代写服务。
那些不是礼物本身。

所以搜的是**具体的品类**：「颈椎按摩仪」「护腰坐垫」「护手霜」「保温杯」。
先想「什么样的东西能解决她的问题 / 贴合她的场景」，再用品类词去搜。

## 组礼盒的判据是「同时被用到」

几件东西要落在**同一个使用场景**里，而不是各自最好。
三件说得通胜过六件堆着。

反例：按摩仪 + 保温杯 + 台灯 —— 三样都好，但凑不成一件事。
正例：颈部按摩仪 + 护手霜 —— 都是「她伏案一天后的放松」，能一起用上。

单件也可以，宁可 1 件也不要凑数。

## 铁律

- **不要虚构商品。** 只能从 `search_gifts` 返回的结果里挑。
- **不要假装了解收礼人。** 档案里没记录就直说没有，按通用方向准备，
  并在结论里讲清楚。编一个「她喜欢 XX」而实际不是，这份礼物就废了。
- 每件的理由必须指回具体依据（她的偏好 / 场景 / 预算）。
  写「品质好」「性价比高」这种放在任何商品上都成立的话算无效。
- 工具返回什么就说什么。搜不到就是搜不到。
- 全程中文，不要复述这些要求。
"""


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
        system_prompt=SYSTEM_PROMPT,
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
