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
import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

MCP_TIMEOUT = 90
RAG_TIMEOUT = 30
SEARCH_PAGE_SIZE = 6


# ══════════════════════════════════════════════════════════════════════
# 中栏档案：**开放式条目**，不再是固定五组
# ══════════════════════════════════════════════════════════════════════
# 2026-09-28 重构。用户的原话：
#
#   「执行流一开始就写完了近半的档案，然后后续思考时多以调用为主……
#     需要重新设计档案，让 agent 每执行一步都有机会写档案，增删操作
#     等都能对档案执行」
#
# 实测确认：run gr-d2eda02e1748 的 164 条事件里，五组档案全在第 8~12 条
# （全程 **7%**），剩下 93% 一条都没写，最终停在「档案完整 3/5」。
#
# 根因是**结构**不是节奏：旧实现只有 read_history / read_preferences 两个
# 工具写档案，而 build_profile 是「固定 5 个 key 的白名单筛选」——最多
# 5 条，结构上不可能继续长。
#
# 现在档案是**扁平条目列表**，每条：
#     {id, rail, text, because, source, at}
# `rail`（栏名）是**开放集合**：下面这组只是**建议**，写进工具文档让模型
# 有默认结构可循；模型可以自建新栏。
#
# ⚠️ 建议栏名**刻意换了一套**（用户明确否决了旧五组：
#    「可以预设一些常驻栏名，但是不能是这几个，因为之前的测试就是这几个，
#      结果效果不佳」）。
#
# 选这组的关键判据：**每一栏的数据来自不同的步骤** —— 这才是生长能分步
# 发生的根本原因。旧五组全部依赖开头那两次查询，所以一次性写满；
# 新栏名里有四栏的数据在**后面**几步才产生。
#
#     人物信息    读历史 / 读偏好之后，由模型归纳写入
#     送礼往来    读历史（送过什么、什么被排除过）
#     在意什么    读偏好
#     行情锚点    检索之后 —— 真实搜到的价格带
#     这盒的取舍  比价之后 —— 排除了什么、为什么
#     这盒怎么搭  组合之后
SUGGESTED_RAILS = (
    ("person", "人物信息"),
    ("history", "送礼往来"),
    ("cares", "在意什么"),
    ("market", "行情锚点"),
    ("triage", "这盒的取舍"),
    ("pairing", "这盒怎么搭"),
)

# 栏名（中文，模型写的就是它）→ 展示元数据。
# ⚠️ 用**中文栏名**做键，因为模型写进 `rail` 的就是中文字符串；
# 另存一份英文 key 只为了前后端约定的稳定 id（图标查表用）。
RAIL_BY_KEY = {k: label for k, label in SUGGESTED_RAILS}
KEY_BY_RAIL = {label: k for k, label in SUGGESTED_RAILS}

RAIL_ICONS = {
    "person": "people", "history": "gift", "cares": "heart",
    "market": "search", "triage": "minus", "pairing": "link",
}
# 自建栏拿不到专属图标时用这个 —— 不编一个不存在的
RAIL_ICON_FALLBACK = "dot"
# 「禁忌」语义仍要危险色：任何栏名里带这些字就按危险区渲染
DANGER_HINTS = ("禁忌", "忌讳", "不能", "过敏", "avoid")


def rail_key(rail: str) -> str:
    """栏名 → 稳定 key。自建栏返回规范化后的自身（前端据此取兜底图标）。"""
    r = str(rail or "").strip()
    if not r:
        return "misc"
    return KEY_BY_RAIL.get(r) or f"x-{rail_norm(r)}"


def is_danger_rail(rail: str) -> bool:
    """这一栏是不是「禁忌」类 —— 前端据此走危险色分区。

    从**栏名文字**判断，而不是查死表：模型自建「海鲜过敏」这类栏时
    也该进危险区，否则最要命的信息会被当成普通条目渲染。
    """
    r = str(rail or "")
    return any(h in r for h in DANGER_HINTS)


