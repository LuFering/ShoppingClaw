"""送礼 agent 的工具集 —— **模型自己决定调哪个、调几次**。

═══════════════════════════════════════════════════════════════════════
2026-09-27：从「六个写死的节点」改成「一组工具 + 真 ReAct 循环」
═══════════════════════════════════════════════════════════════════════

用户的原话：「我感觉这个执行流是不是有点假了，为什么会执行这么快」。

量下来确实如此 —— 送礼是**写死的 6 节点链**（`understand → extract →
search → verify → combine → message`，六条 `add_edge`、零条条件边），
其中**只有 3 处调模型**（理解/组合/寄语），另外三步是**纯代码**：
  · `read_history` / `read_preferences`  一次查表
  · `search_candidates`                  一次 HTTP 检索
  · `verify_candidates`                  一次 for 循环比价

实测前四个阶段总共 **4.8 秒**（检索 0.8s、比价 0.02s）—— 那不是效率高，
是**一半的步骤压根没有智能**。对照规划智能体：它是 `create_agent()` 起的
真 ReAct 循环，每一条执行流都是模型的真实决策。

现在改成同样的形状：

    model ──条件边──► tools ──条件边──► model ──► ... ──► END

每个工具是 `@tool`，模型在 system prompt 里看到说明后自己编排。工具通过
返回 `Command(update={...})` 把产物写进共享状态。

工具本身**不做事件写入**（那是 service 的职责）：service 从每次工具调用里
生成事件，带上真实入参和真实返回。

═══════════════════════════════════════════════════════════════════════
两个实现上的硬约束（规划那边已踩过，这里直接避开）
═══════════════════════════════════════════════════════════════════════

1. **工具必须回一条 `ToolMessage`，且带上 `tool_call_id`。**
   返回 `Command` 的工具如果不带匹配的 ToolMessage，LangGraph 会报
   「Every tool call MUST have a corresponding ToolMessage」直接失败。
   `tool_call_id` 靠 `Annotated[str, InjectedToolCallId]` 注入 ——
   注意它在 `langchain_core.tools`，**不在** `langgraph.prebuilt`。

2. **不能自己造 message role。** 只认 human/ai/system/tool 那几种。

3. **每个会被工具写到的 state 字段都要带 reducer** —— 模型会并行调多个
   工具，同一个键被写两次就报 `InvalidUpdateError`。见 `GiftState`。
"""
from __future__ import annotations

import logging
import re
from typing import Annotated, Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

logger = logging.getLogger(__name__)


# ⚠️ 模块级短名：`_locate` / `_render_profile` 是模块级辅助函数，拿不到
# 函数内的 `st`（tools.py 的惯例是函数内导入 stages 以避免循环导入）。
from src.agents.independent.gift.stages import (  # noqa: E402
    fold_profile as _fold,
    group_by_rail as _group_by_rail,
    locate_entry as _locate,       # noqa: F401  （分支里用）
    rail_norm as _rail_norm,
)


def _note(text: str, tool_call_id: str) -> ToolMessage:
    """工具给模型的回话。必须带 tool_call_id，否则 LangGraph 配对失败。"""
    return ToolMessage(content=text, tool_call_id=tool_call_id)


def _to_stage_state(state: dict) -> dict:
    """agent state → stages 纯函数期望的形状。

    分批推送留下的部分产物（如只有三组 profile）不能直接给组装函数用，
    这里统一收口 —— 纯函数拿到的是完整状态。
    """
    return {
        "recipient": state.get("recipient") or "",
        "occasion": state.get("occasion") or "",
        "budget": state.get("budget") or 0,
        "signals": state.get("signals") or [],
        "user_id": state.get("user_id") or "",
        "run_id": state.get("run_id") or "",
        "context": state.get("context") or {},
        "profile": state.get("profile") or [],
        "understanding": state.get("understanding") or {},
        "picked": state.get("picked") or [],
        "excluded": state.get("excluded") or [],
        "plan": state.get("plan") or {},
    }


# ══════════════════════════════════════════════════════════════
# 取数类工具
# ══════════════════════════════════════════════════════════════

