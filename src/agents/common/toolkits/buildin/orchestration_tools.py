"""编排层工具集（2026-09-22 新增）—— 主智能体专属。

背景：
  主智能体的编排卡上「使用 Skill / 检索 RAG / 调用 MCP」三栏，内容此前是
  `orchestration_composer.py` 里**硬编码的常量**，其中两个 MCP 服务
  （sc.subagent-registry / sc.session-memory）在项目里根本不存在。

  本模块提供**真实可调用**的编排层工具，让那三栏有据可依：
    · list_subagents        —— 决定「该派谁」（读 subagents.yaml，确定性）
    · query_orchestration_sop —— 编排手艺（走向量检索，4 份 SOP 已入库）
    · find_archive          —— 判断「有没有历史档案」（读 shopping_decisions）

设计取舍：
  · `list_subagents` 直读 yaml 而不走向量检索 —— 目录是**确定性数据**，
    用 embedding 反而可能漏掉某个 slug；直读保证「有几个就返回几个」。
  · `query_orchestration_sop` 走 knowledge_manager —— SOP 是**静态方法论**，
    语义检索合适（「送礼怎么派」与「给妈妈挑礼物」需要模糊匹配）。
  · `find_archive` 直查 DB —— 用户档案是**运行时数据**，不该进向量库。

护栏：
  这三个工具都是**路由元数据**，不碰商品/订单/支付，
  不违反 MAIN_AGENT_GUARDRAILS.forbidden_tools（禁的是搜索/出卡/下单/物流）。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field
from sqlalchemy import select

from src.agents.common.toolkits.registry import tool
from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_business import ShoppingDecision

logger = logging.getLogger(__name__)

# subagents.yaml 的位置（与 master_agent/graph.py 的 load_subagent 保持一致）
# 本文件在 src/agents/common/toolkits/buildin/ → 上溯 4 层到 src/agents/
_SUBAGENTS_YAML = (
    Path(__file__).resolve().parent.parent.parent.parent / "subagents" / "subagents.yaml"
)

# slug → 展示名（与 orchestration_composer.SUBAGENT_DISPLAY_NAME 同源）
_DISPLAY = {
    "pre_purchase": "购前助手",
    "post_purchase": "购后助手",
}


def _display(slug: str) -> str:
    return _DISPLAY.get(slug, slug)


# ── 输入模型 ──


class QuerySopInput(BaseModel):
    intent: str = Field(
        ...,
        description="本轮意图的自然语言描述，如「给妈妈挑生日礼物」「对比两款手机」",
    )


class FindArchiveInput(BaseModel):
    target: str = Field(..., description="要查的购物对象，如「降噪耳机」")


# ── 工具实现 ──


@tool(
    category="buildin",
    tags=["编排", "路由", "子智能体"],
    display_name="列出可派遣的子智能体",
    icon="🧭",
)
def list_subagents() -> str:
    """列出当前可派遣的全部子智能体及其职责边界。

    主智能体在决定「该派谁」时调用。返回**确定性**结果 ——
    直接读 subagents.yaml，保证与配置逐字一致（不走向量检索，
    避免因语义相似度漏掉某个 slug）。
    """
    try:
        if not _SUBAGENTS_YAML.exists():
            return f"错误: 找不到子智能体配置 {_SUBAGENTS_YAML}"
        cfg = yaml.safe_load(_SUBAGENTS_YAML.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.error(f"[Tool] 读取 subagents.yaml 失败: {exc}")
        return f"读取子智能体配置失败: {exc}"

    lines = [f"当前可派遣 {len(cfg)} 个子智能体：", ""]
    for slug, spec in cfg.items():
        desc = (spec.get("description") or "").strip().replace("\n", " ")
        tools = spec.get("tools") or []
        lines.append(f"## {_display(slug)}（subagent_type=\"{slug}\"）")
        lines.append(f"- 职责：{desc}")
        lines.append(f"- 工具数：{len(tools)}")
        lines.append("")
    lines.append('派遣方式：调用 `task` 工具，`subagent_type` 填上面的 slug。')
    return "\n".join(lines)


@tool(
    category="buildin",
    tags=["编排", "SOP", "方法论"],
    display_name="检索编排方法论",
    icon="📐",
    args_schema=QuerySopInput,
)
async def query_orchestration_sop(intent: str) -> str:
    """按本轮意图检索对应的编排方法论（SOP）。

    适用场景：送礼推荐、横向对比、使用复盘、意图过泛需澄清。
    返回该类场景的**编排路线**（派谁、串行还是并行、关键约束、汇总话术）。

    参数:
        intent: 本轮意图的自然语言描述
    """
    logger.info(f"[Tool] 检索编排 SOP: {intent}")
    try:
        from src.knowledge.manager import knowledge_manager

        result = await knowledge_manager.query_knowledge(
            query=intent,
            category="编排 SOP",
            source_types=["framework"],
            top_k=2,
        )
        if not result or not str(result).strip():
            return (
                "未检索到匹配的编排方法论。请按通用原则处理："
                "先判断该派购前（找货）还是购后（归档），"
                "无数据依赖时并行、有依赖时串行。"
            )
        return result
    except Exception as exc:
        logger.error(f"[Tool] 检索编排 SOP 失败: {exc}")
        return f"检索失败: {exc}"


@tool(
    category="buildin",
    tags=["编排", "档案", "路由"],
    display_name="查购物档案",
    icon="🗂️",
    args_schema=FindArchiveInput,
)
async def find_archive(user_id: str, target: str) -> str:
    """查用户是否已有某个购物对象的档案记录。

    主智能体据此判断：该走「复盘」（已有档案）还是「重新选」（无档案）。
    只返回**路由元数据**（记录 id / 阶段 / 时间），不返回商品与订单内容。

    参数:
        user_id: 用户ID
        target: 要查的购物对象（如「降噪耳机」）
    """
    logger.info(f"[Tool] 查购物档案: user={user_id} target={target}")
    try:
        # ⚠️ 不要用 _as_user_pk()：那是给 users.id（integer 列）用的。
        #    shopping_decisions.user_id 是 **character varying**，
        #    套转换会报 `operator does not exist: character varying = integer`
        #    （实测踩过）。这里按字符串直接匹配。
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(ShoppingDecision).where(
                    ShoppingDecision.user_id == str(user_id)
                )
            )
            rows = list(result.scalars().all())
    except Exception as exc:
        logger.error(f"[Tool] 查档案失败: {exc}")
        return f"查询失败: {exc}"

    if not rows:
        return f"该用户没有任何购物档案记录（共 0 条）。可派购前助手新建。"

    # 按 target 做包含匹配（档案里 target 是自然语言，如「Sony WH-1000XM5 头戴式降噪耳机」）
    kw = (target or "").strip().lower()
    hits = []
    for r in rows:
        data = r.data or {}
        t = str(data.get("target") or "").lower()
        if kw and (kw in t or any(part and part in t for part in kw.split())):
            hits.append(data)

    if not hits:
        return (
            f"未找到与「{target}」相关的档案（该用户共有 {len(rows)} 条记录）。"
            f"可派购前助手新建。"
        )

    lines = [f"找到 {len(hits)} 条相关档案：", ""]
    for d in hits:
        lines.append(
            f"- {d.get('target')} | 阶段：{d.get('phase')} | "
            f"预算：{d.get('budget') or '未填'} | id：{d.get('id')}"
        )
    lines.append("")
    lines.append("提示：已有档案时，用户回问「值不值」应走复盘（派购后助手），而不是重新选。")
    return "\n".join(lines)
