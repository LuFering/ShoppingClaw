"""采购规划各阶段的实现。

设计：**取数与计算用工具，判断与措辞用模型。**

  · `search_candidates` / `retrieve_dimensions` / `retrieve_risks` —— 真调工具
  · `pick_best` —— 真调模型做多维度取舍

═══════════════════════════════════════════════════════════════════════
2026-09-25 修正：这里原先**一行模型调用都没有**
═══════════════════════════════════════════════════════════════════════

初版把「推理薄」做成了「推理零」：选件是 `min(price)`，阶段间隔 3–11 毫秒
—— 那是函数调用，不是思考。现在 `pick_best` 真问模型，并要求它给出
理由；模型不可用时降级到价格规则，并**如实标注**是哪一种。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 取数预算（与技能 `searching-products` 的口径一致）
SEARCH_KEYWORDS = 2
SEARCH_PAGE_SIZE = 6
MCP_TIMEOUT = 90      # stdio MCP 冷启动已由 lifespan 预热，这里只防长尾
RAG_TIMEOUT = 30


# ══════════════════════════════════════════════════════════
# 模型调用
# ══════════════════════════════════════════════════════════
#
# 胶水代码（取模型 / 问一次 / 抠 JSON / 收敛编号）统一放在
# `src/agents/independent/common_llm.py` —— 与送礼 agent 共用一份。
# 这里只保留本 agent 的用法。

from src.agents.independent.common_llm import (
    as_idx,
    degrade_note,
    parse_json_block,
)
from src.agents.independent.common_llm import ask_model as _ask


async def ask_model(system: str, user: str) -> str:
    """问一次模型。失败返回空串，由调用方降级。"""
    return await _ask(system, user, tag="planning")


# ══════════════════════════════════════════════════════════
# 工具访问
# ══════════════════════════════════════════════════════════

async def _mcp_tool(name: str):
    """按名取一个 MCP 工具。取不到返回 None（调用方降级，不抛）。"""
    try:
        from src.services.mcp_service import get_tools_from_all_servers
        from src.services.mcp_tool_adapter import adapt_mcp_tools

        specs = await get_tools_from_all_servers()
        tools = await adapt_mcp_tools(specs)
        return next((t for t in tools if getattr(t, "name", "") == name), None)
    except Exception as e:
        logger.warning(f"[planning] MCP 工具 {name} 加载失败: {e}")
        return None


async def _builtin_tool(name: str):
    """按名取一个 buildin 工具（RAG 类在这里）。

    ⚠️ 必须从**包** `toolkits` 导入，不能从子模块 `toolkits.registry` 导入 ——
    包 `__init__.py` 里的 `get_all_tool_instances()` 会先调 `_ensure_tools_loaded()`
    去 import 各工具包（`@tool` 装饰器在 import 时才注册），子模块里那个不会。
    从子模块导入拿到的是**空列表**，于是每个 RAG 调用都静默落到兜底分支
    （实测：`query_category_knowledge` 恒取不到 → 「命中 3 条评估维度」
    其实是硬编码的 `["价格","口碑","售后"]`）。
    """
    try:
        from src.agents.common.toolkits import get_all_tool_instances

        return next(
            (t for t in get_all_tool_instances() if getattr(t, "name", "") == name), None
        )
    except Exception as e:
        logger.warning(f"[planning] 内置工具 {name} 加载失败: {e}")
        return None


async def _call(tool, args: dict, timeout: int) -> Any | None:
    """统一调用封装：超时/异常都返回 None，由调用方决定降级。"""
    if tool is None:
        return None
    try:
        return await asyncio.wait_for(tool.ainvoke(args), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(f"[planning] 工具 {getattr(tool,'name','?')} 超时")
        return None
    except Exception as e:
        logger.warning(f"[planning] 工具 {getattr(tool,'name','?')} 失败: {e}")
        return None


def _as_str_list(raw: Any, limit: int = 6) -> list[str]:
    """从 RAG 返回里抠字符串列表。返回结构不稳定，宽容解析。"""
    text = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False) if raw else ""
    if not text:
        return []
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return []
    if isinstance(data, dict):
        for k in ("dimensions", "criteria", "risks", "policies", "items", "data"):
            v = data.get(k)
            if isinstance(v, list):
                out = []
                for x in v:
                    if isinstance(x, str):
                        out.append(x)
                    elif isinstance(x, dict) and x.get("name"):
                        out.append(str(x["name"]))
                return out[:limit]
    if isinstance(data, list):
        return [str(x) for x in data[:limit] if isinstance(x, str)]
    return []


# ══════════════════════════════════════════════════════════
# 各阶段（纯）
# ══════════════════════════════════════════════════════════

def build_needs(state: dict) -> list[dict]:
    """intake：把入口参数摊成「需求」节点。"""
    out: list[dict] = []
    if state.get("scene"):
        out.append({"id": "need-scene", "name": f"场景：{state['scene']}", "importance": 4})
    if state.get("budget"):
        out.append({"id": "need-budget", "name": f"预算 {state['budget']}", "importance": 5})
    if state.get("duration"):
        out.append({"id": "need-when", "name": f"周期 {state['duration']}", "importance": 3})
    for i, c in enumerate(state.get("constraints") or []):
        out.append({"id": f"need-c{i}", "name": str(c), "importance": 4})
    return out


async def retrieve_dimensions(subject: str) -> tuple[list[str], bool]:
    """clarify：查品类知识，得到该品类该看的评估维度。

    返回 `(维度, 是否来自知识库)`。第二个值**必须往上传** ——
    界面上的措辞要跟着它变，否则「命中 3 条评估维度」会被读成
    「知识库里有这个品类的资料」，而实际可能一条都没有、用的是通用兜底。

    查不到用通用维度兜底 —— 不能因为知识库没收录就卡住整条流程。
    """
    raw = await _call(await _builtin_tool("query_category_knowledge"),
                      {"category": subject}, RAG_TIMEOUT)
    hits = _as_str_list(raw)
    return (hits, True) if hits else (["价格", "口碑", "售后"], False)


async def search_candidates(state: dict) -> list[dict]:
    """search：**真调淘宝 MCP**，拿真实 SKU 与价格。

    复用 task_executors.common.parse_search_result —— 它已处理真实淘宝的
    嵌套结构（`result_list.map_data`，见 B6 修复）并把价格统一转成**分**。
    绝不再写第二套解析：两套必然漂。
    """
    base = state.get("subject") or state.get("scene") or "好物"
    keywords = [base]
    if (state.get("constraints") or []):
        keywords.append(f"{base} {state['constraints'][0]}")
    keywords = keywords[:SEARCH_KEYWORDS]

    from src.services.task_executors.common import parse_search_result

    tool = await _mcp_tool("taobao_searchMaterial")
    found: list[dict] = []
    for kw in keywords:
        raw = await _call(tool, {"q": kw, "page_size": SEARCH_PAGE_SIZE}, MCP_TIMEOUT)
        found.extend(parse_search_result(raw) if raw is not None else [])
        if len(found) >= SEARCH_PAGE_SIZE * 2:
            break

    seen, uniq = set(), []
    for it in found:
        key = str(it.get("item_id") or it.get("title"))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
    return uniq[:SEARCH_PAGE_SIZE]


def yuan(cents: Any) -> str:
    try:
        v = int(cents or 0)
    except (TypeError, ValueError):
        return ""
    return f"{v / 100:.0f}" if v else ""


# ⚠️ 候选在链路上有**两种形状**，凡是读候选的地方都必须两种都认：
#   · `search_candidates` 直接吐的**原始 MCP 结果**：title / price(分)
#   · 事件层归一的：name / price_yuan(元)
# 只认后者会导致真实链路里 name 恒为 None —— 模型选出来了，事件里却
# 什么都没显示（踩过：compare 阶段只有 phase、没有 think）。
# 这两个函数放模块级（原先嵌在 pick_best 里），因为 filter 与 deliver
# 也要用同一套判定，嵌在里面就得抄第二份。

def cand_name(c: dict) -> str:
    return str(c.get("name") or c.get("title") or "未命名")


def cand_yuan(c: dict) -> float | None:
    """取「元」价。认不出返回 None —— 与「价格为 0」区分开。"""
    if c.get("price_yuan") is not None:
        try:
            return float(c["price_yuan"])
        except (TypeError, ValueError):
            return None
    p = c.get("price")
    try:
        return float(int(p) / 100) if p else None
    except (TypeError, ValueError):
        return None


async def pick_best(cands: list[dict], state: dict | None = None) -> dict:
    """compare：**让模型做多维度取舍**，并给出理由。

    返回 {"name", "why", "by"}；`by` 标明这次是模型判断还是规则兜底 ——
    界面与事件都如实呈现，不把规则输出说成模型判断。

    为什么不让模型自由发挥：它会挑一个候选池里不存在的商品。
    所以只让它**从给定编号里选**，编号越界整体降级。
    """
    if not cands:
        return {}

    listing = "\n".join(
        f"{i}. {cand_name(c)} ¥{cand_yuan(c) or '—'}" for i, c in enumerate(cands)
    )
    st = state or {}
    system = (
        "你是采购顾问。从候选里选出**最值得买的那一件**，并说明理由。\n\n"
        "判据按重要性：① 是否满足用户的硬约束（场景/预算/用途）"
        "② 价格与口碑的相对位置 ③ 有没有踩到已知风险。\n\n"
        "铁律：\n"
        "1. 只能从给定编号里选，**不要虚构商品**。\n"
        "2. `why` 必须指回具体依据（某条约束、某个价位、某个风险），"
        "写「性价比高」「品质好」这种放在任何商品上都成立的话算无效。\n\n"
        '只输出 JSON：{"idx": 编号, "why": "为什么是它"}'
    )
    user = (
        f"采购场景：{st.get('scene') or '未指定'}\n"
        f"预算：{st.get('budget') or '未指定'}\n"
        f"硬约束：{'、'.join(str(c) for c in (st.get('constraints') or [])) or '（无）'}\n\n"
        f"候选：\n{listing}"
    )

    reply = await ask_model(system, user)
    obj = parse_json_block(reply)
    idx = as_idx((obj or {}).get("idx"))
    why = str((obj or {}).get("why") or "").strip()
    if idx is not None and 0 <= idx < len(cands) and why:
        return {"name": cand_name(cands[idx]), "why": why[:120], "by": "llm"}

    # 走到这儿说明模型**答了但没按契约答**（或压根没答上）。
    # 降级本身没问题，但降级必须**看得见** —— 见 degrade_note 的说明。
    degrade_note(reply, obj, "planning/pick_best")

    # ── 降级：价格最低者（可解释、可复现）──
    priced = [c for c in cands if cand_yuan(c) is not None]
    best = min(priced, key=lambda c: float(cand_yuan(c))) if priced else cands[0]
    return {"name": cand_name(best), "why": "价格最低（模型不可用，已降级为规则）", "by": "rule"}


async def retrieve_risks(subject: str) -> tuple[list[str], bool]:
    """risk：查售后/风控政策。返回 `(风险项, 是否来自知识库)`。

    ⚠️ 参数名必须与 `QueryRiskPolicyInput` 对齐：它要的是
    `product_name` + `category`，**没有 `query` 字段**。
    早先传 `{"query": subject}` 会直接 pydantic 校验失败
    （`2 validation errors ... product_name/category Field required`），
    异常被 `_call` 吞成 None → 静默落到兜底的那一条「长期持有成本待确认」，
    而界面上照样显示「命中 1 条待确认项」，看不出是失败了。
    """
    raw = await _call(await _builtin_tool("query_risk_policy"),
                      {"product_name": subject, "category": subject}, RAG_TIMEOUT)
    hits = _as_str_list(raw)
    return (hits, True) if hits else (["长期持有成本待确认"], False)


def filter_candidates(cands: list[dict], state: dict) -> tuple[list[dict], list[dict]]:
    """filter：按**硬约束**筛掉不满足的候选，返回 (保留, 排除)。

    ═══════════════════════════════════════════════════════════════════
    2026-09-25：这里原先是 `return {"candidates": state.get("candidates")}`
    ═══════════════════════════════════════════════════════════════════

    原注释写着「本轮不真过滤（需 LLM 判断），原样透传以保持图与阶段数一致」
    —— 也就是说这个阶段**只是为了让图上有七个节点而存在**，什么也没做。
    与此同时 `_on_node` 却照样发了一条 think：「不满足的标记为已排除，
    保留在图上可回看」。事件在描述一件没发生的事。

    现在真过滤，但**只用能判定的硬约束**：预算与明确的价格上限。
    为什么这部分不交给模型：超没超预算是算术，代码判定是确定的、可复现的，
    交给模型反而会算错。模型该管的是「哪件更合适」——那是 compare 的事。

    排除的项**不删掉**，单独返回：界面上要能看到「这些被排除了、为什么」，
    直接丢弃会让用户以为搜索没搜到。
    """
    if not cands:
        return [], []

    # 预算可能是 "60000" / 60000 / "6万" 这类，取其中的数字
    budget_yuan = _budget_yuan(state.get("budget"))

    kept: list[dict] = []
    excluded: list[dict] = []
    for c in cands:
        yuan = cand_yuan(c)
        if budget_yuan and yuan is not None and yuan > budget_yuan:
            excluded.append({**c, "_reason": f"超出预算（¥{yuan:g} > ¥{budget_yuan:g}）"})
        else:
            kept.append(c)

    # 全被筛掉时不能返回空池 —— 后面 compare 会没得选，整个推演断在这。
    # 此时如实保留全部，让 compare 去挑最接近的，并在风险阶段说明超预算。
    if not kept and excluded:
        return cands, []

    return kept, excluded


def _budget_yuan(raw: Any) -> float | None:
    """把预算解析成「元」。认不出返回 None（不筛，而不是筛成空）。"""
    if raw is None:
        return None
    s = str(raw).strip().replace(",", "").replace("¥", "")
    mult = 1.0
    if s.endswith("万"):
        mult, s = 10000.0, s[:-1]
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    return v * mult if v > 0 else None


def deliver_question(state: dict) -> dict:
    """deliver：**故意停一次**等用户拍板。

    工作台右栏浮出问题卡是它的核心体验 —— 全程不打断反而看不出
    「agent 会停下来等你」。

    ═══════════════════════════════════════════════════════════════════
    2026-09-25：问题原先是一句写死的话，且**与事实不符**
    ═══════════════════════════════════════════════════════════════════

    原文案恒为「预算要不要放宽？现有候选都逼近 {budget}。」—— 不看结果。
    实测跑「装修 / ¥60000 / 隔音材料」时，选中的是 ¥42 的隔声毡，
    候选里没有任何一件逼近 60000，但界面上照样弹出「都逼近 60000」。

    这是比降级更糟的一类问题：降级至少是诚实的，这个是**编**。
    现在改成按实际结果分三种情形问，问的必须是这次推演里真实存在的取舍。

    ⚠️ 第二版又踩了一次「拿错数据说话」：判断预算压力时我用了**保留下来**的
    候选里最贵的那件，于是「预算 ¥100、最贵保留 ¥94」被算成有压力，
    弹出「要把预算放宽到能一起拿下吗」—— 可那件 ¥94 本来就在预算内，
    根本不需要放宽。**预算压力只可能来自被排除的候选**（filter 按预算剔掉的
    那些），所以判据必须是 excluded，不是 kept。
    """
    selected = state.get("selected") or {}
    budget_yuan = _budget_yuan(state.get("budget"))
    name = str(selected.get("name") or "").strip()
    pick = f"「{name[:24]}」" if name else "当前选中的这件"

    # 被硬约束剔掉的候选 —— 这才是「放宽预算」唯一的现实依据
    excluded = state.get("excluded") or []
    over = [(cand_yuan(c), cand_name(c)) for c in excluded]
    over = [(p, n) for p, n in over if p is not None]

    sel_price = cand_yuan(selected) if selected else None

    if over and budget_yuan:
        # 真有候选因超预算被剔掉：把「放开能拿到什么」摆出来让用户拍板
        cheapest, cheapest_name = min(over, key=lambda x: x[0])
        return {
            "text": f"有 {len(over)} 件因超出 ¥{budget_yuan:g} 的预算被排除了，"
                    f"其中最低的是「{cheapest_name[:20]}」（¥{cheapest:g}）。"
                    f"要把预算放宽到能考虑它们吗？",
            "phase": "deliver",
            "options": [
                {"key": "keep", "label": f"不放宽，就 {pick}", "primary": True},
                {"key": "raise", "label": f"放宽到 ¥{cheapest:g} 以上", "primary": False},
            ],
        }

    if sel_price is not None and budget_yuan and sel_price < budget_yuan * 0.5:
        # 选中的远低于预算 —— 真正的取舍是「要不要把省下的花掉」
        return {
            "text": f"{pick}是 ¥{sel_price:g}，离预算 ¥{budget_yuan:g} 还差得远。"
                    f"要不要加一件搭配的，把这份预算用足？",
            "phase": "deliver",
            "options": [
                {"key": "keep", "label": "就这样，不凑数", "primary": True},
                {"key": "add", "label": "再加一件搭配", "primary": False},
            ],
        }

    return {
        "text": f"按现在的信息，{pick}是最合适的。要就此定下来，还是再收窄一下条件？",
        "phase": "deliver",
        "options": [
            {"key": "keep", "label": "定下来", "primary": True},
            {"key": "narrow", "label": "再收窄条件", "primary": False},
        ],
    }


# ══════════════════════════════════════════════════════════
# 交付物：三份**内容不同**的产物
# ══════════════════════════════════════════════════════════
#
# ⚠️ 2026-09-25 之前这里是坏的：`get_deliverable` 无论要哪一份，都返回
# **同一段「决策图节点」的罗列**，只是标题不同。也就是说「候选对比表」
# 和「预算分配表」其实是同一份东西贴了两个名字，而且都不含候选价格、
# 不含对比、不含预算 —— 用户点「预览」看到的是一张节点清单。
#
# 根因是把「图里有什么」当成了「交付物该是什么」。图是**过程**的投影，
# 交付物是**结论**的载体，两者形状本就不同：图里有 17 个节点、含需求与
# 依据；而交付物要回答的是「买哪件、为什么、花多少钱、有什么坑」。
#
# 所以这里从 state 里重新组织三份**用途不同**的东西：
#   d-plan    采购方案   —— 买哪件 + 理由 + 排除原因（决策结论）
#   d-compare 候选对比表 —— 逐项横比，入选与排除同表（可核对）
#   d-budget  预算分配表 —— 花了多少、占预算几成、剩多少（可执行）

def _price_of(c: dict) -> float | None:
    return cand_yuan(c)


def build_plan_doc(state: dict) -> dict:
    """采购方案：这次买什么、为什么是它、别的为什么不行。"""
    selected = state.get("selected") or {}
    cands = state.get("candidates") or []
    excluded = state.get("excluded") or []

    name = str(selected.get("name") or "").strip()
    why = str(selected.get("why") or "").strip()
    by = str(selected.get("by") or "rule")
    price = cand_yuan(selected) if selected else None

    # 选中的那件可能不在 candidates 里（pick_best 从候选池挑，池子是筛过的）
    alts = [c for c in cands if cand_name(c) != name][:3]

    return {
        "kind": "plan",
        "subject": state.get("subject") or state.get("scene") or "本次采购",
        "scene": state.get("scene") or "",
        "budget": state.get("budget") or "",
        "duration": state.get("duration") or "",
        "constraints": [str(c) for c in (state.get("constraints") or [])],
        "pick": {
            "name": name or "（未选出）",
            "price": price,
            "why": why,
            "by": by,
        },
        "alternatives": [
            {"name": cand_name(c), "price": cand_yuan(c)} for c in alts
        ],
        "excluded": [
            {"name": cand_name(c), "price": cand_yuan(c),
             "reason": str(c.get("_reason") or "")}
            for c in excluded[:6]
        ],
        "risks": [str(r) for r in (state.get("risks") or [])],
        "dimensions": [str(d) for d in (state.get("dimensions") or [])],
    }


def build_compare_doc(state: dict) -> dict:
    """候选对比表：入选与排除放同一张表，逐项可比。"""
    cands = state.get("candidates") or []
    excluded = state.get("excluded") or []
    selected = state.get("selected") or {}
    sel_name = str(selected.get("name") or "")
    dims = [str(d) for d in (state.get("dimensions") or [])][:4]

    rows = []
    for c in cands:
        n = cand_name(c)
        picked = n == sel_name
        rows.append({
            "name": n,
            "price": cand_yuan(c),
            "picked": picked,
            "tag": "入选" if picked else "候选",
            # 入选的那行给模型的完整理由；其余行如实说明它**为什么没被选**
            # —— 留空的话「依据」列整列是空白，表就成了摆设。
            "reason": (str(selected.get("why") or "")[:80] if picked
                       else ("未入选" if sel_name else "")),
        })
    for c in excluded:
        rows.append({
            "name": cand_name(c),
            "price": cand_yuan(c),
            "picked": False,
            "tag": "排除",
            "reason": str(c.get("_reason") or "不满足硬约束"),
        })

    return {
        "kind": "compare",
        "dimensions": dims,
        "rows": rows,
        "counts": {"candidates": len(cands), "excluded": len(excluded)},
    }


def build_budget_doc(state: dict) -> dict:
    """预算分配表：花多少、占几成、剩多少。"""
    selected = state.get("selected") or {}
    cands = state.get("candidates") or []
    budget = _budget_yuan(state.get("budget"))

    sel_price = cand_yuan(selected) if selected else None
    prices = [p for p in (_price_of(c) for c in cands) if p is not None]

    spent = sel_price or 0.0
    ratio = (spent / budget) if (budget and budget > 0) else None

    return {
        "kind": "budget",
        "budget": budget,
        "spent": spent,
        "remaining": (budget - spent) if budget else None,
        "ratio": ratio,
        "range": {"min": min(prices), "max": max(prices)} if prices else None,
        "items": ([{"name": cand_name(selected), "price": sel_price}] if sel_price else []),
    }


DELIVERABLE_BUILDERS = {
    "d-plan": build_plan_doc,
    "d-compare": build_compare_doc,
    "d-budget": build_budget_doc,
}


def build_deliverable(state: dict, did: str) -> dict | None:
    """按 id 产出结构化交付物。未知 id 返回 None。"""
    fn = DELIVERABLE_BUILDERS.get(did)
    return fn(state) if fn else None


def deliverable_markdown(doc: dict, name: str) -> str:
    """把结构化交付物渲染成 Markdown —— 下载用。"""
    kind = doc.get("kind")
    L: list[str] = [f"# {name}", ""]

    if kind == "plan":
        L += [
            f"- 采购对象：{doc.get('subject') or '—'}",
            f"- 场景：{doc.get('scene') or '—'}",
            f"- 预算：{doc.get('budget') or '—'}",
            f"- 周期：{doc.get('duration') or '—'}",
        ]
        if doc.get("constraints"):
            L.append(f"- 硬约束：{'、'.join(doc['constraints'])}")
        L += ["", "## 建议购买", ""]
        p = doc.get("pick") or {}
        price = p.get("price")
        L.append(f"**{p.get('name')}**" + (f"　¥{price:g}" if price else ""))
        if p.get("why"):
            L += ["", f"> {p['why']}", ""]
        src = "模型判断" if p.get("by") == "llm" else "规则兜底"
        L.append(f"（判断来源：{src}）")

        if doc.get("alternatives"):
            L += ["", "## 备选", ""]
            for a in doc["alternatives"]:
                pr = f"　¥{a['price']:g}" if a.get("price") else ""
                L.append(f"- {a['name']}{pr}")
        if doc.get("excluded"):
            L += ["", "## 已排除", ""]
            for e in doc["excluded"]:
                pr = f"　¥{e['price']:g}" if e.get("price") else ""
                why = f" —— {e['reason']}" if e.get("reason") else ""
                L.append(f"- {e['name']}{pr}{why}")
        if doc.get("risks"):
            L += ["", "## 待确认风险", ""]
            L += [f"- {r}" for r in doc["risks"]]
        if doc.get("dimensions"):
            L += ["", "## 评估维度", ""]
            L.append("、".join(doc["dimensions"]))

    elif kind == "compare":
        L += ["| 候选 | 价格 | 结论 | 依据 |", "|---|---|---|---|"]
        for r in doc.get("rows") or []:
            pr = f"¥{r['price']:g}" if r.get("price") else "—"
            L.append(f"| {r['name']} | {pr} | {r.get('tag') or ''} | {r.get('reason') or ''} |")
        c = doc.get("counts") or {}
        L += ["", f"共 {c.get('candidates', 0)} 个候选，排除 {c.get('excluded', 0)} 个。"]

    elif kind == "budget":
        b = doc.get("budget")
        L += [
            f"- 预算：{'¥%g' % b if b else '—'}",
            f"- 本次花费：¥{doc.get('spent') or 0:g}",
        ]
        if doc.get("remaining") is not None:
            L.append(f"- 结余：¥{doc['remaining']:g}")
        if doc.get("ratio") is not None:
            L.append(f"- 预算占用：{doc['ratio'] * 100:.0f}%")
        rng = doc.get("range")
        if rng:
            L += ["", f"候选价格区间：¥{rng['min']:g} – ¥{rng['max']:g}"]
        if doc.get("items"):
            L += ["", "## 明细", ""]
            for it in doc["items"]:
                pr = f"　¥{it['price']:g}" if it.get("price") else ""
                L.append(f"- {it['name']}{pr}")

    return "\n".join(L) + "\n"
