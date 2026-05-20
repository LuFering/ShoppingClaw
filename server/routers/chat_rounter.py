"""聊天路由 — 简化版：agent + stream + threads"""
import logging
import traceback
import uuid
from datetime import datetime

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
        media_type="text/event-stream",  # ✅ 标准 SSE 格式
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
            "Access-Control-Allow-Origin": "*",  # CORS 支持
        }
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


# ── 会话管理 API（PostgreSQL 版）──

@chat.post("/sessions", response_model=ThreadResponse)
async def create_session(
    session_create: ThreadCreate,
    current_user: User = Depends(get_required_user),
):
    """创建新会话（PostgreSQL 持久化）"""
    from src.services.conversation_service import create_thread_view
    
    _db_session = None
    try:
        pg_manager._check_initialized()
        _db_session = pg_manager.AsyncSession()
    except Exception:
        _db_session = None
    
    if not _db_session:
        raise HTTPException(status_code=503, detail="数据库不可用")
    
    try:
        result = await create_thread_view(
            agent_id=session_create.agent_id,
            title=session_create.title,
            metadata=session_create.metadata,
            db=_db_session,
            current_user_id=str(current_user.id),
        )
        return result
    finally:
        await _db_session.close()


@chat.get("/sessions", response_model=list[ThreadResponse])
async def list_sessions(
    agent_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_required_user),
):
    """列出用户所有会话（PostgreSQL 持久化 + 分页）"""
    from src.services.conversation_service import list_threads_view
    
    _db_session = None
    try:
        pg_manager._check_initialized()
        _db_session = pg_manager.AsyncSession()
    except Exception:
        _db_session = None
    
    if not _db_session:
        # Fallback 到内存模式
        return memory_store.list_threads(
            user_id=str(current_user.id),
            agent_id=agent_id,
            limit=limit,
            offset=offset,
        )
    
    try:
        result = await list_threads_view(
            agent_id=agent_id,
            db=_db_session,
            current_user_id=str(current_user.id),
            limit=limit,
            offset=offset,
        )
        return result
    finally:
        await _db_session.close()


@chat.delete("/sessions/{thread_id}")
async def delete_session(
    thread_id: str,
    current_user: User = Depends(get_required_user),
):
    """删除会话（软删除，PostgreSQL）"""
    from src.services.conversation_service import delete_thread_view
    
    _db_session = None
    try:
        pg_manager._check_initialized()
        _db_session = pg_manager.AsyncSession()
    except Exception:
        _db_session = None
    
    if not _db_session:
        raise HTTPException(status_code=503, detail="数据库不可用")
    
    try:
        result = await delete_thread_view(
            thread_id=thread_id,
            db=_db_session,
            current_user_id=str(current_user.id),
        )
        return result
    finally:
        await _db_session.close()


@chat.patch("/sessions/{thread_id}/title")
async def update_session_title(
    thread_id: str,
    title_update: dict = Body(...),
    current_user: User = Depends(get_required_user),
):
    """修改会话标题（PostgreSQL）"""
    from src.services.conversation_service import update_thread_view
    
    new_title = title_update.get("title")
    if not new_title:
        raise HTTPException(status_code=400, detail="标题不能为空")
    
    _db_session = None
    try:
        pg_manager._check_initialized()
        _db_session = pg_manager.AsyncSession()
    except Exception:
        _db_session = None
    
    if not _db_session:
        raise HTTPException(status_code=503, detail="数据库不可用")
    
    try:
        result = await update_thread_view(
            thread_id=thread_id,
            title=new_title,
            db=_db_session,
            current_user_id=str(current_user.id),
        )
        return result
    finally:
        await _db_session.close()


@chat.post("/agent/{agent_id}/stop")
async def stop_generation(
    agent_id: str,
    thread_id: str = Body(..., embed=True),
    current_user: User = Depends(get_required_user),
):
    """停止正在生成的消息"""
    from src.services.sse_session_manager import get_session_manager
    
    manager = get_session_manager()
    manager.deactivate_session(thread_id)
    
    return {
        "message": "生成已停止",
        "thread_id": thread_id,
    }


