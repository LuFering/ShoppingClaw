"""送礼智能体 API —— `/api/gift`。

契约（前端 `web-v2/src/apis/gift_api.js` 对齐此处）：
  POST /api/gift/runs                     → {success, data: run}
  GET  /api/gift/runs?limit=              → {success, data: [run]}
  GET  /api/gift/runs/{id}                → {success, data: run}
  GET  /api/gift/runs/{id}/events         → SSE（after_seq 续传）
  POST /api/gift/runs/{id}/revise         → {success, data: run}  body {key}
  GET  /api/gift/runs/{id}/deliverables/{key} → {success, data: {key,label,data,generated_at}}

run 形状见 `GiftRun.to_dict()`：
  {id, status, recipient, occasion, budget, signals,
   profile:[…], understanding:{…}, profileHead:{…}, error, created_at, updated_at}

事件 kind 与前端 `useGiftWorkbench.apply()` 的 `ev.t` **一一对应**
（stage/step/live/excluded/profile/understanding/deliverable/done）——
前端状态机不改，只把产出源从 mock 换成这里。
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from server.utils.auth_middleware import get_required_user
from server.utils.user_store import User
from src.services import gift_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gift", tags=["gift"])

SSE_POLL_SECONDS = 0.5
SSE_MAX_SECONDS = 600


def _uid(user: User) -> str:
    return str(getattr(user, "id", None) or getattr(user, "user_id", "anonymous"))


def _fmt(kind: str, payload: dict, seq: int) -> str:
    data = json.dumps({"seq": seq, "kind": kind, "payload": payload}, ensure_ascii=False)
    return f"id: {seq}\nevent: {kind}\ndata: {data}\n\n"


@router.post("/runs")
async def create_run(body: dict = Body(...), current_user: User = Depends(get_required_user)):
    """入口页提交 → 建 run，立即返回（推演在后台跑）。"""
    return {"success": True, "data": await gift_service.create_run(_uid(current_user), body)}


@router.get("/runs")
async def list_runs(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_required_user),
):
    return {"success": True, "data": await gift_service.list_runs(_uid(current_user), limit)}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, current_user: User = Depends(get_required_user)):
    """首屏快照：状态 + 人物档案 + 当前理解。刷新页面走这里。"""
    run = await gift_service.get_run(run_id, _uid(current_user))
    if run is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"success": True, "data": run.to_dict()}


@router.get("/runs/{run_id}/events")
async def stream_events(
    run_id: str,
    after_seq: int = Query(default=0, ge=0),
    current_user: User = Depends(get_required_user),
):
    """推演过程 SSE。`after_seq` 实现续传（事件落库且 seq 单调）。"""
    uid = _uid(current_user)
    run = await gift_service.get_run(run_id, uid)
    if run is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    async def gen():
        cursor = after_seq
        waited = 0.0
        while waited < SSE_MAX_SECONDS:
            for ev in await gift_service.list_events(run_id, after_seq=cursor):
                cursor = ev["seq"]
                yield _fmt(ev["kind"], ev["payload"], ev["seq"])
            fresh = await gift_service.get_run(run_id, uid)
            if fresh is not None and fresh.status in ("converged", "failed"):
                for ev in await gift_service.list_events(run_id, after_seq=cursor):
                    cursor = ev["seq"]
                    yield _fmt(ev["kind"], ev["payload"], ev["seq"])
                return
            await asyncio.sleep(SSE_POLL_SECONDS)
            waited += SSE_POLL_SECONDS

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.post("/runs/{run_id}/revise")
async def revise(
    run_id: str,
    key: str = Body(..., embed=True),
    current_user: User = Depends(get_required_user),
):
    """「改一下」—— 把某个档案组标记为待确认，让用户补充后重推。

    本轮不做完整重推（那需要 LLM 参与），先如实把该组置为 pending
    并记一条事件，前端可见「已标记待补充」。
    """
    run = await gift_service.get_run(run_id, _uid(current_user))
    if run is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    profile = list(run.profile or [])
    hit = False
    for g in profile:
        if g.get("key") == key:
            g["state"] = "pending"
            g["note"] = "（已标记待补充）"
            hit = True
    if hit:
        await gift_service._patch_run(run_id, profile=profile)
        await gift_service.emit(run_id, "profile", {"key": key, "state": "pending",
                                                    "note": "（已标记待补充）"})
    fresh = await gift_service.get_run(run_id, _uid(current_user))
    return {"success": True, "data": fresh.to_dict() if fresh else {}}


@router.get("/runs/{run_id}/deliverables/{key}")
async def get_deliverable(
    run_id: str,
    key: str,
    current_user: User = Depends(get_required_user),
):
    d = await gift_service.get_deliverable(run_id, _uid(current_user), key)
    if d is None:
        raise HTTPException(status_code=404, detail="交付物不存在")
    return {"success": True, "data": d}
