import asyncio
import json
import logging
import traceback
import uuid

from langchain_core.messages import HumanMessage, AIMessageChunk, AIMessage, ToolMessage
from src.config import config as conf
from src.agents import agent_manager
from src.plugins.guard import content_guard
from src.repositories.agent_config_repository import AgentConfigRepository
from src.repositories.conversation_repository import ConversationRepository
from src.storage.postgres.manager import pg_manager
from src.services.memory_store import memory_store
from src.services.redis_store import MessageStoreBridge

# 统一存储桥接实例
_store_bridge = MessageStoreBridge()
# ═══ 新增：历史管理与用户记忆 ═══
from src.services.history_manager import HistoryManager
from src.services.user_memory import get_user_memory_service
# ═══ 新增：SSE 协议支持 ═══
from src.services.sse_protocol import EventType
from src.services.sse_adapter import format_sse_event, convert_legacy_chunk_to_sse
from src.agents.common.middleware.sse_monitor import SSEMonitoringMiddleware
from src.services.sse_session_manager import get_session_manager


def extract_agent_state(values: dict) -> dict:
    todos = values.get("todos")
    result = {
        "todos": list(todos)[:20] if todos else [],
        "files": values.get("files")
    }
    return result


def _ensure_full_msg(full_msg: AIMessage | None, accumulated_content: list[str]) -> AIMessage | None:
    if not full_msg and accumulated_content:
        return AIMessage(content="".join(accumulated_content))
    return full_msg


def _safe_json_dumps(value) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def _truncate(value, limit: int = 3000):
    if value is None:
        return None
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + f"... ({len(value)} chars total)"
    text = _safe_json_dumps(value)
    return value if len(text) <= limit else text[:limit] + f"... ({len(value)} chars total)"


def _message_text(content) -> str:
    """Extract displayable text from LangChain message content blocks."""
    if not content:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("content"):
                    parts.append(str(block.get("content")))
        return "".join(parts)
    return str(content)


def _tool_meta(name: str) -> dict:
    """Small frontend metadata registry, inspired by ScienceClaw's SSE protocol."""
    lower = (name or "").lower()
    if any(key in lower for key in ("search", "grep", "find")):
        return {"icon": "🔎", "category": "search", "description": name}
    if any(key in lower for key in ("file", "read", "write", "edit", "ls")):
        return {"icon": "📄", "category": "filesystem", "description": name}
    if any(key in lower for key in ("exec", "shell", "python", "terminal")):
        return {"icon": "⚙️", "category": "execution", "description": name}
    if any(key in lower for key in ("web", "browser", "crawl", "http")):
        return {"icon": "🌐", "category": "network", "description": name}
    if "task" in lower or "agent" in lower:
        return {"icon": "🤖", "category": "agent", "description": name}
    return {"icon": "🧰", "category": "tool", "description": name or "tool"}


def _normalize_step_status(status: str | None) -> str:
    value = (status or "pending").lower()
    if value in {"completed", "complete", "done", "success"}:
        return "completed"
    if value in {"in_progress", "running", "active", "processing"}:
        return "running"
    if value in {"failed", "error", "cancelled", "canceled"}:
        return "failed"
    return "pending"