def rail_norm(text: str) -> str:
    """条目定位用的规范化。

    ⚠️ 从 `screen_candidates` 的 `_norm` 提上来的 —— 那里踩过的坑同样
    适用于这里：模型会**把价格/标点一起写进文本**（「颈椎按摩仪 ¥1350」），
    直接按原文字符串相等去匹配会全部落空。实测那次「排除 8 件」实际
    生效 0 件，模型的意图被静默丢弃。

    所以做两级匹配：先试原文精确相等，再试规范化后的相等/包含。
    """
    t = str(text or "").strip()
    t = re.sub(r"[\s¥￥\d.,，。;；:：]+$", "", t)      # 去价格尾巴与收尾标点
    t = re.sub(r"\s+", "", t)                          # 去内部空白
    return t


def next_entry_id(items: list[dict]) -> str:
    """给新条目分配稳定 id（前端 key / 去重用）。

    ⚠️ 不能靠 `len(items)+1` —— 删过条目之后会撞号，前端 v-for 的 key
    重复会让 Vue 复用到错误的 DOM 节点（表现为「删了一条，结果另一条变了」）。

    ⚠️ 也**不能只认模型写的那几条**：入口 seed 的那条（人物信息）也要有 id。
    自测抓到过 —— seed 那条 id 为 None，于是它与模型写的第一条抢同一个
    号码，前端整列 key 是 null。所以 id 分配必须**统一走这里**。
    """
    mx = 0
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        m = re.fullmatch(r"p(\d+)", str(it.get("id") or ""))
        if m:
            mx = max(mx, int(m.group(1)))
    return f"p{mx + 1}"


def group_by_rail(items: list[dict]) -> list[dict]:
    """扁平条目 → 按栏分组，**保持栏目首次出现的顺序**。

    两处要用同一份分组逻辑（工具回显给模型 / 前端渲染），所以收在这里 ——
    各写一遍必然漂（本仓库既有教训）。
    """
    order: list[str] = []
    buckets: dict[str, list[dict]] = {}
    for it in items or []:
        if not isinstance(it, dict):
            continue
        rail = str(it.get("rail") or "其他").strip() or "其他"
        if rail not in buckets:
            buckets[rail] = []
            order.append(rail)
        buckets[rail].append(it)
    return [
        {
            "rail": rail,
            "key": rail_key(rail),
            "icon": RAIL_ICONS.get(rail_key(rail), RAIL_ICON_FALLBACK),
            "danger": is_danger_rail(rail),
            "items": buckets[rail],
        }
        for rail in order
    ]


def fold_profile(ops: list[dict]) -> list[dict]:
    """把 op 日志折成**当前档案条目列表**。纯函数、确定性。

    ⚠️ 为什么不让工具直接算全量列表（原来的做法）：模型会**并行**调多个
    write_profile（实测同一条消息里两个 call）。各自读同一份旧 state、
    各自算「完整新列表」、再整体覆盖 —— **后者把前者的结果整个丢掉**。
    id 实证：p2 先被写成「送礼往来」，随后被并行的那次顶成「行情锚点」，
    整条送礼往来消失，而且没有任何 drop 事件。

    现在工具只**追加一条 op**，当前值在这里折出来：
      add    → 追加一条（id 按顺序分配，只增不改，所以稳定）
      update → 按文本定位后改写
      drop   → 按文本定位后删除
    追加语义下并行调用各追加各的，不会互相覆盖；折叠是纯函数，
    重放/乱序都得到同一结果。
    """
    items: list[dict] = []
    for op in (ops or []):
        if not isinstance(op, dict):
            continue
        kind = str(op.get("op") or "add").strip().lower()
        text = str(op.get("text") or "").strip()
        because = str(op.get("because") or "").strip()
        rail = str(op.get("rail") or "").strip()

        if kind == "add":
            if not text:
                continue
            # 同栏同文不重复（模型多轮里常重复写同一条）
            dup = any(
                str(i.get("rail") or "").strip() == rail
                and rail_norm(i.get("text")) == rail_norm(text)
                for i in items
            )
            if dup:
                continue
            items.append({
                "id": next_entry_id(items),
                "rail": rail or "其他",
                "text": text,
                "because": because,
                "source": op.get("source") or "本次推演",
                "state": "confirmed",
            })

        elif kind == "update":
            i = locate_entry(items, text)
            if i < 0:
                continue
            new_text = str(op.get("to") or "").strip()
            if not new_text:
                continue
            items[i]["text"] = new_text
            if because:
                items[i]["because"] = because
            items[i]["state"] = "confirmed"

        elif kind == "drop":
            i = locate_entry(items, text)
            if i >= 0:
                items.pop(i)

    return items


