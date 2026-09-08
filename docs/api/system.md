# 系统 API（/api/system/*）

## 健康检查（公开）

`GET /api/system/health`

```json
{ "status": "ok", "service": "ShoppingClaw API" }
```

docker compose healthcheck 使用本端点（curl -f）。

## 系统信息（公开）

`GET /api/system/info`

```json
{
  "success": true,
  "data": {
    "organization": { "name": "ShoppingClaw", "logo": "/logo.png", "avatar": "/avatar.png" },
    "branding": { "name": "ShoppingClaw", "title": "ShoppingClaw", "subtitle": "智能购物助手" },
    "features": [],
    "actions": [],
    "footer": { "copyright": "© 2026 ShoppingClaw. All rights reserved." }
  }
}
```

前端登录页/首页品牌信息据此渲染（Logo 等静态资源由前端自行提供）。

## 审计日志（管理员）

`GET /api/system/audit-logs?limit=50&path_filter=/api/chat` — 需管理员角色

```json
{ "success": true, "data": [ { "id": 1, "user_id": 1, "method": "POST",
  "path": "/api/chat/thread", "status_code": 200, "created_at": "..." } ], "total": 1 }
```

写操作由 `AuditMiddleware` 自动记录到 `operation_logs`。

## 测试回声（公开）

`POST /api/test/echo` — body `{"message": "hi"}`（或 query）→
`{"status":"ok","received":"hi","timestamp":...}`。连通性自检用。

## 根路径

`GET /` → `{message, docs: "/docs", health: "/api/system/health"}`。
