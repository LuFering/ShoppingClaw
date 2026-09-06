"""
SSE 会话管理器 - 参考 ScienceClaw 的会话事件溯源

管理 SSE 会话状态，支持断线重连和事件回放。
每个会话维护一个事件历史队列，客户端可以通过 last_event_id 从断点恢复。

核心功能：
1. 事件回放（断线重连）
2. 心跳机制防止超时
3. 超时保护（asyncio.timeout）
4. 内存管理（自动清理旧事件）
"""
import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional


class SSESession:
    """单个 SSE 会话"""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.events: List[Dict[str, Any]] = []  # 已发送的事件历史
        self.queue: asyncio.Queue = asyncio.Queue()  # 待发送事件
        self.last_event_id: int = 0
        self.is_active: bool = True
        self.created_at: float = time.time()  # 创建时间
        self.last_accessed_at: float = time.time()  # 最后访问时间
        self.event_count: int = 0  # 事件计数器
    
    def add_event(self, event: Dict[str, Any]):
        """添加事件到历史和队列"""
        event["event_id"] = str(self.last_event_id)
        event["timestamp"] = time.time()  # 添加时间戳
        self.events.append(event)
        self.last_event_id += 1
        self.event_count += 1
        self.last_accessed_at = time.time()
    
    def get_events_since(self, cursor: int) -> List[Dict[str, Any]]:
        """
        获取 cursor 之后的所有事件（用于重连回放）
        
        Args:
            cursor: 最后接收的事件 ID
            
        Returns:
            新事件列表
        """
        return [
            e for e in self.events
            if int(e.get("event_id", 0)) > cursor
        ]
    
    def deactivate(self):
        """标记会话为非活跃状态"""
        self.is_active = False


