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
from typing import Any, Callable

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
from src.agents.independent.common_llm import ask_model_streaming


async def ask_model(system: str, user: str) -> str:
    """问一次模型。失败返回空串，由调用方降级。"""
    return await _ask(system, user, tag="planning")


# ══════════════════════════════════════════════════════════
# 工具访问
# ══════════════════════════════════════════════════════════

async def _mcp_tool(name: str):
    """按名取一个 MCP 工具。取不到返回 None（调用方降级，不抛）。

    ⚠️ 取不到时**打 error 而不是 warning**：这说明工具清单是空的，
    整个搜索链路都不工作（实测 MCP 解析失败时会这样）。原先只 warning，
    上层看到的是「搜不到结果」，排查时容易以为是搜索词的问题。
    """
    try:
        from src.services.mcp_service import get_tools_from_all_servers
        from src.services.mcp_tool_adapter import adapt_mcp_tools

        specs = await get_tools_from_all_servers()
        tools = await adapt_mcp_tools(specs)
        hit = next((t for t in tools if getattr(t, "name", "") == name), None)
        if hit is None:
            logger.error(
                "[planning] MCP 工具 %s 不存在（当前共 %d 个工具）—— "
                "搜索链路不可用，检查 MCP 服务是否正常", name, len(tools)
            )
        return hit
    except Exception as e:
        logger.error(f"[planning] MCP 工具 {name} 加载失败: {e}")
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


async def search_candidates(
    state: dict,
    keyword: str | None = None,
    on_progress: Callable[[dict], None] | None = None,
) -> list[dict]:
    """**真调淘宝 MCP**，拿真实 SKU 与价格。

    复用 task_executors.common.parse_search_result —— 它已处理真实淘宝的
    嵌套结构（`result_list.map_data`，见 B6 修复）并把价格统一转成**分**。
    绝不再写第二套解析：两套必然漂。

    ═══════════════════════════════════════════════════════════════════
    2026-09-26：关键词从「代码拼」改成「模型给」
    ═══════════════════════════════════════════════════════════════════
    原先这里是 `base = subject or scene` 加一条约束拼出来的两个词 ——
    搜什么由代码决定。现在 `keyword` 由模型传（它能看到返回结果，
    不合适就换个词再搜）。`keyword` 不传时才回退到旧的拼法，供测试与
    降级路径使用。

    `on_progress` 每次搜索回调一次，带**真实入参与真实返回**。
    """
    if keyword:
        keywords = [keyword]
    else:
        base = state.get("subject") or state.get("scene") or "好物"
        keywords = [base]
        if (state.get("constraints") or []):
            keywords.append(f"{base} {state['constraints'][0]}")
        keywords = keywords[:SEARCH_KEYWORDS]

    from src.services.task_executors.common import parse_search_result

    tool = await _mcp_tool("taobao_searchMaterial")
    found: list[dict] = []
    for kw in keywords:
        args = {"q": kw, "page_size": SEARCH_PAGE_SIZE}
        raw = await _call(tool, args, MCP_TIMEOUT)
        got = parse_search_result(raw) if raw is not None else []
        found.extend(got)
        if on_progress is not None:
            try:
                res = on_progress({
                    "keyword": kw,
                    "args": args,
                    "ok": raw is not None,
                    "count": len(got),
                    # 真实返回的样本：名字 + 价格（元）。截 3 件，够核对。
                    "sample": [
                        {"name": cand_name(c), "price": cand_yuan(c)}
                        for c in got[:3]
                    ],
                })
                # 回调可能是协程（service 那边要 await emit）—— 不 await 的话
                # 事件永远不会发出去，而且不会有任何报错，只是界面没反应。
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                logger.warning(f"[planning] 搜索进度回调失败（忽略）: {e}")
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


