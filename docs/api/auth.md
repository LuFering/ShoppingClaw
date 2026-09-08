# 认证 API（/api/auth/*）

## 登录获取 token

`POST /api/auth/token` — 公开（OAuth2 密码模式，**form-data**，非 JSON）

```
username=<登录标识>&password=<密码>
```

成功 200：

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

失败：`401 {"detail": "..."}`；账户锁定 `423 {"detail": "..."}`。
之后所有业务请求带 `Authorization: Bearer <access_token>`。

## 首次运行检查

`GET /api/auth/check-first-run` — 公开

```json
{ "first_run": true }
```

`first_run=true` 表示系统尚无管理员，需要先 initialize。

## 初始化管理员（仅首次）

`POST /api/auth/initialize` — 公开（仅 `first_run=true` 时可用）

```json
{ "username": "admin", "password": "<强密码>", "email": "admin@example.com" }
```

成功 200：`Token`（同登录响应）。已初始化时调用 → 400/403。

## 当前用户

`GET /api/auth/me` — Bearer 必选

```json
{
  "id": 1,
  "username": "admin",
  "email": "admin@example.com",
  "role": "superadmin",
  "created_at": "..."
}
```

角色：`user` / `admin` / `superadmin`（`isAdmin = admin|superadmin`）。
