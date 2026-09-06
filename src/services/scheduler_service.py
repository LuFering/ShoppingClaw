"""
定时任务调度管理器

职责：
- 基于 APScheduler 管理任务的增删改查
- Redis 分布式锁防重复执行
- 启动/停止/重载任务
- 结果写入 PostgreSQL（执行日志 + 价格快照）
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.base import JobLookupError
from sqlalchemy import select

from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_business import TaskRecord, TaskExecutionLog, PriceSnapshot
from src.services.redis_cache import get_redis_cache

logger = logging.getLogger(__name__)

# ── Redis 分布式锁 Key 前缀 ──
LOCK_PREFIX = "scheduler:lock:"


class SchedulerManager:
    """定时任务调度管理器（单例）"""

    def __init__(self):
        self._scheduler: AsyncIOScheduler | None = None
        self._task_executors: dict[str, Callable] = {}  # task_type → executor async function
        self._started = False

    @property
    def scheduler(self) -> AsyncIOScheduler:
        if self._scheduler is None:
            self._scheduler = AsyncIOScheduler(
                job_defaults={
                    "coalesce": True,          # 合并错过的任务
                    "max_instances": 1,         # 同任务只允许一个实例
                    "misfire_grace_time": 300,  # 错过后5分钟内仍可执行
                }
            )
        return self._scheduler

    # ═══════════════════════════════════════════
    # 执行器注册
    # ═══════════════════════════════════════════

    def register_executor(self, task_type: str, executor: Callable):
        """注册任务执行器"""
        self._task_executors[task_type] = executor
        logger.info(f"[Scheduler] 已注册执行器: {task_type}")

    # ═══════════════════════════════════════════
    # 调度生命周期
    # ═══════════════════════════════════════════

    async def start(self):
        """启动调度器 + 从 DB 加载所有 active 任务"""
        if self._started:
            return

        self.scheduler.start()
        self._started = True
        logger.info("[Scheduler] 调度器已启动")

        # 恢复 DB 中所有 active 任务
        await self._reload_all()

    async def shutdown(self):
        """关闭调度器"""
        if self._scheduler and self._started:
            self._scheduler.shutdown(wait=False)
            self._started = False
            logger.info("[Scheduler] 调度器已关闭")

    async def _reload_all(self):
        """从数据库重新加载所有 active 任务到调度器"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(TaskRecord).where(TaskRecord.status == "active")
            )
            tasks = result.scalars().all()

        count = 0
        for task in tasks:
            try:
                self._add_job(task)
                count += 1
            except Exception as e:
                logger.error(f"[Scheduler] 加载任务 {task.id} 失败: {e}")

        logger.info(f"[Scheduler] 从 DB 恢复了 {count} 个活跃任务")

    # ═══════════════════════════════════════════
    # 任务 CRUD（调度器层面）
    # ═══════════════════════════════════════════

    async def add_task(self, task: TaskRecord):
        """添加新任务到调度器"""
        executor = self._task_executors.get(task.task_type)
        if executor is None:
            raise ValueError(f"未注册的执行器类型: {task.task_type}")

        self._add_job(task)
        logger.info(f"[Scheduler] 已添加任务: {task.id} ({task.task_type})")

    async def remove_task(self, task_id: str):
        """从调度器移除任务"""
        try:
            self.scheduler.remove_job(task_id)
            logger.info(f"[Scheduler] 已移除任务: {task_id}")
        except JobLookupError:
            pass  # 不存在就算了

    async def pause_task(self, task_id: str):
        """暂停任务"""
        try:
            self.scheduler.pause_job(task_id)
        except JobLookupError:
            pass

    async def resume_task(self, task_id: str):
        """恢复任务"""
        try:
            self.scheduler.resume_job(task_id)
        except JobLookupError:
            pass

    async def trigger_now(self, task_id: str):
        """立即手动触发一次任务"""
        # 从 DB 查任务类型
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(TaskRecord).where(TaskRecord.id == task_id))
            task_record = result.scalar_one_or_none()

        if task_record is None:
            raise ValueError(f"任务 {task_id} 不存在")

        executor = self._task_executors.get(task_record.task_type)
        if executor:
            asyncio.create_task(self._execute_with_lock(task_id, executor))
        else:
            raise ValueError(f"任务 {task_id} 没有对应的执行器")

    # ═══════════════════════════════════════════
    # 内部方法
    # ═══════════════════════════════════════════

    def _add_job(self, task: TaskRecord):
        """根据 TaskRecord 创建 APScheduler job"""

        # cron 优先
        if task.cron_expression:
            trigger = CronTrigger.from_crontab(task.cron_expression)
        elif task.interval_seconds:
            trigger = IntervalTrigger(seconds=task.interval_seconds)
        else:
            raise ValueError(f"任务 {task.id} 缺少 cron_expression 或 interval_seconds")

        executor = self._task_executors.get(task.task_type)
        if executor is None:
            raise ValueError(f"未注册的执行器类型: {task.task_type}")

        self.scheduler.add_job(
            func=self._execute_with_lock,
            trigger=trigger,
            args=[task.id, executor],
            id=task.id,
            name=task.name,
            replace_existing=True,
        )

    async def _execute_with_lock(self, task_id: str, executor: Callable):
        """
        带 Redis 分布式锁的任务执行包装器。

        流程:
        1. 尝试获取 Redis 锁（防止多实例重复执行）
        2. 创建执行日志（running）
        3. 调用执行器
        4. 更新执行日志（success/failed）
        5. 更新 TaskRecord 的统计字段
        6. 释放锁
        """
        lock_key = f"{LOCK_PREFIX}{task_id}"
        cache = get_redis_cache()
        started_at = datetime.now(timezone.utc)

        # 1. 分布式锁（30s TTL，超时自动释放）
        try:
            if cache._connected and cache._redis is not None:
                acquired = await cache._redis.set(lock_key, "1", nx=True, ex=30)
            else:
                acquired = True  # Redis 不可用时跳过锁
        except Exception:
            acquired = True  # 异常时放行

        if not acquired:
            logger.info(f"[Scheduler] 任务 {task_id} 已在其他实例执行，跳过")
            return

        # 2. 创建执行日志
        log_entry = TaskExecutionLog(
            task_id=task_id,
            status="running",
            started_at=started_at,
        )

        async with pg_manager.get_async_session_context() as session:
            session.add(log_entry)
            await session.commit()

        # 3. 执行任务
        result_data = None
        error_message = None
        final_status = "success"

        try:
            # 从 DB 读取最新任务配置
            async with pg_manager.get_async_session_context() as session:
                r = await session.execute(select(TaskRecord).where(TaskRecord.id == task_id))
                task = r.scalar_one_or_none()

            if task is None or task.status != "active":
                logger.info(f"[Scheduler] 任务 {task_id} 已删除或暂停，跳过执行")
                final_status = "cancelled"
                return

            result_data = await executor(task)
            logger.info(f"[Scheduler] 任务 {task_id} 执行成功")

        except Exception as e:
            final_status = "failed"
            error_message = str(e)
            logger.error(f"[Scheduler] 任务 {task_id} 执行失败: {e}", exc_info=True)

        finally:
            finished_at = datetime.now(timezone.utc)
            duration_ms = int((finished_at - started_at).total_seconds() * 1000)

            # 4. 更新执行日志
            async with pg_manager.get_async_session_context() as session:
                r2 = await session.execute(
                    select(TaskExecutionLog).where(
                        TaskExecutionLog.task_id == task_id,
                        TaskExecutionLog.started_at == started_at,
                    )
                )
                log = r2.scalar_one_or_none()
                if log:
                    log.status = final_status
                    log.finished_at = finished_at
                    log.duration_ms = duration_ms
                    log.result_data = result_data
                    log.error_message = error_message
                    await session.commit()

            # 5. 更新 TaskRecord 统计
            async with pg_manager.get_async_session_context() as session:
                r3 = await session.execute(select(TaskRecord).where(TaskRecord.id == task_id))
                task_record = r3.scalar_one_or_none()
                if task_record:
                    task_record.run_count = (task_record.run_count or 0) + 1
                    task_record.last_run_at = finished_at
                    task_record.last_result = {
                        "status": final_status,
                        "duration_ms": duration_ms,
                        "summary": str(result_data)[:500] if result_data else None,
                    }
                    await session.commit()

            # 6. 释放锁
            try:
                if cache._connected and cache._redis is not None:
                    await cache._redis.delete(lock_key)
            except Exception:
                pass

    def _get_task_type_from_job(self, task_id: str) -> str:
        """从调度器中查询任务类型（仅用于内部校验）。"""
        job = self.scheduler.get_job(task_id)
        if job is None:
            raise ValueError(f"任务 {task_id} 不在调度器中")
        # 从 APScheduler job args 中无法直接获取 task_type
        # 应使用 trigger_now 中的 DB 查询方式
        raise NotImplementedError("请使用 DB 查询获取任务类型")


# ── 全局单例 ──
_scheduler_manager: SchedulerManager | None = None


def get_scheduler() -> SchedulerManager:
    global _scheduler_manager
    if _scheduler_manager is None:
        _scheduler_manager = SchedulerManager()
    return _scheduler_manager
