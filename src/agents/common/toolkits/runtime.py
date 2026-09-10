"""ToolRuntime — 六层框架之「执行层」与「生命周期层」。

RuntimeChain 将 Handler 组成可插拔的执行链，在所有工具调用时统一管控：
权限校验 → 限流检查 → 幂等防重 → Watchdog 心跳 → 超时/重试 → 结果封装 → 生命周期事件。

每个工具可通过 @tool(handlers=[...]) 定制自己的 Handler 链。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

from src.agents.common.toolkits.result import ToolResult, ToolStatus

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# 工具上下文
# ════════════════════════════════════════════════════════════════

@dataclass
class ToolContext:
    """每次工具调用的完整上下文，在 Handler 链中传递。"""
    tool_name: str
    args: dict[str, Any]
    meta: dict[str, Any] = field(default_factory=dict)       # Registry 元数据
    caller: dict[str, Any] | None = None                     # 调用者信息
    heartbeat: "HeartbeatState | None" = None                # Watchdog 心跳


@dataclass
class HeartbeatState:
    """心跳状态 — 工具内部可调用 ctx.heartbeat.tick() 报告自己还活着。"""
    last_time: float = field(default_factory=time.time)
    _updated: bool = True

    def tick(self, progress: float | None = None) -> None:
        self.last_time = time.time()
        self._updated = True

    def was_updated(self) -> bool:
        return self._updated

    def reset_flag(self) -> None:
        self._updated = False


# ════════════════════════════════════════════════════════════════
# Handler 基类
# ════════════════════════════════════════════════════════════════

class RuntimeHandler(ABC):
    """所有 Handler 的抽象基类。

    每个 Handler 实现一个横切关注点，通过 next_handler 链式调用。
    不调用 next_handler = 拦截，短路径返回 ToolResult。
    """

    @abstractmethod
    async def handle(self, ctx: ToolContext, next_handler: Callable) -> ToolResult:
        ...


# ════════════════════════════════════════════════════════════════
# 内置 Handlers
# ════════════════════════════════════════════════════════════════

class PermissionHandler(RuntimeHandler):
    """权限校验 — 不通过直接返回 forbidden。"""

    async def handle(self, ctx: ToolContext, next_handler: Callable) -> ToolResult:
        required = ctx.meta.get("required_permissions", [])
        if not required:
            return await next_handler(ctx)

        user_perms = set((ctx.caller or {}).get("permissions", []))
        missing = set(required) - user_perms
        if missing:
            logger.warning(f"[Permission] 工具 {ctx.tool_name} 权限不足: 需要 {missing}")
            return ToolResult.forbidden_result(
                error=f"权限不足，需要: {list(missing)}",
                tool_name=ctx.tool_name,
            )
        return await next_handler(ctx)


class RateLimitHandler(RuntimeHandler):
    """限流 — 触发限流返回 rate_limited。"""

    async def handle(self, ctx: ToolContext, next_handler: Callable) -> ToolResult:
        limit = ctx.meta.get("rate_limit")
        if not limit:
            return await next_handler(ctx)

        allowed = await self._check(ctx.tool_name, limit, ctx.caller)
        if not allowed:
            logger.warning(f"[RateLimit] 工具 {ctx.tool_name} 触发限流: {limit}")
            return ToolResult.rate_limited_result(
                error=f"触发限流: {limit}",
                tool_name=ctx.tool_name,
            )
        return await next_handler(ctx)

    async def _check(self, tool_name: str, limit: dict, caller) -> bool:
        """限流检查 — 默认放行，生产环境接 Redis 滑动窗口。"""
        return True


class IdempotencyHandler(RuntimeHandler):
    """幂等防重 — 同一 Task Key 重复调用返回 running / 缓存结果。"""

    async def handle(self, ctx: ToolContext, next_handler: Callable) -> ToolResult:
        task_key = self._make_key(ctx.tool_name, ctx.args)

        # 检查是否已有执行中的任务
        existing = await self._get_task(task_key)
        if existing:
            if existing.get("status") == "running":
                return ToolResult(
                    status=ToolStatus.RUNNING,
                    metadata={
                        "task_key": task_key,
                        "started_at": existing.get("started_at"),
                        "message": f"{ctx.tool_name} 正在执行中，无需重复触发",
                    },
                )
            if existing.get("status") == "success":
                return ToolResult.success(
                    data=existing.get("result"),
                    cached=True,
                    task_key=task_key,
                )

        # 注册执行中
        await self._set_task(task_key, {
            "status": "running",
            "tool_name": ctx.tool_name,
            "started_at": time.time(),
        })

        result = await next_handler(ctx)

        # 更新最终状态
        await self._set_task(task_key, {
            "status": result.status.value,
            "result": result.data,
            "completed_at": time.time(),
        })

        return result

    def _make_key(self, tool_name: str, args: dict) -> str:
        """生成幂等键：工具名 + 排除翻页参数的核心参数哈希。"""
        excluded = {"page", "max_pages"}
        core = {k: v for k, v in sorted(args.items()) if k not in excluded}
        raw = f"{tool_name}:{json.dumps(core, ensure_ascii=False)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    async def _get_task(self, task_key: str) -> dict | None:
        return None  # 生产环境接 Redis

    async def _set_task(self, task_key: str, data: dict) -> None:
        pass  # 生产环境接 Redis


class WatchdogHandler(RuntimeHandler):
    """看门狗 — 心跳检测，区分「慢」和「死」。

    仅在 execution_mode="inline" 的工具上生效。
    """

    def __init__(self, heartbeat_interval: float = 5.0,
                 max_missed_heartbeats: int = 3):
        self._interval = heartbeat_interval
        self._max_missed = max_missed_heartbeats

    async def handle(self, ctx: ToolContext, next_handler: Callable) -> ToolResult:
        if ctx.meta.get("execution_mode") != "inline":
            return await next_handler(ctx)

        heartbeat = HeartbeatState()
        ctx.heartbeat = heartbeat

        task = asyncio.create_task(next_handler(ctx))

        missed = 0
        while not task.done():
            await asyncio.sleep(self._interval)
            if task.done():
                break
            if heartbeat.was_updated():
                missed = 0
                heartbeat.reset_flag()
            else:
                missed += 1
                if missed >= self._max_missed:
                    task.cancel()
                    return ToolResult.hung_result(
                        error=f"工具 {ctx.tool_name} 已挂死: 连续 "
                              f"{missed * self._interval:.0f}s 无心跳响应",
                        tool_name=ctx.tool_name,
                        last_heartbeat=heartbeat.last_time,
                    )

        return await task


class TimeoutRetryHandler(RuntimeHandler):
    """超时 + 重试 — 根据元数据显示式配置执行。

    执行流程：
    1. asyncio.wait_for 包裹 → 超时抛出 TimeoutError
    2. 捕获 retry_on 中声明的异常 → 进入下一轮重试
    3. 达到 max_retries 仍失败 → 返回 timeout / error
    4. attempt 计数值写入 metadata
    """

    async def handle(self, ctx: ToolContext, next_handler: Callable) -> ToolResult:
        timeout = ctx.meta.get("timeout", 30) or 30
        max_retries = ctx.meta.get("max_retries", 0)
        retry_on: tuple = ctx.meta.get("retry_on", ())

        last_error: str = ""
        for attempt in range(max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    next_handler(ctx),
                    timeout=timeout,
                )
                result.metadata["attempt"] = attempt + 1
                result.metadata["tool_name"] = ctx.tool_name
                return result
            except asyncio.TimeoutError:
                last_error = f"执行超时 ({timeout}s)"
                logger.warning(
                    f"[TimeoutRetry] {ctx.tool_name} 超时, "
                    f"attempt {attempt + 1}/{max_retries + 1}"
                )
            except retry_on as e:
                last_error = f"{type(e).__name__}: {e}"
                logger.warning(
                    f"[TimeoutRetry] {ctx.tool_name} 可重试异常, "
                    f"attempt {attempt + 1}/{max_retries + 1}: {e}"
                )
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                break

        is_timeout = "超时" in last_error
        return ToolResult(
            status=ToolStatus.TIMEOUT if is_timeout else ToolStatus.ERROR,
            error=last_error,
            metadata={
                "tool_name": ctx.tool_name,
                "attempt": max_retries + 1,
            },
        )


class ResultWrapHandler(RuntimeHandler):
    """结果封装 — 将原始返回值自动包装为 ToolResult。

    这是 Handler Chain 的最内层（在执行完之后自动包装），
    确保即使工具函数返回原始 dict，上层拿到的也是统一的 ToolResult。
    """

    async def handle(self, ctx: ToolContext, next_handler: Callable) -> ToolResult:
        start = time.time()
        raw = await next_handler(ctx)
        duration_ms = int((time.time() - start) * 1000)

        # 已经包装过的直接返回
        if isinstance(raw, ToolResult):
            raw.metadata.setdefault("duration_ms", duration_ms)
            raw.metadata.setdefault("tool_name", ctx.tool_name)
            return raw

        return ToolResult.success(
            data=raw,
            tool_name=ctx.tool_name,
            duration_ms=duration_ms,
        )


class OffloadHandler(RuntimeHandler):
    """大结果卸载 — 超过阈值写入文件，只返回路径引用。"""

    def __init__(self, threshold: int = 3000, relaxed_threshold: int = 30000,
                 relaxed_tools: set | None = None):
        self._threshold = threshold
        self._relaxed_threshold = relaxed_threshold
        self._relaxed_tools = relaxed_tools or {
            "get_product_full_detail", "get_products_specs_batch",
        }

    async def handle(self, ctx: ToolContext, next_handler: Callable) -> ToolResult:
        result = await next_handler(ctx)
        if result.status != ToolStatus.SUCCESS or not result.data:
            return result

        threshold = (
            self._relaxed_threshold
            if ctx.tool_name in self._relaxed_tools
            else self._threshold
        )

        content_str = str(result.data)
        if len(content_str) > threshold:
            content_hash = hashlib.md5(content_str.encode()).hexdigest()[:8]
            file_path = f"research_data/{ctx.tool_name}_{content_hash}.txt"
            result.metadata["offloaded_to"] = file_path
            result.metadata["original_size"] = len(content_str)

        return result


class LifecycleHandler(RuntimeHandler):
    """生命周期事件 — 发出 tool_start / tool_complete / tool_error 事件。

    供 SSE 监控、OpenTelemetry Trace、Audit 审计消费。
    """

    def __init__(self):
        self._sinks: list[Callable[[str, dict], None]] = []

    def add_sink(self, sink: Callable[[str, dict], None]) -> None:
        """注册事件消费者（SSE / Trace / Audit）。"""
        self._sinks.append(sink)

    @staticmethod
    def _dump(value: Any, limit: int) -> str:
        """把工具返回值安全地转成可展示文本（超长截断）。"""
        if value is None:
            return ""
        try:
            if isinstance(value, str):
                text = value
            else:
                text = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            text = str(value)
        if len(text) > limit:
            return text[:limit] + f"…（已截断，共 {len(text)} 字符）"
        return text

    async def handle(self, ctx: ToolContext, next_handler: Callable) -> ToolResult:
        # 同一次调用共用 ID：前端靠它把 tool_start 与 tool_complete 配对。
        # 只作局部变量，不写回 ctx.meta，避免污染链路上的其它消费者。
        tool_call_id = f"call_{ctx.tool_name}_{hashlib.md5(f'{ctx.tool_name}{time.time()}{id(ctx)}'.encode()).hexdigest()[:12]}"
        args_preview = {k: str(v)[:200] for k, v in ctx.args.items()}

        self._emit("tool_start", {
            "tool_call_id": tool_call_id,
            "id": tool_call_id,
            "tool_name": ctx.tool_name,
            "function": ctx.tool_name,
            "args": args_preview,
            "arguments": args_preview,
            "timestamp": time.time(),
        })

        result = await next_handler(ctx)

        event_type = "tool_complete" if result.is_success else "tool_error"
        result_content = self._dump(result.data, 4000) if result.is_success else ""
        self._emit(event_type, {
            "tool_call_id": tool_call_id,
            "id": tool_call_id,
            "tool_name": ctx.tool_name,
            "function": ctx.tool_name,
            "status": result.status.value,
            "duration_ms": result.metadata.get("duration_ms"),
            "attempt": result.metadata.get("attempt"),
            "error": result.error,
            "cached": result.metadata.get("cached", False),
            "result_content": result_content,
            "result_preview": result_content[:600],
            "timestamp": time.time(),
        })

        return result

    def _emit(self, event_type: str, payload: dict) -> None:
        for sink in self._sinks:
            try:
                sink(event_type, payload)
            except Exception:
                pass


# ════════════════════════════════════════════════════════════════
# Terminal Handler — 链末端，真正执行工具函数
# ════════════════════════════════════════════════════════════════

class ExecuteHandler(RuntimeHandler):
    """链的末端 — 调用实际的工具函数。

    中间 Handler 按协议以 next_handler(ctx) 调用下一环（单参数），
    因此终端 handle 的 next_handler 必须有默认值，否则链末调用直接 TypeError。
    """

    def __init__(self, tool_func: Callable):
        self._func = tool_func

    async def handle(self, ctx: ToolContext, next_handler: Callable | None = None) -> ToolResult:
        if asyncio.iscoroutinefunction(self._func):
            return await self._func(**ctx.args)
        return await asyncio.to_thread(self._func, **ctx.args)


# ════════════════════════════════════════════════════════════════
# RuntimeChain — 可插拔 Handler 链组装器
# ════════════════════════════════════════════════════════════════

class RuntimeChain:
    """将 Handlers 组装成可插拔执行链。

    链结构: h1 → h2 → h3 → ... → ExecuteHandler

    每个 Handler 通过 next_handler(ctx) 将控制权传给下一个，
    不调用 next_handler = 拦截，短路径返回 ToolResult。
    """

    def __init__(self, handlers: list[RuntimeHandler]):
        self._handlers = handlers

    async def execute(
        self,
        tool_name: str,
        tool_func: Callable,
        args: dict,
        caller: dict | None = None,
        handlers: list[RuntimeHandler] | None = None,
    ) -> ToolResult:
        """执行工具调用的完整流水线。

        Args:
            tool_name: 工具名称
            tool_func: 原始工具函数
            args: 调用参数
            caller: 调用者上下文（user_id, permissions）
            handlers: 本次调用的 Handler 链覆盖（per-tool 定制，如内部
                工具跳过权限校验）；None 则使用构造时的默认链

        Returns:
            ToolResult（统一封装后的结果）
        """
        from src.agents.common.toolkits.registry import get_extra_metadata

        meta = get_extra_metadata(tool_name)
        meta_dict = meta.__dict__ if meta else {}

        ctx = ToolContext(
            tool_name=tool_name,
            args=args,
            meta=meta_dict,
            caller=caller,
        )

        # 链末端：执行原始函数
        execute_handler = ExecuteHandler(tool_func)

        # 从后往前包装: h1(h2(h3(...(execute))))
        chain: Callable = execute_handler.handle
        effective = handlers if handlers is not None else self._handlers
        if not effective:
            # 空自定义链（per-tool 覆盖为 []，跳过全部横切 Handler）：
            # 终端 handle 签名是 (ctx, next)，需补一层包装补齐参数
            async def direct(_ctx: ToolContext) -> ToolResult:
                return await execute_handler.handle(_ctx, None)

            chain = direct
        else:
            for handler in reversed(effective):
                outer = handler

                def make_next(h: RuntimeHandler, nxt: Callable) -> Callable:
                    async def wrapped(_ctx: ToolContext) -> ToolResult:
                        return await h.handle(_ctx, nxt)
                    return wrapped

                chain = make_next(outer, chain)

        return await chain(ctx)


# ════════════════════════════════════════════════════════════════
# 全局 Runtime 实例
# ════════════════════════════════════════════════════════════════

_runtime: RuntimeChain | None = None
_lifecycle_handler: LifecycleHandler | None = None


def configure_runtime(
    handlers: list[RuntimeHandler] | None = None,
) -> RuntimeChain:
    """配置全局 Runtime（应用启动时一次性调用）。

    Args:
        handlers: Handler 列表，None 则使用默认链
    """
    global _runtime, _lifecycle_handler

    if handlers is None:
        lifecycle = LifecycleHandler()
        _lifecycle_handler = lifecycle
        handlers = [
            PermissionHandler(),
            RateLimitHandler(),
            IdempotencyHandler(),
            WatchdogHandler(heartbeat_interval=5.0, max_missed_heartbeats=3),
            lifecycle,
            TimeoutRetryHandler(),
            OffloadHandler(),
            ResultWrapHandler(),
        ]

    _runtime = RuntimeChain(handlers)
    return _runtime


def get_runtime() -> RuntimeChain:
    """获取全局 Runtime 实例。"""
    global _runtime
    if _runtime is None:
        _runtime = configure_runtime()
    return _runtime


def get_lifecycle_handler() -> LifecycleHandler | None:
    """获取生命周期 Handler，用于注册事件消费者。"""
    global _lifecycle_handler
    return _lifecycle_handler
