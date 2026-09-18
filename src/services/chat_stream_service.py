import asyncio
import json
import logging
import traceback
import uuid
from datetime import datetime, timezone

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
from src.services.sse_adapter import (
    format_sse_event,
    convert_legacy_chunk_to_sse,
    legacy_chunk_to_events,
    event_type_str,
)
from src.agents.common.middleware.sse_monitor import SSEMonitoringMiddleware
from src.services.sse_session_manager import get_session_manager
# ═══ 新增：编排轨迹合成（把真实执行事实翻成前端契约 v1.0 的 orchestration / subagent_run）
from src.services.orchestration_composer import (
    Orchestrator,
    ORCHESTRATION_REVEAL_STEPS,
    new_trace,
    fill_from_subagent_directory,
    display_name,
    TOOL_ORCHESTRATE,
    # ★ 注意：TOOL_TASK 之前漏引入，导致第一次真的派发任务时
    #   `if tool_name == TOOL_TASK` 直接 NameError，整条流被打断。
    #   契约里的三个编排工具名必须**全部**引进来，缺一个就是线上事故。
    TOOL_TASK,
)


def extract_agent_state(values: dict) -> dict:
    todos = values.get("todos")
    result = {
        "todos": list(todos)[:20] if todos else [],
        "files": values.get("files")
    }
    return result


async def get_agent_state_view(
    *,
    agent_id: str,
    thread_id: str,
    current_user_id: str,
    db=None,
) -> dict:
    """读取某个 thread 的智能体状态（TODO / 文件等），供前端状态面板刷新。

    路由 ``GET /api/chat/agent/{agent_id}/state`` 一直从这里 import 这个函数，
    但它此前并不存在 —— 该接口固定返回 500
    （``cannot import name 'get_agent_state_view'``）。
    这里按流式链路里同样的方式取状态：拿 agent → 取 graph → aget_state → 提取。
    """
    from src.agents import agent_manager

    agent = agent_manager.get_agent(agent_id)
    if agent is None:
        raise ValueError(f"智能体 {agent_id} 不存在或未就绪")

    graph = await agent.get_graph()
    state = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    values = getattr(state, "values", {}) if state else {}
    if not isinstance(values, dict):
        values = {}
    return {"agent_state": extract_agent_state(values)}


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


def _slug_from_task_args(raw_args) -> str:
    """从 `task` 工具调用的 args 里取子智能体 slug。

    args 可能是 dict，也可能是流式过程中尚未拼完的 JSON 字符串。
    取不到返回空串（宁可不发 drill，也不要发前端匹配不到的 slug）。
    """
    args = raw_args
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            return ""
    if not isinstance(args, dict):
        return ""
    for key in ("subagent_type", "subagent_slug", "slug"):
        val = args.get(key)
        if val:
            return str(val)
    return ""


def _resolve_task_slug(tool_msg) -> str:
    """从 `task` 的 ToolMessage 里反查被派遣的子智能体 slug。

    LangGraph 的 ToolMessage 只带 `tool_call_id`，不含原始 args，
    所以依次尝试几条路径：
      1. message 自带的 additional_kwargs / response_metadata；
      2. tool_call_id 里内嵌的 slug（SubAgentMiddleware 常见做法是
         `task-<slug>-<hash>` 或直接把 slug 拼进 id）。
    取不到就返回空串 —— 宁可不下发 drill，也不要发一个前端找不到卡片的 slug。
    """
    for attr in ("additional_kwargs", "response_metadata"):
        meta = getattr(tool_msg, attr, None)
        if isinstance(meta, dict):
            for key in ("subagent_type", "subagent_slug", "slug"):
                val = meta.get(key)
                if val:
                    return str(val)
    tcid = str(getattr(tool_msg, "tool_call_id", "") or "")
    # 形如 task-researcher-ab12cd34 时取中间段
    if tcid.startswith("task-") and tcid.count("-") >= 2:
        rest = tcid[len("task-"):]
        head = rest.rsplit("-", 1)[0]
        if head:
            return head
    return ""


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


