"""送礼推演各阶段的**实现**。

设计：**取数与计算用工具，判断与措辞用模型。**

  · `read_recipient_context` / `search_candidates` —— 真调工具（档案、淘宝 MCP）
  · `decide_understanding` / `decide_combination` / `write_message` —— 真调模型

═══════════════════════════════════════════════════════════════════════
2026-09-25 修正：这里原先**一行模型调用都没有**
═══════════════════════════════════════════════════════════════════════

初版把「推理薄」做成了「推理零」：理解是拼字符串、选件是 `min(price)`、
寄语是 f-string 模板。阶段间隔只有 3–11 毫秒 —— 那是函数调用，不是思考。
界面上却呈现成「对比 6 款，暂定…」这种像推理的措辞，等于用文案掩盖了
没有推理这件事。

现在每个「判断」节点都真的问模型，并保留**可解释性**：
模型必须连 `why`（为什么是它）一起给出，理由指不回依据的一律不采纳。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

MCP_TIMEOUT = 90
RAG_TIMEOUT = 30
SEARCH_PAGE_SIZE = 6


# ── 中栏档案五组：key 固定（前端 ProfileCard 按 key 取图标与分区）──
PROFILE_KEYS = ("relation", "life", "likes", "taboo", "giftpref")

PROFILE_LABELS = {
    "relation": "关系与称谓",
    "life": "生活状态",
    "likes": "已知喜好",
    "taboo": "明确禁忌",
    "giftpref": "送礼偏好",
}
PROFILE_ICONS = {
    "relation": "people", "life": "life", "likes": "heart",
    "taboo": "ban", "giftpref": "gift",
}

# ── 右栏六类交付物（key 固定，前端 DeliverPanel 按 key 渲染）──
DELIVERABLE_KEYS = ("plan", "compare", "budget", "message", "supply", "order")
DELIVERABLE_LABELS = {
    "plan": "礼盒方案", "compare": "候选对比", "budget": "预算分配",
    "message": "寄语文案", "supply": "货源与配送", "order": "送礼订单",
}

# ── 左栏七步（key 固定，前端 ExploreStream 按 key 找步骤）──
STEPS = (
    ("understand", "理解关系"),
    ("extract", "提取需求"),
    ("search", "检索商品"),
    ("verify", "比价验货"),
    ("exclude", "排除候选"),
    ("combine", "组合礼盒"),
    ("message", "生成寄语"),
)
STEP_LABELS = dict(STEPS)

# 收礼人 → 关系称谓的兜底映射（档案里读不到时用）
RELATION_HINT = {
    "妈妈": "母亲", "爸爸": "父亲", "老婆": "配偶", "老公": "配偶",
    "女朋友": "恋人", "男朋友": "恋人", "女儿": "子女", "儿子": "子女",
    "同事": "同事", "朋友": "朋友", "客户": "客户",
}


# ══════════════════════════════════════════════════════════
# 工具访问（与 planning 同法，避免两套写法）
# ══════════════════════════════════════════════════════════

async def _mcp_tool(name: str):
    try:
        from src.services.mcp_service import get_tools_from_all_servers
        from src.services.mcp_tool_adapter import adapt_mcp_tools

        specs = await get_tools_from_all_servers()
        tools = await adapt_mcp_tools(specs)
        return next((t for t in tools if getattr(t, "name", "") == name), None)
    except Exception as e:
        logger.warning(f"[gift] MCP 工具 {name} 加载失败: {e}")
        return None


async def _builtin_tool(name: str):
    """按名取一个 buildin 工具。

    ⚠️ 从**包** `toolkits` 导入，不要从子模块 `toolkits.registry` ——
    包 `__init__.py` 会先 import 各工具包触发 `@tool` 注册，子模块不会，
    拿到的是空列表，于是每个 RAG 调用静默落到兜底分支。
    （详见 planning/stages.py 同函数的说明。）
    """
    try:
        from src.agents.common.toolkits import get_all_tool_instances

        return next(
            (t for t in get_all_tool_instances() if getattr(t, "name", "") == name), None
        )
    except Exception as e:
        logger.warning(f"[gift] 内置工具 {name} 加载失败: {e}")
        return None


async def _call(tool, args: dict, timeout: int) -> Any | None:
    if tool is None:
        return None
    try:
        return await asyncio.wait_for(tool.ainvoke(args), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(f"[gift] 工具 {getattr(tool,'name','?')} 超时")
        return None
    except Exception as e:
        logger.warning(f"[gift] 工具 {getattr(tool,'name','?')} 失败: {e}")
        return None


# ══════════════════════════════════════════════════════════
# 模型调用
# ══════════════════════════════════════════════════════════
#
# 胶水代码（取模型 / 问一次 / 抠 JSON / 收敛编号）统一放在
# `src/agents/independent/common_llm.py` —— 与规划 agent 共用一份。
# 这里只保留本 agent 的用法。

from src.agents.independent.common_llm import (  # noqa: E402
    as_idx,
    degrade_note,
    parse_json_block,
)
from src.agents.independent.common_llm import ask_model as _ask


async def ask_model(system: str, user: str) -> str:
    """问一次模型。失败返回空串，由调用方降级到规则。"""
    return await _ask(system, user, tag="gift")


def _parse_jsonish(raw: Any) -> Any:
    """工具返回可能是 str / dict / list，统一成 Python 对象。失败返回 None。"""
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(str(raw))
    except (ValueError, TypeError):
        return None


# ══════════════════════════════════════════════════════════
# ① 理解关系 —— 真读档案
# ══════════════════════════════════════════════════════════

async def read_recipient_context(state: dict) -> dict:
    """读该用户的历史决策与画像，抽出与「送某人」相关的线索。

    真调 `recall_past_decisions` + `get_user_shopping_context`。
    读不到就返回空 —— **不编造档案**（零幻觉红线，送礼场景尤其致命：
    编一个「她喜欢香水」而实际过敏，这份礼物就废了）。
    """
    recipient = str(state.get("recipient") or "").strip()
    out: dict[str, Any] = {"history": [], "prefs": [], "raw_ok": False}

    try:
        uid = str(state.get("user_id") or "")

        # ═══════════════════════════════════════════════════════════════
        # user_id 必须**显式传**，不能靠 with_user_id + bind_user_id 注入
        # ═══════════════════════════════════════════════════════════════
        #
        # 这两个工具的 `user_id` **声明在 args_schema 里**（与
        # `create_monitor_task` 那类「schema 里没有、靠 runtime 注入」的工具不同）。
        # LangChain 的 StructuredTool 会**先按 args_schema 校验参数、再调用**，
        # 所以无论怎么包装 coroutine，校验都在包装器之前发生 ——
        # 实测报 `user_id Field required`，异常被 `_call` 吞掉返回 None，
        # 于是「读档案」永远读不到东西，而界面照样显示「读了 0 条历史」，
        # 看起来像档案本来就是空的。
        #
        # 我们是调用方，本来就该给出「这是谁」——显式传既过校验，也不涉及
        # 模型编造 id 的问题（那是模型自己填参数时的风险）。
        recall = await _builtin_tool("recall_past_decisions")
        ctx = await _builtin_tool("get_user_shopping_context")

        if recall is not None and recipient:
            raw = await _call(recall, {"user_id": uid, "topic": recipient}, RAG_TIMEOUT)
            data = _parse_jsonish(raw)
            if isinstance(data, list):
                out["history"] = data[:5]
            out["raw_ok"] = out["raw_ok"] or raw is not None

        if ctx is not None:
            raw2 = await _call(ctx, {"user_id": uid}, RAG_TIMEOUT)
            data2 = _parse_jsonish(raw2)
            if isinstance(data2, dict):
                prefs = data2.get("preferences") or data2.get("long_term_preferences") or []
                if isinstance(prefs, list):
                    out["prefs"] = prefs[:8]
            out["raw_ok"] = out["raw_ok"] or raw2 is not None
    except Exception as e:
        logger.warning(f"[gift] 读档案失败（按无档案继续）: {e}")

    return out


def build_profile(state: dict, ctx: dict) -> list[dict]:
    """按「读到的真实档案」组装中栏五组。

    三态语义（前端硬要求）：
      confirmed 已确认 —— 来自档案或用户明确表达
      inferred  智能推测 —— 由上下文推出，但无直接依据
      pending   待确认 —— 需要用户点头

    **没读到就标 pending**，不假装 confirmed。
    """
    recipient = str(state.get("recipient") or "")
    occasion = str(state.get("occasion") or "")
    budget = state.get("budget") or 0
    history = ctx.get("history") or []
    prefs = ctx.get("prefs") or []

    rel = RELATION_HINT.get(recipient, recipient or "收礼人")
    has_history = bool(history)

    groups: list[dict] = []

    # ① 关系与称谓
    groups.append({
        "key": "relation",
        "label": PROFILE_LABELS["relation"],
        "icon": PROFILE_ICONS["relation"],
        "text": f"{rel} · {recipient or '收礼人'}" + (f" · {occasion}" if occasion else ""),
        "state": "confirmed" if recipient else "pending",
        "source": "本次描述" if recipient else "待你补充",
    })

    # ② 生活状态 —— 档案里没有这类字段，只能推测
    groups.append({
        "key": "life",
        "label": PROFILE_LABELS["life"],
        "icon": PROFILE_ICONS["life"],
        "text": "暂无足够依据",
        "note": "（档案里没有生活状态类记录）",
        "state": "pending" if not has_history else "inferred",
        "source": "历史记录" if has_history else "待你补充",
    })

    # ③ 已知喜好 —— 真取用户偏好
    if prefs:
        texts = []
        for p in prefs[:3]:
            if isinstance(p, dict):
                texts.append(str(p.get("value") or p.get("key") or ""))
            else:
                texts.append(str(p))
        text = " · ".join([t for t in texts if t])
        groups.append({
            "key": "likes",
            "label": PROFILE_LABELS["likes"],
            "icon": PROFILE_ICONS["likes"],
            "text": text or "暂无记录",
            "state": "confirmed",
            "source": "购物档案 · 偏好记录",
        })
    else:
        groups.append({
            "key": "likes",
            "label": PROFILE_LABELS["likes"],
            "icon": PROFILE_ICONS["likes"],
            "text": "暂无记录",
            "state": "pending",
            "source": "待你补充",
        })

    # ④ 明确禁忌 —— 这个必须来自真实记录，不能猜（猜错的代价最高）
    taboos = [
        h for h in history
        if isinstance(h, dict) and str(h.get("phase") or "") == "dropped"
    ]
    if taboos:
        names = [str(t.get("target") or t.get("title") or "")[:12] for t in taboos[:2]]
        groups.append({
            "key": "taboo",
            "label": PROFILE_LABELS["taboo"],
            "icon": PROFILE_ICONS["taboo"],
            "text": "、".join([n for n in names if n]),
            "note": "—— 曾明确排除，本次不再考虑",
            "state": "confirmed",
            "danger": True,
            "source": "购物档案 · 已排除记录",
        })
    else:
        groups.append({
            "key": "taboo",
            "label": PROFILE_LABELS["taboo"],
            "icon": PROFILE_ICONS["taboo"],
            "text": "未记录",
            "note": "—— 有忌讳请直接告诉我，这类信息不能靠推断",
            "state": "pending",
            "danger": True,
            "source": "待你补充",
        })

    # ⑤ 送礼偏好 —— 来自本次勾选的 signals
    signals = state.get("signals") or []
    if signals:
        groups.append({
            "key": "giftpref",
            "label": PROFILE_LABELS["giftpref"],
            "icon": PROFILE_ICONS["giftpref"],
            "text": "、".join(str(s) for s in signals),
            "state": "confirmed",
            "source": "本次描述 · 你的选择",
        })
    else:
        groups.append({
            "key": "giftpref",
            "label": PROFILE_LABELS["giftpref"],
            "icon": PROFILE_ICONS["giftpref"],
            "text": "待确认",
            "state": "pending",
            "source": "待你确认",
        })

    return groups


def build_profile_head(state: dict, profile: list[dict]) -> dict:
    """档案抬头。completeness 按**真实**已确认组数算，不写死。"""
    recipient = str(state.get("recipient") or "收礼人")
    confirmed = sum(1 for g in profile if g.get("state") == "confirmed")
    return {
        "name": recipient,
        "initial": recipient[:1] if recipient else "礼",
        "meta": RELATION_HINT.get(recipient, recipient),
        "sub": f"{state.get('occasion') or '送礼'} · 预算 ¥{state.get('budget') or '—'}",
        "completeness": f"档案完整 {confirmed}/{len(profile)}",
    }


# ══════════════════════════════════════════════════════════
# ② 提取需求 / ③ 检索 / ④ 比价 / ⑤ 排除
# ══════════════════════════════════════════════════════════

async def build_understanding(state: dict, profile: list[dict], ctx: dict) -> dict:
    """「当前理解」—— 用模型归纳这次送礼该落在什么上。

    这是**真推理**：把真实读到的档案 + 用户勾的在意点交给模型，
    让它归纳出一句判断。不是拼字符串。

    硬约束（写进 prompt）：只能用给你的档案项，读不到就说没有 ——
    这一步最容易出现「编一条偏好」（送礼场景代价最高）。
    """
    recipient = str(state.get("recipient") or "对方")
    occasion = str(state.get("occasion") or "这次")
    signals = [str(s) for s in (state.get("signals") or [])]
    confirmed = [
        f"- {g.get('label')}：{g.get('text')}（来源：{g.get('source')}）"
        for g in profile if g.get("state") == "confirmed"
        and g.get("key") in ("likes", "life", "taboo")
        and str(g.get("text") or "").strip() not in ("未记录", "暂无记录", "暂无足够依据", "待确认", "")
    ]
    pending = [
        f"- {g.get('label')}" for g in profile if g.get("state") == "pending"
    ]

    system = (
        "你是送礼顾问。任务：把已知信息归纳成**一句**判断，说明这次送礼"
        "应该落在什么上。\n\n"
        "铁律：\n"
        "1. 只用给你的信息，**不要补充任何没给的偏好或事实** —— 编造一条"
        "偏好会让用户照着买错东西。\n"
        "2. 没有可用信息时，就直说没有，并说明你会按什么通用方式处理。\n"
        "3. 这句话要能指回具体依据，不写空泛祝愿。\n"
        "4. **只输出一句话，60 字以内**。不要解释你为什么这么判断，"
        "不要罗列待补充项 —— 那些界面另有位置显示。"
    )
    user = (
        f"收礼人：{recipient}\n场合：{occasion}\n"
        f"用户更在意：{'、'.join(signals) if signals else '（未指定）'}\n\n"
        f"已确认的档案项：\n" + ("\n".join(confirmed) if confirmed else "（无）") + "\n\n"
        f"仍待确认的项：\n" + ("\n".join(pending) if pending else "（无）")
    )

    text = await ask_model(system, user)
    if text:
        return {"text": text[:200], "from": "模型归纳自中栏已确认的档案项", "by": "llm"}

    # ── 降级：模型不可用时用规则拼，并如实标注是规则给的 ──
    basis = "、".join(
        g["text"] for g in profile
        if g.get("state") == "confirmed" and g.get("key") in ("likes", "life")
        and str(g.get("text") or "").strip() not in ("未记录", "暂无记录", "暂无足够依据", "待确认", "")
    )
    if basis:
        t = f"这次重点不在贵不贵，而是「{basis}」能不能真的用上。"
        src = "规则兜底（模型不可用）"
    else:
        t = f"关于{recipient}暂无可用偏好记录，先按{occasion}的一般习惯来搭。"
        src = "无档案依据 · 规则兜底"
    return {"text": t, "from": src, "by": "rule"}


def build_search_keywords(state: dict) -> list[str]:
    """关键词不是「礼物」，而是**她实际会用到的东西**。

    这是送礼最反直觉的一条：搜「礼物」只会出来一堆礼盒包装与代写信，
    搜不出能用的东西。要搜的是品类词。

    ⚠️ 但**只有具体名词能用**。2026-09-24 实测（真实淘宝 MCP）：

        关键词            前 3 个结果
        「日常小家电」  → 服装、电钻工具套装     ❌ 抽象词被拆成「日常」「家电」
        「家居 实用」   → 义乌小商品、毛绒玩具   ❌ 组合词召回的是杂货
        「护手霜」      → 植护 / 香氛 / roopy   ✅
        「香薰」「保温杯」「按摩仪」「丝巾」     ✅ 全是真品类
        「茶 礼盒」     → 绿茶礼盒              ✅

    结论：**用 2-4 字的品类名词**，最多带一个「礼盒」这类修饰。
    用户勾的「实用 / 有心意」是抽象标签，必须翻译成具体商品，
    不能直接当关键词。
    """
    # 在意点 → 可搜的具体品类（每条都实测过）
    SIGNAL_TO_GOODS = {
        "实用": ["保温杯", "护手霜"],
        "有心意": ["香薰", "丝巾"],
        "惊喜感": ["香薰", "按摩仪"],
        "能天天用": ["保温杯", "护手霜"],
        "不放着落灰": ["保温杯", "茶 礼盒"],
        "仪式感": ["香薰", "茶 礼盒"],
        "健康": ["按摩仪", "茶 礼盒"],
    }
    # 收礼人 → 兜底品类
    RECIPIENT_TO_GOODS = {
        "妈妈": ["护手霜", "按摩仪"],
        "爸爸": ["保温杯", "茶 礼盒"],
        "老婆": ["香薰", "丝巾"],
        "老公": ["保温杯", "茶 礼盒"],
        "女朋友": ["香薰", "丝巾"],
        "男朋友": ["保温杯", "按摩仪"],
        "女儿": ["香薰", "睡眠"],
        "儿子": ["保温杯", "睡眠"],
        "同事": ["茶 礼盒", "保温杯"],
        "朋友": ["香薰", "茶 礼盒"],
        "客户": ["茶 礼盒", "丝巾"],
    }

    kws: list[str] = []
    for s in (state.get("signals") or []):
        kws.extend(SIGNAL_TO_GOODS.get(str(s), []))
    if not kws:
        kws = RECIPIENT_TO_GOODS.get(str(state.get("recipient") or ""), ["保温杯", "护手霜"])

    seen, out = set(), []
    for k in kws:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out[:2]


def _round_robin_by_kw(items: list[dict], limit: int) -> list[dict]:
    """按 `_kw`（品类）轮流取，最多 limit 件。

    抽出来是因为**两处需要同一件事**：检索结果的截断、组合时的选件。
    第一版两处各写一遍，其中一处漏了 `_kw` 透传，表现是「代码看着有分组、
    实际全是同一品类」—— 这类重复迟早分叉，所以只留一份。

    为什么必须轮流：同一关键词的结果天然同质（搜「保温杯」前 6 条全是保温杯）。
    顺序截断会让第二个关键词整个失效。
    """
    buckets: dict[str, list[dict]] = {}
    for it in items:
        buckets.setdefault(str(it.get("_kw") or "其他"), []).append(it)

    out: list[dict] = []
    idx = {k: 0 for k in buckets}
    while len(out) < limit:
        progressed = False
        for k in buckets:
            if len(out) >= limit:
                break
            if idx[k] >= len(buckets[k]):
                continue
            progressed = True
            out.append(buckets[k][idx[k]])
            idx[k] += 1
        if not progressed:
            break
    return out


async def search_candidates(state: dict) -> list[dict]:
    """真调淘宝 MCP。复用 parse_search_result，不写第二套解析。

    每条结果打上 `_kw`（来自哪个关键词）——**组合阶段靠它保证品类多样**。
    不打的后果实测过：两个关键词之一是「保温杯」时，组合会连着挑 3 个保温杯，
    那不是一个礼盒，是同一样东西买三遍。
    """
    from src.services.task_executors.common import parse_search_result

    tool = await _mcp_tool("taobao_searchMaterial")
    found: list[dict] = []
    for kw in build_search_keywords(state):
        raw = await _call(tool, {"q": kw, "page_size": SEARCH_PAGE_SIZE}, MCP_TIMEOUT)
        if raw is not None:
            for it in parse_search_result(raw):
                found.append({**it, "_kw": kw})
        if len(found) >= SEARCH_PAGE_SIZE * 2:
            break

    seen, uniq = set(), []
    for it in found:
        key = str(it.get("item_id") or it.get("title"))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)

    # ⚠️ 截断要**按品类轮流取**，不能直接 `uniq[:N]`。
    # 踩过的坑：第一个关键词（保温杯）返回 6 件、第二个（护手霜）6 件，
    # 合并后前 6 条全是保温杯 —— 直接截断就等于把第二个关键词整个丢掉，
    # 组合阶段拿到的候选全是同一品类，只能挑出「三个保温杯」。
    return _round_robin_by_kw(uniq, SEARCH_PAGE_SIZE)


def yuan(cents: Any) -> str:
    try:
        v = int(cents or 0)
    except (TypeError, ValueError):
        return ""
    return f"{v / 100:.0f}" if v else ""


def price_of_yuan(cents: Any) -> int:
    """分 → 元的整数（用于预算计算与前端展示）。"""
    try:
        return int(int(cents or 0) / 100)
    except (TypeError, ValueError):
        return 0


def verify_candidates(cands: list[dict], state: dict) -> tuple[list[dict], list[dict]]:
    """④ 比价验货 + ⑤ 排除候选，一次算完。

    为什么要合并：两步的判据是同一次比较的结果 —— 分开算要遍历两遍，
    且「入选」与「被排除」必须互补（不重不漏）。

    本轮的可解释规则（后续接 LLM 时改这里，事件契约不动）：
      · 预算上限：单价超过预算 60% 的排除（送礼要留组合空间）
      · 价格缺失：拿不到价格的排除（出不了方案）
      · 明显不相关：标题里含「配件 / 维修 / 租赁 / 定制咨询」的排除

    返回 (入选, 被排除)，被排除的**带 why**、不删除 ——
    这是 `.impeccable.md` 的「禁黑箱」：要能回答「为什么最后只剩这几件」。
    """
    budget = int(state.get("budget") or 0)
    single_cap = budget * 0.6 if budget else float("inf")

    picked: list[dict] = []
    excluded: list[dict] = []

    # ⚠️ 只匹配**明确是服务**的词。实测教训（2026-09-24）：
    # 原先还匹配「维修」，结果把「家电钻手工套装…维修多功能」这种
    # 真实商品排除了 —— 它在标题里是「用途」而不是「这是维修服务」。
    # 这类词一旦误伤，用户会觉得「明明能用的东西你为什么不要」。
    # 所以只留几乎不会出现在实物标题里的说法。
    NON_GOODS = ("租赁", "定制咨询", "运费", "差价", "代购服务", "上门服务")

    for i, c in enumerate(cands):
        title = str(c.get("title") or "未命名")
        price = price_of_yuan(c.get("price"))
        item = {
            "id": f"cand-{i}",
            "name": title[:36],
            "price": price,
            "item_id": c.get("item_id"),
            # 必须把 `_kw` 带下去 —— 组合阶段靠它保证品类多样。
            # 这里重建 dict 时漏掉过一次，表现是「三个候选全是保温杯」
            # 而代码看起来明明写了分组逻辑（分组键全成了「其他」）。
            "_kw": c.get("_kw"),
        }

        if not price:
            excluded.append({**item, "why": "拿不到价格，无法纳入预算"})
        elif any(w in title for w in NON_GOODS):
            excluded.append({**item, "why": "非实物商品（服务类）"})
        elif budget and price > single_cap:
            excluded.append({**item, "why": f"单价 ¥{price} 超过预算的 60%（留不出组合空间）"})
        else:
            picked.append(item)

    return picked, excluded


# ══════════════════════════════════════════════════════════
# ⑥ 组合礼盒 / ⑦ 寄语
# ══════════════════════════════════════════════════════════

async def combine(picked: list[dict], state: dict, understanding: dict) -> tuple[dict, list[dict], dict]:
    """⑥ 组合礼盒：**让模型挑并说明理由**。

    分工：
      · 模型负责「选哪几件、各承担什么角色、为什么是它」
      · 代码负责「预算不能超、品类不能重复」这类硬约束

    为什么硬约束不交给模型：它会算错预算，也会连着挑三个同类东西。
    为什么选与说必须交给模型：这是这份礼物的全部价值 ——
    规则排出来的顺序回答不了「为什么最后是这几件」。

    降级：模型不可用时退回「按品类轮流取」，并且理由如实写成规则口径，
    不假装是模型判断的。
    """
    budget = int(state.get("budget") or 0)
    recipient = str(state.get("recipient") or "对方")
    occasion = str(state.get("occasion") or "这次")

    if not picked:
        plan = {
            "title": "这次没能凑出一份方案",
            "thesis": "候选池是空的 —— 可能是关键词太窄，或数据源暂时不可用。"
                      "你可以补充一个具体的品类，我再试一轮。",
            "items": [],
        }
        return plan, [], {"total": 0, "budget": budget, "eta": "", "steps": []}

    # ── 硬约束先行：预算内、品类去重后的候选池 ──
    affordable = [it for it in picked if not budget or int(it.get("price") or 0) <= budget] or picked
    pool = _round_robin_by_kw(affordable, min(len(affordable), 8))

    # ── 交给模型挑 ──
    listing = "\n".join(
        f"{i}. {it.get('name')} ¥{it.get('price')}（来自检索「{it.get('_kw') or '—'}」）"
        for i, it in enumerate(pool)
    )
    confirmed = [
        f"- {g.get('label')}：{g.get('text')}"
        for g in (state.get("_profile") or [])
        if g.get("state") == "confirmed" and str(g.get("text") or "").strip()
        not in ("未记录", "暂无记录", "暂无足够依据", "待确认", "")
    ]

    system = (
        "你是送礼顾问。从候选里挑出**最多 3 件**组成一份礼物，并说明理由。\n\n"
        "判据是「**同时被用到**」—— 几件要落在同一个使用场景里，"
        "而不是各自最好。三件说得通胜过六件堆着。\n\n"
        "铁律：\n"
        "1. 只能从给定候选里挑，**不要虚构商品**，价格也不许改。\n"
        "2. 总数不得超过预算；不得超过 3 件。\n"
        "3. 每件都要给 `why`，且必须指回具体依据（收礼人的偏好 / 场景）。"
        "写「品质好」「性价比高」这类放在任何商品上都成立的话算无效。\n"
        "4. 若候选都不合适，就少挑几件，宁可 1 件也不要凑数。\n\n"
        "只输出 JSON，不要解释文字：\n"
        '{"title":"这份礼物的名字","thesis":"一句话说清这几件如何构成一体",'
        '"items":[{"idx":0,"role":"主力|搭配|点缀","why":"为什么是它"}]}'
    )
    user = (
        f"收礼人：{recipient}\n场合：{occasion}\n预算：{budget or '未指定'} 元\n"
        f"对这次的理解：{understanding.get('text') or '（无）'}\n"
        f"已确认的偏好：\n" + ("\n".join(confirmed) if confirmed else "（无）") + "\n\n"
        f"候选（编号：名称 价格）：\n{listing}"
    )

    raw = await ask_model(system, user)
    obj = parse_json_block(raw)

    chosen: list[dict] = []
    items: list[dict] = []
    used_llm = False

    if obj and isinstance(obj.get("items"), list) and obj["items"]:
        # 校验模型输出：编号合法、不超预算、不超件数。任一条不满足就整体降级 ——
        # 半信半疑地采纳一半，会产出「价格对不上」的方案，比纯规则更糟。
        spent_try = 0
        ok = True
        for i, it in enumerate(obj["items"][:3]):
            idx = as_idx(it.get("idx"))
            if idx is None or not (0 <= idx < len(pool)):
                ok = False
                break
            src = pool[idx]
            price = int(src.get("price") or 0)
            if budget and spent_try + price > budget:
                ok = False
                break
            spent_try += price
            chosen.append(src)
            items.append({
                "role": str(it.get("role") or ["主力", "搭配", "点缀"][i])[:8],
                "name": src["name"],
                "price": price,
                "why": str(it.get("why") or "")[:120],
            })
        if ok and items and all(x["why"] for x in items):
            used_llm = True
        else:
            chosen, items = [], []

    if not used_llm:
        # 降级必须看得见（见 common_llm.degrade_note 的说明）
        degrade_note(raw, obj, "gift/combine")
        # ── 降级：按品类轮流取（可解释、可复现）──
        spent = 0
        for it in pool:
            if len(chosen) >= 3:
                break
            price = int(it.get("price") or 0)
            if budget and spent + price > budget:
                continue
            chosen.append(it)
            spent += price
        if not chosen:
            chosen = [min(picked, key=lambda x: int(x.get("price") or 0))]
        seen_kw: set[str] = set()
        items = []
        for i, it in enumerate(chosen):
            kw = str(it.get("_kw") or "")
            if kw and kw not in seen_kw:
                why = f"检索「{kw}」时相关性最高的一件"
            elif kw:
                why = f"与「{kw}」主力同类，作备选补充"
            else:
                why = "同一批检索结果里相关性最高的一件"
            if kw:
                seen_kw.add(kw)
            items.append({
                "role": ["主力", "搭配", "点缀"][i] if i < 3 else "补充",
                "name": it["name"],
                "price": it.get("price") or 0,
                "why": why,
            })

    spent = sum(int(i.get("price") or 0) for i in items)
    plan = {
        "title": str((obj or {}).get("title") or f"给{recipient}的{occasion}")[:40],
        "thesis": str((obj or {}).get("thesis") or
                      f"{len(items)} 件落在同一个使用场景。")[:160],
        "items": items,
        "by": "llm" if used_llm else "rule",
    }
    budget_rows = [{"label": i["role"], "value": int(i.get("price") or 0)} for i in items]
    order = {
        "total": spent,
        "budget": budget,
        "eta": "以各商品页面为准",
        "steps": ["确认方案", "确认寄语", "下单", "配送到此地址"],
    }
    return plan, budget_rows, order


def build_compare(picked: list[dict], excluded: list[dict]) -> list[dict]:
    """候选对比表：入选与排除**放在同一张表里**（否则看不出取舍）。"""
    rows = []
    for i, p in enumerate(picked[:5]):
        rows.append({
            "name": p["name"], "price": p.get("price") or 0,
            "fit": 9 - i, "use": "入选", "tag": "入选",
        })
    for e in excluded[:5]:
        rows.append({
            "name": e["name"], "price": e.get("price") or 0,
            "fit": 2, "use": "—", "tag": "排除",
        })
    return rows


async def build_message(state: dict, plan: dict, understanding: dict) -> dict:
    """⑦ 寄语文案 —— 由模型写，素材必须是前面每一步的真实判断。

    `.impeccable.md` 的「禁黑箱」在情感语境的翻译：
    寄语里每一句都要能指回某一步的依据，不是通用祝福。

    降级（模型不可用）时退回模板，并标注来源 —— 不假装是模型写的。
    """
    recipient = str(state.get("recipient") or "你")
    occasion = str(state.get("occasion") or "这次")
    items = plan.get("items") or []
    item_lines = "\n".join(f"- {i['role']}：{i['name']}（{i['why']}）" for i in items)
    signals = "、".join(str(x) for x in (state.get("signals") or []))

    system = (
        f"你要替用户给「{recipient}」写一张送礼卡片（{occasion}）。\n\n"
        "要求：\n"
        "1. 三段结构：称呼 → 挑了什么 → 为什么。收尾一句轻的，不要升华。\n"
        "2. **素材只能用给你的这些**，不要编造共同经历或对方的事。\n"
        "3. 语气按关系来：给长辈平实、少形容词；给伴侣具体；给同事克制。\n"
        "4. 禁止「感恩」「一路有你」「未来可期」这类放在任何人身上都成立的模板句。\n"
        "5. 不要提价格、折扣、购买渠道。\n"
        "6. 只输出卡片正文，不要标题、不要解释。"
    )
    user = (
        f"收礼人：{recipient}\n场合：{occasion}\n"
        f"用户更在意：{signals or '（未指定）'}\n"
        f"这次的理解：{understanding.get('text') or '（无）'}\n\n"
        f"挑了这些：\n{item_lines}"
    )

    text = await ask_model(system, user)
    if text:
        return {"tone": "真诚", "text": text[:800], "by": "llm"}

    names = "、".join([i["name"][:10] for i in items[:3]]) or "这份礼物"
    t = (
        f"{recipient}：\n\n这次挑的是{names}。\n\n"
        f"{understanding.get('text') or ''}\n\n"
        f"挑它们时想的不是贵不贵，是你会不会真的用上。"
    )
    return {"tone": "真诚", "text": t, "by": "rule"}


def build_supply(picked: list[dict], plan: dict) -> list[dict]:
    """货源与配送：取自真实候选的 item_id（能指回具体商品）。"""
    by_name = {p["name"]: p for p in picked}
    out = []
    for it in (plan.get("items") or []):
        src = by_name.get(it["name"]) or {}
        out.append({
            "item": it["name"][:20],
            "from": "淘宝",
            "eta": "以商品页为准",
            "note": f"item_id {str(src.get('item_id') or '')[:12]}" if src.get("item_id") else "",
        })
    return out
