"""统一工具结果协议 — ToolStatus 枚举 + ToolResult 数据结构。

所有工具经由 ToolRuntime 执行后，统一返回 ToolResult 格式，
供 Agent 决策、SSE 监控、Trace 链路、Audit 审计消费。
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ToolStatus(str, Enum):
    """工具执行状态 — 完整状态机。

    状态流转：
        pending → running → success
                 running → error
                 running → timeout → (重试) → success / timeout
                 running → hung (watchdog 判定)
                 running → cancelled (外部中断)
    """

    PENDING = "pending"          # 已提交，等待执行
    RUNNING = "running"          # 正在执行
    SUCCESS = "success"          # 成功完成
    ERROR = "error"              # 异常失败
    TIMEOUT = "timeout"          # 超时
    HUNG = "hung"                # 挂死（watchdog 心跳超时判定）
    CANCELLED = "cancelled"      # 被外部取消
    FORBIDDEN = "forbidden"      # 权限不足
    RATE_LIMITED = "rate_limited"  # 触发限流

    @classmethod
    def terminal_statuses(cls) -> set["ToolStatus"]:
        """不会继续流转的终态集合。"""
        return {cls.SUCCESS, cls.ERROR, cls.TIMEOUT, cls.HUNG, cls.CANCELLED}

    @classmethod
    def transient_statuses(cls) -> set["ToolStatus"]:
        """可继续流转的过渡态集合。"""
        return {cls.PENDING, cls.RUNNING}

    @classmethod
    def blocked_statuses(cls) -> set["ToolStatus"]:
        """执行被拦截（未调用工具函数）的状态集合。"""
        return {cls.FORBIDDEN, cls.RATE_LIMITED}


@dataclass
class ToolResult:
    """所有工具的统一定向返回结构。

    Attributes:
        status: 执行状态（success / error / timeout / hung / ...）
        data: 业务数据，success 时有值
        error: 人类可读的错误描述，失败时有值
        metadata: 运行时元信息（tool_name, duration_ms, attempt, cached 等）
    """

    status: ToolStatus
    data: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # ── 便捷构造器 ──

    @classmethod
    def success(cls, data: Any = None, **meta) -> "ToolResult":
        meta.setdefault("completed_at", _time.time())
        return cls(status=ToolStatus.SUCCESS, data=data, metadata=meta)

    @classmethod
    def failure(cls, status: ToolStatus, error: str, **meta) -> "ToolResult":
        meta.setdefault("completed_at", _time.time())
        return cls(status=status, error=error, metadata=meta)

    @classmethod
    def error_result(cls, error: str, **meta) -> "ToolResult":
        return cls.failure(ToolStatus.ERROR, error, **meta)

    @classmethod
    def timeout_result(cls, error: str, **meta) -> "ToolResult":
        return cls.failure(ToolStatus.TIMEOUT, error, **meta)

    @classmethod
    def hung_result(cls, error: str, **meta) -> "ToolResult":
        return cls.failure(ToolStatus.HUNG, error, **meta)

    @classmethod
    def forbidden_result(cls, error: str, **meta) -> "ToolResult":
        return cls.failure(ToolStatus.FORBIDDEN, error, **meta)

    @classmethod
    def rate_limited_result(cls, error: str, **meta) -> "ToolResult":
        return cls.failure(ToolStatus.RATE_LIMITED, error, **meta)

    # ── 状态查询 ──

    @property
    def is_success(self) -> bool:
        return self.status == ToolStatus.SUCCESS

    @property
    def is_terminal(self) -> bool:
        return self.status in ToolStatus.terminal_statuses()

    @property
    def is_transient(self) -> bool:
        return self.status in ToolStatus.transient_statuses()

    @property
    def is_blocked(self) -> bool:
        return self.status in ToolStatus.blocked_statuses()

    # ── 序列化 ──

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata,
        }

    def to_agent_message(self) -> str:
        """转为 Agent 可理解的消息文本。"""
        if self.is_success:
            return str(self.data) if self.data is not None else ""
        return f"[工具执行失败: {self.status.value}] {self.error or ''}"