async def pick_best(
    cands: list[dict],
    state: dict | None = None,
    on_think: Callable[[str, str], None] | None = None,
) -> dict:
    """compare：**让模型做多维度取舍**，并给出理由。

    返回 {"name", "why", "by"}；`by` 标明这次是模型判断还是规则兜底 ——
    界面与事件都如实呈现，不把规则输出说成模型判断。

    为什么不让模型自由发挥：它会挑一个候选池里不存在的商品。
    所以只让它**从给定编号里选**，编号越界整体降级。

    `on_think` 传了就走流式：模型「先说人话、后给 JSON」，那段人话逐段
    回调出去，界面上就是**看着它想**而不是干等十几秒。
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

    if on_think is not None:
        reply = await ask_model_streaming(system, user, on_think, tag="planning/pick_best")
    else:
        reply = await ask_model(system, user)
    obj = parse_json_block(reply)
    idx = as_idx((obj or {}).get("idx"))
    why = str((obj or {}).get("why") or "").strip()
    if idx is not None and 0 <= idx < len(cands) and why:
        # why 不再截断到 120 字：那是模型真正在比较什么，砍掉就只剩结论，
        # 「AI 味」有一半来自这种被压扁的措辞。
        return {"name": cand_name(cands[idx]), "why": why, "by": "llm"}

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
    budget_yuan = _budget_yuan(state.get("budget"))
    items = plan_items(state)
    # 单件时沿用旧措辞；买一套时说「这套 N 件」而不是报第一件的名字
    if len(items) == 1:
        name = str(items[0].get("name") or "")
        pick = f"「{name[:24]}」" if name else "当前选中的这件"
    elif items:
        pick = f"这套 {len(items)} 件"
    else:
        pick = "当前选中的这件"

    # 被硬约束剔掉的候选 —— 这才是「放宽预算」唯一的现实依据
    excluded = effective_excluded(state)
    over = [(cand_yuan(c), cand_name(c)) for c in excluded]
    over = [(p, n) for p, n in over if p is not None]

    sel_price = plan_total(state)
    if sel_price is None and len(items) == 1:
        sel_price = _num(items[0].get("price_yuan"))

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


def plan_items(state: dict) -> list[dict]:
    """这次要买的**整套**商品。单件采购时就是一个元素的列表。

    ═══════════════════════════════════════════════════════════════════
    2026-09-27：从 `selected`（单件）改成 `plan.items`（整套）
    ═══════════════════════════════════════════════════════════════════
    原先交付物只认 `selected` 一件 —— 因为那时 `make_decision` 只收单件。
    实测「搬家 / 预算 12000」：模型算了整套 5 件 ¥11163（占 93%），
    却只能交出一张床，于是预算表显示「占 28%」，和它自己写的理由差 3 倍。

    兼容旧的单件形状：老 run 的 `products.selected` 仍然能读出来，
    这样已经跑完的任务刷新后不会突然变空。
    """
    plan = state.get("plan") or {}
    items = plan.get("items") or []
    if items:
        return [i for i in items if isinstance(i, dict)]

    # ── 回退：旧的单件 selected ──
    sel = state.get("selected") or {}
    if sel.get("name"):
        return [{
            "name": sel.get("name"),
            "item_id": sel.get("item_id"),
            "price_yuan": sel.get("price_yuan"),
            "quantity": sel.get("quantity"),
            "quantity_basis": sel.get("quantity_basis") or "",
            "subtotal": sel.get("total_estimate"),
            "why": sel.get("why") or "",
        }]
    return []


def plan_why(state: dict) -> str:
    """整套的取舍逻辑。旧的单件 selected 里 why 就是它。"""
    plan = state.get("plan") or {}
    if plan.get("why"):
        return str(plan["why"])
    return str((state.get("selected") or {}).get("why") or "")


def plan_total(state: dict) -> float | None:
    """整套估算总额。**每一件都有小计**时才算得准，否则如实返回 None。

    缺任何一件就置空 —— 拿部分和冒充总额正是「28% vs 93%」那类错的来源。
    """
    items = plan_items(state)
    if not items:
        return None
    subs = [_num(i.get("subtotal")) for i in items]
    if any(s is None for s in subs):
        return None
    return round(sum(subs), 2)


def item_category(c: dict) -> str:
    """商品属于哪个采购品类。

    来源是**模型搜索时给的 `category`**（见 tools.search_products），
    没给就用关键词兜底。两者都没有时归到「其他」——
    宁可归错组，也不要让对比表因为一个缺字段就整张塌掉。
    """
    return str(c.get("_category") or "").strip() or "其他"


def dedup_by_item(items: list[dict]) -> list[dict]:
    """按 item_id / 名字去重，**保持首次出现的顺序**。

    ⚠️ 排除名单必须去重：模型答应用户「拉满预算」后会推翻重排，
    `drop_candidates` 只追加不回改，同一件会被反复记。实测一次 run 的
    排除名单里 29 条只有 26 个 distinct item_id，有件被记了 3 次。
    """
    seen, out = set(), []
    for c in items or []:
        if not isinstance(c, dict):
            continue
        key = str(c.get("item_id") or cand_name(c))
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def effective_excluded(state: dict) -> list[dict]:
    """**当前仍然成立**的排除名单 —— 去重，且剔除已经被选中的那些。

    ═══════════════════════════════════════════════════════════════════
    2026-09-27：选中的商品不能还挂在「已排除」里
    ═══════════════════════════════════════════════════════════════════
    `drop_candidates` 只往 excluded 里追加，**从不撤回**。而模型会改主意：
    实测一次 run 里它先以「超预算」排掉雅兰床垫，用户答「升级品质」后
    又把它选了回来 —— 于是同一件商品同时出现在候选与排除两个名单里。

    后果是交付物自相矛盾：对比表把它标成「排除」，而采购方案说买它；
    更隐蔽的是 `_state_from_run` 会按排除名单把候选里的它剔掉，
    于是「入选 6 件」的对比表只标得出 5 件。

    判定以 **item_id 优先**（同名多件时不能误伤），没有 item_id 才退回名字。
    """
    picked_ids = {
        str(i.get("item_id") or "") for i in plan_items(state) if i.get("item_id")
    }
    picked_names = {str(i.get("name") or "") for i in plan_items(state)}

    out = []
    for e in dedup_by_item(state.get("excluded") or []):
        iid = str(e.get("item_id") or "")
        if iid and picked_ids:
            if iid in picked_ids:
                continue
        elif cand_name(e) in picked_names:
            continue
        out.append(e)
    return out


def build_plan_doc(state: dict) -> dict:
    """采购方案：这次买什么、为什么是它、别的为什么不行。

    ═══════════════════════════════════════════════════════════════════
    2026-09-27：从「一件」改成「一套」
    ═══════════════════════════════════════════════════════════════════
    原先这里只有一个 `pick`，备选取的是 `cands[:3]` —— 候选池的**前三个**，
    跟选中项可能根本不是同一品类。实测要买床，备选列出来的是沙发、沙发、
    餐桌。价格区间同理：「¥11.70 – ¥3611.60」的 min 是个凳子、max 是个沙发。

    现在按品类分组：备选只取**同品类**的，价格区间只算**同品类**的。
    买一件时行为与从前一致（只有一个品类，备选就是同类里的其他件）。
    """
    items = plan_items(state)
    cands = state.get("candidates") or []
    excluded = effective_excluded(state)

    picked_ids = {str(i.get("item_id") or "") for i in items if i.get("item_id")}
    picked_names = {str(i.get("name") or "") for i in items}

    def _is_picked(c: dict) -> bool:
        """是不是这次买下的那件。

        ⚠️ 优先按 **item_id** 比。同名商品可能有多件（不同店铺/规格），
        只按名字比会把它们全算成已选 —— 实测一次运行里 4 件同名床，
        对比表里 2 件都标了「入选」。
        """
        iid = str(c.get("item_id") or "")
        if iid and picked_ids:
            return iid in picked_ids
        return cand_name(c) in picked_names

    picks = [{
        "name": str(i.get("name") or "（未选出）"),
        "price": _num(i.get("price_yuan")),
        "why": str(i.get("why") or ""),
        "by": str((state.get("plan") or {}).get("by") or "llm"),
        "quantity": _num(i.get("quantity")),
        "quantity_basis": str(i.get("quantity_basis") or ""),
        "subtotal": _num(i.get("subtotal")),
        "category": item_category(i),
    } for i in items]

    # 备选：**同品类**里没被选中的那些。跨品类的「备选」没有可比性 ——
    # 买床时列一张沙发当备选，用户看不出该比什么。
    #
    # ⚠️ 还要**按名字去重**：淘宝同一款会由多家店卖，返回的是不同 item_id、
    # 同一个标题。按 item_id 去重拦不住它们，于是「备选」里会出现三行一模一样
    # 的名字（实测）。对读的人来说那是噪音，不是三个选项。
    alts: list[dict] = []
    for i in items:
        cat = item_category(i)
        seen_names: set[str] = set()
        same: list[dict] = []
        for c in cands:
            if item_category(c) != cat or _is_picked(c):
                continue
            n = cand_name(c)
            if n in seen_names:
                continue
            seen_names.add(n)
            same.append(c)
            if len(same) >= 3:
                break
        alts.extend({
            "name": cand_name(c), "price": cand_yuan(c), "category": cat,
        } for c in same)

    return {
        "kind": "plan",
        "subject": state.get("subject") or state.get("scene") or "本次采购",
        "scene": state.get("scene") or "",
        "budget": state.get("budget") or "",
        "duration": state.get("duration") or "",
        "constraints": [str(c) for c in (state.get("constraints") or [])],
        # 整套的商品列表。前端按 category 分组渲染。
        "picks": picks,
        "why": plan_why(state),
        "total": plan_total(state),
        # ⚠️ 保留单件的 `pick` 字段（取第一件），是为了兼容还没更新的读取方
        # —— 前端工作台的存档逻辑、旧事件的回放都读它。新代码请用 `picks`。
        "pick": picks[0] if picks else None,
        "alternatives": alts,
        "excluded": [
            {"name": cand_name(c), "price": cand_yuan(c),
             "reason": str(c.get("_reason") or ""),
             "category": item_category(c)}
            for c in excluded[:6]
        ],
        "risks": [str(r) for r in (state.get("risks") or [])],
        "dimensions": [str(d) for d in (state.get("dimensions") or [])],
    }


def build_compare_doc(state: dict) -> dict:
    """候选对比表：入选与排除放同一张表，**按品类分组**。

    ⚠️ 分组是必须的：买一套家具时池子里有 5 个品类，混在一张表里
    40 行平铺，看不出「床这一项我比了什么」。分组后每个品类内部横比，
    才读得出取舍。
    """
    cands = state.get("candidates") or []
    excluded = effective_excluded(state)
    items = plan_items(state)
    dims = [str(d) for d in (state.get("dimensions") or [])][:4]

    picked_ids = {str(i.get("item_id") or "") for i in items if i.get("item_id")}
    picked_names = {str(i.get("name") or "") for i in items}
    # 每件选中项的**同类理由**，按 item_id / 名字取
    why_by_id = {
        str(i.get("item_id") or ""): str(i.get("why") or "")
        for i in items if i.get("item_id")
    }
    why_by_name = {str(i.get("name") or ""): str(i.get("why") or "") for i in items}

    def _picked(c: dict) -> bool:
        iid = str(c.get("item_id") or "")
        if iid and picked_ids:
            return iid in picked_ids
        return cand_name(c) in picked_names

    def _why(c: dict) -> str:
        iid = str(c.get("item_id") or "")
        if iid and why_by_id.get(iid):
            return why_by_id[iid]
        return why_by_name.get(cand_name(c), "")

    rows = []
    for c in cands:
        p = _picked(c)
        rows.append({
            "name": cand_name(c),
            "price": cand_yuan(c),
            "picked": p,
            "category": item_category(c),
            "tag": "入选" if p else "候选",
            # 入选的那行给模型的完整理由。
            # 未入选的**不写「未入选」**：那是废话，用户看得出来。
            # 空着比写废话好 —— 模型没给落选理由时不该由我们编一句。
            "reason": _why(c)[:80] if p else "",
        })
    for c in excluded:
        rows.append({
            "name": cand_name(c),
            "price": cand_yuan(c),
            "picked": False,
            "category": item_category(c),
            "tag": "排除",
            "reason": str(c.get("_reason") or "不满足硬约束"),
        })

    # 按品类分组，组内保持原顺序（模型搜出来的先后就是它比较的先后）
    groups: list[dict] = []
    idx: dict[str, dict] = {}
    for r in rows:
        g = idx.get(r["category"])
        if g is None:
            g = {"category": r["category"], "rows": []}
            idx[r["category"]] = g
            groups.append(g)
        g["rows"].append(r)

    return {
        "kind": "compare",
        "dimensions": dims,
        "groups": groups,
        # 拍平的 rows 保留 —— 旧前端与下载渲染读它
        "rows": rows,
        "counts": {
            "candidates": len(cands),
            "excluded": len(excluded),
            "picked": len(items),
        },
    }


def build_budget_doc(state: dict) -> dict:
    """预算分配表：花多少、占几成、剩多少、**每个品类各花多少**。

    ═══════════════════════════════════════════════════════════════════
    ⚠️ 2026-09-27 修口径：分子分母必须同量纲
    ═══════════════════════════════════════════════════════════════════
    之前这里拿 `selected.total_estimate`（**一件**的估算）去比预算
    （**整件事**的钱）。实测「搬家 / 预算 12000」选中一张 ¥3401 的床，
    于是显示：

        占预算 28%          ← 3401 / 12000
        整套方案5件合计约¥11163  ← 模型自己算的，占 93%

    同一张卡片上两个数差 3 倍。现在分子改成**整套小计之和**，与预算同量纲。

    估不出来时**如实标注口径**，而不是把单价伪装成总花费 ——
    「不编造」在这里的意思是：宁可显示「单价 ¥3401（未含用量）」，
    也不显示「花费 ¥3401 / 占用 28%」这种误导性的确定数字。
    """
    items = plan_items(state)
    cands = state.get("candidates") or []
    budget = _budget_yuan(state.get("budget"))

    prices = [p for p in (_price_of(c) for c in cands) if p is not None]

    # 整套总额；估不出来（有任一件缺小计）就是 None，退回单价口径
    total = plan_total(state)
    any_qty = any(_num(i.get("quantity")) for i in items)
    unit_only = plan_items(state)[0].get("price_yuan") if len(items) == 1 else None
    if unit_only is not None:
        unit_only = _num(unit_only)

    spent = total
    ratio = (spent / budget) if (spent is not None and budget and budget > 0) else None

    # 按品类拆账 —— 用户想知道「钱花在哪一类上了」
    by_cat: list[dict] = []
    for i in items:
        by_cat.append({
            "category": item_category(i),
            "name": str(i.get("name") or ""),
            "quantity": _num(i.get("quantity")),
            "unit_price": _num(i.get("price_yuan")),
            "subtotal": _num(i.get("subtotal")),
        })

    return {
        "kind": "budget",
        "budget": budget,
        "spent": spent,
        "remaining": (budget - spent) if (spent is not None and budget) else None,
        "ratio": ratio,
        # 单价永远单独给出 —— 它是真实数据，只是不该当总价用
        "unit_price": unit_only,
        "quantity": _num(items[0].get("quantity")) if len(items) == 1 else None,
        "quantity_basis": str(items[0].get("quantity_basis") or "") if len(items) == 1 else "",
        # 口径标记：前端据此决定显示「整套估算」还是「单价（未含用量）」
        "caliber": "total" if spent is not None else ("unit_only" if unit_only else "none"),
        # 整套拆账：每件的小计与占比
        "items": by_cat,
        "range": {"min": min(prices), "max": max(prices)} if prices else None,
        "partial": bool(items) and spent is None and any_qty,
        # 图表数据：前端画饼图，PDF 也用它（见 _budget_chart 的说明）
        "chart": _budget_chart(items, spent, budget),
    }


def _num(v: Any) -> float | None:
    """宽松取数：模型可能给 "6" 这种字符串。取不到返回 None。"""
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def build_report_doc(state: dict) -> dict:
    """**采购规划报告** —— 一份能直接交出去的完整文档，不是一张表。

    ═══════════════════════════════════════════════════════════════════
    2026-09-27：为什么要有它
    ═══════════════════════════════════════════════════════════════════
    用户原话：「这个交付方式还是太简陋了…要么生成一个详细的采购规划报告
    而非这种非常敷衍不专业的几张表」。

    他说得对。原先三份「交付物」各自都只是一张表或一份清单，读者要自己在
    脑子里把三份拼起来 —— 而真实的采购规划交付物应该是一份**读完就能照着
    下单**的文档：先讲清楚这次要解决什么、约束是什么，再逐项给出推荐与
    理由，然后才是价格与预算，最后是风险与待办。

    这份报告**不是把三张表拼在一起**，而是按读者的顺序重新组织：
    结论在前、依据在后；每个数字都带出处；被排除的也写清楚为什么
    （否则用户不知道「为什么不是那个更便宜的」）。

    ⚠️ 内容全部来自**已有的结构化数据**（模型给的 why / 用量依据 /
    排除理由），不在这里另调一次模型 —— 那会让同一份 run 每次打开
    都得出不同的报告，用户没法核对。模型该说的它已经说过了。
    """
    items = plan_items(state)
    cands = state.get("candidates") or []
    excluded = effective_excluded(state)
    budget = _budget_yuan(state.get("budget"))
    total = plan_total(state)

    # ── 1. 摘要：整份报告最先被读到的三行 ──
    scene = state.get("scene") or state.get("subject") or "本次采购"
    if total is not None and budget:
        ratio = total / budget
        summary = (f"本次为「{scene}」规划了 {len(items)} 个品类的采购，"
                   f"估算总额 ¥{total:g}，占预算 ¥{budget:g} 的 {ratio * 100:.0f}%"
                   + (f"，结余 ¥{budget - total:g}。" if budget > total else "。"))
    elif total is not None:
        summary = f"本次为「{scene}」规划了 {len(items)} 个品类的采购，估算总额 ¥{total:g}。"
    elif items:
        summary = (f"本次为「{scene}」选出 {len(items)} 件商品，"
                   f"但**用量未能估出**，因此没有总额 —— 见下方各自说明。")
    else:
        summary = f"本次「{scene}」未选出合适的商品。"

    # 每个品类一段。这一段是报告的主体 —— 要能照着它下单。
    sections: list[dict] = []
    for i in items:
        cat = item_category(i)
        price = _num(i.get("price_yuan"))
        qty = _num(i.get("quantity"))
        sub = _num(i.get("subtotal"))
        # 同品类的备选：让读者知道「还有别的选择、为什么没选它」
        alts = [
            {"name": cand_name(c), "price": cand_yuan(c)}
            for c in cands
            if item_category(c) == cat and cand_name(c) != str(i.get("name") or "")
        ][:3]
        # 同品类被排除的：解释「为什么不是那个更便宜的」
        outs = [
            {"name": cand_name(c), "price": cand_yuan(c),
             "reason": str(c.get("_reason") or "")}
            for c in excluded if item_category(c) == cat
        ][:4]
        sections.append({
            "category": cat,
            "name": str(i.get("name") or ""),
            "price": price,
            "quantity": qty,
            "quantity_basis": str(i.get("quantity_basis") or ""),
            "subtotal": sub,
            "why": str(i.get("why") or ""),
            "alternatives": alts,
            "excluded": outs,
        })

    return {
        "kind": "report",
        "title": f"{scene} · 采购规划报告",
        "subject": state.get("subject") or scene,
        "scene": state.get("scene") or "",
        "budget": state.get("budget") or "",
        "duration": state.get("duration") or "",
        "constraints": [str(c) for c in (state.get("constraints") or [])],
        "summary": summary,
        # 报告开头的一组关键数字
        "headline": {
            "categories": len(items),
            "total": total,
            "budget": budget,
            "remaining": (budget - total) if (total is not None and budget) else None,
            "ratio": (total / budget) if (total is not None and budget and budget > 0) else None,
            "candidates": len(cands),
            "excluded": len(excluded),
        },
        "thesis": plan_why(state),
        "sections": sections,
        "chart": _budget_chart(items, total, budget),
        "risks": [str(r) for r in (state.get("risks") or [])],
        "dimensions": [str(d) for d in (state.get("dimensions") or [])],
        "generated_note": (
            "本报告由采购规划智能体推演生成。商品与价格为淘宝实时返回的真实数据；"
            "用量为依据场景常识的**估算**，下单前请自行核对。"
        ),
    }


def _budget_chart(items: list[dict], total: float | None, budget: float | None) -> dict:
    """预算分配的图表数据（前端用 echarts 画，PDF 里自己画）。

    ⚠️ 只给**数据**，不在这里生成图片。两个原因：
      · 前端已经有 echarts，能画交互式图表（hover 看数值），比静态图好；
      · 后端画图要么多一个依赖，要么手搓 SVG —— 没必要。

    没有小计的品类**不进饼图**（用 0 会画出误导性的扇区），
    但在 `missing` 里列出来，让调用方如实说明「这几类没算进去」。
    """
    parts, missing = [], []
    for i in items:
        sub = _num(i.get("subtotal"))
        if sub is None:
            missing.append(item_category(i))
            continue
        parts.append({"name": item_category(i), "value": round(sub, 2)})

    return {
        "type": "pie",
        "unit": "元",
        "series": parts,
        "total": total,
        "budget": budget,
        # 结余单独一项 —— 不放进饼图，否则「没花的钱」看起来像花掉了
        "remaining": (round(budget - total, 2)
                      if (total is not None and budget and budget > total) else None),
        "missing": missing,
    }


def budget_chart(state: dict) -> dict:
    """给预算表的图表数据（与报告里的同一个）。"""
    return _budget_chart(plan_items(state), plan_total(state),
                         _budget_yuan(state.get("budget")))


DELIVERABLE_BUILDERS = {
    "d-report": build_report_doc,
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

    if kind == "report":
        # 报告不是「三张表拼起来」，而是按读者的顺序重新组织：
        # 结论在前、依据在后；每个数字都带出处；排除的也写清为什么。
        h = doc.get("headline") or {}
        L += [f"> {doc.get('summary') or ''}", ""]
        L += [
            f"- 采购对象：{doc.get('subject') or '—'}",
            f"- 场景：{doc.get('scene') or '—'}",
            f"- 预算：{doc.get('budget') or '—'}",
            f"- 周期：{doc.get('duration') or '—'}",
        ]
        if doc.get("constraints"):
            L.append(f"- 硬约束：{'、'.join(doc['constraints'])}")
        L += [
            "",
            f"- 入选品类：{h.get('categories', 0)} 个",
            f"- 浏览候选：{h.get('candidates', 0)} 件（排除 {h.get('excluded', 0)} 件）",
        ]
        if h.get("total") is not None:
            L.append(f"- 估算总额：¥{h['total']:g}")
        if h.get("ratio") is not None:
            L.append(f"- 预算占用：{h['ratio'] * 100:.0f}%"
                     + (f"，结余 ¥{h['remaining']:g}" if h.get("remaining") is not None else ""))

        if doc.get("thesis"):
            L += ["", "## 整体取舍", "", str(doc["thesis"])]

        # 图表数据渲染成一张 markdown 表 —— 下载的文件里也要看得见构成
        ch = doc.get("chart") or {}
        if ch.get("series"):
            L += ["", "## 预算构成", "", "| 品类 | 金额 | 占比 |", "|---|---:|---:|"]
            tot = ch.get("total") or sum(x["value"] for x in ch["series"])
            for x in ch["series"]:
                pct = f"{x['value'] / tot * 100:.0f}%" if tot else "—"
                L.append(f"| {x['name']} | ¥{x['value']:g} | {pct} |")
            L.append(f"| **合计** | **¥{tot:g}** | 100% |")
            if ch.get("remaining"):
                L.append(f"| 未动用 | ¥{ch['remaining']:g} | — |")
            if ch.get("missing"):
                L.append("")
                L.append(f"> ⚠️ {'、'.join(ch['missing'])} 未估出用量，未计入上表。")

        idx = 0
        for sec in doc.get("sections") or []:
            idx += 1
            cat = sec.get("category") or f"第 {idx} 项"
            L += ["", f"## {idx}. {cat}", "", f"**推荐：{sec.get('name') or '—'}**", ""]
            if sec.get("price") is not None:
                line = f"- 单价：¥{sec['price']:g}"
                if sec.get("quantity"):
                    line += f" × {sec['quantity']:g}"
                    if sec.get("subtotal") is not None:
                        line += f" = ¥{sec['subtotal']:g}"
                L.append(line)
            if sec.get("quantity_basis"):
                L.append(f"- 用量依据：{sec['quantity_basis']}")
            if sec.get("why"):
                L += ["", f"{sec['why']}"]
            if sec.get("alternatives"):
                L += ["", "同品类其他候选："]
                for a in sec["alternatives"]:
                    pr = f"　¥{a['price']:g}" if a.get("price") else ""
                    L.append(f"- {a['name']}{pr}")
            if sec.get("excluded"):
                L += ["", "已排除："]
                for e in sec["excluded"]:
                    pr = f"　¥{e['price']:g}" if e.get("price") else ""
                    L.append(f"- {e['name']}{pr} —— {e.get('reason') or '不满足硬约束'}")

        if doc.get("risks"):
            L += ["", "## 风险与待确认", ""]
            L += [f"- {r}" for r in doc["risks"]]
        if doc.get("dimensions"):
            L += ["", "## 评估维度", "", "、".join(doc["dimensions"])]
        L += ["", "---", "", doc.get("generated_note") or ""]

    elif kind == "plan":
        L += [
            f"- 采购对象：{doc.get('subject') or '—'}",
            f"- 场景：{doc.get('scene') or '—'}",
            f"- 预算：{doc.get('budget') or '—'}",
            f"- 周期：{doc.get('duration') or '—'}",
        ]
        if doc.get("constraints"):
            L.append(f"- 硬约束：{'、'.join(doc['constraints'])}")
        L += ["", "## 建议购买", ""]
        picks = doc.get("picks") or ([doc["pick"]] if doc.get("pick") else [])
        for p in picks:
            price = p.get("price")
            head = f"**{p.get('name')}**"
            if p.get("category"):
                head = f"[{p['category']}] {head}"
            L.append(head + (f"　¥{price:g}" if price else ""))
            if p.get("quantity") and p.get("subtotal") is not None:
                L.append(f"- 用量 {p['quantity']:g}"
                         + (f"（{p['quantity_basis']}）" if p.get("quantity_basis") else "")
                         + f"，小计 ¥{p['subtotal']:g}")
            elif p.get("quantity_basis"):
                L.append(f"- {p['quantity_basis']}")
            if p.get("why"):
                L.append(f"- 理由：{p['why']}")
            L.append("")
        if doc.get("total") is not None:
            L += [f"**整套合计：¥{doc['total']:g}**", ""]
        if picks:
            src = "模型判断" if picks[0].get("by") == "llm" else "规则兜底"
            L.append(f"（判断来源：{src}）")
        if doc.get("why"):
            L += ["", f"> {doc['why']}"]

        if doc.get("alternatives"):
            L += ["", "## 备选（同品类）", ""]
            for a in doc["alternatives"]:
                pr = f"　¥{a['price']:g}" if a.get("price") else ""
                cat = f"[{a['category']}] " if a.get("category") else ""
                L.append(f"- {cat}{a['name']}{pr}")
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
        # 按品类分组渲染 —— 买一套时 40 行平铺看不出「床这一项比了什么」
        for g in (doc.get("groups") or [{"category": "", "rows": doc.get("rows") or []}]):
            if g.get("category"):
                L += [f"### {g['category']}", ""]
            L += ["| 候选 | 价格 | 结论 | 依据 |", "|---|---|---|---|"]
            for r in g.get("rows") or []:
                pr = f"¥{r['price']:g}" if r.get("price") else "—"
                L.append(f"| {r['name']} | {pr} | {r.get('tag') or ''} | {r.get('reason') or ''} |")
            L.append("")
        c = doc.get("counts") or {}
        L += ["", f"共 {c.get('candidates', 0)} 个候选，排除 {c.get('excluded', 0)} 个，"
                 f"入选 {c.get('picked', 0)} 件。"]

    elif kind == "budget":
        b = doc.get("budget")
        L += [f"- 预算：{'¥%g' % b if b else '—'}"]
        # 口径决定怎么写 —— 不把单价伪装成总花费（见 build_budget_doc 的说明）
        if doc.get("caliber") == "total":
            L.append(f"- 估算花费：¥{doc['spent']:g}")
            if doc.get("remaining") is not None:
                L.append(f"- 结余：¥{doc['remaining']:g}")
            if doc.get("ratio") is not None:
                L.append(f"- 预算占用：{doc['ratio'] * 100:.0f}%")
        elif doc.get("caliber") == "unit_only":
            up = doc.get("unit_price")
            L += [
                f"- 选中商品单价：¥{up:g}",
                "",
                "> ⚠️ **未含用量估算** —— 上面是单价，不是整件事的总花费。"
                "要算总价，还需要知道覆盖面积/用量。",
            ]
        rng = doc.get("range")
        if rng:
            L += ["", f"候选价格区间：¥{rng['min']:g} – ¥{rng['max']:g}"]
        if doc.get("items"):
            L += ["", "## 明细", ""]
            for it in doc["items"]:
                cat = f"[{it['category']}] " if it.get("category") else ""
                line = f"- {cat}{it.get('name') or ''}"
                if it.get("quantity") and it.get("subtotal") is not None:
                    line += f"　{it['quantity']:g} 份 × ¥{it['unit_price']:g} = ¥{it['subtotal']:g}"
                elif it.get("unit_price"):
                    line += f"　¥{it['unit_price']:g}"
                L.append(line)

    return "\n".join(L) + "\n"