@chat.post("/history/{thread_id}/regenerate")
async def regenerate_last_message(
    thread_id: str,
    current_user: User = Depends(get_required_user),
):
    """重新生成最后一条回复"""
    # TODO: 实现重新生成逻辑
    # 1. 获取历史消息
    # 2. 删除最后一条 AI 消息
    # 3. 重新调用 Agent
    raise HTTPException(
        status_code=501,
        detail="重新生成功能尚未实现",
    )


@chat.delete("/history/{thread_id}/messages/{msg_id}")
async def delete_message(
    thread_id: str,
    msg_id: str,
    current_user: User = Depends(get_required_user),
):
    """删除单条消息"""
    # TODO: 实现消息删除逻辑
    # 1. 验证消息属于当前用户
    # 2. 从数据库中删除
    raise HTTPException(
        status_code=501,
        detail="消息删除功能尚未实现",
    )


# ── 用户记忆管理 API ────────────────────────────────────

@chat.get("/memory")
async def get_user_memory(
    current_user: User = Depends(get_required_user),
):
    """获取用户全局记忆（AGENTS.md）"""
    from src.services.user_memory import get_user_memory_service
    
    memory_service = get_user_memory_service()
    global_memory = await memory_service.get_global_memory(str(current_user.id))
    
    return {
        "user_id": str(current_user.id),
        "global_memory": global_memory,
        "has_memory": bool(global_memory),
    }


@chat.put("/memory")
async def update_user_memory(
    memory_update: dict = Body(...),
    current_user: User = Depends(get_required_user),
):
    """更新用户全局记忆（AGENTS.md）"""
    from src.services.user_memory import get_user_memory_service
    
    content = memory_update.get("content", "")
    if not content:
        raise HTTPException(status_code=400, detail="记忆内容不能为空")
    
    memory_service = get_user_memory_service()
    await memory_service.update_global_memory(str(current_user.id), content)
    
    return {
        "message": "记忆已更新",
        "user_id": str(current_user.id),
        "content_length": len(content),
    }


@chat.get("/memory/session/{thread_id}")
async def get_session_context(
    thread_id: str,
    current_user: User = Depends(get_required_user),
):
    """获取会话上下文（CONTEXT.md）"""
    from src.services.user_memory import get_user_memory_service
    
    memory_service = get_user_memory_service()
    session_context = await memory_service.get_session_context(thread_id)
    
    return {
        "thread_id": thread_id,
        "session_context": session_context,
        "has_context": bool(session_context),
    }


@chat.put("/memory/session/{thread_id}")
async def update_session_context(
    thread_id: str,
    context_update: dict = Body(...),
    current_user: User = Depends(get_required_user),
):
    """更新会话上下文（CONTEXT.md）"""
    from src.services.user_memory import get_user_memory_service
    
    content = context_update.get("content", "")
    if not content:
        raise HTTPException(status_code=400, detail="上下文内容不能为空")
    
    memory_service = get_user_memory_service()
    await memory_service.update_session_context(thread_id, content)
    
    return {
        "message": "会话上下文已更新",
        "thread_id": thread_id,
        "content_length": len(content),
    }


# ── 系统统计 API ────────────────────────────────────────

@chat.get("/system/statistics")
async def get_system_statistics(
    current_user: User = Depends(get_required_user),
):
    """获取系统使用统计"""
    from src.services.sse_session_manager import get_session_manager
    
    # SSE 会话统计
    sse_manager = get_session_manager()
    sse_stats = sse_manager.get_stats()
    
    # 内存存储统计
    memory_stats = {
        "total_threads": len(memory_store.threads),
        "active_threads": len([
            t for t in memory_store.threads.values()
            if t.get("user_id") == str(current_user.id)
        ]),
    }
    
    return {
        "sse_sessions": sse_stats,
        "memory_store": memory_stats,
        "timestamp": datetime.utcnow().isoformat(),
    }


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