class SSESessionManager:
    """
    SSE 会话管理器（单例模式）
    
    功能:
    1. 管理多个 SSE 会话
    2. 支持事件回放（断线重连）
    3. 心跳机制防止超时
    
    使用方式:
    ```python
    manager = SSESessionManager()
    
    # 创建会话
    session = await manager.create_session(session_id)
    
    # 发送事件
    await manager.emit(session_id, event_dict)
    
    # 生成 SSE 流
    async for sse_line in manager.event_generator(session_id, last_event_id=0):
        yield sse_line
    ```
    """
    
    _instance = None
    _sessions: Dict[str, SSESession] = {}
    _max_history = 1000  # 每个会话最多保留 1000 个事件
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
    
    async def create_session(self, session_id: str) -> SSESession:
        """
        创建新的 SSE 会话
        
        Args:
            session_id: 会话 ID（通常是 thread_id）
            
        Returns:
            SSESession 对象
        """
        session = SSESession(session_id)
        self._sessions[session_id] = session
        return session
    
    async def emit(self, session_id: str, event: Dict[str, Any]):
        """
        发送事件到指定会话
        
        Args:
            session_id: 会话 ID
            event: 事件字典
        """
        session = self._sessions.get(session_id)
        if not session:
            return
        
        session.add_event(event)
        await session.queue.put(event)
        
        # 清理旧事件（保留最近 max_history 个）
        if len(session.events) > self._max_history:
            session.events = session.events[-self._max_history:]
    
    async def event_generator(
        self,
        session_id: str,
        last_event_id: int = 0,
        timeout: int = 600,
        max_timeout: int = 10800,  # 最大超时时间（3小时）
    ) -> AsyncGenerator[str, None]:
        """
        SSE 事件生成器 — 先回放，再流式
        
        Args:
            session_id: 会话 ID
            last_event_id: 最后接收的事件 ID（用于重连）
            timeout: 心跳间隔（秒）
            max_timeout: 最大超时时间（秒），防止无限等待
            
        Yields:
            格式化的 SSE 字符串
        """
        session = self._sessions.get(session_id)
        if not session:
            yield self._format_sse({
                "type": "error",
                "error": "Session not found",
                "session_id": session_id,
            })
            return
        
        start_time = time.time()
        
        try:
            # ═══ 1. 回放断连期间的事件 ═══
            missed = session.get_events_since(last_event_id)
            if missed:
                logging.info(
                    f"[SSE] Replaying {len(missed)} missed events for session {session_id}"
                )
                for event in missed:
                    yield self._format_sse(event)
            
            # ═══ 2. 流式发送新事件（带超时保护）═══
            while session.is_active:
                # 检查是否超过最大超时时间
                elapsed = time.time() - start_time
                if elapsed > max_timeout:
                    logging.warning(
                        f"[SSE] Session {session_id} exceeded max timeout ({max_timeout}s)"
                    )
                    yield self._format_sse({
                        "type": "error",
                        "error_type": "timeout",
                        "message": f"请求处理超时（{max_timeout}秒），请简化您的问题后重试",
                    })
                    break
                
                try:
                    event = await asyncio.wait_for(
                        session.queue.get(),
                        timeout=timeout
                    )
                    yield self._format_sse(event)
                    session.last_accessed_at = time.time()
                    
                except asyncio.TimeoutError:
                    # 发送心跳防止连接超时
                    yield ": heartbeat\n\n"
                    logging.debug(f"[SSE] Heartbeat sent for session {session_id}")
        
        except Exception as e:
            logging.error(f"[SSE] Error in event generator for session {session_id}: {e}")
            yield self._format_sse({
                "type": "error",
                "error": str(e),
            })
        finally:
            # 清理资源
            logging.info(
                f"[SSE] Session {session_id} closed after {time.time() - start_time:.2f}s, "
                f"total events: {session.event_count}"
            )
    
    def deactivate_session(self, session_id: str):
        """
        停用会话
        
        Args:
            session_id: 会话 ID
        """
        session = self._sessions.get(session_id)
        if session:
            session.deactivate()
    
    def cleanup_session(self, session_id: str):
        """
        清理会话（从管理器中移除）
        
        Args:
            session_id: 会话 ID
        """
        if session_id in self._sessions:
            session = self._sessions[session_id]
            logging.info(
                f"[SSE] Cleaning up session {session_id}: "
                f"created={time.time() - session.created_at:.2f}s ago, "
                f"events={session.event_count}"
            )
            del self._sessions[session_id]
    
    def cleanup_inactive_sessions(self, max_age: int = 3600):
        """
        清理不活跃的会话
        
        Args:
            max_age: 最大不活跃时间（秒），默认 1 小时
        """
        now = time.time()
        to_remove = []
        
        for session_id, session in self._sessions.items():
            if not session.is_active or (now - session.last_accessed_at) > max_age:
                to_remove.append(session_id)
        
        for session_id in to_remove:
            self.cleanup_session(session_id)
        
        if to_remove:
            logging.info(f"[SSE] Cleaned up {len(to_remove)} inactive sessions")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取会话管理器统计信息
        
        Returns:
            统计信息字典
        """
        now = time.time()
        active_sessions = [
            s for s in self._sessions.values() if s.is_active
        ]
        
        return {
            "total_sessions": len(self._sessions),
            "active_sessions": len(active_sessions),
            "total_events": sum(s.event_count for s in self._sessions.values()),
            "avg_events_per_session": (
                sum(s.event_count for s in self._sessions.values()) / len(self._sessions)
                if self._sessions else 0
            ),
        }
    
    @staticmethod
    def _format_sse(event: Dict[str, Any]) -> str:
        """
        格式化标准 SSE 事件（不修改原始 event 字典）

        SSE 格式:
        ```
        id: 123
        event: message_chunk
        data: {"content": "..."}

        ```
        """
        event_type = event.get("type", "message")
        event_id = event.get("event_id", "0")
        # 构建干净的 data，排除协议字段
        sse_data = {k: v for k, v in event.items()
                     if k not in ("type", "event_id")}

        lines = [
            f"id: {event_id}",
            f"event: {event_type}",
            f"data: {json.dumps(sse_data, ensure_ascii=False)}",
            "",  # 空行表示事件结束
            ""  # 额外空行（SSE 规范）
        ]
        return "\n".join(lines)


# 全局单例
_session_manager: SSESessionManager | None = None


def get_session_manager() -> SSESessionManager:
    """获取全局 SSESessionManager 实例"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SSESessionManager()
    return _session_manager
