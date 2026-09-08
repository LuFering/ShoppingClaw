# 部署运维

## 1. 拓扑

```
[用户] → Nginx(80/443)
            ├── / → 静态前端 /www/wwwroot/shoppingclaw（构建产物）
            └── /api → 127.0.0.1:5050（shoppingclaw-api 容器）
```

compose 服务（本服务器实际运行）：

| 服务 | 端口暴露 | 说明 |
| --- | --- | --- |
| api | `5050:5050` | uvicorn 单进程；代码 bind mount 热重载模式 |
| postgres | `127.0.0.1:5432:5432` | **仅回环**（安全：曾因公网暴露被勒索删库，见故障手册） |
| redis | 不暴露 | 容器网络内 |

数据目录：`docker/volumes/postgresql`（PG 数据）、`docker/volumes/redis`
（AOF）；运行时 `saves/`（日志、users.json、Chroma）——均已 gitignore。

## 2. 日常操作

```bash
sudo docker compose up -d            # 启动/按新 compose 重建
sudo docker compose restart api      # 仅重启 API（代码改动生效）
sudo docker compose ps               # 状态
sudo docker compose logs -f api      # 实时日志（落盘于 saves/logs/，轮转保留）
sudo docker compose logs --tail=200 api

curl http://127.0.0.1:5050/api/system/health   # 健康
```

常用排查：

```bash
sudo docker exec shoppingclaw-postgres psql -U postgres -d shoppingclaw -c "\dt"
sudo docker exec shoppingclaw-redis redis-cli keys 'thread:*' | head
```

## 3. 代码更新流程

1. 服务器是开发/单机混合形态：直接编辑仓库文件（bind mount），
   `sudo docker compose restart api` 生效。
2. 改动依赖（pyproject/uv.lock）或 Dockerfile：`sudo docker compose up -d --build`。
3. 改动 compose 文件本身：`sudo docker compose up -d`（重建容器配置）。
4. 前端发布：`cd web-v2 && npm ci && npm run build`，产物上传
   `/www/wwwroot/shoppingclaw/`（面板/nginx 托管，注意先备份旧 assets）。

## 4. 备份与恢复

### 备份（建议每日）

```bash
# PG 全量（业务 + 对话 + checkpointer）
sudo docker exec shoppingclaw-postgres pg_dump -U postgres -d shoppingclaw \
  -F c -f /tmp/sc_$(date +%F).dump
sudo docker cp shoppingclaw-postgres:/tmp/sc_$(date +%F).dump /home/ubuntu/backups/
```

Redis 为影子层可不备份；`saves/` 建议 tar 带走（Chroma 向量库）。

### 恢复

```bash
sudo docker cp /home/ubuntu/backups/sc_2026-09-08.dump shoppingclaw-postgres:/tmp/
sudo docker exec shoppingclaw-postgres pg_restore -U postgres -d shoppingclaw \
  --clean --if-exists /tmp/sc_2026-09-08.dump
sudo docker compose restart api
```

> 勒索事件后的教训：**任何指向数据库的恢复操作先快照**；恢复前确认当前
> 容器数据目录（docker/volumes）不是被破坏的那一份。

## 5. 镜像管理（离线/换机）

仓库提供脚本：`docker/pull_image.sh <image:tag>`（国内镜像源加速）、
`docker/save_docker_images.sh|ps1`（离线导出 tar）。

## 6. 安全基线

- PostgreSQL 仅绑定 127.0.0.1（compose ports 已限定；勿改回 `0.0.0.0`）。
- `.env` 的 `POSTGRES_PASSWORD` 与 `JWT_SECRET_KEY` 生产使用强随机值；
  `.env` 不入库。
- 审计日志可经 `GET /api/system/audit-logs`（管理员）查询。
- 清理测试数据注意外键顺序：先删 `operation_logs` → 再删 `users`；
  `conversations.user_id` 是 varchar，与 `users.id`(int) 比较用 `id::text`。