def locate_entry(items: list[dict], text: str) -> int:
    """按文本定位条目下标，找不到返回 -1。

    两级匹配：原文精确 → 规范化后相等/包含。见 `rail_norm` 的说明 ——
    模型会把价格和标点一起写进文本，只做精确匹配会全部落空
    （screen_candidates 那次「排除 8 件、实际生效 0 件」就是这么来的）。
    """
    raw = str(text or "").strip()
    if not raw:
        return -1
    for i, it in enumerate(items):
        if str(it.get("text") or "").strip() == raw:
            return i
    n = rail_norm(raw)
    if not n:
        return -1
    for i, it in enumerate(items):
        if rail_norm(it.get("text")) == n:
            return i
    for i, it in enumerate(items):
        t = rail_norm(it.get("text"))
        if t and (n in t or t in n):
            return i
    return -1


def build_profile_summary(items: list[dict]) -> dict:
    """档案抬头 —— 取代旧的 `completeness: "档案完整 3/5"`。

    ⚠️ 旧的分母是固定的 5（PROFILE_KEYS 的长度），那是**架构决定的**；
    骨架拆掉后分母不存在了，留着「N/5」就是**假数字**：
    agent 写到第 6 条时它还是 5，自建新栏时它也不会变。
    所以改成**真实条数** —— 就是 len(items)，不加任何修饰。
    """
    grouped = group_by_rail(items)
    return {
        "count": len([i for i in (items or []) if isinstance(i, dict)]),
        "rails": len(grouped),
    }


def build_rail_hint() -> str:
    """给模型的「可用栏名」提示串（写进工具文档）。"""
    return "、".join(f"「{label}」" for _k, label in SUGGESTED_RAILS)

# ══════════════════════════════════════════════════════════════════════
# 「推演所得」—— 中栏的第二类内容，**随推演逐步长出来**
# ══════════════════════════════════════════════════════════════════════
# 2026-09-27：调研 Letta（原 MemGPT）后改的。它的做法是：agent 在整轮工作里
# **持续改写**自己的记忆块（系统提示明写「发现新的用户偏好就写进记忆块」），
# 而不是开头算一次。它的 `human` 块初始内容也很有意思 —— 不是空白，而是
# 一句诚实的「我还没认识这个人」，加一段「我打算怎么去了解」。
#
# 对照我们这边：5 组档案确实只在 understand 一个节点产出（那是数据本身
# 决定的，硬摊开就是造假）。但**推演过程中真的在产生新信息** —— 搜了哪些
# 方向、排除了什么、为什么这么搭配 —— 这些现在只进了右栏交付物。
# 把它们回流到中栏，生长就是真的：不用多跑一次模型，不用 sleep 演节奏。
#
# ⚠️ 与 `PROFILE_KEYS` 分开命名，不混进「人物档案」：
#   前者的主语是**收礼人**（她喜欢什么、忌讳什么）
#   后者的主语是**这次推演**（我们查了什么、排除了什么、怎么搭的）
# 混在一起会让「已知喜好：颈椎按摩仪」这种话看起来像她的喜好，其实是我们的检索词。
RUN_FINDING_KEYS = ("searched", "excluded", "pairing")

