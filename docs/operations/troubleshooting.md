# 故障排查手册

真实事故沉淀。每条：现象 → 根因 → 处置 → 预防。新增故障必须追加到本文。

## 1. Redis 连接池跨事件循环（对话存储 500 / 消息丢失）

- **现象**：`POST /api/chat/thread` 500；日志
  `RuntimeError: Lock bound to a different event loop` /
  `Task got Future attached to a different loop`；AI 消息不入库。
- **根因**：`redis.asyncio` 连接池/锁惰性绑定首个事件循环；同步包装
  （cache_decorator 的 ThreadPoolExecutor + `asyncio.run`）在 serve loop
  内访问共享池 → 池绑定临时 loop → 主 loop 后续命令全炸。
- **处置**：同步路径改走独立短连接（`RedisCache.sync_get/sync_set`）；
  lifespan 预热共享池绑定 serve loop；`MessageStoreBridge._call` 全容错降级。
- **预防**：Redis 访问只走三条合法路径（存储文档第 5 节）；
  日志 grep：`docker compose logs api | grep -i "different loop"`。

## 2. PostgreSQL 公网暴露遭勒索删库（登录 500 / 数据清空）

- **现象**：某日起所有接口 500；`\dt` 空；出现勒索表/README；
  pg 端口曾对外可达。
- **处置**：停服 → 从备份/快照恢复 PG → 轮换 `POSTGRES_PASSWORD` →
  端口改绑 `127.0.0.1` → 重启验证 → 审计公网安全组。
- **预防**：compose 中 postgres ports 只写 `127.0.0.1:5432:5432`（已固化），
  云安全组不放行 5432；数据库与 Redis 都按"可随时重建+定期备份"管理。

## 3. 对话无法持久化（历史丢失）

- **现象**：刷新后历史为空；或 PG `conversations.messages` 只有用户消息、
  无 AI 消息；或出现 `content` 为 null 的假 AI 消息。
- **根因**（按时间顺序修复）：① Redis 先写且未容错，缓存抖动跳过 PG 写入；
  ② 时间戳用 `event_loop.time()` 单调钟（假时间）；③ 异常兜底路径抛二次
  异常导致保存中断；④ agent 不存在时保存空消息。
- **处置**：消息保存改为 PG 先落（try）→ bridge 镜像（try）；时间戳统一
  ISO；兜底分支 try 包裹；空内容不落库（save_partial_message 守卫）。
- **预防**：见存储文档第 3 节时序；改此链路必须端到端验证三层
  （SSE done + PG 行 + history API）。

## 4. 登录后立刻被"认证失败"踢出

- **现象**：登录成功跳转后马上弹"认证失败，请重新登录"。
- **根因**：某"可选鉴权"接口错误使用了强制登录依赖 `get_required_user`
  （或中间件对静态资源强制鉴权），登录态请求到该接口返回 401 → 前端
  全局拦截清理 token。
- **处置**：把接口依赖改为 `get_current_user`（可选鉴权语义）；
  前端对 401 只清 token 不弹致命错（按接口语境提示）。
- **预防**：鉴权依赖分级见 [API 约定](../api/index.md#鉴权依赖分级)。

## 5. 前端报 `[object Object]` / `Unexpected token 'I'...`

- **现象**：创建管理员/表单提交报 `[object Object]`；登录报
  `Unexpected token 'I', "Internal S"... is not valid JSON`。
- **根因**：① 前端把后端错误对象直接模板化展示（JS 隐式 toString）；
  ② 后端不可达时 Nginx/代理返回 502/纯文本，`response.json()` 解析失败。
- **处置**：错误展示统一取 `err.detail ?? err.message ?? JSON.stringify(err)`
  的字符串字段；fetch 前检查 `content-type` 或 try/catch json 解析；
  先 curl 后端确认存活。
- **预防**：前端错误提取统一封装（base.js）；后端可用性由
  `/api/system/health` 探活。

## 6. 容器内 import 失败（No module named 'src' / 'server'）

- **现象**：`docker exec shoppingclaw-api python xxx.py` 或自定义 worker
  报找不到 src/server 包。
- **根因**：容器内包根是 `/app`，但 exec 默认工作目录/路径不含 /app。
- **处置**：脚本开头 `sys.path.insert(0, "/app")`；或
  `cd /app && python xxx.py`。
- **预防**：容器内验证一律显式加路径（见 AGENTS.md）。

## 7. 删除用户/线程时外键或类型报错

- **现象**：删 users 报 `operation_logs_user_id_fkey`；按
  `conversations.user_id = 整数` 删不到行。
- **根因**：users.id 为 int，conversations.user_id 为 varchar；审计日志带
  外键。
- **处置**：先删日志再删用户；用户维过滤用
  `user_id = (SELECT id::text FROM users WHERE ...)`。
- **预防**：SQL 清理先 `\d 表` 看类型与外键（部署文档第 6 节）。

## 8. 其它速查

| 现象 | 处置 |
| --- | --- |
| 容器重启后 `Event loop is closed` 大量出现 | 正常关闭日志；确认新进程已起（`docker ps` + 预热日志 `[OK] Redis connected (pre-warmed)`） |
| 接口慢/卡 | 看日志 request_id 串起的调用链；常见：知识库初始化、embedding 拉取 |
| SSE 到一半断开 | 客户端断连属预期（服务端已兜底保存）；高频出现查限流/网络代理缓冲 |
| Redis 键堆积 `thread:*` | PG 与 Redis 双删单边失败所致；核对后 `redis-cli DEL` 残键 |
| 前端能开但接口 502 | nginx `/api` 反代目标 5050 容器未健康；`curl 127.0.0.1:5050/api/system/health` |
| 磁盘被日志占满 | `saves/logs/` 轮转保留 + docker json-file 50m×3 上限；`df -h` 核查 |
