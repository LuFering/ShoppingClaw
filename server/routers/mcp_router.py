"""MCP 服务器管理 API

契约与前端 `web-v2/src/apis/mcp_api.js` 对齐：
  GET    /api/mcp/servers            → {success, data:[McpServer]}
  POST   /api/mcp/servers            → {success, data:McpServer}（后端分配 id）
  PUT    /api/mcp/servers/{id}       → {success, data:McpServer}
  DELETE /api/mcp/servers/{id}       → {success}
  POST   /api/mcp/servers/{id}/test  → {success, data:{ok, message}}
  GET    /api/mcp/market             → {success, data:[]}

背景（2026-09-22）：此前 MCP 配置硬编码在 mcp_service.py，前端 McpHubView 用的是
编造的种子数据（含 mcp.jd.example.com 占位域名）。本路由让配置可管理。

注意：**工具白名单不在此管理** —— 它是安全边界，保持代码硬编码
（见 mcp_tool_adapter.py 的 _MCP_TOOL_WHITELIST）。
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from server.utils.auth_middleware import get_required_user
from server.utils.user_store import User
from src.repositories.mcp_server_repository import MCPServerRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])

# 允许的传输类型（与前端表单选项一致）
_ALLOWED_TYPES = {"stdio", "http", "sse"}


def _new_id() -> str:
    return f"mc-{uuid.uuid4().hex[:8]}"


def _validate_payload(body: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
    """校验并规范化前端提交的载荷。

    Args:
        partial: True 用于 PUT（允许只提交部分字段，不做必填校验）。
                 False 用于 POST（name / endpoint 必填）。

    Raises:
        HTTPException: 400 —— 字段缺失或非法
    """
    out: dict[str, Any] = {}

    if "name" in body:
        name = str(body.get("name") or "").strip()
        if name:
            out["name"] = name
    if not partial and not out.get("name"):
        raise HTTPException(status_code=400, detail="缺少 name")

    if "endpoint" in body:
        endpoint = str(body.get("endpoint") or "").strip()
        if not endpoint and not partial:
            raise HTTPException(status_code=400, detail="缺少 endpoint（命令或 URL）")
        if endpoint:
            out["endpoint"] = endpoint
    elif not partial:
        raise HTTPException(status_code=400, detail="缺少 endpoint（命令或 URL）")

    if "type" in body:
        t = str(body.get("type") or "").strip().lower()
        if t not in _ALLOWED_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"type 必须是 {'/'.join(sorted(_ALLOWED_TYPES))}",
            )
        out["type"] = t

    if "desc" in body:
        out["desc"] = str(body.get("desc") or "")
    if "enabled" in body:
        out["enabled"] = bool(body.get("enabled"))
    # env：只在前端**显式提交**时才覆盖。
    # 列表接口不回传 env 值（凭据），所以前端表单通常是空的 ——
    # 此时若照单全收会清空已有凭据，必须要求显式提交。
    if isinstance(body.get("env"), dict) and body["env"]:
        out["env_json"] = body["env"]

    return out


@router.get("/servers")
async def list_servers(current_user: User = Depends(get_required_user)):
    """列出全部 MCP 服务器。"""
    repo = MCPServerRepository()
    rows = await repo.list()
    return {"success": True, "data": [r.to_dict() for r in rows]}


@router.post("/servers")
async def create_server(
    body: dict[str, Any] = Body(...),
    current_user: User = Depends(get_required_user),
):
    """新建 MCP 服务器（后端分配 id）。"""
    repo = MCPServerRepository()
    payload = _validate_payload(body, partial=False)
    payload["id"] = _new_id()
    if await repo.exists_by_name(payload["name"]):
        raise HTTPException(status_code=409, detail=f"名称已存在：{payload['name']}")
    row = await repo.create(payload)
    return {"success": True, "data": row.to_dict()}


@router.put("/servers/{server_id}")
async def update_server(
    server_id: str,
    body: dict[str, Any] = Body(...),
    current_user: User = Depends(get_required_user),
):
    """按 id 更新 MCP 服务器。"""
    repo = MCPServerRepository()
    existing = await repo.get_by_id(server_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="服务器不存在")
    payload = _validate_payload(body, partial=True)
    row = await repo.update_by_id(server_id, payload)
    return {"success": True, "data": row.to_dict() if row else None}


@router.delete("/servers/{server_id}")
async def delete_server(
    server_id: str,
    current_user: User = Depends(get_required_user),
):
    """按 id 删除 MCP 服务器。"""
    repo = MCPServerRepository()
    ok = await repo.delete_by_id(server_id)
    if not ok:
        raise HTTPException(status_code=404, detail="服务器不存在")
    return {"success": True}


@router.post("/servers/{server_id}/test")
async def test_server(
    server_id: str,
    current_user: User = Depends(get_required_user),
):
    """连通性测试：实际拉起进程/请求并统计工具数。

    不做后台轮询 —— 由前端手动触发，结果落库。
    """
    repo = MCPServerRepository()
    row = await repo.get_by_id(server_id)
    if row is None:
        raise HTTPException(status_code=404, detail="服务器不存在")

    cfg = {
        "type": row.type,
        "command": row.endpoint,  # stdio 用 command
        "enabled": True,
        "env": row.env_json or {},
    }

    ok = False
    message = ""
    tools_count = 0

    try:
        if row.type == "stdio":
            from src.services.mcp_service import _get_stdio_tool_specs

            specs = _get_stdio_tool_specs(row.name, cfg)
            tools_count = len(specs)
            ok = tools_count > 0
            message = f"连接成功，发现 {tools_count} 个工具" if ok else "进程启动但未返回工具"
        else:
            # http / sse：当前项目未实现，如实说明而不是假装成功
            message = f"{row.type} 传输尚未实现，暂无法测试"
    except Exception as exc:
        message = f"测试失败：{exc}"
        logger.warning(f"[MCP] 测试 {row.name} 失败: {exc}")

    # 结果落库（供前端展示心跳）
    try:
        import time

        await repo.update_by_id(
            server_id,
            {
                "status": "connected" if ok else "failed",
                "tools_count": tools_count,
                "heartbeat": time.strftime("%H:%M:%S") if ok else "—",
            },
        )
    except Exception as exc:
        logger.warning(f"[MCP] 测试结果落库失败（忽略）: {exc}")

    return {"success": True, "data": {"ok": ok, "message": message, "tools": tools_count}}


@router.get("/market")
async def list_market(current_user: User = Depends(get_required_user)):
    """MCP 市场。

    当前返回空数组：项目没有真实的市场源，编一份"可安装列表"等于制造假数据。
    前端 `mcp_api.js` 对此有降级处理，返回空即展示"暂无可用"。
    """
    return {"success": True, "data": []}
