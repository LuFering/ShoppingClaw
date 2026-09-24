"""采购规划各阶段的**纯实现** —— 无事件、无 DB、无副作用。

为什么要拆成纯函数（方案 §3.5 的落地方式）：
  同一套阶段逻辑有两个消费方 ——
    · `planning_service._advance()` —— 驱动流程、写事件、维护图快照
    · `graph.py` 的 LangGraph 节点 —— 声明流程骨架，可用于单测/可视化
  若两处各写一份，必然分叉。所以逻辑只在这里写一遍：纯函数进、纯数据出，
  「写事件」和「改图」留给调用方。

本轮的范围是**取数是真的、推理是薄的**：
  · `search_candidates` 真调淘宝 MCP
  · `retrieve_dimensions` / `retrieve_risks` 真查 RAG
  · 取舍与排序先用可解释的占位规则（见 `pick_best`），
    后续把 LLM 判断接进来时**只改这几个函数**，事件契约与前端都不用动。
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
    """按名取一个 buildin 工具（RAG 类在这里）。"""
    try:
        from src.agents.common.toolkits.registry import get_all_tool_instances

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


async def retrieve_dimensions(subject: str) -> list[str]:
    """clarify：查品类知识，得到该品类该看的评估维度。

    查不到用通用维度兜底 —— 不能因为知识库没收录就卡住整条流程。
    """
    raw = await _call(await _builtin_tool("query_category_knowledge"),
                      {"category": subject}, RAG_TIMEOUT)
    return _as_str_list(raw) or ["价格", "口碑", "售后"]


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


def pick_best(cands: list[dict]) -> dict | None:
    """compare：选首要候选。

    占位规则：价格最低者 —— 可解释、可复现，且不会因为模型抖动而变化。
    后续接多维度评分时改这里，图与事件契约都不动。
    """
    priced = [c for c in cands if c.get("price_yuan")]
    if not priced:
        return cands[0] if cands else None
    return min(priced, key=lambda c: float(c["price_yuan"]))


async def retrieve_risks(subject: str) -> list[str]:
    """risk：查售后/风控政策。"""
    raw = await _call(await _builtin_tool("query_risk_policy"),
                      {"query": subject}, RAG_TIMEOUT)
    return _as_str_list(raw) or ["长期持有成本待确认"]


def deliver_question(state: dict) -> dict:
    """deliver：**故意停一次**等用户拍板。

    工作台右栏浮出问题卡是它的核心体验 —— 全程不打断反而看不出
    「agent 会停下来等你」。返回 None 表示不问（当前实现总是问）。
    """
    return {
        "text": f"预算要不要放宽？现有候选都逼近 {(state.get('budget') or '上限')}。",
        "phase": "deliver",
        "options": [
            {"key": "keep", "label": "不放宽", "primary": False},
            {"key": "raise", "label": "放宽一档", "primary": True},
        ],
    }
