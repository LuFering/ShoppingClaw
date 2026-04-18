import asyncio
import json
import logging
import traceback
import uuid

from langchain_core.messages import HumanMessage, AIMessageChunk, AIMessage
from src.config import config as conf
from src.agents import agent_manager
from src.plugins.guard import content_guard
from src.repositories.agent_config_repository import AgentConfigRepository
from src.repositories.conversation_repository import ConversationRepository
from src.storage.postgres.manager import pg_manager


def extract_agent_state(values: dict) -> dict:
    todos = values.get("todos")
    result = {
        "todos": list(todos)[:20],
        "files": values.get("files")
    }
    return result


def _ensure_full_msg(full_msg: AIMessage | None, accumulated_content: list[str]) -> AIMessage | None:
    if not full_msg and accumulated_content:
        return AIMessage(content="".join(accumulated_content))
    return full_msg


async def _resolve_agent_config(
    db, agent_id: str,  user_id: str, agent_config_id: int | str | None
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
    """保存部分消息到数据库(临时占位实现)"""
    # TODO: 实现完整的消息保存逻辑
    if conv_repo is None:
        logging.warning("Database not available, skipping message save")
        return
    
    try:
        # 这里应该调用 conv_repo 保存消息
        pass
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

    # TODO:优化成Streamable HTTP
    def make_chunk(content=None, **kwargs):
        """实现 SSE 协议的数据格式部分"""
        return (
                json.dumps(  # 将 request_id、response 等内容打包成一个 JSON 字符串
                    {"request_id": meta.get("request_id"), "response": content, **kwargs}, ensure_ascii=False
                ).encode("utf-8")  # 将这个字符串转换成字节
                + b"\n"
        )


    if image_content:
        human_message = HumanMessage(
            content=[
                {"type": "text", "text": query},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_content}"}},
            ]
        )
        message_type = "multimodal_image"
    else:
        human_message = HumanMessage(content=query)
        message_type = "text"
    init_msg = {"role": "user", "content": query, "type": "human"}

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

    messages = [human_message]  # ← 只有当前用户消息（历史由 Checkpointer 管理）

    user_id = str(current_user.id)


    # # 获取或创建 Agent 配置
    logging.debug(f">>>进入[stream_agent_chat]")
    logging.info(f"config:{config}")
    agent_config_id = config.get("agent_config_id")
    config_item, agent_config_id = await _resolve_agent_config(db, agent_name,user_id, agent_config_id)

    # 如果没有 thread_id，自动生成（新对话）
    if not (thread_id := config.get("thread_id")):
        thread_id = str(uuid.uuid4())
        logging.warning(f"No thread_id provided, generated new thread_id: {thread_id}")

    # 构建 input_context（传递给 LangGraph）
    agent_config = (config_item.config_json or {}).get("context", {})
    input_context = {
        "user_id": user_id,
        "thread_id": thread_id,  # ← 关键：对话上下文 ID
        "agent_config_id": agent_config_id,
        "agent_config": agent_config,
    }

    full_msg = None
    accumulated_content: list[str] = []

    try:  # 外层 try: 包裹整个业务逻辑,捕获异常
        # TODO: 临时跳过数据库消息保存
        if db is not None:
            conv_repo = ConversationRepository(db)

            try:
                await conv_repo.add_message_by_thread_id(
                    thread_id=thread_id,
                    role="user",
                    content=query,
                    message_type=message_type,
                    image_content=image_content,
                    extra_metadata={"raw_message": human_message.model_dump()},
                )
            except Exception as e:
                logging.error(f"Error saving user message: {e}")
        else:
            logging.warning("Database not available, skipping message save")
            conv_repo = None  # 后续操作需要检查 conv_repo 是否为 None

        # 先构建 langgraph_config
        langgraph_config = {"configurable": {"thread_id": thread_id, "user_id": user_id}}

        full_msg = None
        accumulated_content = []
        # 流式执行 Agent 推理
        async for msg, metadata in agent.stream_messages(messages, input_context=input_context):
            if isinstance(msg, AIMessageChunk):
                accumulated_content.append(msg.content)

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
                yield make_chunk(content=msg.content, msg=msg.model_dump(), metadata=metadata, status="loading")
            else:
                msg_dict = msg.model_dump()  # 转成dict类型
                yield make_chunk(msg=msg_dict, metadata=metadata, status="loading")

                try:  # 如果是工具调用，更新 agent_state
                    if msg_dict.get("type") == "tool":
                        graph = await agent.get_graph()
                        state = await graph.aget_state(langgraph_config)
                        agent_state = extract_agent_state(getattr(state, "values", {})) if state else {}
                        if agent_state:
                            yield make_chunk(status="agent_state", agent_state=agent_state, meta=meta)
                except Exception as e:
                    logging.error(f"Error processing tool message: {e}")
        full_msg = _ensure_full_msg(full_msg, accumulated_content)

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
            agent_state = extract_agent_state(getattr(state, "values", {})) if state else {}
        except Exception:
            agent_state = {}

        if agent_state:
            yield make_chunk(status="agent_state", agent_state=agent_state, meta=meta)

        # # 先存储数据库，再返回 finished，避免前端查询时数据未落库
        # if conv_repo:
        #     await save_messages_from_langgraph_state(
        #         agent_instance=agent,
        #         thread_id=thread_id,
        #         conv_repo=conv_repo,
        #         config_dict=langgraph_config,
        #     )

        # 完成信号
        yield make_chunk(status="finished", meta=meta)

    # 异常处理（断开连接）
    except (asyncio.CancelledError, ConnectionError) as e:
        logging.warning(f"Client disconnected, cancelling stream: {e}")

        async def save_cleanup():
            nonlocal full_msg
            full_msg = _ensure_full_msg(full_msg, accumulated_content)

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

        error_msg = f"Error streaming messages: {e}"
        error_type = "unexpected_error"

        full_msg = _ensure_full_msg(full_msg, accumulated_content)

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