def _todos_to_plan_steps(todos) -> list[dict]:
    if not isinstance(todos, list):
        return []
    steps: list[dict] = []
    for index, todo in enumerate(todos[:20]):
        if isinstance(todo, dict):
            content = todo.get("content") or todo.get("description") or todo.get("title") or str(todo)
            tool_call_ids = todo.get("tool_call_ids") or todo.get("toolCallIds") or []
            steps.append({
                "id": str(todo.get("id") or f"step_{index + 1}"),
                "description": content,
                "title": content,
                "status": _normalize_step_status(todo.get("status")),
                "toolCallIds": tool_call_ids if isinstance(tool_call_ids, list) else [],
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


async def _resolve_agent_config(
        db, agent_id: str, user_id: str, agent_config_id: int | str | None
) -> tuple:
    """解析 agent_config，返回 (config_item, agent_config_id)"""

    # TODO: 临时跳过数据库配置加载,返回默认配置
    if db is None:
        logging.warning("Database not available, using default agent config")

        # 创建一个简单的模拟对象
        class MockConfig:
            id = 0
            config_json = {"context": {}}

        return MockConfig(), 0

    config_repo = AgentConfigRepository(db)
    config_item = None
    if agent_config_id is not None:
        try:
            config_item = await config_repo.get_by_id(int(agent_config_id))
        except Exception:
            logging.warning(f"Failed to fetch agent config {agent_config_id}: {traceback.format_exc()}")
            config_item = None

    if config_item is None:
        config_item = await config_repo.get_or_create_default(
            agent_id=agent_id, created_by=user_id
        )
        agent_config_id = config_item.id

    return config_item, agent_config_id


async def save_partial_message(
        conv_repo,
        thread_id,
        full_msg,
        param=None,  # 兼容旧调用方式
        error_message=None,
        error_type=None
):
    """保存部分消息到数据库（使用 ConversationRepository）
    
    Args:
        conv_repo: ConversationRepository 实例
        thread_id: 会话 ID
        full_msg: AIMessage 对象
        param: 兼容参数（未使用）
        error_message: 错误信息
        error_type: 错误类型
    """
    if conv_repo is None:
        logging.warning("Database not available, skipping message save")
        return

    try:
        # 将 LangChain Message 转换为字典格式
        message_dict = {
            "role": "ai",
            "content": full_msg.content if hasattr(full_msg, 'content') else str(full_msg),
            "type": "ai",
            "timestamp": asyncio.get_event_loop().time(),
        }
        
        if error_message:
            message_dict["error_message"] = error_message
        if error_type:
            message_dict["error_type"] = error_type
        
        # 追加到数据库
        await conv_repo.add_message(thread_id, message_dict)
        logging.debug(f"[SaveMessage] Saved AI message to thread {thread_id}")
        
    except Exception as e:
        logging.error(f"Failed to save partial message: {e}")


async def check_and_handle_interrupts(agent, langgraph_config, make_chunk, meta, thread_id):
    """检查并处理中断(人工审批)

    TODO: 实现完整的中断检查逻辑
    当前: 空实现,直接返回
    """
    # 空异步生成器,表示没有中断需要处理
    return
    yield  # ← 使函数成为异步生成器


async def save_messages_from_langgraph_state(agent_instance, thread_id, conv_repo, config_dict):
    pass


async def stream_agent_chat(
        *,
        agent_name: str,
        query: str,
        config: dict,
        meta: dict,
        image_content: str | None,
        current_user,
        db,
):
    start_time = asyncio.get_event_loop().time()  # ← 性能监控

    # ═══ 初始化 SSE 会话管理器 ═══
    thread_id = config.get("thread_id") or str(uuid.uuid4())
    session_manager = get_session_manager()
    await session_manager.create_session(thread_id)
    
    # ═══ SSE 监控中间件引用（延迟获取：get_graph() 在 stream_messages 内部首次调用时创建）═══
    sse_middleware = None  # 在首次 drain 前从 agent.sse_middleware 获取

    # TODO:优化成Streamable HTTP
    def make_chunk(content=None, **kwargs):
        """实现 SSE 协议的数据格式部分 - 兼容旧格式"""
        chunk_data = {"request_id": meta.get("request_id"), "response": content, **kwargs}
        
        # ═══ 转换为新的 SSE 事件格式 ═══
        sse_events = convert_legacy_chunk_to_sse(chunk_data)
        return "".join(sse_events).encode("utf-8")

    if image_content:
        human_message = HumanMessage(
            content=[
                {"type": "text", "text": query},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_content}"}},
            ]
        )
        message_type = "multimodal_image"
    else:
        human_message = HumanMessage(content=query)  # <-传给messages
        message_type = "text"  # <-传给init_msg
    init_msg = {"role": "user", "content": query, "type": "human"}  # <-第一次chunk给前端

    if image_content:
        init_msg["message_type"] = message_type
        init_msg["image_content"] = image_content
    else:
        init_msg["message_type"] = message_type

    yield make_chunk(state="init", meta=meta, msg=init_msg)  # 先返回 init chunk，让前端知道"已收到请求"

    # 内容安全审查
    # if conf.enable_content_guard and await content_guard.check(query):
    #     yield make_chunk(
    #         status="error", error_type="content_guard_blocked", error_message="输入内容包含敏感词", meta=meta
    #     )
    #     return

    try:  # 获取 Agent 实例
        agent = agent_manager.get_agent(agent_name)
    except Exception as e:
        logging.error(f"Error getting agent {agent_name}: {e}, {traceback.format_exc()}")
        yield make_chunk(
            state="error",
            error_type="agent_error",
            error_message=f"智能体 {agent_name} 获取失败: {str(e)}",
            meta=meta,
        )
        return

    messages = [human_message]  # <- 传给agent

    user_id = str(current_user.id)

    # # 获取或创建 Agent 配置
    logging.debug(f">>>进入[stream_agent_chat]")
    logging.info(f"config:{config}")
    agent_config_id = config.get("agent_config_id")  # 前端传来的config中取出agent_config_id
    # config_item是 AgentConfig 对象
    config_item, agent_config_id = await _resolve_agent_config(db, agent_name, user_id, agent_config_id)

    # 如果没有 thread_id，自动生成（新对话）
    if not (thread_id := config.get("thread_id")):
        thread_id = str(uuid.uuid4())
        logging.warning(f"No thread_id provided, generated new thread_id: {thread_id}")

    # 确保 meta 中的 thread_id 与实际使用的一致
    meta["thread_id"] = thread_id

    # 构建 input_context（传递给 LangGraph）
    # config_json为AgentConfig 对象的核心配置（含 context 等）
    agent_config = (config_item.config_json or {}).get("context", {})
    input_context = {
        "user_id": user_id,
        "thread_id": thread_id,  # ← 关键：对话上下文 ID
        "agent_config_id": agent_config_id,
        "agent_config": agent_config,
    }

    full_msg = None
    accumulated_content: list[str] = []
    active_tool_calls: dict[str, dict] = {}
    emitted_tool_call_ids: set[str] = set()

    def emit_plan_from_state(agent_state: dict) -> bytes | None:
        steps = _todos_to_plan_steps(agent_state.get("todos") if isinstance(agent_state, dict) else None)
        if not steps:
            return None
        return make_chunk(
            status="thinking_process",
            event="plan_update",
            plan={"steps": steps},
            meta=meta,
        )

    def emit_tool_call(tool_call: dict, *, status: str = "calling") -> bytes:
        tool_call_id = str(tool_call.get("id") or tool_call.get("tool_call_id") or uuid.uuid4())
        function = tool_call.get("name") or tool_call.get("function") or "unknown"
        args = tool_call.get("args") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip().startswith(("{", "[")) else {"input": args}
            except Exception:
                args = {"input": args}
        active_tool_calls[tool_call_id] = {
            "tool_call_id": tool_call_id,
            "function": function,
            "args": args,
            "started_at": asyncio.get_event_loop().time(),
        }
        emitted_tool_call_ids.add(tool_call_id)
        meta_info = _tool_meta(function)
        return make_chunk(
            status="thinking_process",
            event="tool_call",
            tool_call={
                "tool_call_id": tool_call_id,
                "function": function,
                "name": function,
                "args": args,
                "status": status,
                "tool_meta": meta_info,
                "icon": meta_info.get("icon"),
            },
            meta=meta,
        )

    def emit_tool_result(tool_msg: ToolMessage) -> bytes:
        tool_call_id = str(getattr(tool_msg, "tool_call_id", "") or uuid.uuid4())
        cached = active_tool_calls.pop(tool_call_id, {})
        function = getattr(tool_msg, "name", "") or cached.get("function") or "unknown"
        started_at = cached.get("started_at")
        duration_ms = None
        if started_at:
            duration_ms = int((asyncio.get_event_loop().time() - started_at) * 1000)
        meta_info = _tool_meta(function)
        # 记录完成的工具调用（持久化用）
        _completed_tool_calls.append({
            "id": tool_call_id,
            "name": function,
            "args": cached.get("args", {}),
            "status": "completed",
            "duration_ms": duration_ms,
            "icon": meta_info.get("icon"),
            "category": meta_info.get("category"),
        })
        return make_chunk(
            status="thinking_process",
            event="tool_result",
            tool_call={
                "tool_call_id": tool_call_id,
                "function": function,
                "name": function,
                "args": cached.get("args", {}),
                "content": _truncate(getattr(tool_msg, "content", ""), 3000),
                "output": _truncate(getattr(tool_msg, "content", ""), 3000),
                "status": "completed",
                "duration_ms": duration_ms,
                "tool_meta": meta_info,
                "icon": meta_info.get("icon"),
            },
            meta=meta,
        )

    try:  # 外层 try: 包裹整个业务逻辑,捕获异常
        conv_repo = None
        if db is not None:
            conv_repo = ConversationRepository(db)
            try:
                await conv_repo.add_message(
                    thread_id=thread_id,
                    message={
                        "role": "user",
                        "content": query,
                        "type": "human",
                        "message_type": message_type,
                        "image_content": image_content,
                        "raw_message": human_message.model_dump() if hasattr(human_message, 'model_dump') else str(human_message),
                    },
                )
            except Exception as e:
                logging.error(f"Error saving user message to db: {e}")

        # 始终存入统一存储桥接 (供 History API 读取)
        await _store_bridge.add_message(thread_id, {
            "role": "user",
            "content": query,
            "type": "human",
            "message_type": message_type,
            "timestamp": asyncio.get_event_loop().time(),
        })

        # ═══ 自动标题生成：首条用户消息时自动生成对话标题 ═══
        user_msgs = await _store_bridge.get_messages(thread_id)
        user_msg_count = sum(1 for m in user_msgs if m.get("role") == "user")
        title_updated = False
        if user_msg_count == 1:
            # 第一条用户消息，自动生成标题（截取前30个字符）
            generated_title = query.strip()
            # 清理换行和多余空格
            generated_title = " ".join(generated_title.split())
            if len(generated_title) > 30:
                generated_title = generated_title[:30] + "..."
            if generated_title:
                logging.info(f"[AutoTitle] 为线程 {thread_id} 自动生成标题: {generated_title}")
                # 更新统一存储桥接
                await _store_bridge.update_thread(thread_id, title=generated_title)
                # 更新 PostgreSQL
                if conv_repo:
                    try:
                        await conv_repo.update_title(thread_id, generated_title)
                    except Exception as e:
                        logging.warning(f"[AutoTitle] PostgreSQL 标题更新失败: {e}")
                # 发送 title_update SSE 事件给前端
                title_event = {
                    "type": EventType.TITLE,
                    "thread_id": thread_id,
                    "title": generated_title,
                }
                yield format_sse_event(EventType.TITLE, title_event).encode("utf-8") + b"\n"
                title_updated = True

        # 先构建 langgraph_config
        langgraph_config = {"configurable": {"thread_id": thread_id, "user_id": user_id}}

        full_msg = None
        accumulated_content = []
        _pg_full_text: list[str] = []  # PostgreSQL 用：完整文本，不清空，保证 PG 存整段
        last_reasoning_length = 0  # 记录上一次发送的 reasoning_content 长度
        # 思考过程持久化：累积整个流式过程中的思考数据
        _thinking_chunks: list[str] = []  # 推理文本片段
        _completed_tool_calls: list[dict] = []  # 工具调用完成记录
        # 流式执行 Agent 推理
        async for chunk in agent.stream_messages(messages, input_context=input_context):
            # ═══ 处理 SSE 监控中间件事件 ═══
            if sse_middleware is None:
                sse_middleware = getattr(agent, 'sse_middleware', None)
            if sse_middleware is not None:
                middleware_events = sse_middleware.drain_events()
                if middleware_events:
                    names = [e.get("tool_name", e.get("type", "?")) for e in middleware_events]
                    print(f"[SSE-DRAIN] drained {len(middleware_events)} events: {names}", flush=True)
                for event in middleware_events:
                    await session_manager.emit(thread_id, event)
                    yield format_sse_event(event["type"], event).encode("utf-8") + b"\n"
            
            msg = None
            metadata = {}

            # 健壮性解包：兼容 base.py 的不同返回格式
            if isinstance(chunk, tuple):
                # 处理嵌套 tuple: ((message, mode), metadata)
                if len(chunk) == 2:
                    inner, metadata = chunk
                    if isinstance(inner, tuple) and len(inner) >= 1:
                        msg = inner[0]
                        if isinstance(inner[0], str) and len(inner) == 2:
                            msg = inner[1]
                    else:
                        msg = inner
                else:
                    msg = chunk[0]
                    metadata = chunk[-1] if isinstance(chunk[-1], dict) else {}
            elif isinstance(chunk, dict):
                # 某些模式下直接返回字典
                msg = chunk
            else:
                msg = chunk

            # 确保 metadata 是字典
            if not isinstance(metadata, dict):
                metadata = {}

            # 原有的消息处理逻辑
            if isinstance(msg, AIMessageChunk):
                content = _message_text(msg.content)
                additional_kwargs = getattr(msg, 'additional_kwargs', {})
                reasoning_content = additional_kwargs.get('reasoning_content', '')
                
                # 发送思考过程（如果有）- 只发送增量部分
                if reasoning_content:
                    # DeepSeek 的 reasoning_content 是累积模式，需要提取增量
                    new_reasoning = reasoning_content[last_reasoning_length:]
                    if new_reasoning:  # 只有当有新内容时才发送
                        logging.debug(f"[Reasoning] 总长度={len(reasoning_content)}, 上次长度={last_reasoning_length}, 增量长度={len(new_reasoning)}")
                        yield make_chunk(
                            status="thinking_process",
                            event="thinking",
                            content=new_reasoning
                        )
                        last_reasoning_length = len(reasoning_content)  # 更新长度
                        _thinking_chunks.append(new_reasoning)  # 持久化用

                for tool_chunk in getattr(msg, "tool_call_chunks", None) or []:
                    tool_call_id = tool_chunk.get("id")
                    tool_name = tool_chunk.get("name")
                    if tool_call_id and tool_name and str(tool_call_id) not in emitted_tool_call_ids:
                        yield emit_tool_call({
                            "id": str(tool_call_id),
                            "name": tool_name,
                            "args": tool_chunk.get("args") or {},
                        })

                if content is not None:  # 允许空字符串，只要不是 None
                    accumulated_content.append(content)
                    _pg_full_text.append(content)

                # # 敏感词检查（每 10 个 chunk 检查一次）
                # content_for_check = "".join(accumulated_content[-10:])
                # if conf.enable_content_guard and await content_guard.check_with_keywords(content_for_check):
                #     full_msg = AIMessage(content="".join(accumulated_content))
                #     if conv_repo:
                #         await save_partial_message(conv_repo, thread_id, full_msg, "content_guard_blocked")
                #     meta["time_cost"] = asyncio.get_event_loop().time() - start_time
                #     yield make_chunk(status="interrupted", message="检测到敏感内容，已中断输出", meta=meta)
                #     return

                ## 流式返回给前端
                yield make_chunk(content=content, msg=msg.model_dump(), metadata=metadata, status="loading")
            else:
                # 处理非 Chunk 类型的消息（如完整的 AIMessage, ToolMessage 或 updates 字典）
                is_process_update = (metadata or {}).get("stream_mode") == "updates"
                
                # 如果 msg 是字典（updates 模式的状态快照），则不执行 model_dump
                if isinstance(msg, dict):
                    msg_dict = msg
                elif hasattr(msg, 'model_dump'):
                    msg_dict = msg.model_dump()  # 转成dict类型
                else:
                    # 兼容其他不可序列化的类型，转为字符串
                    msg_dict = {"content": str(msg), "type": "unknown"}

                if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                    for tool_call in msg.tool_calls:
                        tool_call_id = str(tool_call.get("id") or "")
                        if tool_call_id and tool_call_id in emitted_tool_call_ids:
                            continue
                        yield emit_tool_call(tool_call)

                if isinstance(msg, ToolMessage):
                    yield emit_tool_result(msg)
                    # 持久化 render_product_card 结果到存储，供历史记录加载
                    _tool_name = getattr(msg, "name", "")
                    if _tool_name == "render_product_card":
                        _card_content = getattr(msg, "content", "")
                        if _card_content:
                            try:
                                _card_data = json.loads(_card_content) if isinstance(_card_content, str) else _card_content
                                _cards = []
                                if isinstance(_card_data, dict):
                                    if _card_data.get("type") == "product_card" and _card_data.get("data"):
                                        _cards = [_card_data["data"]]
                                    elif _card_data.get("cards"):
                                        _cards = _card_data["cards"]
                                if _cards:
                                    _now = asyncio.get_event_loop().time()
                                    # 先保存卡片之前已累积的文本，确保历史消息的正确顺序
                                    if accumulated_content:
                                        _prev_text = "".join(accumulated_content)
                                        if _prev_text.strip():
                                            _txt_msg = {
                                                "role": "assistant",
                                                "type": "ai",
                                                "content": _prev_text,
                                                "timestamp": _now,
                                            }
                                            await _store_bridge.add_message(thread_id, _txt_msg)
                                            if conv_repo:
                                                try:
                                                    await conv_repo.add_message(thread_id, _txt_msg)
                                                except Exception as _e2:
                                                    pass
                                        accumulated_content.clear()
                                    # 保存商品卡片（同步写入 PostgreSQL）
                                    _card_msg = {
                                        "role": "tool",
                                        "type": "ai",
                                        "content": "",
                                        "tool_name": "render_product_card",
                                        "productCards": _cards,
                                        "timestamp": _now,
                                    }
                                    await _store_bridge.add_message(thread_id, _card_msg)
                                    if conv_repo:
                                        try:
                                            await conv_repo.add_message(thread_id, _card_msg)
                                        except Exception as _e3:
                                            pass
                            except Exception as _e:
                                logging.warning(f"保存商品卡片到内存失败: {_e}")

                # ═══ 处理中间件通过 custom 模式写入的自定义 SSE 事件 ═══
                if isinstance(msg, dict) and msg.get("status") == "thinking_process" and msg.get("event"):
                    # 直接转换为标准 SSE 格式，绕过默认的 make_chunk 逻辑
                    legacy_chunk = {
                        "status": "thinking_process",
                        "event": msg.get("event"),
                        "content": msg.get("content"),
                        "plan": msg.get("plan"),
                        "tool_call": msg.get("tool_call"),
                    }
                    sse_events = convert_legacy_chunk_to_sse(legacy_chunk)
                    for sse in sse_events:
                        yield sse.encode("utf-8") + b"\n"
                    continue

                # ═══ 处理 custom 模式下的其他自定义事件 ═══
                if isinstance(msg, dict) and (metadata or {}).get("stream_mode") == "custom":
                    # 尝试识别并转换
                    if msg.get("status") == "thinking_process" and msg.get("event"):

                        legacy_chunk = {
                            "status": "thinking_process",
                            "event": msg.get("event"),
                            "content": msg.get("content"),
                            "plan": msg.get("plan"),
                            "tool_call": msg.get("tool_call"),
                        }
                        sse_events = convert_legacy_chunk_to_sse(legacy_chunk)
                        for sse in sse_events:
                            yield sse.encode("utf-8") + b"\n"
                        continue

                if not is_process_update:
                    # 暴力序列化方案：确保 100% 不报错
                    try:
                        if hasattr(msg, 'model_dump'):
                            safe_msg = msg.model_dump()
                        elif isinstance(msg, dict):
                            # 对字典中的每个值进行暴力转换
                            safe_msg = {}
                            for k, v in msg.items():
                                if hasattr(v, 'model_dump'):
                                    safe_msg[k] = v.model_dump()
                                elif isinstance(v, (str, int, float, bool, list)) or v is None:
                                    safe_msg[k] = v
                                else:
                                    # 遇到 Overwrite/AddableDict 等，直接转字符串描述
                                    safe_msg[k] = f"<{type(v).__name__}>"
                        else:
                            safe_msg = {"content": str(msg), "type": "unknown"}
                        
                        yield make_chunk(msg=safe_msg, metadata=metadata, status="loading")
                    except Exception as e:
                        # 即使这里报错，也发送一个极简的错误占位符，绝不让流断开
                        logging.error(f"[CRITICAL] Serialization error: {e}")
                        yield make_chunk(msg={"error": "serialization_failed"}, metadata={}, status="loading")

                try:  # 如果是工具调用，更新 agent_state
                    if msg_dict.get("type") == "tool":
                        graph = await agent.get_graph()
                        state = await graph.aget_state(langgraph_config)
                        agent_state = extract_agent_state(getattr(state, "values", {})) if state else {}
                        if agent_state:
                            yield make_chunk(status="agent_state", agent_state=agent_state, meta=meta)
                            plan_chunk = emit_plan_from_state(agent_state)
                            if plan_chunk:
                                yield plan_chunk
                except Exception as e:
                    logging.error(f"Error processing tool message: {e}")
        full_msg = _ensure_full_msg(full_msg, _pg_full_text)

        # if conf.enable_content_guard and hasattr(full_msg, "content") and await content_guard.check(full_msg.content):
        #     if conv_repo:
        #         await save_partial_message(conv_repo, thread_id, full_msg, "content_guard_blocked")
        #     meta["time_cost"] = asyncio.get_event_loop().time() - start_time
        #     yield make_chunk(status="interrupted", message="检测到敏感内容，已中断输出", meta=meta)
        #     return

        # # 检查中断（人工审批）
        # async for chunk in check_and_handle_interrupts(agent, langgraph_config, make_chunk, meta, thread_id):
        #     yield chunk

        # 保存 AI 响应并返回完成信号
        meta["time_cost"] = asyncio.get_event_loop().time() - start_time
        try:  # 获取最终 agent_state（TODO、files 等）
            graph = await agent.get_graph()
            state = await graph.aget_state(langgraph_config)
            state_values = getattr(state, "values", {}) if state else {}
            agent_state = extract_agent_state(state_values)
        except Exception as e:
            logging.error(f"Error getting final state: {e}")
            agent_state = {}

        if agent_state:
            yield make_chunk(status="agent_state", agent_state=agent_state, meta=meta)
            plan_chunk = emit_plan_from_state(agent_state)
            if plan_chunk:
                yield plan_chunk

        for tool_call_id, tool_call in list(active_tool_calls.items()):
            meta_info = _tool_meta(tool_call.get("function", "unknown"))
            yield make_chunk(
                status="thinking_process",
                event="tool_result",
                tool_call={
                    "tool_call_id": tool_call_id,
                    "function": tool_call.get("function", "unknown"),
                    "name": tool_call.get("function", "unknown"),
                    "args": tool_call.get("args", {}),
                    "status": "completed",
                    "duration_ms": int((asyncio.get_event_loop().time() - tool_call.get("started_at", start_time)) * 1000),
                    "tool_meta": meta_info,
                    "icon": meta_info.get("icon"),
                },
                meta=meta,
            )
            active_tool_calls.pop(tool_call_id, None)

        # 保存 AI 响应到内存存储 (供 History API 读取)
        if accumulated_content:
            ai_content = "".join(accumulated_content)
            _now = asyncio.get_event_loop().time()
            await _store_bridge.add_message(thread_id, {
                "role": "assistant",
                "content": ai_content,
                "type": "ai",
                "timestamp": _now,
            })
            # 同步保存剩余文本到 PostgreSQL（卡片前的文本已在流式过程中增量保存）
            if conv_repo:
                try:
                    await conv_repo.add_message(
                        thread_id=thread_id,
                        message={
                            "role": "assistant",
                            "content": ai_content,
                            "type": "ai",
                        },
                    )
                except Exception as e:
                    logging.error(f"Error saving AI message to PostgreSQL: {e}")

        # 保存思考过程到存储（供 History API 加载时恢复）
        if _thinking_chunks or _completed_tool_calls:
            _thinking_msg = {
                "role": "system",
                "type": "thinking",
                "content": "",
                "thinkingProcess": {
                    "steps": [{"type": "thinking", "content": c} for c in _thinking_chunks],
                    "planSteps": _todos_to_plan_steps(agent_state.get("todos") if isinstance(agent_state, dict) else None) or [],
                    "toolCalls": _completed_tool_calls,
                },
                "timestamp": asyncio.get_event_loop().time(),
            }
            await _store_bridge.add_message(thread_id, _thinking_msg)
            if conv_repo:
                try:
                    await conv_repo.add_message(thread_id, _thinking_msg)
                except Exception as _e:
                    logging.warning(f"保存思考过程到 PostgreSQL 失败: {_e}")

        # 完成信号
        meta["time_cost"] = asyncio.get_event_loop().time() - start_time
        
        # ═══ 发送 DONE 事件（含统计信息）═══
        if sse_middleware is None:
            sse_middleware = getattr(agent, 'sse_middleware', None)
        if sse_middleware is not None:
            stats = sse_middleware.get_stats()
        else:
            stats = {"total_tool_calls": 0, "total_duration_ms": 0, "failed_calls": 0}
        done_event = {
            "type": EventType.DONE,
            "statistics": {
                "total_tool_calls": stats["total_tool_calls"],
                "total_duration_ms": stats["total_duration_ms"],
                "failed_calls": stats["failed_calls"],
                "time_cost": meta["time_cost"],
            }
        }
        await session_manager.emit(thread_id, done_event)
        yield format_sse_event(EventType.DONE, done_event).encode("utf-8") + b"\n"
        
        # ═══ 停用会话 ═══
        session_manager.deactivate_session(thread_id)

    # 异常处理（断开连接）
    except (asyncio.CancelledError, ConnectionError) as e:
        logging.warning(f"Client disconnected, cancelling stream: {e}")
        
        # ═══ 清理会话 ═══
        session_manager.deactivate_session(thread_id)

        # 保存已累积的内容到统一存储桥接
        if accumulated_content:
            await _store_bridge.add_message(thread_id, {
                "role": "assistant",
                "content": "".join(accumulated_content),
                "type": "ai",
                "partial": True,
                "timestamp": asyncio.get_event_loop().time(),
            })

        async def save_cleanup():
            nonlocal full_msg
            full_msg = _ensure_full_msg(full_msg, _pg_full_text)

            async with pg_manager.get_async_session_context() as new_db:
                new_conv_repo = ConversationRepository(new_db)
                await save_partial_message(
                    new_conv_repo,
                    thread_id,
                    full_msg=full_msg,
                    error_message="对话已中断" if not full_msg else None,
                    error_type="interrupted",
                )

        cleanup_task = asyncio.create_task(save_cleanup())
        try:
            await asyncio.shield(cleanup_task)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logging.error(f"Error during cleanup save: {exc}")

        yield make_chunk(status="interrupted", message="对话已中断", meta=meta)

    except Exception as e:
        logging.error(f"Error streaming messages: {e}, {traceback.format_exc()}")

        # 保存已累积的内容到统一存储桥接
        if accumulated_content:
            await _store_bridge.add_message(thread_id, {
                "role": "assistant",
                "content": "".join(accumulated_content),
                "type": "ai",
                "partial": True,
                "timestamp": asyncio.get_event_loop().time(),
            })

        error_msg = f"Error streaming messages: {e}"
        error_type = "unexpected_error"

        full_msg = _ensure_full_msg(full_msg, _pg_full_text)

        async with pg_manager.get_async_session_context() as new_db:
            new_conv_repo = ConversationRepository(new_db)
            await save_partial_message(
                new_conv_repo,
                thread_id,
                full_msg=full_msg,
                error_message=error_msg,
                error_type=error_type,
            )

        yield make_chunk(status="error", error_type=error_type, error_message=error_msg, meta=meta)
    finally:
        # 关闭数据库会话
        try:
            if db is not None:
                await db.close()
        except Exception:
            pass
