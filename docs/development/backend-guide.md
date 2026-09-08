# 后端开发指南

面向新增成员与日常开发。**动手前先读**：[后端架构](../architecture/backend.md)、
[存储架构](../architecture/storage.md)（涉及数据时必读）。

## 1. 环境

**推荐方式（与线上一致）**：docker compose 开发模式运行，代码挂载即改即生效
（api 容器内 uvicorn 由 compose command 启动；改代码后

```bash
sudo docker compose restart api
sudo docker compose logs -f api
```

**本地直跑（可选）**：需要 Python 3.12 + uv（或 pip），先启动依赖：

```bash
# 依赖容器（仅 PG+Redis），并给 .env 追加指向 localhost 的 URL：
sudo docker compose up -d postgres redis
export POSTGRES_URL="postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/shoppingclaw"
export REDIS_URL="redis://127.0.0.1:6379/0"
uv sync && uv run uvicorn server.main:app --reload --port 5050
```

注意：本地跑时 `sys.path` 需含仓库根（uv 默认如此）；容器内则是 `/app`
（见 AGENTS.md 导入纪律）。

## 2. 目录与分层约定

```
server/routers/   新接口入口：定义 Pydantic schema → 校验/鉴权依赖 → 调 service
src/services/     业务逻辑：对话、存储、SSE、任务、推荐……
src/repositories/ 数据访问：一个仓储一个表域（会话/审计/任务…），封装 SQLAlchemy
src/storage/postgres/models_business.py  所有业务表模型唯一出处
```

规则：

- **路由层禁止写业务逻辑**；字段级 schema 放路由文件内 Pydantic 类。
- service 之间允许互相调用，但**不反向 import 路由层**。
- 新表必须先在 `models_business.py` 定义（`__tablename__` 命名蛇形复数），
  启动时 `create_business_tables` 自动建表；删改列需给迁移（当前无迁移框架，
  小改动用幂等 SQL 或直接重启建表，破坏性变更需团队评审）。
- 新工具/执行器先看是否已有注册机制（`tool_registry.py`、task_executors 目录）。

## 3. 新增一个 HTTP 接口（标准步骤）

1. 在 `server/routers/` 对应文件加端点（新域则新建 router 并注册到
   `server/main.py` 的 include_router 区）。
2. 鉴权依赖按敏感度选 `get_required_user` / `get_current_user` /
   `get_admin_user`（`server/utils/auth_middleware.py`）——别用错层级。
3. 涉及对话/消息写入：遵循存储文档的时序（PG 先落 try → bridge 镜像 try）。
4. 同步更新 `docs/api/` 对应文档（改 SSE 事件还要改
   `src/services/sse_protocol.py` 枚举与前端 switch）。
5. 验证：curl + 日志 + 数据落库核对；测试数据用完即清。

## 4. 编码规范

- **导入**：`from src.…` / `from server.…`；禁止 `ShoppingClaw.*` 前缀、
  禁止顶层 `agents/deepagents` import（死代码）。
- **时间**：入库一律 `datetime.now(timezone.utc).isoformat()`。
- **日志**：loguru（`src/utils/logging_config.py`），落盘
  `saves/logs/`（轮转保留）；业务模块 `logger = logging.getLogger(__name__)`
  亦可（已桥接）。请求级 request_id 自动注入日志。
- **异步**：请求处理全 async；CPU 重活/同步 SDK 用 `asyncio.to_thread`。
- **Redis**：见存储文档第 5 节三条合法路径；业务代码不许裸建 redis 客户端。
- **异常**：业务错误 raise `HTTPException(status, detail=中文可读)`；
  服务层异常向上抛由路由层转 500（detail 含原因），
  兜底路径要 try 住避免二次抛异常（参考 chat_stream_service 各保存点）。
- 命名：函数/变量 snake_case；API 路径小写连字符；类 PascalCase。

## 5. 改动风险对照

| 改动 | 额外要求 |
| --- | --- |
| 改 conversations/messages 结构 | 读存储文档；兼容无 timestamp 旧数据；前端顺序渲染不受影响 |
| 改 SSE 事件 | 同步 sse_protocol.py 枚举、前端 AgentChatComponent.vue、docs/api/chat.md |
| 改 Redis 访问 | 必须走桥接/缓存封装，禁止跨 loop |
| 删用户/线程 | 注意外键（operation_logs）与类型（varchar vs int）问题，见故障手册 |
| 加依赖 | `pyproject.toml`（uv sync 锁 uv.lock）；容器内需 `docker compose up -d --build` |

## 6. 测试与验证

- 仓库无强制 CI；改动后至少完成：import 检查（容器内
  `python -c "import server.main"`）+ 目标接口端到端 curl + 日志无 traceback。
- 涉及存储/鉴权/SSE 的三类改动做数据核对：
  PG（`psql` 查 conversations/task_records）与 Redis（`keys thread:*`）。
- 临时验证脚本用完即删，别留在 test/ 污染仓库。
