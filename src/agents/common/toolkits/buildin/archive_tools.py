"""购物档案工具集（2026-09-22 新增）—— 购后助手专属工具。

背景：
  购后助手（post_purchase）此前从未被派发过：它没有能产生用户可见价值的
  工具，而 new_signals 也没有任何消费方。前端契约里早已定义了
  save_to_archive / update_record_phase / set_reminder / write_review
  四个工具与对应组件，但后端从未注册 —— 链路是断的。

本文件补齐这四个工具，并规定为购后助手专属。
new_signals 双向落库：用户偏好 + 购物档案。

设计约束：
  1. ShoppingRecord 字段与前端 decisions_seed.js 对齐，否则档案页读出来
     是缺字段的半残记录。
  2. 记录 id 由后端生成，避免与前端生成的 nd-1 / us-3 撞号。
  3. 全部写操作 try/except 包裹 —— 归档失败不能打断对话。
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select

from src.agents.common.toolkits.registry import tool
from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_business import ShoppingDecision, User

logger = logging.getLogger(__name__)

ARCHIVE_PHASES = ("need", "candidate", "decided", "using", "dropped")


def _norm_reminder(r: Any) -> "dict | None":
    """把一条提醒归一成 {id, text, at, done}。

    历史上有两种形状（实测 DB 里并存）：
      · 老：前端种子写的裸字符串  "下单前确认接口供电"
      · 新：本模块写的对象        {id, due, done, text, createdAt}
    前端两处消费方（档案页 / 对话里的 ReminderListTool）都按对象读，
    裸字符串会渲染成空行。这里统一升级成对象，读-改-写时顺带把老数据洗掉。
    """
    if isinstance(r, str):
        text = r.strip()
        return {"id": "", "text": text, "at": "", "done": False} if text else None
    if isinstance(r, dict):
        text = str(r.get("text") or "").strip()
        if not text:
            return None
        return {
            "id": r.get("id") or "",
            "text": text,
            # due 是本模块早期的字段名，前端读的是 at（ReminderListTool.vue:20）。
            # 两个都认，写出去只用 at。
            "at": r.get("at") or r.get("due") or "",
            "done": bool(r.get("done")),
        }
    return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rel_time(ts_ms: int) -> str:
    """前端 updatedAt 用的是相对文案（'3天前'），这里给出一致的兜底。"""
    return "刚刚"


class SaveToArchiveInput(BaseModel):
    target: str = Field(..., description="归档对象，如 '降噪耳机'")
    category: str = Field("", description="品类，如 '家电 · 自用'")
    phase: str = Field("need", description="阶段：need/candidate/decided/using/dropped")
    note: str = Field("", description="需求说明或备注")
    budget: str = Field("", description="预算区间，如 '¥1500 内'")
    for_whom: str = Field("", description="给谁买，如 '妈妈'")
    scenario: str = Field("", description="使用场景，如 '通勤'")
    ai_summary: str = Field("", description="一句话结论")
    risk: str = Field("", description="风险或注意事项")
    ai_recommend: str = Field("", description="推荐结论")
    rec_reason: str = Field("", description="推荐理由")
    thread_id: str = Field("", description="关联会话 id，便于从档案跳回对话")
    run_id: str = Field(
        "",
        description="关联任务实例 id（规划 / 送礼的 run），便于从档案跳回它的推演过程",
    )


class UpdateRecordPhaseInput(BaseModel):
    record_id: str = Field(..., description="记录 id（后端生成的 ai-xxx 或前端的 nd-1）")
    phase: str = Field(..., description="目标阶段：need/candidate/decided/using/dropped")
    note: str = Field("", description="本次流转的备注，如 '已下单'")


class SetReminderInput(BaseModel):
    record_id: str = Field(..., description="所属记录 id")
    text: str = Field(..., description="提醒内容，如 '确认是否收货'")
    due: str = Field("", description="期望时间，如 '3天后' 或具体日期")


class WriteReviewInput(BaseModel):
    record_id: str = Field(..., description="所属记录 id")
    content: str = Field(..., description="使用复盘正文")
    rating: str = Field("", description="满意度，如 '满意 / 一般 / 后悔'")


async def _load_record(session, user_id: str, record_id: str):
    result = await session.execute(
        select(ShoppingDecision).where(
            ShoppingDecision.user_id == user_id,
            ShoppingDecision.id == record_id,
        )
    )
    return result.scalars().first()


def _new_record(payload: dict, user_id: str, thread_id: str = "") -> dict:
    """补齐 ShoppingRecord 的全部字段（与前端 decisions_seed 对齐）。

    前端按整字段渲染，缺字段会显示成空白项，所以这里全部给默认值。
    """
    ts = int(datetime.now(timezone.utc).timestamp() * 1000)
    return {
        "id": f"ai-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}",
        "phase": payload.get("phase") or "need",
        "source": "ai_draft",
        "target": payload.get("target") or "",
        "category": payload.get("category") or "",
        "note": payload.get("note") or "",
        "rawIdea": payload.get("note") or "",
        "budget": payload.get("budget") or "",
        "forWhom": payload.get("for_whom") or "",
        "scenario": payload.get("scenario") or "",
        "aiSummary": payload.get("ai_summary") or "",
        "candidates": payload.get("candidates") or [],
        "aiRecommend": payload.get("ai_recommend") or "",
        "recReason": payload.get("rec_reason") or "",
        "risk": payload.get("risk") or "",
        "bestPrice": payload.get("best_price") or "",
        "dealPrice": payload.get("deal_price") or "",
        "purchasedAt": payload.get("purchased_at") or "",
        "reviewNote": "",
        "dropNote": "",
        "reminders": [],
        "insights": payload.get("insights") or [],
        "threadId": thread_id or None,
        # 指回来源任务实例（规划 / 送礼的 run）。档案不只是"记了一笔"，
        # 用户要能从记录跳回它当初是怎么算出来的 —— 这是「可追溯」在
        # 跨页面场景下的落点。手工记录留空。
        "runId": payload.get("run_id") or None,
        "ts": ts,
        "updatedAt": _rel_time(ts),
    }


@tool(
    category="buildin",
    tags=["档案", "归档", "购后"],
    display_name="存入购物档案",
    icon="🗂️",
    args_schema=SaveToArchiveInput,
)
async def save_to_archive(
    user_id: str,
    target: str,
    category: str = "",
    phase: str = "need",
    note: str = "",
    budget: str = "",
    for_whom: str = "",
    scenario: str = "",
    ai_summary: str = "",
    risk: str = "",
    ai_recommend: str = "",
    rec_reason: str = "",
    thread_id: str = "",
    run_id: str = "",
) -> str:
    """把一条购物需求存入用户的购物档案（决策库）。

    购后助手专属工具。用于把本轮对话沉淀成可追踪的档案记录，
    之后可推进阶段、设提醒、写复盘。

    参数:
        user_id: 用户ID
        target: 归档对象（如 '降噪耳机'）
        phase: 阶段，need/candidate/decided/using/dropped，默认 need
        thread_id: 关联会话ID（可选，便于从档案跳回对话）
    """
    logger.info(f"[Tool] 存入购物档案: {user_id} | {target} | phase={phase}")
    try:
        if phase not in ARCHIVE_PHASES:
            phase = "need"
        record = _new_record(
            {
                "target": target,
                "category": category,
                "phase": phase,
                "note": note,
                "budget": budget,
                "for_whom": for_whom,
                "scenario": scenario,
                "ai_summary": ai_summary,
                "risk": risk,
                "ai_recommend": ai_recommend,
                "rec_reason": rec_reason,
                "run_id": run_id,
            },
            user_id,
            thread_id,
        )
        async with pg_manager.get_async_session_context() as session:
            session.add(
                ShoppingDecision(
                    id=record["id"],
                    user_id=user_id,
                    phase=phase,
                    data=record,
                )
            )
        return json.dumps(
            {"status": "success", "record_id": record["id"], "phase": phase},
            ensure_ascii=False,
        )
    except Exception as e:
        logger.error(f"存入购物档案失败: {e}")
        return f"归档失败: {str(e)}"


@tool(
    category="buildin",
    tags=["档案", "阶段", "购后"],
    display_name="推进档案阶段",
    icon="🔄",
    args_schema=UpdateRecordPhaseInput,
)
async def update_record_phase(user_id: str, record_id: str, phase: str, note: str = "") -> str:
    """推进购物档案中某条记录的阶段（需求池 → 候选中 → 已决策 → 使用中）。

    参数:
        user_id: 用户ID
        record_id: 记录ID
        phase: 目标阶段 need/candidate/decided/using/dropped
        note: 本次流转备注
    """
    logger.info(f"[Tool] 推进档案阶段: {record_id} -> {phase}")
    if phase not in ARCHIVE_PHASES:
        return f"错误: 未知阶段 {phase}，可选 {', '.join(ARCHIVE_PHASES)}"
    try:
        async with pg_manager.get_async_session_context() as session:
            row = await _load_record(session, user_id, record_id)
            if row is None:
                return f"错误: 未找到记录 {record_id}"
            data = dict(row.data or {})
            data["phase"] = phase
            data["updatedAt"] = "刚刚"
            if note:
                data["note"] = note
            if phase == "dropped" and note:
                data["dropNote"] = note
            row.data = data
            row.phase = phase
            from sqlalchemy.orm import attributes

            attributes.flag_modified(row, "data")
        return json.dumps({"status": "success", "phase": phase}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"推进档案阶段失败: {e}")
        return f"推进失败: {str(e)}"


@tool(
    category="buildin",
    tags=["档案", "提醒", "购后"],
    display_name="设置档案提醒",
    icon="⏰",
    args_schema=SetReminderInput,
)
async def set_reminder(user_id: str, record_id: str, text: str, due: str = "") -> str:
    """给购物档案中的某条记录设置提醒（如比价、收货确认、保修到期）。

    带 due 时会**同时**建一条定时任务，让提醒真的会响（此前只写进
    reminders 数组，永远不会被触发）。
    

    参数:
        user_id: 用户ID
        record_id: 记录ID
        text: 提醒内容
        due: 期望时间（可选）
    """
    logger.info(f"[Tool] 设置档案提醒: {record_id} | {text}")
    try:
        async with pg_manager.get_async_session_context() as session:
            row = await _load_record(session, user_id, record_id)
            if row is None:
                return f"错误: 未找到记录 {record_id}"
            data = dict(row.data or {})
            # 先归一历史数据（裸字符串 → 对象），顺带把老的 "due" 洗成 "at"
            reminders = [x for x in (_norm_reminder(r) for r in (data.get("reminders") or [])) if x]
            reminders.append(
                {
                    "id": f"rm-{uuid.uuid4().hex[:8]}",
                    "text": text,
                    "at": due,
                    "done": False,
                    "createdAt": _now_iso(),
                }
            )
            data["reminders"] = reminders
            data["updatedAt"] = "刚刚"
            row.data = data
            from sqlalchemy.orm import attributes

            attributes.flag_modified(row, "data")

        # ── 补断链：带 due 的提醒要真的会响 ──
        # 只写进 reminders 数组的话，这条提醒永远躺在 DB 里没人触发。
        # 落一条 agent 定时任务，让调度器到点真的跑一次（结果进事件流）。
        scheduled = None
        if due and due.strip():
            try:
                from src.agents.common.toolkits.buildin.monitor_tools import (
                    create_monitor_task,
                )

                target = str(data.get("target") or "购物提醒").strip()
                raw = await create_monitor_task.ainvoke(
                    {
                        "user_id": user_id,
                        "task_type": "agent",
                        "target": f"到点提醒：{text}（关联档案「{target}」）",
                        "interval_hours": 24,
                        "task_name": f"提醒 · {target[:20]} · {due[:10]}",
                    }
                )
                scheduled = raw
            except Exception as sched_err:
                # 建任务失败不影响提醒已写入的事实 —— 只记日志
                logger.warning(f"设置提醒的定时任务失败（提醒已保存）: {sched_err}")

        result = {"status": "success", "count": len(reminders)}
        if scheduled:
            result["scheduled"] = scheduled
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        logger.error(f"设置提醒失败: {e}")
        return f"设置失败: {str(e)}"


@tool(
    category="buildin",
    tags=["档案", "复盘", "购后"],
    display_name="写入使用复盘",
    icon="📝",
    args_schema=WriteReviewInput,
)
async def write_review(user_id: str, record_id: str, content: str, rating: str = "") -> str:
    """给购物档案中的某条记录写入使用复盘（购后体验反馈）。

    参数:
        user_id: 用户ID
        record_id: 记录ID
        content: 复盘正文
        rating: 满意度（可选）
    """
    logger.info(f"[Tool] 写入使用复盘: {record_id}")
    try:
        async with pg_manager.get_async_session_context() as session:
            row = await _load_record(session, user_id, record_id)
            if row is None:
                return f"错误: 未找到记录 {record_id}"
            data = dict(row.data or {})
            data["reviewNote"] = content
            if rating:
                data["rating"] = rating
            data["updatedAt"] = "刚刚"
            row.data = data
            from sqlalchemy.orm import attributes

            attributes.flag_modified(row, "data")
        return json.dumps({"status": "success"}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"写入复盘失败: {e}")
        return f"写入失败: {str(e)}"
