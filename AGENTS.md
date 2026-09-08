# AGENTS.md — AI 协作公约

本文件面向 AI 编码助手与人类协作者，约定在 ShoppingClaw 仓库中工作的
**硬性规则与高频事实**，避免重复犯错。人类开发者同样适用。

## 环境事实（务必先知道）

- 服务以 docker compose 运行于服务器：api(5050) + postgres + redis；
  仓库根 `/home/ubuntu/ShoppingClaw`，代码 bind mount（`server/`、`src/`
  → 容器 `/app/server`、`/app/src`），改代码需重启 api 容器生效。
- 容器内 Python 导入路径是 `/app`：一律 `from src.xxx` / `from server.xxx`，
  禁止 `ShoppingClaw.` 前缀（容器内不存在该包）。
- 容器内执行脚本需 `sys.path.insert(0, "/app")`（如 docker exec 跑测试时）。
- docker 命令需 `sudo`（服务器无 docker 组）；部分 sudo 需完整权限。
- 生产数据在 PostgreSQL/Redis **容器内**，`docker/volumes/` 与 `saves/` 是
  运行时数据（saves/ 已 gitignore）；任何"清理数据"操作先确认指向。

## 架构铁律（违反会出线上事故）

1. **PG 是主真相，Redis 是影子**。写路径先落 PostgreSQL（try/except 保护），
   再经 `MessageStoreBridge` 镜像缓存；缓存失败只记 warning，绝不向调用方抛错。
2. **禁止跨事件循环访问 Redis 共享连接池**（`redis.asyncio` 连接池的锁惰性
   绑定首个 loop）。三条合法路径：
   - async 代码：lifespan 预热后的共享池（serve loop 内）；
   - 同步代码（线程）：`RedisCache.sync_get/sync_set` 独立短连接；
   - `MessageStoreBridge._call` 统一容错封装。
3. **时间戳统一** `datetime.now(timezone.utc).isoformat()`（ISO-8601 UTC）；
   禁止把 `asyncio.get_event_loop().time()`（单调浮点秒）当作时间入库。
4. **不要在 running loop 里 `asyncio.run`/ThreadPoolExecutor 包装共享资源**；
   不要在请求路径里反复创建事件循环。
5. 消息保存顺序：用户消息/AI 消息 → PG 先（try）→ bridge 后（try）；空内容
   不落库（save_partial_message 有守卫，勿删）。

## 常用命令

```bash
sudo docker compose -f /home/ubuntu/ShoppingClaw/docker-compose.yml up -d
sudo docker compose logs -f api
curl http://127.0.0.1:5050/api/system/health
sudo docker exec shoppingclaw-api python -c "..."   # 容器内验证（注意 sys.path）
```

## 高频修改点对照

| 需求 | 位置 |
| --- | --- |
| 新 HTTP 接口 | `server/routers/` + `server/main.py` 注册 + 同步 `docs/api/` |
| 对话/SSE/持久化 | `src/services/chat_stream_service.py` |
| 存储读写 | `src/services/redis_store.py`(bridge) · `src/repositories/conversation_repository.py` |
| Agent/工具 | `src/agents/`（master_agent/ 图、subagents/、common/ 中间件） |
| 前端请求 | `web-v2/src/apis/*.js`（base.js 统一鉴权封装） |

## 工作流要求

- 改动影响运行中的服务时，先备份/确认回滚方式；重大改动先小步验证再铺开。
- 涉及对话存储、认证、SSE 协议的改动必须做端到端验证（curl API + 查 PG/Redis），
  不能只看"能 import"。
- 测试数据用完即清（容器数据库与 Redis 键），不留垃圾。
- 每次线上故障修复后：沉淀根因 → 修复 → 验证 → 更新
  `docs/operations/troubleshooting.md`。

## 未提交代码警示

- `src/services/home/suggestion_service.py` 当前未被 git 跟踪（历史遗留），
  但它被运行链路引用 —— 改动该文件时不要删除，完成功能后应提交入库。