RUN_FINDING_LABELS = {
    "searched": "搜过的方向",
    "excluded": "已排除",
    "pairing": "搭配逻辑",
}
RUN_FINDING_ICONS = {
    "searched": "search", "excluded": "minus", "pairing": "link",
}


def build_run_finding(key: str, *, keywords=None, excluded=None, plan=None) -> dict | None:
    """组装一条「推演所得」。没有真实内容时返回 None —— **不编**。

    三条各自的真实来源：
      searched  检索阶段实际用过的关键词（`_kw`，来自 search_candidates）
      excluded  比价验货阶段真正排掉的商品与理由（带 why，不删）
      pairing   组合阶段模型给出的搭配逻辑（plan.thesis）
    """
    if key == "searched":
        kws = [str(k).strip() for k in (keywords or []) if str(k).strip()]
        # 去重保序：同一方向可能搜多轮
        kws = list(dict.fromkeys(kws))
        if not kws:
            return None
        return {
            "key": "searched",
            "label": RUN_FINDING_LABELS["searched"],
            "icon": RUN_FINDING_ICONS["searched"],
            "text": "、".join(kws[:6]),
            "note": f"共 {len(kws)} 个方向" if len(kws) > 1 else "",
            "state": "derived",
            "source": "本次检索",
            # ⚠️ 这是**累加型**的：模型每搜一次词，列表就长一点。前端按 key
            # 原地更新（而不是追加新块）—— 否则搜 4 次会出 4 个「搜过的方向」，
            # 每个都比上一个长。实测就是这么冒出来的 4 条重复。
            "accumulate": True,
        }

    if key == "excluded":
        rows = [e for e in (excluded or []) if isinstance(e, dict)]
        if not rows:
            return None
        names = [str(e.get("name") or "")[:14] for e in rows[:3]]
        # 理由取第一条 —— 同批排除的理由通常同源（超预算 / 配件 / 场景不符）
        why = str((rows[0].get("why") or "")).strip()
        return {
            "key": "excluded",
            "label": RUN_FINDING_LABELS["excluded"],
            "icon": RUN_FINDING_ICONS["excluded"],
            "text": f"{len(rows)} 件：" + "、".join(n for n in names if n),
            "note": why[:60],
            "state": "derived",
            "source": "本次比价",
            "accumulate": True,   # 同 searched：分批排除，原地更新
        }

    if key == "pairing":
        p = plan or {}
        thesis = str(p.get("thesis") or "").strip()
        items = [i for i in (p.get("items") or []) if isinstance(i, dict)]
        if not thesis and not items:
            return None
        # 搭配的构成：主力/搭配/点缀 + 各自名字，这是模型给的真实角色划分
        roles = [
            f"{i.get('role') or '一件'}：{str(i.get('name') or '')[:12]}"
            for i in items[:3]
        ]
        return {
            "key": "pairing",
            "label": RUN_FINDING_LABELS["pairing"],
            "icon": RUN_FINDING_ICONS["pairing"],
            "text": thesis[:80] if thesis else "、".join(roles),
            "note": " · ".join(roles) if thesis and roles else "",
            "state": "derived",
            "source": "本次组合",
        }

    return None


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