@tool
async def read_history(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """读收礼人的**历史决策记录**（以前送过什么、什么阶段、什么反馈）。

    这是了解一个人最实的一块：TA 收到过什么、哪些被排除过。
    与 `read_preferences` 是**两次独立的查询**，你可以只调其中一个。

    读不到会如实告诉你「没有记录」—— 那就按通用方向准备，
    **不要假装了解对方**。
    """
    from src.agents.independent.gift import stages as st

    history = await st.read_history(state)
    prev = state.get("context") or {}
    ctx = {"history": history, "prefs": prev.get("prefs") or [],
           "raw_ok": bool(history or prev.get("raw_ok"))}
    # 只写**这次真读到的**（0~2 条），不再把固定五组里属于历史那批全写进去
    added = st.seed_history_entry(history)

    if history:
        lines = [f"· {h.get('target') or h.get('recommend') or '（无题）'}"
                 f"（{h.get('phase') or '—'}）" for h in history[:5]]
        body = (f"读到 {len(history)} 条历史决策：\n" + "\n".join(lines)
                + "\n\n（已把要点写进档案的「送礼往来」栏。）")
    else:
        body = ("没有关于这位收礼人的历史决策记录。\n"
                "后续请按通用方向准备，并在结论里说明「无历史依据」。")

    return Command(update={
        "context": ctx,
        # seed 出来的条目转成 add op 追加（state 里是 op 日志，见 graph.py）
        "profile": [
            {"op": "add", "rail": x.get("rail"), "text": x.get("text"),
             "because": x.get("because"), "source": x.get("source")}
            for x in (added or []) if isinstance(x, dict)
        ],
        "messages": [_note(body, tool_call_id)],
    })


@tool
async def read_preferences(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """读用户的**长期偏好**（品牌、预算、场景、在意点等档案字段）。

    这是第二次独立查询 —— 与 `read_history` 的结果互为补充。
    读不到会如实说明，**不要编造偏好**。
    """
    from src.agents.independent.gift import stages as st

    prefs = await st.read_preferences(state)
    prev = state.get("context") or {}
    ctx = {"history": prev.get("history") or [], "prefs": prefs,
           "raw_ok": bool(prev.get("raw_ok") or prefs)}
    # 同上：只写这次真读到的（筛完可能为空 —— 读到但与收礼人无关时不占条数）
    added = st.seed_prefs_entry(prefs)

    if prefs:
        # 只显示**值**：键名是机器名（gift_for_mom_budget_max），
        # 原样铺出来只是一串读不懂的字段
        vals = [str(p.get("value") or p) for p in prefs if isinstance(p, dict)]
        body = f"读到 {len(prefs)} 条长期偏好：\n" + "、".join(vals[:8])
        # ⚠️ 如实告诉模型「筛掉了什么」：它的 12 条偏好**全部**是用户自己
        # 要买笔记本的，与收礼人无关。不说清的话模型会以为档案读到了，
        # 进而在结论里引用「妈妈喜欢华为」——那是错的。
        if not added:
            body += ("\n\n⚠️ 这些偏好都是**用户自己买东西**的（笔记本/耳机等），"
                     "与这位收礼人无关，所以**没有**写进 TA 的档案。"
                     "请不要据此推断 TA 的喜好。")
        else:
            body += "\n\n（已把与收礼人相关的写进档案的「在意什么」栏。）"
    else:
        body = "没有读到长期偏好记录。"

    return Command(update={
        "context": ctx,
        # seed 出来的条目转成 add op 追加（state 里是 op 日志，见 graph.py）
        "profile": [
            {"op": "add", "rail": x.get("rail"), "text": x.get("text"),
             "because": x.get("because"), "source": x.get("source")}
            for x in (added or []) if isinstance(x, dict)
        ],
        "messages": [_note(body, tool_call_id)],
    })


@tool
async def search_gifts(
    keyword: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """按关键词搜真实商品，返回商品名与价格。

    **用具体的品类词**（「颈椎按摩仪」「护手霜」），不要用「礼物」「生日礼物」
    —— 那只会搜出礼盒包装。搜不到或结果不合适，换个词再搜是你的自由。

    Args:
        keyword: 搜索关键词，用品类词
    """
    from src.agents.independent.gift import stages as st

    s = _to_stage_state(state)
    s["_kw"] = keyword
    found = await st.search_candidates_for(s, keyword)

    if found:
        # ⚠️ 用 `cand_name` / `cand_cents` 取名字与价格，不要直接读字段 ——
        # MCP 原始结果的字段是 `title`（不是 `name`）、价格是**分**。
        # 实测写 `c.get("name")` 的后果：返回里全是「None ¥91」。
        lines = [
            f"- {st.cand_name(c)} ¥{st.price_of_yuan(st.cand_cents(c))}"
            for c in found[:6]
        ]
        body = f"关键词「{keyword}」返回 {len(found)} 件：\n" + "\n".join(lines)
    else:
        body = f"关键词「{keyword}」没有返回结果，换个品类词再试"

    return Command(update={
        "picked": found,
        "searched": [keyword],
        "messages": [_note(body, tool_call_id)],
    })


def _render_profile(items: list[dict]) -> str:
    """把档案渲染成给模型看的文本（按栏分组）。

    与 `screen_candidates` 把「候选里的原名」回给模型是同一手法 ——
    那里踩过的坑是：模型排除 8 件、实际生效 0 件，因为它在盲改。
    让它**看得见当前档案**，它才知道下一笔该 add 还是 update。
    """
    groups = _group_by_rail(items)
    if not groups:
        return "（档案目前是空的）"
    out = []
    for g in groups:
        out.append(f"【{g['rail']}】")
        for it in g["items"]:
            out.append(f"  · [{it.get('id')}] {it.get('text')}")
    return "\n".join(out)


@tool
def write_profile(
    rail: Annotated[str, "栏名。可用建议栏名，也可自建一个更贴切的新栏名"],
    op: Annotated[str, "add 新增 / update 改写 / drop 删除"],
    text: Annotated[str, "add/update 写新内容；drop 时填要删的那条（原样照抄）"],
    because: Annotated[str, "这条信息来自哪次**真实**结果，必须能指回去"],
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    to: Annotated[str, "update 专用：要改成什么。add/drop 不用填"] = "",
) -> Command:
    """往人物档案里写一条，或改写 / 删除已有的一条。

    **每做完一步就该想一次：这一步的结果里，有哪条是关于这个人 / 这次送礼
    的、值得记进档案的？** 有就写，没有就别写 —— 不要为了凑数写。

    ⚠️ **入口已经写过一条「人物信息」**（送给谁/场合/预算，来源「入口参数」）。
    要补充它就用 `update`，不要 add 一条新的 —— 那会让同一件事出现两次。

    建档建议（可以自建新栏，不限于这几个）：
      「人物信息」TA 是谁、什么场合、什么预算          ← 入口**已有**，补充用 update
      「送礼往来」以往送过什么、什么被排除过          ← 读完历史
      「在意什么」TA 的偏好与在意的点                  ← 读完偏好
      「行情锚点」真实搜到的价格带、有哪些品类        ← 检索之后
      「这盒的取舍」排除了什么、为什么                ← 比价之后
      「这盒怎么搭」这几件为什么构成一体              ← 组合之后
    涉及禁忌 / 过敏 / 不能送的东西，栏名里带上「禁忌」二字 —— 界面会把它
    单独放进危险区强调显示。

    三条铁律：
    1. `because` 必须指回**具体哪次工具返回**里的什么。
       写不出 because 就说明这条是你编的，不要写。
    2. `text` 只写具体信息，不要写「暂无记录」「无」「待确认」这类空话 ——
       读不到就不写这一条，**空的档案比塞满空话的档案诚实**。
    3. `drop` / `update` 时 `text` 要**原样照抄**档案里那条（我每次都会把
       当前档案回给你，照着复制）。改写用 update 而不是 drop+add ——
       后者会丢掉这条的历史。

    Args:
        rail: 栏名
        op: add / update / drop
        text: add/update 的新内容；drop 时填要删的那条原文
        because: 依据 —— 这条来自哪次真实结果
        to: update 时改成什么
    """
    # ⚠️ 只**追加一条 op**，不在这里算全量列表 —— 见 stages.fold_profile
    # 的说明：并行调用时「各自算全量再覆盖」会整个丢掉另一次的结果
    # （id 实证：p2 被顶掉，整条「送礼往来」消失且无 drop 事件）。
    cur = _fold(state.get("profile"))
    rail = str(rail or "").strip()
    text = str(text or "").strip()
    because = str(because or "").strip()

    # ── 红线：没有 because 就是编的 ──
    if not because:
        return Command(update={"messages": [_note(
            "⚠️ 没有填 `because`。请写清这条信息来自**哪次真实结果**"
            "（例如「read_history 返回的第 2 条」「搜『护颈仪』返回的价格」）。"
            "写不出来就说明这条是推断或编造的 —— 那就不要写进档案。\n\n"
            "当前档案：\n" + _render_profile(cur), tool_call_id)]})

    if op == "add":
        if not rail or not text:
            return Command(update={"messages": [_note(
                "⚠️ add 需要同时给出 `rail` 和 `text`。\n\n当前档案：\n"
                + _render_profile(cur), tool_call_id)]})
        # 同栏同文不重复写（模型多轮里常重复同一条）
        for it in cur:
            if (str(it.get("rail") or "").strip() == rail
                    and _rail_norm(it.get("text")) == _rail_norm(text)):
                return Command(update={"messages": [_note(
                    f"「{rail}」里已经有这一条了，没有重复添加。\n\n"
                    "当前档案：\n" + _render_profile(cur), tool_call_id)]})
        op_entry = {"op": "add", "rail": rail, "text": text,
                    "because": because, "source": "本次推演"}
        body = f"已写入「{rail}」：{text}\n（依据：{because}）"

    elif op == "update":
        i = _locate(cur, text)
        if i < 0:
            return Command(update={"messages": [_note(
                f"⚠️ 档案里找不到「{text}」，没有改动。请**原样照抄**下面某条的"
                "文字再来一次。\n\n当前档案：\n" + _render_profile(cur),
                tool_call_id)]})
        new_text = str(to or "").strip()
        if not new_text:
            return Command(update={"messages": [_note(
                "⚠️ update 需要填 `to`（改成什么）。若想删掉这条请用 drop。",
                tool_call_id)]})
        op_entry = {"op": "update", "text": text, "to": new_text,
                    "because": because}
        body = f"已改写：{text} → {new_text}\n（依据：{because}）"

    elif op == "drop":
        i = _locate(cur, text)
        if i < 0:
            return Command(update={"messages": [_note(
                f"⚠️ 档案里找不到「{text}」，没有删除。请**原样照抄**下面某条的"
                "文字再来一次。\n\n当前档案：\n" + _render_profile(cur),
                tool_call_id)]})
        gone = cur[i].get("text")
        op_entry = {"op": "drop", "text": text, "because": because}
        body = f"已删除：{gone}\n（依据：{because}）"

    else:
        return Command(update={"messages": [_note(
            f"⚠️ `op` 只能是 add / update / drop，收到的是「{op}」。",
            tool_call_id)]})

    # 追加一条 op —— reducer 是 _merge_lists，并行调用各追加各的，互不覆盖
    preview = _fold(list(state.get("profile") or []) + [op_entry])
    return Command(update={
        "profile": [op_entry],
        "messages": [_note(body + "\n\n当前档案：\n" + _render_profile(preview),
                           tool_call_id)],
    })


# ══════════════════════════════════════════════════════════════
# 判断类工具
# ══════════════════════════════════════════════════════════════

@tool
def screen_candidates(
    names: Annotated[list[str], "要排除的商品名（必须与搜索结果里的名字一致）"],
    reason: Annotated[str, "排除理由，要具体（超预算 / 配件 / 场景不符）"],
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """把不合适的候选排除掉，并记下理由。

    排除的项**不会消失**，会带上理由保留 —— 用户要能看到「这些被排除了、
    为什么」。理由要写具体，不要写「不合适」。

    ⚠️ 送礼要留组合空间：单价超过预算 60% 的值得排除（一件占满预算就没法
    搭配了）。但**这个判断由你做** —— 代码只提供这条经验，不替你决定。

    Args:
        names: 要排除的商品名列表
        reason: 排除理由
    """
    from src.agents.independent.gift import stages as st

    pool = list(state.get("picked") or [])
    # 按**规范化后的名字**建索引，同时提供容错匹配：
    # 模型常把价格一起写进名字（「颈椎按摩仪 ¥1350」），而候选里只有原名。
    # 直接 `by_name[n]` 会全部落空 —— 实测模型"排除 8 件"实际生效 0 件，
    # 它的排除理由完全被丢弃。
    def _norm(x: str) -> str:
        # 去掉价格尾巴与空白，只留名称主体
        return re.sub(r"[\s¥￥\d.,]+$", "", str(x)).strip()

    by_name = {st.cand_name(c): c for c in pool}
    by_norm = {_norm(st.cand_name(c)): c for c in pool}

    dropped, missed = [], []
    for n in names:
        hit = by_name.get(n) or by_norm.get(_norm(n))
        if hit is None:
            missed.append(n)
        else:
            dropped.append({**hit, "why": reason})

    body = f"已排除 {len(dropped)} 件：{reason}"
    if missed:
        # ⚠️ 把**候选里的原名**列出来 —— 只说「没找到」模型只能瞎猜；
        # 给出原文它下一轮就能对上。
        avail = "、".join(st.cand_name(c)[:20] for c in pool[:5])
        body += (f"\n⚠️ 这些名字没在候选里找到，未生效：{missed[:3]}"
                 f"\n候选里的原名是：{avail}")

    return Command(update={
        "excluded": dropped,
        "messages": [_note(body, tool_call_id)],
    })


@tool
def compose_gift(
    title: Annotated[str, "这份礼物的名字，如「妈妈的松弛时刻」"],
    thesis: Annotated[str, "一句话说清这几件如何构成一体"],
    items: Annotated[list[dict], "挑中的商品，每项 {name, role, why}"],
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """从候选里挑出**最多 3 件**组成一份礼物，并说明理由。

    判据是「**同时被用到**」—— 几件要落在同一个使用场景里，而不是各自最好。
    三件说得通胜过六件堆着。

    铁律：
    - 只能从搜索结果里挑，**不要虚构商品**，价格也不许改。
    - 总数不得超过预算。
    - 每件的 `why` 必须指回具体依据（收礼人的偏好 / 场景）。

    **这是收敛动作**：调完之后应当准备给用户交代，不要再搜新商品。

    Args:
        title: 礼物名字
        thesis: 一句话的整体构思
        items: [{name, role: 主力|搭配|点缀, why}]
    """
    from src.agents.independent.gift import stages as st

    pool = list(state.get("picked") or [])
    # 与 screen_candidates 同一套容错：模型可能把价格写进名字
    def _norm(x: str) -> str:
        return re.sub(r"[\s¥￥\d.,]+$", "", str(x)).strip()

    by_name = {st.cand_name(c): c for c in pool}
    by_norm = {_norm(st.cand_name(c)): c for c in pool}
    budget = int(state.get("budget") or 0)

    kept, missed = [], []
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        nm = str(it.get("name") or "")
        hit = by_name.get(nm) or by_norm.get(_norm(nm))
        if hit is None:
            missed.append(nm)
            continue
        kept.append({
            # 用候选里的**原名**，而不是模型写的（可能带价格尾巴）
            "name": st.cand_name(hit),
            "price": st.price_of_yuan(st.cand_cents(hit)),
            "role": str(it.get("role") or "一件"),
            "why": str(it.get("why") or ""),
        })

    if not kept:
        avail = "、".join(st.cand_name(c)[:20] for c in pool[:5]) or "（候选为空）"
        return Command(update={
            "messages": [_note(
                "⚠️ 你给的商品名都不在候选里，请**原样复制**搜索结果里的名字"
                "（不要加价格）。"
                + (f"\n未找到：{missed[:3]}" if missed else "")
                + f"\n候选里的原名是：{avail}",
                tool_call_id,
            )],
        })

    total = sum(int(i["price"] or 0) for i in kept)
    # 超预算**如实回报**，但不强行砍掉 —— 由模型自己决定怎么改
    over = total > budget > 0

    plan = {"title": title, "thesis": thesis, "items": kept, "by": "llm",
            "total": total}
    lines = [f"已组好「{title}」：{thesis}", ""]
    for i in kept:
        lines.append(f"· [{i['role']}] {i['name']} ¥{i['price']} —— {i['why']}")
    lines.append(f"合计 ¥{total}（预算 ¥{budget}）")
    if over:
        lines.append(f"⚠️ 超出预算 ¥{total - budget}，请调整后再定。")
    if missed:
        lines.append(f"⚠️ 未找到：{missed[:3]}")

    return Command(update={
        "plan": plan,
        "messages": [_note("\n".join(lines), tool_call_id)],
    })


@tool
async def write_note(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """生成寄语文案。

    **寄语里每一句都要能指回前面某一步的依据**，不是通用祝福。
    「祝你生日快乐」这种放在任何人身上都成立的话算无效。

    调用前请确认已经组好礼盒（`compose_gift`）—— 寄语要讲清这几件为什么
    是它们。
    """
    from src.agents.independent.gift import stages as st

    s = _to_stage_state(state)
    if not (s.get("plan") or {}).get("items"):
        return Command(update={
            "messages": [_note("⚠️ 还没有组好礼盒，请先调 `compose_gift`。",
                               tool_call_id)],
        })

    msg = await st.build_message(s, s["plan"], s.get("understanding") or {})
    body = f"寄语已生成（{msg.get('by')}）：\n{str(msg.get('text') or '')[:200]}"
    return Command(update={
        "message": msg,
        "messages": [_note(body, tool_call_id)],
    })


@tool
def ask_user(
    question: Annotated[str, "要问用户的问题，要具体，基于你这次实际拿到的东西"],
    options: Annotated[list[str], "2~4 个选项，让用户能一键回答"],
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """当信息不足以继续、或需要用户在取舍上拍板时，向用户提问。

    问之前先想清楚：这个问题是不是必须用户回答？能从已有信息推断的就别问。
    问题要基于你**这次实际拿到的结果**（比如「档案里没有她的偏好，
    要不要按通用方向选，还是你补充几条」），不要问放之四海皆准的话。

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


GIFT_TOOLS = [
    read_history,
    read_preferences,
    write_profile,
    search_gifts,
    screen_candidates,
    compose_gift,
    write_note,
    ask_user,
]
