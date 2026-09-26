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
from typing import Annotated, Any

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
    category: Annotated[str, "这一搜属于哪个采购品类，如「床」「沙发」。一次采购要买多个品类时用它分组"] = "",
) -> Command:
    """在淘宝搜真实商品，返回商品名与价格。

    搜不到或结果不合适时，**换个关键词再搜**是你的自由 —— 加场景词、加规格词。
    不要一次搜不到就放弃。

    Args:
        keyword: 搜索关键词。用**品类词**，不要用「礼物」「推荐」这类词
        category: 这次搜索属于哪个采购品类（如「床」「沙发」「隔音毡」）。
            要买多个品类时**务必填** —— 候选对比表按它分组，备选与价格区间
            也按同品类算。不填则退回用关键词当品类名。
    """
    from src.agents.independent.planning import stages as st

    found = await st.search_candidates(_to_stage_state(state), keyword=keyword)

    # 给每件打上品类标记 —— 下游的对比表分组、备选、价格区间都靠它。
    # 用模型给的 `category`，没给就用关键词兜底（关键词本身就是个粗略品类）。
    cat = (category or "").strip() or keyword
    found = [{**c, "_category": cat} for c in found]

    if found:
        lines = []
        for c in found[:5]:
            p = st.cand_yuan(c)
            lines.append(f"- {st.cand_name(c)}" + (f" ¥{p:g}" if p is not None else ""))
        body = f"关键词「{keyword}」返回 {len(found)} 件：\n" + "\n".join(lines)
    else:
        body = f"关键词「{keyword}」没有返回结果，换个词试试"

    # 池子满了就**明说**，让模型先去筛，而不是继续往里堆。
    # ═══════════════════════════════════════════════════════════════════
    # 2026-09-27：上限改成**按品类**计
    # ═══════════════════════════════════════════════════════════════════
    # 实测模型搜了 7 次、候选池涨到 30 个才去排除 —— 决策图上几十个节点，
    # 界面被淹没。光在 system prompt 里写规矩不够，工具返回时要**当面提醒**，
    # 它才会立刻处理（模型对工具返回的敏感度远高于对提示词的记忆）。
    #
    # 买一套家具时池子里有 5 个品类，只报「总共 N 件」没有可操作性 ——
    # 模型不知道该砍哪一类。所以要按品类分别报，指出**哪一类**超了。
    pool = _dedup_pool((state.get("candidates") or []) + found)
    by_cat: dict[str, int] = {}
    for c in pool:
        by_cat[st.item_category(c)] = by_cat.get(st.item_category(c), 0) + 1
    over = {k: v for k, v in by_cat.items() if v > CANDIDATE_CAP}
    if over:
        detail = "、".join(f"{k} {v} 件" for k, v in over.items())
        body += (
            f"\n\n⚠️ 候选池超出上限（每类最多 {CANDIDATE_CAP} 件）：{detail}。"
            f"请**先用 `drop_candidates` 排除明显不合适的**（配件类、场景不符、"
            f"档次明显不符的），把超标的品类收到 {CANDIDATE_CAP} 件以内，"
            f"再继续搜或收敛。"
        )

    return Command(update={
        "candidates": found,
        "messages": [_note(body, tool_call_id)],
    })


# 候选池上限，**按品类**计（不是总数）。与 system prompt 里的说法必须一致 ——
# 两处写不同的数字，模型会按提示词的来，工具提醒就成了噪音。
CANDIDATE_CAP = 5