# ══════════════════════════════════════════════════════════════════════
# 档案读取：**拆成两次独立调用**
# ══════════════════════════════════════════════════════════════════════
# 2026-09-27：原先是一个函数内部串行调两个工具、都返回后才组装五组档案，
# 于是中栏在**第 25ms** 一次亮出全部五组，之后再无变化 —— 看起来是一张
# 静态卡片，而不是「随推演逐步长出来的档案」（用户的反馈）。
#
# 拆开后有个真实的好处：这两次调用本来就是**两次独立的 RAG 往返**
# （实测 understand 节点总耗时 5.4s），各自的返回支撑不同的档案组：
#   · recall_past_decisions   → 历史 → 关系/生活状态/禁忌
#   · get_user_shopping_context → 偏好 → 已知喜好
# 所以「先后到达」是真实的，不是人为拉长的。逐批推送即可做出诚实的生长感。
#
# ⚠️ user_id 必须**显式传**，不能靠 with_user_id + bind_user_id 注入：
# 这两个工具的 user_id **声明在 args_schema 里**（与 create_monitor_task
# 那类「schema 里没有、靠 runtime 注入」的不同）。LangChain 的 StructuredTool
# 会**先按 args_schema 校验、再调用**，所以无论怎么包装 coroutine，校验都在
# 包装器之前 —— 实测报 `user_id Field required`，异常被 `_call` 吞掉返回 None，
# 于是「读档案」永远读不到东西，界面照样显示「读了 0 条历史」，看着像档案本来
# 就是空的。我们是调用方，本来就该给出「这是谁」。

# ══════════════════════════════════════════════════════════════════════
# 工具返回的是 **markdown 文本**，不是 JSON —— 必须按文本解析
# ══════════════════════════════════════════════════════════════════════
# 2026-09-27：这是「档案永远读不到东西」的真正根因。
#
# `get_user_shopping_context` 返回的是：
#
#     ### 用户综合购物上下文
#     **1. 长期偏好**: {'brand_preference': '华为', 'gift_recipient': '妈妈', ...}
#     **2. 最近5条历史决策**: 暂无数据
#     ...
#
# 而这里原先用 `_parse_jsonish` 直接 `json.loads` —— 那段文本不是合法 JSON，
# 于是返回 None，`data.get("preferences")` 拿不到东西，**偏好永远是空列表**。
# 实测一次 run：understand 节点 63ms 就跑完，证据写着「读了 0 条历史、
# 0 条偏好」，而用户的 preferences 里白纸黑字写着「妈妈 / 生日礼物 / 预算 1500」。
#
# 所以这里按 markdown 的实际形状解析：找 `**N. 长期偏好**: ` 之后的那个
# Python 字面量（注意工具用的是 `str(dict)`，是**单引号**的 Python repr，
# 不是 JSON），用 ast.literal_eval 读它。
def _extract_prefs_dict(text: Any) -> dict:
    """从工具返回的 markdown 里抠出「长期偏好」那个字典。

    返回 {} 表示没抠到 —— 调用方据此如实显示「暂无记录」，不编造。
    """
    if not isinstance(text, str) or not text:
        return {}
    # 定位「长期偏好」那一行
    m = re.search(r"长期偏好\*\*[:：]\s*(\{.*?\})\s*(?:\n|$)", text, re.S)
    if not m:
        return {}
    raw = m.group(1).strip()
    # 工具用的是 str(dict)（Python repr，单引号），优先 literal_eval；
    # 万一将来改成 JSON 也能接住。
    try:
        import ast
        val = ast.literal_eval(raw)
        return val if isinstance(val, dict) else {}
    except (ValueError, SyntaxError):
        try:
            val = json.loads(raw)
            return val if isinstance(val, dict) else {}
        except (ValueError, TypeError):
            return {}