def _now_iso() -> str:
    """统一的消息时间戳（UTC ISO-8601，可被 JSON/前端直接消费）"""
    return datetime.now(timezone.utc).isoformat()


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

    # 无任何已累积内容时（如 agent 获取失败/从未开始流式），不伪造空 AI 消息
    if full_msg is None:
        logging.debug("No accumulated content, skipping partial message save")
        return

    try:
        # 将 LangChain Message 转换为字典格式
        message_dict = {
            "role": "ai",
            "content": full_msg.content if hasattr(full_msg, 'content') else str(full_msg),
            "type": "ai",
            "timestamp": _now_iso(),
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
    logging.info(f"[REPLAY-TRACE] stream_agent_chat ENTER thread={thread_id}")
    await session_manager.create_session(thread_id)
    
    # ═══ SSE 监控中间件引用（延迟获取：get_graph() 在 stream_messages 内部首次调用时创建）═══
    sse_middleware = None  # 在首次 drain 前从 agent.sse_middleware 获取

    # TODO:优化成Streamable HTTP
    def make_chunk(content=None, **kwargs):
        """实现 SSE 协议的数据格式部分 - 兼容旧格式。

        同时把每个事件写进 SSE 会话缓冲，供刷新 / 断线后用
        ``GET /api/chat/sessions/{thread_id}/events`` 回放。
        顺序是「先 emit 再序列化」：emit 会分配自增 event_id，
        序列化时正好把它当作 SSE 的 ``id:`` 行，前端就能拿它做续传游标。
        """
        chunk_data = {"request_id": meta.get("request_id"), "response": content, **kwargs}

        events = legacy_chunk_to_events(chunk_data)
        for etype, edata in events:
            # 就地写入 type，让 emit_nowait 把自增的 event_id 写回**同一个** dict。
            # 若这里改成 {"type": ..., **edata} 建新字典，被序列化的 edata 就没有
            # event_id，format_sse_event 会退化成用毫秒时间戳当 id——
            # 结果直播流的 id 是时间戳、回放缓冲的 id 是自增序号，两边对不上，
            # 前端拿直播 id 去续传会一条都回放不出来。
            edata["type"] = event_type_str(etype)
            session_manager.emit_nowait(thread_id, edata)
        return "".join(
            format_sse_event(event_type_str(t), d) for t, d in events
        ).encode("utf-8")

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
        if agent is None:
            raise ValueError(f"agent '{agent_name}' 不存在或未就绪")
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
    # 前端/调用方可通过 config.model（"provider/model"）按请求切换模型，
    # 由 DynamicModelMiddleware 在运行时解析；未传则用默认模型。
    requested_model = config.get("model")
    if requested_model and isinstance(requested_model, str):
        input_context["model"] = requested_model

    full_msg = None
    accumulated_content: list[str] = []
    active_tool_calls: dict[str, dict] = {}
    emitted_tool_call_ids: set[str] = set()
    # 真实 tool_call_id -> SubagentRun。
    # 必须定义在 emit_tool_result 之前的作用域里：后者在 task 完成时
    # 要按 id 反查并下发终态 subagent_run。放在后面虽然靠闭包延迟解析
    # 也能跑，但那是在依赖「调用晚于定义」的隐式顺序，太脆。
    _subagent_runs: dict[str, object] = {}

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

    def emit_tool_call(
        tool_call: dict,
        *,
        status: str = "calling",
        message_id: str | None = None,
        subagent_run: dict | None = None,
    ) -> bytes:
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
            # 记录该工具调用所属的 AI 消息 id，供完成事件复用
            "message_id": message_id,
        }
        emitted_tool_call_ids.add(tool_call_id)
        meta_info = _tool_meta(function)
        _tool_call_payload = {
            "tool_call_id": tool_call_id,
            "function": function,
            "name": function,
            "args": args,
            "status": status,
            "tool_meta": meta_info,
            "icon": meta_info.get("icon"),
            # 归属的 AI 消息 id：前端据此把工具挂到对应消息的 tool_calls 上，
            # 从而按「正文->工具->正文」顺序自然切段（对标 Yuxi message_id）
            "message_id": message_id,
        }
        # ═══ 富载荷：task 卡的 subagent_run ═══
        # task 是 langchain 的 subagent_task 中间件真正发出来的工具调用
        # （不是我们合成的），它本身不带契约 v1.0 的 subagent_run 字段。
        # 这里由编排层把「这个子智能体在做什么」翻译成契约形态挂上去，
        # 否则前端 TaskTool.vue 只能渲染一张没有任何内容的空壳卡。
        # 同理 orchestration 字段由 _synthesize_orchestration 单独走。
        if subagent_run is not None:
            _tool_call_payload["subagent_run"] = subagent_run
        return make_chunk(
            status="thinking_process",
            event="tool_call",
            tool_call=_tool_call_payload,
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
        _done_payload = {
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
            # 完成事件沿用 start 时记录的 message_id，保证同一工具
            # 的 start/complete 归属同一条 AI 消息
            "message_id": cached.get("message_id"),
        }
        # ═══ task 完成：把终态 subagent_run 一起下发 ═══
        # 否则 subagent_run 永远停在 start 时那份「running」快照，
        # 前端卡片会一直转圈。
        if function == TOOL_TASK:
            _final_run = _subagent_runs.get(tool_call_id)
            if _final_run is not None:
                _done_payload["subagent_run"] = _final_run.build()  # type: ignore[attr-defined]
        return make_chunk(
            status="thinking_process",
            event="tool_result",
            tool_call=_done_payload,
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
                        "timestamp": _now_iso(),
                        "raw_message": human_message.model_dump() if hasattr(human_message, 'model_dump') else str(human_message),
                    },
                )
            except Exception as e:
                logging.error(f"Error saving user message to db: {e}")

        # 同步镜像到统一存储桥接（Redis/内存仅为加速/影子层，失败不影响主链路）
        try:
            await _store_bridge.add_message(thread_id, {
                "role": "user",
                "content": query,
                "type": "human",
                "message_type": message_type,
                "timestamp": _now_iso(),
            })
        except Exception as e:
            logging.warning(f"用户消息镜像到桥接存储失败（忽略）: {e}")

        # ═══ 自动标题生成：首条用户消息时自动生成对话标题 ═══
        # 以 PostgreSQL（持久真相）统计；桥接存储不可靠（进程重启/影子模式）
        user_msgs = []
        if conv_repo:
            try:
                user_msgs = await conv_repo.get_messages(thread_id)
            except Exception:
                user_msgs = []
        if not user_msgs:
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
                # 同时写进 SSE 会话缓冲：刷新后回放能恢复会话标题
                # （emit_nowait 就地补 event_id，format_sse_event 复用同一 dict，id 与缓冲一致）
                session_manager.emit_nowait(thread_id, title_event)
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

        def _collect_thinking_event(evt: dict) -> None:
            """把自定义 thinking_process 事件同步进持久化缓冲（修复过程组历史丢失）。"""
            etype = evt.get("event")
            if etype == "thinking":
                c = evt.get("content")
                if c:
                    _thinking_chunks.append(str(c))
            elif etype == "tool_call":
                tc = evt.get("tool_call") or {}
                tcid = str(tc.get("tool_call_id") or "")
                if tcid and any(x.get("id") == tcid for x in _completed_tool_calls):
                    return
                _completed_tool_calls.append({
                    "id": tcid or str(uuid.uuid4()),
                    "name": tc.get("function") or tc.get("name") or "unknown",
                    "args": tc.get("args") or {},
                    "status": tc.get("status") or "completed",
                    "duration_ms": tc.get("duration_ms"),
                    "icon": tc.get("icon"),
                    "category": tc.get("category"),
                })
        # ═══ 编排合成器：维护气泡边界 + 合成 orchestrate/task 卡 ═══
        # 契约规则：一个气泡 = 一段前置文本 + 它引出的那个状态块（tool_start）。
        # 只有「即将发 tool_start」时才推进气泡 id，纯文本段一律复用当前 id。
        # 这条规则与 Yuxi 的 _stream_message_id（同 run 共享 id）等价，但把
        # 「何时换」的判断权显式交给调用方，避免正文被拼成一大段或用空对空切碎。
        _round_no = int((meta or {}).get("round") or 1)
        orchestrator = Orchestrator(f"round-{_round_no}")
        # 已发过的 orchestrate 卡，避免重复合成（同一轮只应有一张）
        _orch_synthesized = False
        # 本轮出现过的工具名 —— 用于推导 skills / plannedTools
        _seen_tool_names: list[str] = []

        # ═══ 气泡归属：编排层合成的工具，必须落在「编排气泡」里 ═══
        # 线上实测踩到的坑（S0 实测，run 01a0b29f）：
        #   orchestrate 卡用 message_id="round-1-s1"（编排气泡），
        #   紧跟着的 task 卡却用了 LLM 的 run id "lc_run--01a0b29f-…"，
        #   结果两张卡被前端分到**两个气泡**里，卡片被硬生生劈开。
        #   这正是项目里反复踩过三次的 message_id 坑。
        # 规则：整轮里所有 tool_start / tool_complete，只要它属于编排决策
        #   （orchestrate 自身、以及被 orchestrate 决策派出去的 task），
        #   一律挂编排气泡；其余业务工具（search_products 等）仍挂 LLM run id，
        #   这样它们会紧跟在那段解说正文之后，形成「正文→工具」的自然节奏。
        _ORCH_OWNED_TOOLS = {TOOL_ORCHESTRATE, TOOL_TASK}

        def _tool_bubble(tool_name: str, llm_message_id: str | None) -> str | None:
            """决定一个工具事件该挂哪个气泡。"""
            if tool_name in _ORCH_OWNED_TOOLS:
                return orchestrator.bubble()
            return llm_message_id or orchestrator.bubble()

        # 真实 tool_call_id -> SubagentRun。task 完成时按它反查是谁跑完了。
        # （已在函数作用域顶部声明，这里不再重复定义，避免遮蔽。）

        # 子智能体「打算用哪些工具」的静态声明。
        # 来源：subagents.yaml 里的工具清单。子智能体实现尚未落地时，
        # 这份计划让卡片先有内容可渲染（plannedTools 先亮，tools 后补）。
        _SUBAGENT_PLANNED_TOOLS: dict[str, list[str]] = {
            "researcher": ["search_products", "get_product_full_detail", "get_products_specs_batch"],
            "analyst": ["get_products_specs_extract", "filter_products_by_criteria", "query_category_knowledge"],
            "critic": ["query_risk_policy"],
            "memory_manager": [],
            "pre_purchase": ["search_products", "get_product_full_detail"],
            "post_purchase": [],
        }

        def _planned_tools_for(slug: str) -> list[str]:
            return list(_SUBAGENT_PLANNED_TOOLS.get(slug) or [])

        async def _synthesize_orchestration(*, tool_chunk, orchestrator, make_chunk, all_tool_names):
            """合成 orchestrate 卡的渐进显形。

            这是「runtime 合成」路线（对照表 v2 的 §3.1 方式 B）：
            **不改 LLM、不注册新工具**，而是在 runtime 侧把已经发生的执行事实
            翻译成契约形态。好处是零 LLM 成本，且渐进节奏完全可控。

            5 档显形（ORCHESTRATION_REVEAL_STEPS）：
              Skill → RAG → MCP → 派遣 → 决策
            每档复用**同一个 tool_call_id**，前端 upsertToolCall 就地覆盖，
            所以卡片会一段一段长出来，前端零改动。

            ⚠️ 本函数只在**模型已经发出 `task`**（= 它自己决定要派）时才被调用。
            所以这里不含任何「要不要派」的判定 —— 那张卡本身就是派遣的结果。
            原先的第一档「意图分诊 + 置信度」已于 2026-09-18 移除（见 composer docstring）。
            """
            try:
                args = tool_chunk.get("args") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                subagent_slug = str(args.get("subagent_type") or args.get("slug") or "researcher")
                task_desc = str(args.get("description") or args.get("task") or "")
            except Exception:
                subagent_slug, task_desc = "researcher", ""

            # ── 从真实执行事实推导轨迹（不含意图/置信度）──
            trace = new_trace()
            try:
                from src.agents.subagents import load_subagent_slugs  # type: ignore
                available = await load_subagent_slugs()
            except Exception:
                # subagents.yaml 的 key —— 与后端实际配置一致
                available = ["researcher", "analyst", "critic", "memory_manager"]

            fill_from_subagent_directory(
                trace,
                available_slugs=available,
                selected=[(subagent_slug, task_desc)],
            )
            # 把「本轮已出现的工具」作为 Skill 的佐证补进去
            for name in all_tool_names[-3:]:
                trace.skills.append(
                    {"id": f"tool_{name}", "name": name, "detail": "本轮已调用"}
                )

            # ── 渐进显形：同 id 连发 5 档 ──
            orchestrator.begin_orchestration()
            for n in range(1, len(ORCHESTRATION_REVEAL_STEPS) + 1):
                payload = orchestrator.reveal_step(trace, n)
                yield make_chunk(**payload)
                # 让前端有时间逐档渲染；过密会合并成一帧、看不出渐进
                await asyncio.sleep(0.12)

            # ── 收尾 ──
            yield make_chunk(**orchestrator.complete_orchestration(trace))

        def _emit_composed(payload: dict) -> bytes:
            """把合成出的旧风格 chunk 经统一出口下发（走 make_chunk 才进回放缓冲）。"""
            return make_chunk(**payload)

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
                    # ★ 补 message_id —— sse_monitor 自身不发这个字段。
                    # 没有它，前端会把工具卡挂到 __local__ 兜底条目，
                    # 工具卡就不跟随气泡了（见后端落地对照表 v2 风险 R1）。
                    # 沿用「当前气泡」而非新开，保证「正文 → 工具」同属一条。
                    if not event.get("message_id"):
                        event["message_id"] = orchestrator.bubble()
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
                        # ═══ 合成 orchestrate 卡（契约层虚构的编排动作，registry 里没有）═══
                        # 时机：第一次看见 `task` 工具调用 = 派遣决策已定。
                        # 在它之前把编排轨迹显形出来，用户先看到「为什么派、派谁」，
                        # 再看到子智能体真正开始干活 —— 这正是契约的「文本先行 → 状态块」节奏。
                        if tool_name == "task" and not _orch_synthesized:
                            _orch_synthesized = True
                            async for _c in _synthesize_orchestration(
                                tool_chunk=tool_chunk,
                                orchestrator=orchestrator,
                                make_chunk=make_chunk,
                                all_tool_names=_seen_tool_names,
                            ):
                                yield _c

                        # ═══ 给 task 卡挂上契约 v1.0 的 subagent_run ═══
                        # 子智能体自身的工具实现还没落地（research 工具包缺 'jd' 模块），
                        # 但「它在做什么、用了哪些 Skill/RAG、计划调哪些工具」这些
                        # 编排事实我们**知道**，所以先把卡片填成有内容的样子，
                        # 等真实子智能体接上来时只需把 tools 换成实际执行记录。
                        _sub_run_payload = None
                        if tool_name == TOOL_TASK:
                            try:
                                _tc_args = tool_chunk.get("args") or {}
                                if isinstance(_tc_args, str):
                                    _tc_args = json.loads(_tc_args) if _tc_args.strip().startswith("{") else {}
                                _t_slug = str(
                                    _tc_args.get("subagent_type")
                                    or _tc_args.get("slug")
                                    or "researcher"
                                )
                                _t_desc = str(
                                    _tc_args.get("description") or _tc_args.get("task") or ""
                                )
                            except Exception:
                                _t_slug, _t_desc = "researcher", ""
                            _t_call_id = str(tool_call_id)
                            _run = _subagent_runs.get(_t_call_id)
                            if _run is None:
                                _, _run, _ = orchestrator.start_task(
                                    slug=_t_slug,
                                    task=_t_desc,
                                    planned_tools=_planned_tools_for(_t_slug),
                                )
                                # ★ 关键：把合成 id 换成 langchain 真实 tool_call_id。
                                #   task 卡是中间件真发的，前端按真实 id 匹配卡片；
                                #   若 subagent_run.call_id 仍是自造 id，卡片挂不上。
                                orchestrator.rebind_task_call_id(_run, _t_call_id)
                                _subagent_runs[_t_call_id] = _run
                            _sub_run_payload = _run.build()

                        yield emit_tool_call(
                            {
                                "id": str(tool_call_id),
                                "name": tool_name,
                                "args": tool_chunk.get("args") or {},
                            },
                            # 气泡归属：task 挂编排气泡（与 orchestrate 同泡），
                            # 避免编排卡被切成两个气泡（S0 实测踩坑）。
                            message_id=_tool_bubble(tool_name, getattr(msg, "id", None)),
                            subagent_run=_sub_run_payload,
                        )
                        # 记录工具名，供编排轨迹推导 skills
                        if tool_name not in _seen_tool_names:
                            _seen_tool_names.append(tool_name)

                        # ═══ subagent_drill: expand ═══
                        # 子智能体开始干活前 → 展开它的卡片，让用户看见内部过程。
                        # 顺序讲究：必须**在** task 的 tool_start 之后发，
                        # 否则 setToolCallDrill 倒序找不到刚建的那张卡。
                        if tool_name == TOOL_TASK:
                            _expand_slug = ""
                            _run_ref = _subagent_runs.get(str(tool_call_id))
                            if _run_ref is not None:
                                _expand_slug = getattr(_run_ref, "slug", "") or ""
                            if not _expand_slug:
                                _expand_slug = _slug_from_task_args(tool_chunk.get("args"))
                            if _expand_slug:
                                yield make_chunk(
                                    status="subagent_drill",
                                    slug=display_name(_expand_slug),
                                    action="expand",
                                    description="",
                                    message_id=orchestrator.bubble(),
                                )

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
                # message_id 取 LangChain 的 run id（AIMessageChunk.id）：
                # 同一轮 LLM 调用的所有增量 chunk 共享同一 id，不同轮次则不同。
                # 前端据此把「正文 + 该轮产生的工具调用」归为同一条消息，
                # 从而按 正文->工具->正文 的顺序自然切段（对标 Yuxi message_id）。
                yield make_chunk(
                    content=content,
                    msg=msg.model_dump(),
                    metadata=metadata,
                    status="loading",
                    message_id=getattr(msg, "id", None),
                )
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
                        _tc_name = tool_call.get("name") or tool_call.get("function") or ""
                        yield emit_tool_call(
                            tool_call,
                            message_id=_tool_bubble(_tc_name, getattr(msg, "id", None)),
                        )

                if isinstance(msg, ToolMessage):
                    # ═══ task 收尾：先把子智能体状态置 completed，再发完成事件 ═══
                    # 顺序很重要：emit_tool_result 会从 active_tool_calls 取缓存，
                    # 而 subagent_run 需要「已完成」的终态一起下发，否则卡片
                    # 永远停在 running（前端不会自己猜完成）。
                    _done_tool_name = getattr(msg, "name", "")
                    _done_call_id = str(getattr(msg, "tool_call_id", "") or "")
                    _done_run = None
                    if _done_tool_name == TOOL_TASK and _done_call_id:
                        _done_run = _subagent_runs.get(_done_call_id)
                        if _done_run is not None:
                            _done_run.status = "completed"  # type: ignore[attr-defined]
                    yield emit_tool_result(msg)
                    # ═══ subagent_drill: collapse ═══
                    # 子智能体干完 → 把之前展开的那一段收起来，视线交还给主线对话。
                    # 这是后端的**全新事件**（原先完全没有），前端 case 已就绪。
                    # 只写 drill 标志、不当场改展开态 —— 由 BaseToolCall 自己 watch，
                    # 这样用户手动折叠过的卡片不会被强行重开。
                    if _done_tool_name == TOOL_TASK:
                        _slug = ""
                        if _done_run is not None:
                            _slug = getattr(_done_run, "slug", "") or ""
                        if not _slug:
                            _slug = _resolve_task_slug(msg)
                        if _slug:
                            yield make_chunk(
                                status="subagent_drill",
                                slug=display_name(_slug),
                                action="collapse",
                                description="",
                                message_id=orchestrator.bubble(),
                            )
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
                                    _now = _now_iso()
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
                                            try:
                                                await _store_bridge.add_message(thread_id, _txt_msg)
                                            except Exception as _e1:
                                                logging.warning(f"卡片前文本镜像到桥接存储失败（忽略）: {_e1}")
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
                                    try:
                                        await _store_bridge.add_message(thread_id, _card_msg)
                                    except Exception as _e3b:
                                        logging.warning(f"商品卡片镜像到桥接存储失败（忽略）: {_e3b}")
                                    if conv_repo:
                                        try:
                                            await conv_repo.add_message(thread_id, _card_msg)
                                        except Exception as _e4:
                                            pass
                            except Exception as _e:
                                logging.warning(f"保存商品卡片到内存失败: {_e}")

                # ═══ 处理中间件通过 custom 模式写入的自定义 SSE 事件 ═══
                if isinstance(msg, dict) and msg.get("status") == "thinking_process" and msg.get("event"):
                    # 持久化收集：该通道才是 SC 推理内容/工具调用的真实来源
                    _collect_thinking_event(msg)
                    # 走 make_chunk 而不是直接 convert：只有经 make_chunk 才会写进
                    # SSE 会话缓冲（刷新后回放要用），也才能拿到与缓冲一致的 event_id。
                    # 原先直接 yield 转换结果，导致这类事件既进不了回放、
                    # id 还退化成毫秒时间戳，前端续传时对不上。
                    yield make_chunk(
                        status="thinking_process",
                        event=msg.get("event"),
                        content=msg.get("content"),
                        plan=msg.get("plan"),
                        tool_call=msg.get("tool_call"),
                    )
                    continue

                # ═══ 处理 custom 模式下的其他自定义事件 ═══
                if isinstance(msg, dict) and (metadata or {}).get("stream_mode") == "custom":
                    # 尝试识别并转换
                    if msg.get("status") == "thinking_process" and msg.get("event"):
                        _collect_thinking_event(msg)

                        # 同上：走 make_chunk 才会进回放缓冲、id 才与缓冲一致
                        yield make_chunk(
                            status="thinking_process",
                            event=msg.get("event"),
                            content=msg.get("content"),
                            plan=msg.get("plan"),
                            tool_call=msg.get("tool_call"),
                        )
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

        # 保存 AI 响应：PostgreSQL 主存储优先，桥接存储镜像兜底
        if accumulated_content:
            ai_content = "".join(accumulated_content)
            _ai_msg = {
                "role": "assistant",
                "content": ai_content,
                "type": "ai",
                "timestamp": _now_iso(),
            }
            # 1) PostgreSQL（主存储，完整文本）
            if conv_repo:
                try:
                    await conv_repo.add_message(thread_id, _ai_msg)
                except Exception as e:
                    logging.error(f"Error saving AI message to PostgreSQL: {e}")
            # 2) 镜像到桥接存储（Redis/内存，供 History API 快速读取；失败不影响主链路）
            try:
                await _store_bridge.add_message(thread_id, _ai_msg)
            except Exception as e:
                logging.warning(f"AI 消息镜像到桥接存储失败（忽略）: {e}")

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
                "timestamp": _now_iso(),
            }
            # PostgreSQL 主存储优先
            if conv_repo:
                try:
                    await conv_repo.add_message(thread_id, _thinking_msg)
                except Exception as _e:
                    logging.warning(f"保存思考过程到 PostgreSQL 失败: {_e}")
            # 镜像到桥接存储（失败不影响主链路）
            try:
                await _store_bridge.add_message(thread_id, _thinking_msg)
            except Exception as _e:
                logging.warning(f"保存思考过程到桥接存储失败（忽略）: {_e}")

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

        # 保存已累积的内容到统一存储桥接（失败不阻断后续 PG 兜底）
        if accumulated_content:
            try:
                await _store_bridge.add_message(thread_id, {
                    "role": "assistant",
                    "content": "".join(accumulated_content),
                    "type": "ai",
                    "partial": True,
                    "timestamp": _now_iso(),
                })
            except Exception as _e:
                logging.warning(f"中断内容镜像到桥接存储失败（忽略）: {_e}")

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

        # 保存已累积的内容到统一存储桥接（失败不阻断后续 PG 兜底）
        if accumulated_content:
            try:
                await _store_bridge.add_message(thread_id, {
                    "role": "assistant",
                    "content": "".join(accumulated_content),
                    "type": "ai",
                    "partial": True,
                    "timestamp": _now_iso(),
                })
            except Exception as _e:
                logging.warning(f"错误内容镜像到桥接存储失败（忽略）: {_e}")

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
