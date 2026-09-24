"""主动助理 API。

前端契约（web-v2/src/apis/assistant_api.js 已声明，此处一字不差对齐）：
  GET  /api/assistant/overview → {success, data:{messages, brief, feed, todos}}
  POST /api/assistant/messages → {success, data:{reply, created}}   body {text}

  messages 卡片 kind：
    brief  {id, kind, time, date, points:[{tone,text}]}
    hit    {id, kind, hitType, time, product, change, source}
    draft  {id, kind, time, product, summary}
    user/ai{id, kind, time, text}   ← 对话消息（P3 接入）
"""
from fastapi import APIRouter, Body, Depends

from server.utils.auth_middleware import get_required_user
from server.utils.user_store import User
from src.services import assistant_service

router = APIRouter(prefix="/assistant", tags=["assistant"])


def _uid(user: User) -> str:
    """与 decisions_router / task_router 保持同一口径（str(users.id)）。"""
    return str(getattr(user, "id", None) or getattr(user, "user_id", "anonymous"))


@router.get("/overview")
async def overview(current_user: User = Depends(get_required_user)):
    """主动助理首页数据：简报 / 情报流 / 待办 / 卡片序列。

    全部由 PG 实时聚合（不缓存、不落库），任一子查询失败只让那一块为空，
    整体接口始终返回 200 —— 主动助理是装饰性界面，不该因部分失败整页崩。
    """
    return {"success": True, "data": await assistant_service.get_overview(_uid(current_user))}


@router.post("/messages")
async def send_message(
    text: str = Body(..., embed=True),
    current_user: User = Depends(get_required_user),
):
    """助理页对话入口（方案 §4 P3 / §5 决策 #3 的方案 A：轻量 JSON）。

    监控类意图直接建任务；其余交给 MasterAgent 非流式回一段文本。
    与 /overview 同样的原则：永不抛异常，失败也返回 200 + 可读文案，
    否则前端输入框会变成一个只会报错的摆设。
    """
    return {"success": True, "data": await assistant_service.send_message(text, _uid(current_user))}