async def read_history(state: dict) -> list[dict]:
    """读与「送某人」相关的历史决策记录。

    ═══════════════════════════════════════════════════════════════════
    2026-09-27：改读 `shopping_decisions` 表 —— 原先那个工具查错了地方
    ═══════════════════════════════════════════════════════════════════
    原先走 `recall_past_decisions`，而那个工具查的是
    `users.config_json.history` —— **那是个从没被写入过的字段**
    （实测用户 7 的 config_json 里只有 `preferences` 一个键）。
    真正的历史决策在 `shopping_decisions` 表里（同一用户有 10 条）。
    于是这个函数永远返回空，界面显示「读了 0 条历史」，看着像档案本来就是空的。

    这里直接查表 —— 与 `archive_tools._load_record` 同一张表、同一个
    归属口径（`user_id` 是 String(64)，与其它表一致）。

    匹配策略：先按收礼人/场合做**宽松**过滤（记录名里含「妈妈」等），
    取不到就返回**最近的几条**而不是空 —— 「送过什么」本身就是有用的
    上下文，不该因为名字对不上就当作没有。仍取不到才是真的空。
    """
    uid = str(state.get("user_id") or "")
    if not uid:
        return []
    recipient = str(state.get("recipient") or "").strip()
    occasion = str(state.get("occasion") or "").strip()
    try:
        from sqlalchemy import desc, select

        from src.storage.postgres.manager import pg_manager
        from src.storage.postgres.models_business import ShoppingDecision

        async with pg_manager.get_async_session_context() as session:
            r = await session.execute(
                select(ShoppingDecision)
                .where(ShoppingDecision.user_id == uid)
                .order_by(desc(ShoppingDecision.created_at))
                .limit(20)
            )
            rows = list(r.scalars().all())
    except Exception as e:
        logger.warning(f"[gift] 读历史失败（按无档案继续）: {e}")
        return []

    def _blob(row) -> str:
        d = row.data or {}
        # 记录里可能叫 target / title / aiRecommend，全拼起来做匹配
        return " ".join(str(d.get(k) or "") for k in
                        ("target", "title", "aiRecommend", "forWhom", "scenario"))

    # 先挑与收礼人/场合沾边的
    hits = [row for row in rows
            if recipient and recipient in _blob(row)]
    if not hits and occasion:
        hits = [row for row in rows if occasion in _blob(row)]
    # 都没沾上就用最近的几条兜底 —— 「送过什么」比「什么都没读过」有用
    picked = hits[:5] if hits else rows[:3]

    out = []
    for row in picked:
        d = row.data or {}
        out.append({
            "target": d.get("target") or d.get("title") or "",
            "phase": row.phase,
            "for_whom": d.get("forWhom") or "",
            "summary": d.get("aiSummary") or "",
            "recommend": d.get("aiRecommend") or "",
        })
    return [x for x in out if x["target"] or x["recommend"]]


async def read_preferences(state: dict) -> list[Any]:
    """读该用户的长期偏好。

    ⚠️ 工具返回的是 **markdown 文本**而不是 JSON —— 原先用 `_parse_jsonish`
    解析必然得到 None（见 `_extract_prefs_dict` 的说明）。这里按文本形状抠。
    抠不到返回空列表 —— 调用方如实显示「暂无记录」，不编造。
    """
    try:
        ctx = await _builtin_tool("get_user_shopping_context")
        if ctx is None:
            return []
        raw = await _call(ctx, {"user_id": str(state.get("user_id") or "")}, RAG_TIMEOUT)
        prefs = _extract_prefs_dict(raw)
        if not prefs:
            return []
        # 归一成 [{key, value}]，与 build_profile 里读 prefs 的形状一致
        return [{"key": str(k), "value": str(v)} for k, v in prefs.items()][:12]
    except Exception as e:
        logger.warning(f"[gift] 读偏好失败（按无档案继续）: {e}")
        return []


async def read_recipient_context(state: dict) -> dict:
    """读该用户的历史决策与画像，抽出与「送某人」相关的线索。

    保留这个组合入口给**不需要分批**的调用方（测试、以及将来可能的别处）。
    图里改用 `read_history` / `read_preferences` 两次调用以便分批推送。
    """
    history = await read_history(state)
    prefs = await read_preferences(state)
    return {
        "history": history,
        "prefs": prefs,
        # raw_ok 的原意是「至少有一次工具调用真的返回了东西」。
        # 拆开后按「任一非空」判定 —— 语义不变，且不必再多传一个标志。
        "raw_ok": bool(history or prefs),
    }


