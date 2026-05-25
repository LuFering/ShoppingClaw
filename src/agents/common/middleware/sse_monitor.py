"""
SSE 监控中间件 - 参考 ScienceClaw 的 SSEMonitoringMiddleware

拦截工具调用，生成结构化的 SSE 事件（tool_start/tool_complete），
包含耗时统计、元数据等信息。
"""
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4


import json
import logging

_log = logging.getLogger(__name__)

from src.agents.common.middleware.base import AgentMiddleware, ToolCallRequest
from src.services.sse_protocol import EventType
from src.services.tool_registry import get_tool_registry


def _serialize_tool_result(result) -> str | None:
    """Serialize tool result to JSON string for frontend parsing."""
    if result is None:
        return None
    if isinstance(result, str):
        return result
    if isinstance(result, (dict, list)):
        try:
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception:
            return str(result)
    content_attr = getattr(result, "content", None)
    if content_attr is not None:
        if isinstance(content_attr, str):
            return content_attr
        try:
            return json.dumps(content_attr, ensure_ascii=False, default=str)
        except Exception:
            return str(content_attr)
    return str(result)

class SSEMonitoringMiddleware(AgentMiddleware):
    """
    SSE 监控中间件
    
    功能:
    1. 拦截所有工具调用
    2. 在调用前发送 tool_start 事件
    3. 在调用后发送 tool_complete 事件（含耗时）
    4. 收集统计数据
    
    使用方式:
    ```python
    middleware = SSEMonitoringMiddleware()
    graph = builder.compile(middleware=[middleware])
    
    # 在流式响应中获取事件
    events = middleware.drain_events()
    ```
    """
    
    def __init__(self):
        self.events: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self.stats = {
            "total_tool_calls": 0,
            "total_duration_ms": 0,
            "failed_calls": 0,
        }
    
    def wrap_tool_call(self, request: ToolCallRequest, handler) -> Any:
        """
        包装工具调用，发送结构化 SSE 事件
        
        Args:
            request: 工具调用请求
            handler: 原始处理函数
            
        Returns:
            工具调用结果
        """
        tool_name = request.tool_call.get("name", "unknown")
        _log.info(f"[SSE-DEBUG] wrap_tool_call ENTER: tool={tool_name}")
        tool_args = request.tool_call.get("args", {})
        
        # 获取工具元数据
        registry = get_tool_registry()
        meta = registry.get_meta(tool_name)
        
        start_time = time.time()
        
        # ═══ 发送 tool_start 事件 ═══
        self._emit({
            "type": EventType.TOOL_START,
            "tool_name": tool_name,
            "tool_call_id": request.tool_call.get("id", ""),
            "arguments": tool_args,
            "meta": {
                "icon": meta.icon,
                "category": meta.category,
                "description": meta.description,
            },
            "event_id": f"tool_{uuid4().hex[:8]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        
        try:
            # 执行工具调用
            result = handler(request)
            
            # 计算耗时
            duration_ms = int((time.time() - start_time) * 1000)
            
            # ═══ 发送 tool_complete 事件 ═══
            result_content = _serialize_tool_result(result)
            _log.info(f"[SSE-DEBUG] tool_complete: tool={tool_name} rc_len={len(result_content) if result_content else 0}")

            self._emit({
                "type": EventType.TOOL_COMPLETE,
                "tool_name": tool_name,
                "tool_call_id": request.tool_call.get("id", ""),
                "result_preview": str(result)[:500] if result else "",  # 截断预览
                "result_content": result_content,
                "duration_ms": duration_ms,
                "meta": {
                    "icon": meta.icon,
                    "category": meta.category,
                    "description": meta.description,
                },
                "event_id": f"tool_{uuid4().hex[:8]}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            
            # 更新统计
            with self._lock:
                self.stats["total_tool_calls"] += 1
                self.stats["total_duration_ms"] += duration_ms
            
            return result
            
        except Exception as e:
            # ═══ 发送 error 事件 ═══
            self._emit({
                "type": EventType.ERROR,
                "tool_name": tool_name,
                "tool_call_id": request.tool_call.get("id", ""),
                "error": str(e),
                "error_type": type(e).__name__,
                "event_id": f"error_{uuid4().hex[:8]}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            
            # 更新统计
            with self._lock:
                self.stats["failed_calls"] += 1
            
            raise
    
    async def awrap_tool_call(self, request: ToolCallRequest, handler) -> Any:
        """异步版本的 wrap_tool_call"""
        return self.wrap_tool_call(request, handler)
    
    def _emit(self, event: Dict[str, Any]):
        """
        添加事件到队列（线程安全）
        
        Args:
            event: 事件字典
        """
        with self._lock:
            self.events.append(event)
    
    def drain_events(self) -> List[Dict[str, Any]]:
        """
        取出并清空所有事件（线程安全）
        
        Returns:
            事件列表
        """
        with self._lock:
            events = self.events.copy()
            self.events.clear()
            return events
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计数据
        
        Returns:
            统计字典
        """
        with self._lock:
            return self.stats.copy()
    
    def reset_stats(self):
        """重置统计数据"""
        with self._lock:
            self.stats = {
                "total_tool_calls": 0,
                "total_duration_ms": 0,
                "failed_calls": 0,
            }
