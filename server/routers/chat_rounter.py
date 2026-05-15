"""聊天路由 — 简化版：agent + stream + threads"""
import logging
import traceback
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from server.utils.auth_middleware import get_required_user
from server.utils.user_store import User
from src import config as conf
from src.agents import agent_manager
from src.services.memory_store import memory_store
from src.storage.postgres.manager import pg_manager

chat = APIRouter(prefix="/chat", tags=["chat"])


# ── 模型 ──────────────────────────────────────────────────

class ThreadCreate(BaseModel):
    title: str | None = None
    agent_id: str
    metadata: dict | None = None


class ThreadUpdate(BaseModel):
    title: str | None = None
    is_pinned: bool | None = None


class ThreadResponse(BaseModel):
    id: str
    user_id: str
    agent_id: str
    title: str | None = None
    is_pinned: bool = False
    created_at: str
    updated_at: str


# ── 默认智能体 ────────────────────────────────────────────

@chat.get("/default_agent")
async def get_default_agent(current_user: User = Depends(get_required_user)):
    try:
        default_agent_id = getattr(conf.config, 'default_agent_id', None)
        if not default_agent_id:
            agents = await agent_manager.get_agents_info()
            if agents:
                default_agent_id = agents[0].get("id", "")
        return {"default_agent_id": default_agent_id}
    except Exception as e:
        logging.error(f"获取默认智能体出错: {e}")
        raise HTTPException(status_code=500, detail=f"获取默认智能体出错: {str(e)}")


# ── 智能体列表 ────────────────────────────────────────────

@chat.get("/agent")
async def get_agent(current_user: User = Depends(get_required_user)):
    agents_info = await agent_manager.get_agents_info()
    return {
        "agents": [
            {
                "id": a["id"],
                "name": a.get("name", "Unknown"),
                "description": a.get("description", ""),
                "examples": a.get("examples", []),
                "has_checkpointer": a.get("has_checkpointer", False),
                "capabilities": a.get("capabilities", []),
            }
            for a in agents_info
        ]
    }


# ── 智能体详情 ────────────────────────────────────────────

@chat.get("/agent/{agent_id}")
async def get_single_agent(agent_id: str, current_user: User = Depends(get_required_user)):
    try:
        if not (agent := agent_manager.get_agent(agent_id)):
            raise HTTPException(status_code=404, detail=f"智能体 {agent_id} 不存在")
        info = await agent.get_info()
        return {
            "id": info["id"],
            "name": info.get("name", "Unknown"),
            "description": info.get("description", ""),
            "examples": info.get("examples", []),
            "configurable_items": info.get("configurable_items", []),
            "has_checkpointer": info.get("has_checkpointer", False),
            "capabilities": info.get("capabilities", []),
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"获取智能体 {agent_id} 信息出错: {e}")
        raise HTTPException(status_code=500, detail=f"获取智能体信息出错: {str(e)}")


# ── 聊天流式响应 (核心) ───────────────────────────────────

@chat.post("/agent/{agent_name}")
async def chat_agent(
    agent_name: str,
    query: str = Body(...),
    config: dict = Body({}),
    meta: dict = Body(None),
    image_content: str | None = Body(None),
    current_user: User | None = Depends(get_required_user),
):
    from src.services.chat_stream_service import stream_agent_chat

    if not meta:
        meta = {}
    if "request_id" not in meta or not meta.get("request_id"):
        meta["request_id"] = str(uuid.uuid4())

    meta.update({
        "query": query,
        "agent_name": agent_name,
        "thread_id": config.get("thread_id"),
        "server_model_name": config.get("model", agent_name),
        "user_id": current_user.id,
        "has_image": bool(image_content),
    })

    # 尝试获取数据库会话
    _db_session = None
    try:
        pg_manager._check_initialized()
        _db_session = pg_manager.AsyncSession()
    except Exception:
        _db_session = None

    return StreamingResponse(
        stream_agent_chat(
            agent_name=agent_name,
            query=query,
            config=config,
            meta=meta,
            image_content=image_content,
            current_user=current_user,
            db=_db_session,
        ),
        media_type="application/json",
    )


# ── 线程 CRUD ─────────────────────────────────────────────

@chat.post("/thread", response_model=ThreadResponse)
async def create_thread(
    thread: ThreadCreate,
    current_user: User = Depends(get_required_user),
):
    """创建新对话线程 (内存模式)"""
    new_thread = memory_store.create_thread(
        agent_id=thread.agent_id,
        title=thread.title or "新的对话",
        user_id=str(current_user.id),
    )
    return new_thread


@chat.get("/threads", response_model=list[ThreadResponse])
async def list_threads(
    agent_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_required_user),
):
    """获取用户对话线程列表 (内存模式)"""
    return memory_store.list_threads(
        user_id=str(current_user.id),
        agent_id=agent_id,
        limit=limit,
        offset=offset,
    )


@chat.delete("/thread/{thread_id}")
async def delete_thread(
    thread_id: str,
    current_user: User = Depends(get_required_user),
):
    deleted = memory_store.delete_thread(thread_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="线程不存在")
    return {"message": "删除成功"}


@chat.put("/thread/{thread_id}", response_model=ThreadResponse)
async def update_thread(
    thread_id: str,
    thread_update: ThreadUpdate,
    current_user: User = Depends(get_required_user),
):
    """更新对话线程"""
    updated = memory_store.update_thread(
        thread_id=thread_id,
        title=thread_update.title,
        is_pinned=thread_update.is_pinned,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="线程不存在")
    return updated


# ── 历史 & 状态 ───────────────────────────────────────────

@chat.get("/agent/{agent_id}/history")
async def get_agent_history(
    agent_id: str,
    thread_id: str,
    current_user: User = Depends(get_required_user),
):
    """获取智能体历史消息 (内存模式)"""
    messages = memory_store.get_messages(thread_id)
    return {"history": messages}


@chat.get("/agent/{agent_id}/state")
async def get_agent_state(
    agent_id: str,
    thread_id: str,
    current_user: User = Depends(get_required_user),
):
    """获取智能体当前状态"""
    try:
        from src.services.chat_stream_service import get_agent_state_view
        return await get_agent_state_view(
            agent_id=agent_id,
            thread_id=thread_id,
            current_user_id=str(current_user.id),
            db=None,
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"获取AgentState出错: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取AgentState出错: {str(e)}")