def seed_profile(state: dict) -> list[dict]:
    """入口就确定的那一条：**人物信息**（关系 + 场合 + 预算）。

    这是全档案里唯一**不需要任何查询**就成立的信息 —— 用户自己填的。
    旧实现把这类信息混在「固定五组」里一次性写满；现在只写这一条，
    让后面的信息必须由模型在**真实拿到结果之后**才写。

    ⚠️ 只写用户明确给过的字段。`budget` 是这次送礼的约束，不是「她的特点」，
    所以跟「这次要送生日礼」放同一条里，不另立一栏冒充人物特征。
    """
    recipient = str(state.get("recipient") or "").strip()
    occasion = str(state.get("occasion") or "").strip()
    budget = state.get("budget") or 0
    if not recipient and not occasion:
        return []

    bits = [b for b in (recipient, occasion) if b]
    text = " · ".join(bits)
    if budget:
        text += f"（预算 ¥{budget}）"
    item = {
        "rail": "人物信息",
        "text": text,
        "because": "你在入口页填的：送给谁 / 什么场合 / 预算",
        "source": "入口参数",
        "state": "confirmed",
    }
    item["id"] = next_entry_id([])      # p1
    return [item]


def seed_history_entry(history: list[dict]) -> list[dict]:
    """读完历史后，用它**真实**写一条「送礼往来」。

    只在真读到记录时才产生 —— 读不到就不写（旧实现在这种情况下会写一条
    「未记录」，那是**空槽冒充内容**，会让条数虚高）。
    """
    rows = [h for h in (history or []) if isinstance(h, dict)]
    if not rows:
        return []
    names = []
    for h in rows[:3]:
        n = str(h.get("target") or h.get("recommend") or "").strip()
        if not n:
            continue
        phase = str(h.get("phase") or "").strip()
        names.append(f"{n}（{phase}）" if phase else n)
    if not names:
        return []

    # 「已排除」是最该单独说清的 —— 它是禁忌的来源
    dropped = [
        str(h.get("target") or h.get("recommend") or "")[:14]
        for h in rows if str(h.get("phase") or "") == "dropped"
    ]
    text = "、".join(names)
    entry = {
        "rail": "送礼往来",
        "text": f"以往 {len(rows)} 条：{text}",
        "because": f"读历史决策记录，返回 {len(rows)} 条",
        "source": "购物档案 · 历史决策",
    }
    out = [entry]
    if dropped:
        out.append({
            "rail": "明确禁忌",
            "text": "、".join([d for d in dropped if d]),
            "because": "历史决策里 phase=dropped 的记录 —— 曾明确排除",
            "source": "购物档案 · 已排除记录",
        })
    return out


def seed_prefs_entry(prefs: list[dict]) -> list[dict]:
    """读完偏好后，用它真实写一条「在意什么」。

    复用旧 `build_profile` 里那段筛选逻辑（SELF_USE / 数值剔除），
    因为它的判据是被实测验证过的：用户 7 的 12 条偏好**全部**是
    「他自己要买笔记本电脑」的（laptop_* / brand_preference / max_budget），
    没有一条关于收礼人 —— 那些铺进档案会得出「妈妈喜欢华为 16 英寸笔记本」
    这种荒谬结论。

    ⚠️ 筛完为空时**返回空列表**（而不是写一条「暂无记录」）：
    读到了但与本场景无关，和「什么都没读到」是两件事，前者不该占档案条数。
    """
    if not prefs:
        return []

    def _kv(p):
        if isinstance(p, dict):
            return str(p.get("key") or ""), str(p.get("value") or "")
        return "", str(p)

    RELEVANT = ("gift", "recipient", "mom", "dad", "occasion")
    SELF_USE = ("laptop", "headphone", "phone", "computer", "car", "self",
                "brand_preference", "max_budget", "use_scenario",
                "category_interest", "chosen_model", "size_preference")

    def _numeric(v: str) -> bool:
        return bool(re.fullmatch(r"[\d\s.,¥￥]+", (v or "").strip()))

    def _is_self_use(k: str) -> bool:
        kl = (k or "").lower()
        return any(t in kl for t in SELF_USE)

    pairs = [_kv(x) for x in prefs if _kv(x)[1]]
    pairs = [(k, v) for k, v in pairs if not _is_self_use(k)]
    if not pairs:
        return []

    def _score(kv):
        k, v = kv
        kl = (k or "").lower()
        s = 0
        if any(t in kl for t in RELEVANT):
            s -= 4
        if _numeric(v):
            s += 3
        if len(v) <= 2:
            s += 1
        return s

    chosen = sorted(pairs, key=_score)[:4]
    texts = list(dict.fromkeys(v for _k, v in chosen if v))
    if not texts:
        return []
    return [{
        "rail": "在意什么",
        "text": " · ".join(texts),
        "because": f"读长期偏好，筛出 {len(texts)} 条与收礼人相关的",
        "source": "购物档案 · 偏好记录",
    }]


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


