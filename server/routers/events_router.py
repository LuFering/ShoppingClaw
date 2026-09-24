"""事件流 API —— 主动助理与首页状态卡共用的数据出口。

契约（前端已声明，此处对齐）：
  web-v2/src/apis/home_api.js:4
    GET  /api/events/recent?limit=8 → {success, data:[{id,type,main,sub,time}]}
  web-v2/src/apis/assistant_api.js:5
    "事件数据（feed/brief）与 /api/events/recent 同源（任务日志聚合），
      后端实现一处即可两处受益"

实现说明：
  · 事件来源是 `notify_service`（Redis List，由定时任务执行后写入）
  · 首版只做「最近事件」；更久的历史回溯走 task_execution_logs
  · 鉴权：必须登录 —— 事件是按用户存的
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from server.utils.auth_middleware import get_required_user
from server.utils.user_store import User
from src.services import notify_service

router = APIRouter(prefix="/events", tags=["events"])


def _uid(user: User) -> str:
    """与 decisions_router / task_router 保持同一口径（str(users.id)）。"""
    return str(getattr(user, "id", None) or getattr(user, "user_id", "anonymous"))


@router.get("/recent")
async def recent_events(
    limit: int = Query(default=8, ge=1, le=50),
    current_user: User = Depends(get_required_user),
):
    """最近的通知事件（新的在前）。首页状态卡与助理情报流共用。"""
    events = await notify_service.recent(_uid(current_user), limit=limit)
    return {"success": True, "data": events, "total": len(events)}


@router.post("/{event_id}/dismiss")
async def dismiss_event(event_id: str, current_user: User = Depends(get_required_user)):
    """标记事件已忽略/已处理（前端卡片上的「忽略」按钮）。"""
    ok = await notify_service.dismiss(_uid(current_user), event_id)
    return {"success": ok}


@router.get("/stream")
async def stream_events(current_user: User = Depends(get_required_user)):
    """事件实时推送（SSE）。

    用独立会话 id `notify:{uid}`，与对话的 `thread_id` 会话互不干扰：
    `notify_service.emit()` 只在用户开着这个连接时才推，关掉就落回 Redis。

    事件类型 `notify_event`，data 里带完整 event 对象。前端收到后
    重新拉一次 /api/events/recent 即可（省得前端维护增量合并逻辑）。
    """
    uid = _uid(current_user)
    from src.services.sse_session_manager import get_session_manager

    mgr = get_session_manager()
    sid = f"notify:{uid}"

    existing = getattr(mgr, "_sessions", {}).get(sid)
    if existing is None:
        await mgr.create_session(sid)

    return StreamingResponse(
        mgr.event_generator(sid, last_event_id=0),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )
