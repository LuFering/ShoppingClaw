"""采购规划 API —— `/api/planning`。

前端契约（`web-v2/src/apis/planning_api.js` 对齐此处）：
  POST /api/planning/runs                  → {success, data: run}
  GET  /api/planning/runs?limit=           → {success, data: [run]}
  GET  /api/planning/runs/{id}             → {success, data: run}
  GET  /api/planning/runs/{id}/events      → SSE（after_seq 续传）
  POST /api/planning/runs/{id}/answer      → {success, data: run}  body {key}
  GET  /api/planning/runs/{id}/deliverables/{did} → {success, data: {name, content}}

run 的形状见 `PlanningRun.to_dict()`：
  {id, status, scene, budget, duration, constraints, subject,
   graph:{nodes, edges}, meta, question, error, created_at, updated_at}

为什么不像 assistant 那样只给一个聚合端点：
  工作台要「看着图长出来」，聚合端点只能给快照；也不像 chat 那样有 15 种
  事件 —— 这里刻意只发 5 种（phase/think/retrieve/call/graph/question/
  deliverable/done 归为 6 类），够工作台用即可。
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from server.utils.auth_middleware import get_required_user
from server.utils.user_store import User
from src.services import planning_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/planning", tags=["planning"])

# SSE 轮询间隔：事件是落库的，没有进程内队列可 await，
# 所以按固定间隔查新事件。500ms 对「看着它长出来」足够跟手，
# 且一次 run 的事件量很小（几十条），查询成本可忽略。
SSE_POLL_SECONDS = 0.5
SSE_MAX_SECONDS = 600   # 单连接上限；前端断线会自动重连并带 after_seq 续传


def _uid(user: User) -> str:
    """与 decisions_router / task_router / assistant_router 同一口径。"""
    return str(getattr(user, "id", None) or getattr(user, "user_id", "anonymous"))


def _fmt(kind: str, payload: dict, seq: int) -> str:
    """按 SSE 规范序列化一条事件。字段名与前端解析对齐。"""
    data = json.dumps({"seq": seq, "kind": kind, "payload": payload}, ensure_ascii=False)
    return f"id: {seq}\nevent: {kind}\ndata: {data}\n\n"


@router.post("/runs")
async def create_run(
    body: dict = Body(...),
    current_user: User = Depends(get_required_user),
):
    """入口页提交 → 建 run，立即返回（图在后台推进）。"""
    return {"success": True, "data": await planning_service.create_run(_uid(current_user), body)}


@router.get("/runs")
async def list_runs(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_required_user),
):
    return {"success": True, "data": await planning_service.list_runs(_uid(current_user), limit)}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, current_user: User = Depends(get_required_user)):
    """工作台首屏快照：run 状态 + 完整决策图 + 待确认问题。

    刷新页面走这里 —— 一次拿全，不重放事件。
    """
    run = await planning_service.get_run(run_id, _uid(current_user))
    if run is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"success": True, "data": run.to_dict()}


@router.get("/runs/{run_id}/events")
async def stream_events(
    run_id: str,
    after_seq: int = Query(default=0, ge=0),
    current_user: User = Depends(get_required_user),
):
    """执行流 + 图变更的 SSE 增量。

    `after_seq` 实现续传：前端断线重连时带上最后收到的 seq，不会重放旧事件，
    也不会漏 —— 事件落库且 seq 单调，这是能这么做的前提。
    """
    uid = _uid(current_user)
    run = await planning_service.get_run(run_id, uid)
    if run is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    async def gen():
        cursor = after_seq
        waited = 0.0
        while waited < SSE_MAX_SECONDS:
            events = await planning_service.list_events(run_id, after_seq=cursor)
            for ev in events:
                cursor = ev["seq"]
                yield _fmt(ev["kind"], ev["payload"], ev["seq"])
            # 收敛或失败后把尾批事件发完就收口，不留悬空连接
            fresh = await planning_service.get_run(run_id, uid)
            if fresh is not None and fresh.status in ("converged", "failed"):
                rest = await planning_service.list_events(run_id, after_seq=cursor)
                for ev in rest:
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
            "X-Accel-Buffering": "no",     # nginx 不缓冲（否则事件会攒着一起发）
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.post("/runs/{run_id}/answer")
async def answer(
    run_id: str,
    key: str = Body(..., embed=True),
    current_user: User = Depends(get_required_user),
):
    """用户回答待确认问题 → 从下一阶段续跑。"""
    run = await planning_service.answer_question(run_id, _uid(current_user), key)
    if run is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"success": True, "data": run}


@router.post("/runs/{run_id}/deliver")
async def mark_delivered(
    run_id: str,
    current_user: User = Depends(get_required_user),
):
    """标记这条采购已交付 —— 「生成交付」按钮的动作。

    ⚠️ 与「取交付物正文」是两件事，别混（这个区分原先不存在，导致按钮
    点了没反应）：正文在收敛时就算好并随事件下发过了；这个接口记的是
    **用户的交付确认**，历史列表据此把「待交付」变成「已交付」。

    未收敛的任务如实拒绝（409），前端据此给提示 —— 不静默失败。
    """
    got = await planning_service.mark_delivered(run_id, _uid(current_user))
    if got is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if got.get("rejected") == "not_converged":
        raise HTTPException(
            status_code=409,
            detail=f"任务还在「{got.get('status')}」，尚无可交付的成果",
        )
    return {"success": True, "data": got}


@router.get("/runs/{run_id}/deliverables/{did}")
async def get_deliverable(
    run_id: str,
    did: str,
    current_user: User = Depends(get_required_user),
):
    """交付物正文（Markdown）。"""
    d = await planning_service.get_deliverable(run_id, _uid(current_user), did)
    if d is None:
        raise HTTPException(status_code=404, detail="交付物不存在")
    return {"success": True, "data": d}


@router.get("/runs/{run_id}/deliverables/{did}/export/{fmt}")
async def export_deliverable(
    run_id: str,
    did: str,
    fmt: str,
    current_user: User = Depends(get_required_user),
):
    """导出产出物：`fmt` ∈ {pdf, csv, md}。

    ⚠️ 支持哪些格式由**产出物自己声明**（后端 ARTIFACT_SPEC 的 formats），
    这里不写 if/else —— 声明了没实现的渲染器会在服务层返回 None，走到 404。

    ⚠️ 文件名用 RFC 5987 的 `filename*=UTF-8''…` 传中文：
    只给 `filename=` 的话 HTTP 头按 latin-1 编码，中文会变成乱码
    （浏览器里就是一堆问号）。
    """
    from urllib.parse import quote

    got = await planning_service.export_deliverable(
        run_id, _uid(current_user), did, fmt
    )
    if got is None:
        raise HTTPException(status_code=404, detail=f"这份交付物不支持导出为 {fmt}")
    data, fname, mime = got

    return Response(
        content=data,
        media_type=mime,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{did}.{fmt}"; '
                f"filename*=UTF-8''{quote(fname)}"
            ),
        },
    )
