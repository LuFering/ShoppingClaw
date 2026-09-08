# API 通用约定

- **Base URL**：`http://<host>:5050/api`（生产经 Nginx 反代，路径不变）
- **协议**：HTTP/1.1 + JSON；对话接口为 SSE（`text/event-stream`）
- **OpenAPI**：`GET /docs`（Swagger UI）提供字段级 schema，本目录文档约定
  语义、调用顺序与错误行为——两边冲突时以代码为准并回报文档缺陷

## 认证

除 `/api/auth/token`、`/api/auth/check-first-run`、`/api/auth/initialize`、
`/api/system/health|info` 与首页推荐（可选鉴权）外，所有接口都需要请求头：

```
Authorization: Bearer <access_token>
```

- 获取 token：`POST /api/auth/token`（OAuth2 密码模式，form 参数），见
  [auth.md](auth.md)。
- 无/坏 token → `401 {"detail": "..."}`；无权限 → `403`；
  账号锁定 → `423`。

### 鉴权依赖分级

| 依赖 | 语义 | 使用场景 |
| --- | --- | --- |
| `get_required_user` | 必须登录，否则 401 | 绝大多数业务接口 |
| `get_current_user` | 可选：登录给个性化，未登录放行 | 首页推荐等低敏接口 |
| `get_admin_user` | 必须管理员 | 审计日志等管理接口 |

> 给"可选鉴权"接口错误使用强制依赖会导致登录用户被 401 踢出——保持分级。

## 错误格式

FastAPI 默认错误体（本项目不再包一层 `success`）：

```json
{ "detail": "错误描述" }
```

| 状态码 | 含义 |
| --- | --- |
| 400 | 参数错误（如记忆内容为空） |
| 401 | 未认证/token 失效 |
| 403 | 无权限（非管理员访问管理接口） |
| 404 | 资源不存在（agent/thread/task 不存在等） |
| 423 | 账户锁定（多次登录失败） |
| 429 | 触发速率限制（对话默认 20 次/分） |
| 500 | 服务端异常（detail 常含可读原因） |

部分接口（系统信息、任务列表等）返回 `{"success": true, "data": ...}` 包裹，
以各接口文档为准。

## 速率限制

对话类接口滑动窗口限流（默认 `max_requests=20` / `window=60s` / 用户维度），
超限返回 429。查询剩余额度：`GET /api/chat/rate-limit-status`。

## SSE 流调用基础

见 [chat.md 的 SSE 事件协议章节](chat.md#sse-事件协议)。

## 通用 JSON 字段约定

| 字段 | 约定 |
| --- | --- |
| 时间 | UTC ISO-8601（`datetime.now(timezone.utc).isoformat()`）字符串 |
| id | 线程/会话为 uuid 字符串；agent id 如 `MasterAgent` |
| 分页 | `limit`（默认随接口，≤500）+ `offset`（默认 0） |
