# 快速开始

## 前置条件

- Linux 服务器（或 Docker Desktop 的 Win/mac），已装 **Docker Engine + Compose**。
- 一个可用的 LLM API Key（当前默认 SiliconFlow；如用别家改 `.env` 的
  `SILICONFLOW_API_KEY` 对应变量）。
- 服务器 docker 命令需要 `sudo`（本仓库 CI 环境无 docker 组）。

## 第 1 步：环境变量

```bash
cd ShoppingClaw
cp .env.template .env
vim .env   # 至少填写 SILICONFLOW_API_KEY（其余可先留默认）
```

`.env` 关键项（完整见 [.env.template](../../.env.template)）：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `SILICONFLOW_API_KEY` | 空 | LLM 供应商 Key（对话/标题生成） |
| `TAVILY_API_KEY` | 空 | Web 检索（可选） |
| `JWT_SECRET_KEY` | 模板占位 | **生产必须改成强随机值** |
| `POSTGRES_*` | postgres | DB 账号/密码/库名 |
| `REDIS_URL` | `redis://redis:6379/0` | 容器网络内地址，一般不动 |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | 本地模型（可选） |
| `TAOBAO_SESSION` / `TAOBAO_PID` | 空 | 淘宝导购 MCP 凭据（可选） |

> `.env` 已被 gitignore，严禁入库；`.env.template` 是唯一模板来源。

## 第 2 步：启动服务

```bash
docker compose up -d            # 构建并启动 api + postgres + redis
docker compose ps               # 等 api 变 healthy（首启约 1-2 分钟）
curl http://localhost:5050/api/system/health
# {"status":"ok","service":"ShoppingClaw API"}
```

启动后：

- Swagger 文档：http://localhost:5050/docs
- 健康检查：`/api/system/health`；系统信息：`/api/system/info`

## 第 3 步：初始化管理员并登录

首次启动数据库为空，先检查再初始化（接口见 [auth 文档](../api/auth.md)）：

```bash
# 1) 检查是否需要初始化
curl http://localhost:5050/api/auth/check-first-run

# 2) 创建管理员（仅首次需要）
curl -X POST http://localhost:5050/api/auth/initialize \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<强密码>","email":"admin@example.com"}'

# 3) 登录获取 token
curl -X POST http://localhost:5050/api/auth/token \
  -d 'username=admin&password=<强密码>'

# 4) 携带 token 访问（所有业务接口都需要）
curl http://localhost:5050/api/auth/me \
  -H "Authorization: Bearer <token>"
```

## 第 4 步：发起一次对话（SSE）

```bash
curl -N -X POST http://localhost:5050/api/chat/agent/MasterAgent \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"query":"推荐 200 元以内的无线耳机","config":{}}'
```

响应是 `text/event-stream`：先 `title`/`message_chunk`/`thinking`/`tool_call`
事件，最后 `done` 事件带统计。完整协议见 [chat API](../api/chat.md)。

## 第 5 步：前端（web-v2）

```bash
cd web-v2
npm ci
npm run dev        # http://localhost:5173，/api 代理到 http://localhost:5050
```

代理目标可用环境变量覆盖：`VITE_API_URL=http://127.0.0.1:5050 npm run dev`。
生产构建：`npm run build`，产物 `dist/` 交给 Nginx（本服务器部署于
`/www/wwwroot/shoppingclaw`，由面板统一管理）。

## 验证服务链路（日常自检）

```bash
# API 与鉴权
curl -s http://localhost:5050/api/system/info | head -c 200
# 对话（真实验证，见上）；随后三层核对：
sudo docker exec shoppingclaw-postgres psql -U postgres -d shoppingclaw \
  -c "select id,title,jsonb_array_length(messages) from conversations order by updated_at desc limit 3;"
sudo docker exec shoppingclaw-redis redis-cli keys 'thread:*' | head
```

## 常见问题（速查）

| 现象 | 处置 |
| --- | --- |
| 登录/接口报 `Internal Server Error` | 先看日志 `docker compose logs -f api`，常见 Redis 未预热/DB 未迁移 |
| 改了代码不生效 | 代码已 bind mount，执行 `sudo docker compose restart api` |
| 改了 `docker-compose.yml`/依赖 | 需要 `sudo docker compose up -d`（重建容器） |
| 想跑本地（不用容器） | 见后端开发指南的环境章节 |

完整排障手册见 [operations/troubleshooting.md](../operations/troubleshooting.md)。
