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


SYSTEM_PROMPT = """\
你是送礼顾问。用户要送一份礼物给某个人，你要**自己决定怎么查、查什么、
什么时候可以给结论**，最后交付一份说得清理由的礼物。

## 你手上的工具

- `read_history()` —— 读收礼人的历史决策记录（以前送过什么、什么被排除过）。
  **开始前先调这个**：不知道对方是谁，后面搜什么都只能靠猜。
- `read_preferences()` —— 读长期偏好（品牌、场景、在意点）。
  与上一个是两次独立查询，读不到会如实告诉你。
- `write_profile(rail, op, text, because)` —— **往人物档案里写一条**，
  或改写 / 删除已有的一条（`op` = add / update / drop）。
  这是你**每一步都能做、也应当做**的动作，见下。
- `search_gifts(keyword)` —— 按品类词搜真实商品。搜不到或结果不合适，
  **换个词再搜**是你的自由。
- `screen_candidates(names, reason)` —— 排除不合适的候选，记下理由。
- `compose_gift(title, thesis, items)` —— 组礼盒。**这是收敛动作**。
- `write_note()` —— 生成寄语。要在组好礼盒之后调。
- `ask_user(question, options)` —— 信息不足或需要用户拍板时提问。

## 怎么做事

顺序由你定，下面是建议不是规定：

1. 先调 `read_history` / `read_preferences` 看这个人是谁、已知什么。
2. 按你判断的品类词去搜。**一次搜一个品类**，看结果再决定下一步。
   搜两三轮通常够了 —— 不要反复搜个不停。
3. 搜回来的要**真的比**：价格、是否命中偏好、场景是否匹配。
   不合适的用 `screen_candidates` 排除，写清具体理由。
4. 觉得够了就 `compose_gift` 定下来。**这是收敛动作**，
   之后不要再搜新商品。
5. 组好后调 `write_note` 写寄语。

## 档案是你**一步步写出来**的，不是开头读一次

这是这份工作里最容易被忽略的部分。档案不是「读出来的结果」，而是
你每做完一步就往上添一笔的**活文档** —— 用户全程盯着它，它长什么样
就代表你想到了哪一步。

**每做完一步，停下来问自己一次：刚才那次返回里，有哪条是关于这个人 /
这次送礼的、值得记进档案的？** 有就 `write_profile` 写进去，没有就别写。

不必一次写全，也不要把读到的原文整段抄进去。几个例子：

- 开头：档案里**已经有一条「人物信息」**（你在入口页填的：送给谁、什么
  场合、什么预算）。如果你想说的人物信息比它更全，用 `update` 改它；
  **不要**再 add 一条 —— 那会让同一件事在档案里出现两次。
- 读完历史 → 写「送礼往来」：以往送过什么、什么被排除过。
  有明确排除过的，单独写一条「明确禁忌」。
- 读完偏好 → 写「在意什么」：TA 在意的点。
  ⚠️ 偏好记录里可能混着**用户自己**要买东西的字段（笔记本、耳机之类）。
  那不是收礼人的喜好，**不要**写进 TA 的档案 —— 写错人比信息少更糟。
- 搜完一轮 → 写「行情锚点」：真实搜到的价格带、有哪些品类可选。
- 比价排除完 → 写「这盒的取舍」：排除了什么、为什么。
- 组好礼盒 → 写「这盒怎么搭」：这几件为什么构成一体。

改动已有的条目用 `update`，不要 drop + add（那会丢掉它的来历）。
发现自己早先写错或用不上了，就 `drop` 掉 —— 档案不是只增不减的。

`because` 是硬要求：必须能指回**具体哪次工具返回**里的什么。
填不出来就说明这条是你编的，那就不要写。宁可档案短，也不要写没有依据的话。

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
- **档案里每一条都要有 because**，且能指回真实的工具返回。
  档案是给用户看的「我了解到什么」，不是许愿池。
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
