import asyncio
import json
import logging
import traceback
import uuid

from langchain_core.messages import HumanMessage, AIMessageChunk, AIMessage
from src import config as conf
from src.agents import agent_manager
from src.plugins.guard import content_guard
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


async def _resolve_agent_config(db, agent_id, department_id, user_id, agent_config_id):
    """解析 agent_config，返回 (config_item, agent_config_id)"""
    pass


async def save_partial_message(conv_repo, thread_id, full_msg, param):
    pass


def check_and_handle_interrupts(agent, langgraph_config, make_chunk, meta, thread_id):
    pass


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
                json.dump(  # 将 request_id、response 等内容打包成一个 JSON 字符串
                    {"request_id": meta.get("request_id"), "response": content, **kwargs},
                    ensure_ascii=False).encode("utf-8")  # 将这个字符串转换成字节
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

    #内容安全审查
    if conf.enable_content_guard and await content_guard.check(query):
        yield make_chunk(
            status="error", error_type="content_guard_blocked", error_message="输入内容包含敏感词", meta=meta
        )
        return

    try:#获取 Agent 实例
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

    messages = [human_message] # ← 只有当前用户消息（历史由 Checkpointer 管理）

    user_id = str(current_user.id)
    department_id = current_user.department_id
    if not department_id:
        yield make_chunk(status="error", error_type="no_department", error_message="当前用户未绑定部门", meta=meta)
        return

    # 获取或创建 Agent 配置
    agent_config_id = config.get("agent_config_id")
    config_item, agent_config_id = await _resolve_agent_config(db, agent_name, department_id, user_id, agent_config_id)

    # 如果没有 thread_id，自动生成（新对话）
    if not (thread_id := config.get("thread_id")):
        thread_id = str(uuid.uuid4())
        logging.warning(f"No thread_id provided, generated new thread_id: {thread_id}")

    # 构建 input_context（传递给 LangGraph）
    agent_config = (config_item.config_json or {}).get("context", {})
    input_context = {
        "user_id": user_id,
        "thread_id": thread_id, # ← 关键：对话上下文 ID
        "department_id": department_id,
        "agent_config_id": agent_config_id,
        "agent_config": agent_config,
    }


    full_msg = None
    accumulated_content :list[str]=[]


    try:# 保存用户消息到数据库
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

        # 先构建 langgraph_config
        langgraph_config = {"configurable": {"thread_id": thread_id, "user_id": user_id}}

        full_msg = None
        accumulated_content = []
        #流式执行 Agent 推理
        async for msg, metadata in agent.stream_messages(messages, input_context=input_context):
            if isinstance(msg, AIMessageChunk):
                accumulated_content.append(msg.content)

                # 敏感词检查（每 10 个 chunk 检查一次）
                content_for_check = "".join(accumulated_content[-10:])
                if conf.enable_content_guard and await content_guard.check_with_keywords(content_for_check):
                    full_msg = AIMessage(content="".join(accumulated_content))
                    await save_partial_message(conv_repo, thread_id, full_msg, "content_guard_blocked")
                    meta["time_cost"] = asyncio.get_event_loop().time() - start_time
                    yield make_chunk(status="interrupted", message="检测到敏感内容，已中断输出", meta=meta)
                    return

                ## 流式返回给前端
                yield make_chunk(content=msg.content, msg=msg.model_dump(), metadata=metadata, status="loading")
            else:
                msg_dict = msg.model_dump()  # 转成dict类型
                yield make_chunk(msg=msg_dict, metadata=metadata, status="loading")

                try:# 如果是工具调用，更新 agent_state
                    if msg_dict.get("type") == "tool":
                        graph = await agent.get_graph()
                        state = await graph.aget_state(langgraph_config)
                        agent_state = extract_agent_state(getattr(state, "values", {})) if state else {}
                        if agent_state:
                            yield make_chunk(status="agent_state", agent_state=agent_state, meta=meta)
                except Exception as e:
                    logging.error(f"Error processing tool message: {e}")
        full_msg = _ensure_full_msg(full_msg, accumulated_content)

        if conf.enable_content_guard and hasattr(full_msg, "content") and await content_guard.check(full_msg.content):
            await save_partial_message(conv_repo, thread_id, full_msg, "content_guard_blocked")
            meta["time_cost"] = asyncio.get_event_loop().time() - start_time
            yield make_chunk(status="interrupted", message="检测到敏感内容，已中断输出", meta=meta)
            return

        #检查中断（人工审批）
        async for chunk in check_and_handle_interrupts(agent, langgraph_config, make_chunk, meta, thread_id):
            yield chunk

        #保存 AI 响应并返回完成信号
        meta["time_cost"] = asyncio.get_event_loop().time() - start_time
        try:# 获取最终 agent_state（TODO、files 等）
            graph = await agent.get_graph()
            state = await graph.aget_state(langgraph_config)
            agent_state = extract_agent_state(getattr(state, "values", {})) if state else {}
        except Exception:
            agent_state = {}

        if agent_state:
            yield make_chunk(status="agent_state", agent_state=agent_state, meta=meta)

        # 先存储数据库，再返回 finished，避免前端查询时数据未落库
        await save_messages_from_langgraph_state(
            agent_instance=agent,
            thread_id=thread_id,
            conv_repo=conv_repo,
            config_dict=langgraph_config,
        )

        # 完成信号
        yield make_chunk(status="finished", meta=meta)

    #异常处理（断开连接）
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