async def search_candidates_for(state: dict, keyword: str) -> list[dict]:
    """按**模型给的关键词**搜一次真实商品（ReAct 工具用）。

    与 `search_candidates` 的区别：后者用 `build_search_keywords` 拼出来的
    几个词（那是写死流程时的产物）。模型自己决定搜什么时，一次只搜一个词 ——
    它看到结果会自己决定要不要换个词再搜。

    同样给每件打 `_kw`：组合阶段靠它保证品类多样（不打的后果实测过 ——
    两个关键词之一是「保温杯」时，组合会连着挑 3 个保温杯）。
    """
    from src.services.task_executors.common import parse_search_result

    kw = str(keyword or "").strip()
    if not kw:
        return []
    tool = await _mcp_tool("taobao_searchMaterial")
    raw = await _call(tool, {"q": kw, "page_size": SEARCH_PAGE_SIZE}, MCP_TIMEOUT)
    if raw is None:
        return []
    found = [{**it, "_kw": kw} for it in parse_search_result(raw)]

    seen, uniq = set(), []
    for it in found:
        key = str(it.get("item_id") or it.get("title"))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
    return uniq[:SEARCH_PAGE_SIZE]


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


def cand_name(c: dict) -> str:
    """候选商品名。

    ⚠️ **必须用这个，不要直接 `c["name"]`** —— search_candidates 返回的是
    MCP 的**原始结果**，字段是 `title`；事件层归一后才叫 `name`。
    两种形状在这一条链路上并存（规划那边同样如此）。

    实测踩过：工具里写 `c.get("name")`，恒为 None，界面上商品名全是
    「None ¥91」——价格也是从**别处**取的，看着像「有价格没名字」。
    """
    return str(c.get("name") or c.get("title") or "未命名")


def cand_cents(c: dict) -> int:
    """候选价格的**分**。取不到返回 0（与「真的是 0 元」不作区分 ——
    送礼场景 0 元商品没有意义，不值得为它区分）。
    """
    if c.get("price_yuan") is not None:
        try:
            return int(float(c["price_yuan"]) * 100)
        except (TypeError, ValueError):
            return 0
    try:
        return int(c.get("price") or 0)
    except (TypeError, ValueError):
        return 0


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
        # ⚠️ 用 `cand_name` / `cand_cents`，不要 `p["name"]` ——
        # picked 里是 MCP 原始结果（字段叫 `title`，价格是**分**）。
        # 实测写 p["name"] 直接 KeyError，被 _emit_deliverables_for 的
        # except 吞成一条 warning，于是「候选对比」这份交付物**永远是空的**。
        rows.append({
            "name": cand_name(p), "price": price_of_yuan(cand_cents(p)),
            "fit": 9 - i, "use": "入选", "tag": "入选",
        })
    for e in excluded[:5]:
        rows.append({
            "name": cand_name(e), "price": price_of_yuan(cand_cents(e)),
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
    # 同一套口径：picked 是 MCP 原始候选，名字在 `title` 上
    by_name = {cand_name(p): p for p in picked}
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
