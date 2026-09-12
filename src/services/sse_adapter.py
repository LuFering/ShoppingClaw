"""
SSE 协议适配器 - 将旧的 status-based 协议转换为新的 EventType-based 协议

这个模块提供了向后兼容的转换函数，允许逐步迁移到新的 SSE 协议。
"""
import json
import logging
from typing import Any, Dict, Optional

from src.services.sse_protocol import EventType


def format_sse_event(event_type: EventType | str, data: Dict[str, Any]) -> str:
    """
    格式化标准 SSE 事件
    
    SSE 格式规范:
    ```
    event: message_chunk
    id: 123
    data: {"content": "..."}
    
    ```
    
    Args:
        event_type: 事件类型（EventType 枚举或字符串）
        data: 事件数据字典
        
    Returns:
        格式化的 SSE 字符串
    """
    if isinstance(event_type, EventType):
        event_type = event_type.value
    
    # 生成事件 ID（如果未提供）
    if "event_id" not in data:
        import time
        data["event_id"] = str(int(time.time() * 1000))

    event_id = data.get("event_id", "0")
    # 构建 data 的副本，排除协议字段，避免污染 SSE 输出
    sse_data = {k: v for k, v in data.items() if k not in ("event_id", "type")}

    lines = [
        f"event: {event_type}",
        f"id: {event_id}",
        f"data: {json.dumps(sse_data, ensure_ascii=False)}",
        "",  # 空行表示事件结束
        ""  # 额外空行（SSE 规范）
    ]
    return "\n".join(lines)


def _coerce_plan_steps(plan: Any) -> list[dict]:
    """把 plan 归一化成步骤列表，绝不抛异常。

    正常情况 plan 是 ``{"steps": [...]}``（见 ThinkingProcessMiddleware）。
    但线上实测出现过 plan 是**字符串**的情况——LangGraph 的 custom 流在某些
    中间件写入后会把嵌套结构转成 str。此时原来的 ``plan.get("steps")`` 直接抛
    AttributeError，异常冒泡到 stream_agent_chat 的外层 except，
    **整条 SSE 流被打断**，前端只能看到一句
    「Error streaming messages: 'str' object has no attribute 'get'」。

    宁可少推一次计划更新，也不能让整轮对话崩掉，所以这里做容错：
    字符串尝试 JSON 解析，解析不出或结构不对就返回空列表。
    """
    if isinstance(plan, dict):
        steps = plan.get("steps")
        return steps if isinstance(steps, list) else []
    if isinstance(plan, list):
        return plan
    if isinstance(plan, str):
        try:
            return _coerce_plan_steps(json.loads(plan))
        except Exception:
            logging.warning(
                "[sse_adapter] plan_update 的 plan 不是预期结构，已忽略: %r",
                plan[:200] if len(plan) > 200 else plan,
            )
            return []
    return []


