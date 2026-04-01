import logging
import uuid

from aiohttp.web_response import StreamResponse
from fastapi import APIRouter, Body

from src.services.chat_stream_service import stream_agent_chat

chat = APIRouter(prefix="/chat", tags=["chat"])


@chat.post("/agent/{agent_id}")
async def chat_agent(
        agent_name: str,  # 智能体 ID，从 URL 路径获取
        query: str = Body(...),  # 用户问题
        config: dict = Body({}),  # 配置项：thread_id, model, agent_config_id
        meta: dict = Body(None),  # 元数据：request_id, model_provider
):
    logging.info(f"agent_id:{agent_name},query:{query},config:{config},meta:{meta}")

    # request_id 用于链路追踪，如果前端没传则自动生成 UUID
    if "request_id" not in meta or not meta.get("request_id"):
        meta["request_id"] = str(uuid.uuid4())

    # meta更新,补充关键上下文信息，传递给后续的流式处理函数
    meta.update(
        {
            "query": query,
            "agent_name": agent_name,
            "thread_id": config.get("thread_id"),  # 线程ID,多轮对话历史管理
        }
    )

    # 返回 StreamingResponse（HTTP 分块传输），媒体类型为 application/json
    """前端会收到多个 JSON 行（NDJSON 格式），每行一个 chunk"""
    return StreamResponse(
        stream_agent_chat(
            agent_name=agent_name,
            query=query,
            config=config,
            meta=meta,
        ),
        media_type="application/json",
    )
