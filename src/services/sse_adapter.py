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


def event_type_str(t) -> str:
    """事件类型统一成字符串（EventType 是枚举，直接拼进 SSE 会变成 'EventType.XXX'）。"""
    return t.value if isinstance(t, EventType) else str(t)


def legacy_chunk_to_events(chunk: Dict[str, Any]) -> list[tuple[str, Dict[str, Any]]]:
    """把旧的 status-based chunk 拆成 [(event_type, data), ...]。

    这是「事件构造」那一半，`convert_legacy_chunk_to_sse` 是「序列化」那一半。
    拆开是为了让**会话缓冲（供刷新后回放）**复用同一份判定逻辑——
    否则线上实时发的事件和断线后回放的事件会漂移成两套。

    旧格式:
    ```python
    {"status": "loading", "content": "...", "event": "tool_call", "tool_call": {...}}
    ```
    """
    status = chunk.get("status") or chunk.get("state", "")
    events: list[tuple[str, Dict[str, Any]]] = []

    # ═══ Init 事件 ═══
    if status == "init":
        events.append((EventType.INIT, {
            "meta": chunk.get("meta", {}),
            "msg": chunk.get("msg", {}),
        }))

    # ═══ Loading/Thinking 事件 ═══
    elif status == "loading":
        content = chunk.get("content") or chunk.get("response", "")
        if content:
            events.append((EventType.MESSAGE_CHUNK, {
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
            content = chunk.get("content", "")
            if content:
                events.append((EventType.THINKING, {"content": content}))
        elif event_type == "tool_call":
            tool_call = chunk.get("tool_call", {})
            tool_status = tool_call.get("status", "calling")

            if tool_status == "calling":
                _start_event = {
                    "tool_name": tool_call.get("function") or tool_call.get("name", ""),
                    "tool_call_id": tool_call.get("tool_call_id", ""),
                    "arguments": tool_call.get("args", {}),
                    "meta": tool_call.get("tool_meta", {}),
                    "message_id": tool_call.get("message_id"),
                }
                # ═══ 富载荷透传：契约 v1.0 的两个编排卡字段 ═══
                # 这两个字段是「runtime 合成」出来的，不是工具真实返回值，
                # 但前端 OrchestrateTool.vue / TaskTool.vue 完全靠它们渲染。
                # 若在这里被白名单丢掉，卡片会退化成空壳 —— 静默失败，很难查。
                # 所以：显式透传，且未显形分区必须保持空值（不省略键）。
                if "orchestration" in tool_call:
                    _start_event["orchestration"] = tool_call["orchestration"]
                if "subagent_run" in tool_call:
                    _start_event["subagent_run"] = tool_call["subagent_run"]
                events.append((EventType.TOOL_START, _start_event))
            elif tool_status == "completed":
                _done_event = {
                    "tool_name": tool_call.get("function") or tool_call.get("name", ""),
                    "tool_call_id": tool_call.get("tool_call_id", ""),
                    "result_preview": str(tool_call.get("content", ""))[:500],
                    "result_content": tool_call.get("content", ""),
                    "duration_ms": tool_call.get("duration_ms"),
                    "meta": tool_call.get("tool_meta", {}),
                    "message_id": tool_call.get("message_id"),
                }
                if "orchestration" in tool_call:
                    _done_event["orchestration"] = tool_call["orchestration"]
                if "subagent_run" in tool_call:
                    _done_event["subagent_run"] = tool_call["subagent_run"]
                events.append((EventType.TOOL_COMPLETE, _done_event))

        elif event_type == "tool_result":
            tool_call = chunk.get("tool_call", {})
            _result_event = {
                "tool_name": tool_call.get("function") or tool_call.get("name", ""),
                "tool_call_id": tool_call.get("tool_call_id", ""),
                "result_preview": str(tool_call.get("content", ""))[:500],
                "result_content": tool_call.get("content", ""),
                "duration_ms": tool_call.get("duration_ms"),
                "meta": tool_call.get("tool_meta", {}),
                "message_id": tool_call.get("message_id"),
            }
            # 同上：收尾事件也必须带上富载荷，否则卡片停在 running 态。
            if "orchestration" in tool_call:
                _result_event["orchestration"] = tool_call["orchestration"]
            if "subagent_run" in tool_call:
                _result_event["subagent_run"] = tool_call["subagent_run"]
            events.append((EventType.TOOL_COMPLETE, _result_event))

        elif event_type == "plan_update":
            events.append((EventType.PLAN_UPDATE, {
                "steps": _coerce_plan_steps(chunk.get("plan")),
            }))

    # ═══ Agent State 事件 ═══
    elif status == "agent_state":
        agent_state = chunk.get("agent_state", {})
        todos = agent_state.get("todos", [])
        if todos:
            events.append((EventType.PLAN_UPDATE, {
                "steps": _convert_todos_to_steps(todos),
            }))

    # ═══ Subagent Drill 事件（★ 本次新增，后端原先完全没有）═══
    # 子智能体「展开 / 收起」：expand 让用户看见它内部在做什么，
    # collapse 干完后把那段收起来、视线交还主线。
    # 前端 case 'subagent_drill' → setToolCallDrill(slug, action) 已就绪，
    # 只写 drill 标志、不当场改展开态（用户手动折叠过的不被强行重开）。
    elif status == "subagent_drill":
        events.append((EventType.SUBAGENT_DRILL, {
            "slug": chunk.get("slug", ""),
            "action": chunk.get("action", "expand"),
            "description": chunk.get("description", ""),
            "message_id": chunk.get("message_id"),
        }))

    # ═══ Finished 事件 ═══
    elif status == "finished":
        events.append((EventType.DONE, {
            "statistics": chunk.get("statistics", {}),
        }))

    # ═══ Error 事件 ═══
    elif status == "error":
        events.append((EventType.ERROR, {
            "error_type": chunk.get("error_type", "unknown"),
            "message": chunk.get("error_message", "未知错误"),
        }))

    return events


def convert_legacy_chunk_to_sse(chunk: Dict[str, Any]) -> list[str]:
    """将旧的 status-based chunk 转换为新的 SSE 事件文本。

    Args:
        chunk: 旧的 chunk 字典

    Returns:
        SSE 事件字符串列表
    """
    return [format_sse_event(event_type_str(t), d) for t, d in legacy_chunk_to_events(chunk)]


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