def convert_legacy_chunk_to_sse(chunk: Dict[str, Any]) -> list[str]:
    """
    将旧的 status-based chunk 转换为新的 SSE 事件
    
    旧格式:
    ```python
    {
        "status": "loading",
        "content": "...",
        "event": "tool_call",
        "tool_call": {...}
    }
    ```
    
    新格式:
    ```
    event: message_chunk
    id: 123
    data: {"content": "..."}
    
    event: tool_start
    id: 124
    data: {"tool_name": "...", ...}
    ```
    
    Args:
        chunk: 旧的 chunk 字典
        
    Returns:
        SSE 事件字符串列表
    """
    status = chunk.get("status") or chunk.get("state", "")
    events = []
    
    # ═══ Init 事件 ═══
    if status == "init":
        events.append(format_sse_event(EventType.INIT, {
            "meta": chunk.get("meta", {}),
            "msg": chunk.get("msg", {}),
        }))
    
    # ═══ Loading/Thinking 事件 ═══
    elif status == "loading":
        content = chunk.get("content") or chunk.get("response", "")
        if content:
            events.append(format_sse_event(EventType.MESSAGE_CHUNK, {
                "content": content,
                "role": "assistant",
                # 归属的 AI 消息 id（LangChain run id）。同一轮的所有增量共享该值，
                # 前端据此把正文与工具归并为同一条消息，实现 正文->工具->正文 交错。
                "message_id": chunk.get("message_id"),
            }))
    
    # ═══ Thinking Process 事件 ═══
    elif status == "thinking_process":
        event_type = chunk.get("event", "")
        
        if event_type == "thinking":
            # 思考过程内容
            content = chunk.get("content", "")
            if content:
                events.append(format_sse_event(EventType.THINKING, {
                    "content": content,
                }))
        elif event_type == "tool_call":
            tool_call = chunk.get("tool_call", {})
            tool_status = tool_call.get("status", "calling")
            
            if tool_status == "calling":
                events.append(format_sse_event(EventType.TOOL_START, {
                    "tool_name": tool_call.get("function") or tool_call.get("name", ""),
                    "tool_call_id": tool_call.get("tool_call_id", ""),
                    "arguments": tool_call.get("args", {}),
                    "meta": tool_call.get("tool_meta", {}),
                    "message_id": tool_call.get("message_id"),
                }))
            elif tool_status == "completed":
                events.append(format_sse_event(EventType.TOOL_COMPLETE, {
                    "tool_name": tool_call.get("function") or tool_call.get("name", ""),
                    "tool_call_id": tool_call.get("tool_call_id", ""),
                    "result_preview": str(tool_call.get("content", ""))[:500],
                    "duration_ms": tool_call.get("duration_ms"),
                    "meta": tool_call.get("tool_meta", {}),
                    "message_id": tool_call.get("message_id"),
                }))
        
        elif event_type == "tool_result":
            tool_call = chunk.get("tool_call", {})
            events.append(format_sse_event(EventType.TOOL_COMPLETE, {
                "tool_name": tool_call.get("function") or tool_call.get("name", ""),
                "tool_call_id": tool_call.get("tool_call_id", ""),
                "result_preview": str(tool_call.get("content", ""))[:500],
                "result_content": tool_call.get("content", ""),
                "duration_ms": tool_call.get("duration_ms"),
                "meta": tool_call.get("tool_meta", {}),
                "message_id": tool_call.get("message_id"),
            }))
        
        elif event_type == "plan_update":
            events.append(format_sse_event(EventType.PLAN_UPDATE, {
                "steps": _coerce_plan_steps(chunk.get("plan")),
            }))
    
    # ═══ Agent State 事件 ═══
    elif status == "agent_state":
        agent_state = chunk.get("agent_state", {})
        todos = agent_state.get("todos", [])
        if todos:
            events.append(format_sse_event(EventType.PLAN_UPDATE, {
                "steps": _convert_todos_to_steps(todos),
            }))
    
    # ═══ Finished 事件 ═══
    elif status == "finished":
        events.append(format_sse_event(EventType.DONE, {
            "statistics": chunk.get("statistics", {}),
        }))
    
    # ═══ Error 事件 ═══
    elif status == "error":
        events.append(format_sse_event(EventType.ERROR, {
            "error_type": chunk.get("error_type", "unknown"),
            "message": chunk.get("error_message", "未知错误"),
        }))
    
    return events


def _convert_todos_to_steps(todos: list) -> list[dict]:
    """将 TODO 列表转换为步骤列表"""
    steps = []
    for index, todo in enumerate(todos[:20]):
        if isinstance(todo, dict):
            content = todo.get("content") or todo.get("description") or str(todo)
            steps.append({
                "id": str(todo.get("id") or f"step_{index + 1}"),
                "description": content,
                "title": content,
                "status": _normalize_step_status(todo.get("status")),
                "toolCallIds": todo.get("tool_call_ids") or [],
            })
        else:
            content = str(todo)
            steps.append({
                "id": f"step_{index + 1}",
                "description": content,
                "title": content,
                "status": "pending",
                "toolCallIds": [],
            })
    return steps


def _normalize_step_status(status: str | None) -> str:
    """标准化步骤状态"""
    value = (status or "pending").lower()
    if value in {"completed", "complete", "done", "success"}:
        return "completed"
    if value in {"in_progress", "running", "active", "processing"}:
        return "running"
    if value in {"failed", "error", "cancelled", "canceled"}:
        return "failed"
    return "pending"


# ═══ 使用示例 ═══

if __name__ == "__main__":
    # 示例 1: 直接创建 SSE 事件
    event = format_sse_event(EventType.MESSAGE_CHUNK, {
        "content": "你好，世界！",
        "role": "assistant",
    })
    print("示例 1 - 直接创建:")
    print(event)
    print()
    
    # 示例 2: 转换旧格式 chunk
    legacy_chunk = {
        "status": "thinking_process",
        "event": "tool_call",
        "tool_call": {
            "tool_call_id": "call_123",
            "function": "search_products",
            "args": {"query": "iPhone 16"},
            "status": "calling",
            "tool_meta": {
                "icon": "🔍",
                "category": "jd_api",
                "description": "搜索商品",
            },
        },
    }
    
    sse_events = convert_legacy_chunk_to_sse(legacy_chunk)
    print("示例 2 - 转换旧格式:")
    for sse in sse_events:
        print(sse)
        print()
