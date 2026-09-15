"""购物档案（决策库）API 路由

契约与前端 `web-v2/src/apis/decisions_api.js` 对齐：
  GET    /api/decisions        → {success, data: [ShoppingRecord]}   （全量）
  PUT    /api/decisions/batch  → body {records: [ShoppingRecord]}    （整册同步，以本次提交为准）
  DELETE /api/decisions        → 重置为空

说明：前端以「整册同步」模式工作（页面 deep-watch 全量保存），
故 batch 采用「先清空该用户全部记录、再整批写入」的最简实现。
"""
from typing import Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy import delete, select

from server.utils.auth_middleware import get_required_user
from server.utils.user_store import User
from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_business import ShoppingDecision

router = APIRouter(prefix="/decisions", tags=["decisions"])


def _uid(user: User) -> str:
    """取稳定的用户标识（与 chat 路由保持一致：用 users.id）"""
    return str(getattr(user, "id", None) or getattr(user, "user_id", "anonymous"))


@router.get("")
async def list_decisions(current_user: User = Depends(get_required_user)):
    """返回当前用户的全部购物档案记录"""
    uid = _uid(current_user)
    async with pg_manager.get_async_session_context() as session:
        result = await session.execute(
            select(ShoppingDecision).where(ShoppingDecision.user_id == uid)
        )
        rows = result.scalars().all()
    return {"success": True, "data": [r.data for r in rows]}


@router.put("/batch")
async def sync_decisions(
    body: dict[str, Any] = Body(...),
    current_user: User = Depends(get_required_user),
):
    """整册同步：以本次提交的 records 为准，覆盖该用户的全部档案"""
    uid = _uid(current_user)
    records = body.get("records") or []

    async with pg_manager.get_async_session_context() as session:
        await session.execute(delete(ShoppingDecision).where(ShoppingDecision.user_id == uid))
        written = 0
        for rec in records:
            if not isinstance(rec, dict) or not rec.get("id"):
                continue
            session.add(
                ShoppingDecision(
                    id=str(rec["id"]),
                    user_id=uid,
                    phase=str(rec.get("phase") or "need"),
                    data=rec,
                )
            )
            written += 1
        await session.commit()

    return {"success": True, "count": written}


@router.delete("")
async def reset_decisions(current_user: User = Depends(get_required_user)):
    """重置：清空当前用户的购物档案"""
    uid = _uid(current_user)
    async with pg_manager.get_async_session_context() as session:
        await session.execute(delete(ShoppingDecision).where(ShoppingDecision.user_id == uid))
        await session.commit()
    return {"success": True}
