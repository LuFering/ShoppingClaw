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

from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_business import TaskRecord, TaskExecutionLog, PriceSnapshot
from src.services.scheduler_service import get_scheduler

router = APIRouter(prefix="/tasks", tags=["tasks"])


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
async def create_task(body: TaskCreate):
    """创建定时任务"""
    if not body.cron_expression and not body.interval_seconds:
        raise HTTPException(400, "必须指定 cron_expression 或 interval_seconds")

    if body.cron_expression and body.interval_seconds:
        raise HTTPException(400, "cron_expression 和 interval_seconds 只能指定一个")

    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    task = TaskRecord(
        id=task_id,
        user_id="default",
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

    return {"success": True, "data": task.to_dict()}


@router.get("")
async def list_tasks(
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    limit: int = Query(default=50, le=200),
):
    """查询任务列表"""
    async with pg_manager.get_async_session_context() as session:
        stmt = select(TaskRecord).order_by(TaskRecord.created_at.desc())
        if status:
            stmt = stmt.where(TaskRecord.status == status)
        if task_type:
            stmt = stmt.where(TaskRecord.task_type == task_type)
        stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        tasks = result.scalars().all()

    return {"success": True, "data": [t.to_dict() for t in tasks], "total": len(tasks)}


@router.get("/{task_id}")
async def get_task(task_id: str):
    """获取单个任务详情"""
    async with pg_manager.get_async_session_context() as session:
        result = await session.execute(select(TaskRecord).where(TaskRecord.id == task_id))
        task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(404, "任务不存在")
    return {"success": True, "data": task.to_dict()}


@router.put("/{task_id}")
async def update_task(task_id: str, body: TaskUpdate):
    """更新任务"""
    async with pg_manager.get_async_session_context() as session:
        result = await session.execute(select(TaskRecord).where(TaskRecord.id == task_id))
        task = result.scalar_one_or_none()

        if not task:
            raise HTTPException(404, "任务不存在")

        update_data = body.model_dump(exclude_unset=True)
        scheduler = get_scheduler()

        for key, value in update_data.items():
            setattr(task, key, value)

        task.updated_at = datetime.now(timezone.utc)
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

    return {"success": True, "data": task.to_dict()}


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    """删除任务"""
    scheduler = get_scheduler()
    await scheduler.remove_task(task_id)

    async with pg_manager.get_async_session_context() as session:
        result = await session.execute(select(TaskRecord).where(TaskRecord.id == task_id))
        task = result.scalar_one_or_none()
        if task:
            await session.delete(task)
            await session.commit()

    return {"success": True, "message": f"任务 {task_id} 已删除"}


# ═══════════════════════════════════════════
# 手动触发 & 执行日志
# ═══════════════════════════════════════════

@router.post("/{task_id}/trigger")
async def trigger_task(task_id: str):
    """手动立即触发一次任务"""
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
):
    """获取任务的执行日志"""
    async with pg_manager.get_async_session_context() as session:
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
    since = datetime.now(timezone.utc) - timedelta(days=days)

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
