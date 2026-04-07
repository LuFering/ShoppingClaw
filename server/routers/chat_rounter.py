import logging
import uuid

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from server.utils.auth_middleware import get_current_user, get_db
from src.services.chat_stream_service import stream_agent_chat
from src.storage.postgres.models_business import User

chat = APIRouter(prefix="/chat", tags=["chat"])


@chat.post("/agent/{agent_name}")
async def chat_agent(
        agent_name: str,  # 智能体 ID,从 URL 路径获取
        query: str = Body(...),  # 用户问题
        config: dict = Body({}),  # 配置项:thread_id, model, agent_config_id
        meta: dict = Body(None),  # 元数据:request_id, model_provider
        image_content: str | None = Body(None),  # ← base64 图片
        current_user: User | None = Depends(get_current_user),  # ← 允许匿名用户
        # db: AsyncSession = Depends(get_db),  # ← 临时注释，跳过数据库
):
    # TODO: 临时测试代码 - 创建匿名用户
    from src.storage.postgres.models_business import User as UserModel
    if current_user is None:
        current_user = UserModel(
            user_name="anonymous",
            user_id="test-user",
            phone_number="00000000000",
            password_hash="dummy_hash"
        )
    
    # 临时创建一个假的 db 对象（None），传递给 stream_agent_chat
    db = None
    
    logging.info(f"agent_id:{agent_name},query:{query},config:{config},meta:{meta}")
    logging.info(f"image_content present: {image_content is not None}")
    if image_content:
        logging.info(f"image_content length: {len(image_content)}")
        logging.info(f"image_content preview: {image_content[:50]}...")


    # request_id 用于链路追踪，如果前端没传则自动生成 UUID
    if "request_id" not in meta or not meta.get("request_id"):
        meta["request_id"] = str(uuid.uuid4())#UUID是一个用于生成通用唯一识别码的库

    # meta更新,补充关键上下文信息，传递给后续的流式处理函数
    meta.update(#丰富 meta 信息（用于日志和监控）
        {
            "query": query,
            "agent_name": agent_name,
            "thread_id": config.get("thread_id"),  # 线程ID,多轮对话历史管理
            "server_model_name": config.get("model", agent_name),
            "user_id": current_user.id,
            "has_image": bool(image_content),
        }
    )

    # 返回流式响应，媒体类型为 application/json
    """前端会收到多个 JSON 行（NDJSON 格式），每行一个 chunk"""
    return StreamingResponse(#打字机效果
        stream_agent_chat(
            agent_name=agent_name,
            query=query,
            config=config,
            meta=meta,
            image_content=image_content,
            current_user=current_user,
            db=db,
        ),
        media_type="application/json", # ← 每行都是 JSON
    )