def _dedup_pool(items: list[dict]) -> list[dict]:
    """按 item_id / 名字去重 —— 模型会多轮搜索，同一件会重复出现。"""
    from src.agents.independent.planning import stages as st

    seen, out = set(), []
    for c in items:
        key = str(c.get("item_id") or st.cand_name(c))
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


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
    picks: Annotated[list[dict], "要买的商品列表，每项见下"],
    why: Annotated[str, "整套的取舍逻辑：为什么这么搭配、总账怎么算"],
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """定下最终买**哪些**商品，并说明理由。

    **这是收敛动作**：调完之后应当准备给用户交代，不要再搜新商品。

    ═══════════════════════════════════════════════════════════════════
    ⚠️ 一次采购可以是「一套」，不是只能「一件」
    ═══════════════════════════════════════════════════════════════════
    「搬家买家具」「装修」这类任务要买的是**多个不同品类**（床、沙发、
    衣柜…），互相不可替代，全部列进 `picks`。

    实测踩过：一次「搬家 / 预算 12000」的运行，模型搜齐 5 个品类、算好
    整套 ¥11163（占预算 93%），却因为旧签名只收单件，最终只交出一张床
    —— 预算表显示「占 28%」，和它自己写的理由差了 3 倍。是工具签名在逼
    模型迁就一个错误的接口，不是模型算错。

    `picks` 每一项的字段：

      picked          商品名，必须与候选里的名字完全一致
      item_id         该商品的 item_id。同名商品有多件时**必须**给，用来消歧
      quantity        买几份（件/卷/平米）。整数件通常就是 1
      quantity_basis  用量怎么估出来的，一句话
      subtotal        小计 = 单价 × 用量。估不出来就留空，**不要瞎填**
      why             为什么在**同类里**是它（比的是什么）

    单件采购就传一个元素的列表。

    ═══════════════════════════════════════════════════════════════════
    ⚠️ 预算是「整件事」的钱，商品是「一件」的价
    ═══════════════════════════════════════════════════════════════════
    用户说「预算 6 万装修」指的是整件事；淘宝返回的是单价。直接拿单价去比
    预算会得出荒唐结论 —— 实测一次 6 万的预算算出「花费 ¥165、占用 0.3%」。
    所以每件都要估用量、给小计，**整套小计相加**才是这次采购的花费。

    Args:
        picks: 要买的商品列表，每项含 picked/item_id/quantity/quantity_basis/subtotal/why
        why: 整套的取舍逻辑（为什么这么搭配、总账怎么算）
    """
    from src.agents.independent.planning import stages as st

    pool = (state.get("candidates") or []) + (state.get("excluded") or [])

    items: list[dict] = []
    missed: list[str] = []
    for p in (picks or []):
        if not isinstance(p, dict):
            continue
        name = str(p.get("picked") or p.get("name") or "").strip()
        if not name:
            continue
        iid = str(p.get("item_id") or "")

        # 同名商品可能有多件（不同店铺/规格，item_id 不同）。只给名字的话
        # 系统只能猜一件 —— 实测一次运行里 4 件同名商品，结果 4 个节点
        # 都被标成「已采纳」。有 item_id 就按它精确定位。
        if iid:
            hit = next((c for c in pool if str(c.get("item_id") or "") == iid), None)
        else:
            hit = next((c for c in pool if st.cand_name(c) == name), None)

        if hit is None:
            missed.append(name + (f"（item_id={iid}）" if iid else ""))
            continue

        price = st.cand_yuan(hit)
        qty = _positive(p.get("quantity"))
        sub = _positive(p.get("subtotal"))
        # 小计没给但用量与单价都在 → 自己算。这是算术，不该让模型心算，
        # 但也不覆盖它明确给的数（它可能知道些我们不知道的，比如套装优惠）。
        if sub is None and qty is not None and price is not None:
            sub = round(qty * price, 2)

        items.append({
            "name": st.cand_name(hit),
            "item_id": hit.get("item_id"),
            "price_yuan": price,
            "quantity": qty,
            "quantity_basis": str(p.get("quantity_basis") or "").strip(),
            "subtotal": sub,
            "why": str(p.get("why") or "").strip(),
            # ⚠️ 把品类**带过来**：交付物的备选与预算拆账都按品类分组，
            # 而入选项是从候选里挑出来的 —— 不带上就会全归到「其他」，
            # 备选列不出来、预算表分不了组（单测实测踩过）。
            "_category": hit.get("_category") or "",
        })

    if not items:
        # 一个都没对上 —— 如实回报，别让模型以为定下来了
        return Command(update={
            "messages": [_note(
                "⚠️ 候选里没找到你给的任何商品，请用搜索结果里的原名或 item_id。"
                + (f"未找到：{missed[:3]}" if missed else ""),
                tool_call_id,
            )],
        })

    total = sum(i["subtotal"] for i in items if i["subtotal"] is not None)
    any_sub = any(i["subtotal"] is not None for i in items)

    lines = [f"已定下 {len(items)} 件："]
    for i in items:
        seg = f"· {i['name']}"
        if i["price_yuan"] is not None:
            seg += f" ¥{i['price_yuan']:g}"
        if i["quantity"]:
            seg += f" × {i['quantity']:g}"
        if i["subtotal"] is not None:
            seg += f" = ¥{i['subtotal']:g}"
        lines.append(seg)
    if any_sub:
        lines.append(f"整套合计：¥{total:g}")
    if missed:
        lines.append(f"⚠️ 这些名字没在候选里找到，未生效：{missed[:3]}")

    return Command(update={
        "plan": {
            "items": items,
            "why": why,
            "by": "llm",
            # 总价只在**每一件都有小计**时才算得准。缺任何一件就如实置空，
            # 不能拿部分和冒充总额（那正是「28% vs 93%」那类错的来源）。
            "total": round(total, 2) if (any_sub and len(items) == sum(
                1 for i in items if i["subtotal"] is not None)) else None,
        },
        "messages": [_note("\n".join(lines) + f"\n理由：{why}", tool_call_id)],
    })


def _positive(v: Any) -> float | None:
    """宽松取正数：模型可能给 "6" 这种字符串、也可能给 0 表示「没填」。

    取不到或非正返回 None —— 与「真的是 0」区分开。
    """
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


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
        "plan": state.get("plan") or {},
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
