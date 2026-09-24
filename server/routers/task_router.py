"""
定时任务 API 路由

提供任务的 CRUD、手动触发、执行日志、价格历史查询
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from server.utils.auth_middleware import get_required_user
from src.utils.datetime_utils import utc_now_naive
from server.utils.user_store import User
from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_business import TaskRecord, TaskExecutionLog, PriceSnapshot
from src.services.scheduler_service import get_scheduler

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _uid(user: User) -> str:
    """取稳定的用户标识。

    与 decisions_router._uid() 保持同一口径（str(users.id)）——
    主动助理要按用户把「监控任务」和「购物档案」对起来看，
    两边用户键必须一致，否则关联不上。

    历史问题：本文件原先硬编码 user_id="default"，所有任务都挂在
    default 名下，与 shopping_decisions 的 str(users.id) 对不上。
    """
    return str(getattr(user, "id", None) or getattr(user, "user_id", "anonymous"))


async def _reload_task_view(task_id: str) -> dict:
    """从 DB 重读任务再转 dict。

    调度相关的写入（注册 job、回填 next_run_at）发生在 ORM 对象之外，
    手里那个对象可能是旧快照 —— 返回前重读一次，保证响应与库一致。
    """
    async with pg_manager.get_async_session_context() as session:
        result = await session.execute(select(TaskRecord).where(TaskRecord.id == task_id))
        rec = result.scalar_one_or_none()
    return rec.to_dict() if rec else {}


# ═══════════════════════════════════════════
# Pydantic Models
# ═══════════════════════════════════════════

class TaskCreate(BaseModel):
    name: str
    task_type: str               # price/stock/coupon/rank/shop
    cron_expression: Optional[str] = None
    interval_seconds: Optional[int] = None
    task_params: dict = {}
    notify_enabled: bool = True
    notify_channels: list[str] = ["sse"]


class TaskUpdate(BaseModel):
    name: Optional[str] = None
    cron_expression: Optional[str] = None
    interval_seconds: Optional[int] = None
    task_params: Optional[dict] = None
    notify_enabled: Optional[bool] = None
    status: Optional[str] = None  # active/paused


# ═══════════════════════════════════════════
# CRUD
# ═══════════════════════════════════════════

@router.post("")
async def create_task(body: TaskCreate, current_user: User = Depends(get_required_user)):
    """创建定时任务"""
    uid = _uid(current_user)
    if not body.cron_expression and not body.interval_seconds:
        raise HTTPException(400, "必须指定 cron_expression 或 interval_seconds")

    if body.cron_expression and body.interval_seconds:
        raise HTTPException(400, "cron_expression 和 interval_seconds 只能指定一个")

    task_id = str(uuid.uuid4())
    now = utc_now_naive()

    task = TaskRecord(
        id=task_id,
        user_id=uid,
        name=body.name,
        task_type=body.task_type,
        status="active",
        cron_expression=body.cron_expression,
        interval_seconds=body.interval_seconds,
        task_params=body.task_params,
        notify_enabled=body.notify_enabled,
        notify_channels=body.notify_channels,
        created_at=now,
        updated_at=now,
    )

    # 保存到 DB
    async with pg_manager.get_async_session_context() as session:
        session.add(task)
        await session.commit()

    # 注册到调度器
    scheduler = get_scheduler()
    try:
        await scheduler.add_task(task)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # 重读：add_task 会把 APScheduler 的 next_run_time 回填进 task_records，
    # 而上面那个 task 对象是注册前建的，直接 to_dict() 会返回 next_run_at=None
    return {"success": True, "data": await _reload_task_view(task_id)}


@router.get("")
async def list_tasks(
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    current_user: User = Depends(get_required_user),
):
    """查询任务列表（仅当前用户）"""
    uid = _uid(current_user)
    async with pg_manager.get_async_session_context() as session:
        stmt = (
            select(TaskRecord)
            .where(TaskRecord.user_id == uid)
            .order_by(TaskRecord.created_at.desc())
        )
        if status:
            stmt = stmt.where(TaskRecord.status == status)
        if task_type:
            stmt = stmt.where(TaskRecord.task_type == task_type)
        stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        tasks = result.scalars().all()

    return {"success": True, "data": [t.to_dict() for t in tasks], "total": len(tasks)}


@router.get("/{task_id}")
async def get_task(task_id: str, current_user: User = Depends(get_required_user)):
    """获取单个任务详情（仅限本人任务）"""
    uid = _uid(current_user)
    async with pg_manager.get_async_session_context() as session:
        result = await session.execute(
            select(TaskRecord).where(TaskRecord.id == task_id, TaskRecord.user_id == uid)
        )
        task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(404, "任务不存在")
    return {"success": True, "data": task.to_dict()}


@router.put("/{task_id}")
async def update_task(
    task_id: str, body: TaskUpdate, current_user: User = Depends(get_required_user)
):
    """更新任务（仅限本人任务）"""
    uid = _uid(current_user)
    async with pg_manager.get_async_session_context() as session:
        result = await session.execute(
            select(TaskRecord).where(TaskRecord.id == task_id, TaskRecord.user_id == uid)
        )
        task = result.scalar_one_or_none()

        if not task:
            raise HTTPException(404, "任务不存在")

        update_data = body.model_dump(exclude_unset=True)
        scheduler = get_scheduler()

        for key, value in update_data.items():
            setattr(task, key, value)

        task.updated_at = utc_now_naive()
        await session.commit()

        # 同步到调度器
        if body.status == "paused":
            await scheduler.pause_task(task_id)
        elif body.status == "active":
            await scheduler.resume_task(task_id)

        # 如果修改了调度配置，需要重建 job
        if body.cron_expression is not None or body.interval_seconds is not None:
            await scheduler.remove_task(task_id)
            try:
                await scheduler.add_task(task)
            except ValueError as e:
                raise HTTPException(400, str(e))

    # 同 create_task：重建 job 后 next_run_at 已变，重读一次再返回
    return {"success": True, "data": await _reload_task_view(task_id)}


@router.delete("/{task_id}")
async def delete_task(task_id: str, current_user: User = Depends(get_required_user)):
    """删除任务（仅限本人任务）"""
    uid = _uid(current_user)
    async with pg_manager.get_async_session_context() as session:
        result = await session.execute(
            select(TaskRecord).where(TaskRecord.id == task_id, TaskRecord.user_id == uid)
        )
        task = result.scalar_one_or_none()
        if not task:
            raise HTTPException(404, "任务不存在")
        await session.delete(task)
        await session.commit()

    # 先确认归属再从调度器摘掉：顺序反过来的话，别人的 task_id 也能被停掉
    scheduler = get_scheduler()
    await scheduler.remove_task(task_id)

    return {"success": True, "message": f"任务 {task_id} 已删除"}


# ═══════════════════════════════════════════
# 手动触发 & 执行日志
# ═══════════════════════════════════════════

@router.post("/{task_id}/trigger")
async def trigger_task(task_id: str, current_user: User = Depends(get_required_user)):
    """手动立即触发一次任务（仅限本人任务）"""
    uid = _uid(current_user)
    # 先校验归属，再交给调度器 —— 否则任何人拿 task_id 就能跑别人的监控
    async with pg_manager.get_async_session_context() as session:
        result = await session.execute(
            select(TaskRecord).where(TaskRecord.id == task_id, TaskRecord.user_id == uid)
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(404, "任务不存在")

    scheduler = get_scheduler()
    try:
        await scheduler.trigger_now(task_id)
        return {"success": True, "message": f"任务 {task_id} 已触发"}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{task_id}/logs")
async def get_task_logs(
    task_id: str,
    limit: int = Query(default=20, le=100),
    current_user: User = Depends(get_required_user),
):
    """获取任务的执行日志（先校验任务归属）"""
    uid = _uid(current_user)
    async with pg_manager.get_async_session_context() as session:
        owned = await session.execute(
            select(TaskRecord.id).where(TaskRecord.id == task_id, TaskRecord.user_id == uid)
        )
        if owned.scalar_one_or_none() is None:
            raise HTTPException(404, "任务不存在")
        result = await session.execute(
            select(TaskExecutionLog)
            .where(TaskExecutionLog.task_id == task_id)
            .order_by(TaskExecutionLog.started_at.desc())
            .limit(limit)
        )
        logs = result.scalars().all()

    return {"success": True, "data": [log.to_dict() for log in logs], "total": len(logs)}


# ═══════════════════════════════════════════
# 价格历史
# ═══════════════════════════════════════════

@router.get("/price-history/{product_id}")
async def get_price_history(
    product_id: str,
    days: int = Query(default=7, le=90),
    limit: int = Query(default=100, le=500),
):
    """获取商品的价格历史趋势"""
    from datetime import timedelta
    since = utc_now_naive() - timedelta(days=days)

    async with pg_manager.get_async_session_context() as session:
        result = await session.execute(
            select(PriceSnapshot)
            .where(PriceSnapshot.product_id == product_id, PriceSnapshot.snapshot_at >= since)
            .order_by(PriceSnapshot.snapshot_at.asc())
            .limit(limit)
        )
        snapshots = result.scalars().all()

    data = [s.to_dict() for s in snapshots]

    # 计算趋势摘要
    trend = None
    if len(data) >= 2:
        prices = [s.price for s in snapshots if s.price]
        if prices:
            first, last = prices[0], prices[-1]
            change_pct = (last - first) / first * 100 if first else 0
            trend = {
                "direction": "down" if change_pct < -1 else ("up" if change_pct > 1 else "flat"),
                "change_pct": round(change_pct, 1),
                "first_price": first,
                "last_price": last,
                "snapshots": len(prices),
            }

    return {"success": True, "data": data, "trend": trend, "total": len(data)}
