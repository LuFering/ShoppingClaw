# 参与贡献

感谢你关注 ShoppingClaw。欢迎提交 Issue、修复 Bug、补充测试、改进文档或贡献新功能。

## 开始前

- 先搜索现有 [Issues](https://github.com/LuFering/ShoppingClaw/issues) 与 [docs/](docs/index.md)，避免重复工作。
- 较大的功能、公开接口、存储或架构变化，先与团队讨论范围与方案再动手。
- 一个提交只解决一个明确问题，不混入无关重构与"顺手优化"。
- 修改不熟悉的模块前，先读 [ARCHITECTURE.md](ARCHITECTURE.md) 与对应的 `docs/` 文档。

## 开发环境

项目运行在 Docker Compose 中（开发模式挂载源码、支持热重载）：

```bash
docker compose up -d                # 启动 api + postgres + redis
docker compose logs -f api          # 跟踪 API 日志
curl http://localhost:5050/api/system/health
```

前端（web-v2）在宿主机或容器内以 npm 运行，`/api` 由 Vite 代理到 5050：

```bash
cd web-v2 && npm ci && npm run dev
```

## 提交规范

- 提交信息用中文，一句话说清"做了什么、为什么"：
  `fix(chat): 修复 AI 消息在 Redis 故障时丢失的问题`；
  类型前缀：`fix` / `feat` / `refactor` / `docs` / `chore` / `test` / `ops`。
- 涉及 API、存储、SSE 协议、配置或行为变化的提交，必须同步更新 `docs/`
  对应文档，否则视为未完成。
- 提交前自查：

```bash
git diff --check        # 无空白错误
git status              # 无意外文件（saves/ 等运行时数据不得入库）
```

## 代码约定速览（详见 docs/development/backend-guide.md）

- 后端导入一律 `src.*` / `server.*`，禁止 `ShoppingClaw.*` 前缀与顶层
  `agents/deepagents` 导入。
- 消息/时间戳一律 UTC ISO-8601（`datetime.now(timezone.utc).isoformat()`），
  禁止 `event_loop.time()` 单调时钟当时间用。
- 任何 Redis 访问都走 `MessageStoreBridge`/`RedisCache.sync_*` 容错封装，
  新代码禁止直接 `redis.asyncio` 建连后跨事件循环复用。
- 异步代码（serve loop）与同步代码（线程）对 Redis 使用不同连接路径，
  详见存储文档。
- 路由层不写业务逻辑；数据写入以 PostgreSQL 为主、缓存为影子。

## 评审与合并

- 至少一位其他成员 Review 后合并；破坏性变更（删库/改表/改协议）需两人。
- UI 改动在 PR 描述附截图或录屏；接口改动附调用示例与验证结果。
- 线上故障修复请把根因与处置沉淀到
  [docs/operations/troubleshooting.md](docs/operations/troubleshooting.md)。
