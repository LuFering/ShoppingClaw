"""跨事件循环安全的 asyncio.Lock 辅助。

背景：uvicorn 的请求处理 loop 与后台任务（scheduler / asyncio.create_task 的 Agent 轮询）
可能运行在【不同的事件循环】上。asyncio.Lock 在创建时绑定当时的 running loop，
若后续在另一 loop 上 `async with lock`，Python 3.12 会抛
`RuntimeError: ... is bound to a different event loop`。

本工具提供 `loop_safe_lock`：真正的锁在【首次实际使用、且拿到当前 running loop】时才创建，
并在每次进入前校验绑定；若绑定到了别的 loop 则自动重建（丢弃旧锁并发警告）。
这样共享同一模块级/单例锁实例的调用方不再因 loop 交叉而崩溃。
"""
import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 记录每个锁实例绑定的 loop id，用于跨 loop 检测
_bindings: dict[int, int] = {}


def _running_loop_id() -> int:
    try:
        return id(asyncio.get_running_loop())
    except RuntimeError:
        return 0  # 无 running loop（同步上下文），按 0 处理


def _make_lock() -> asyncio.Lock:
    loop_id = _running_loop_id()
    lock = asyncio.Lock()
    _bindings[id(lock)] = loop_id
    return lock


def _ensure_lock_loop(lock: asyncio.Lock) -> asyncio.Lock:
    """校验 lock 绑定的 loop 是否仍与当前一致；不一致则重建。"""
    loop_id = _running_loop_id()
    bound = _bindings.get(id(lock))
    if bound is not None and bound != 0 and bound != loop_id:
        logger.warning(
            "asyncio.Lock 跨事件循环使用：重建锁（%s -> %s）",
            bound, loop_id,
        )
        return _make_lock()
    if bound is None:
        _bindings[id(lock)] = loop_id
    return lock


class LoopSafeLock:
    """跨 loop 安全的异步锁。用法：`async with LoopSafeLock() as lock: ...`
    或 `lock = LoopSafeLock()` 后 `async with lock:`。"""

    def __init__(self) -> None:
        self._lock: asyncio.Lock | None = None

    @property
    def lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = _make_lock()
        self._lock = _ensure_lock_loop(self._lock)
        return self._lock

    async def __aenter__(self) -> "LoopSafeLock":
        await self.lock.acquire()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        self.lock.release()

    async def acquire(self) -> None:
        await self.lock.acquire()

    def release(self) -> None:
        self.lock.release()

    def locked(self) -> bool:
        return self.lock.locked()


def loop_safe(lock: asyncio.Lock) -> asyncio.Lock:
    """就地校验一个已存在 asyncio.Lock 的绑定 loop，不匹配则返回新锁。
    用于改造已有 `self._lock = asyncio.Lock()` 的类：把 `async with self._lock`
    改为 `async with loop_safe(self._lock):`。"""
    return _ensure_lock_loop(lock)
