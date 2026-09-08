# ShoppingClaw

**智能购物助手** —— 基于 LangGraph 多智能体编排的电商决策引擎。

用户以自然语言提出购物需求（比价、找券、查库存、商品对比、价格监控），
系统通过主 Agent 调度 Researcher / Critic / Analyst 等子 Agent 与工具链，
最终输出带依据的结构化决策与推荐。

## 核心特性

- 🤖 **多 Agent 协作**：Master Agent 作为决策大脑，子 Agent 以 LangChain Tool 形式被 `SubAgentMiddleware` 调度（ReAct 循环 + Information Gap 驱动的动态路由）
- 🔍 **京东电商工具链**：JD SDK 直接集成于 `@tool`（商品搜索 / 详情 / 价格）
- 🛍 **多平台 MCP**：本地 stdio MCP 接入淘宝联盟 / 多多进宝（sinataoke_cn）
- ⚡ **SSE 流式协议**：打字机文本 + 思考过程（thinking）+ 工具调用（tool_call）全链路可视化
- 💾 **双存储架构**：PostgreSQL 为主真相存储（会话消息 JSONB 事件溯源），Redis 为影子/加速层，桥接层全容错降级（详见 [存储架构](docs/architecture/storage.md)）
- 🔐 **用户体系**：JWT 认证、管理员首启初始化、操作审计日志、滑动窗口限流
- ⏱ **定时任务**：价格 / 库存 / 优惠券 / 排名 / 店铺监控（cron / interval）
- 🧠 **智能扩展**：知识库（Chroma RAG）、意图识别、商品对比、个性化推荐、用户长期记忆
- 🐳 **一键部署**：docker compose 编排 API + PostgreSQL + Redis

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.12 · FastAPI · LangGraph/LangChain · uv |
| 前端 | Vue 3 · Vite · Ant Design Vue · ECharts · G6 |
| 存储 | PostgreSQL 16（JSONB） · Redis 7 · Chroma（本地知识库） |
| 部署 | Docker Compose · Nginx 反代 |

## 快速开始

前置：Docker Engine + Docker Compose，以及可用的 LLM API Key（SiliconFlow 等，写入 `.env`）。

```bash
cp .env.template .env        # 填写 API Keys
docker compose up -d         # 启动 api + postgres + redis
docker compose ps            # 等待 api healthy
```

- API 文档：http://localhost:5050/docs
- 健康检查：http://localhost:5050/api/system/health
- 首次启动：调用 `POST /api/auth/initialize` 创建管理员（见 [快速开始](docs/intro/quick-start.md)）

前端开发：

```bash
cd web-v2
npm ci && npm run dev        # http://localhost:5173（/api 代理到 5050）
```

## 项目结构

```text
ShoppingClaw/
├── README.md · ARCHITECTURE.md · CONTRIBUTING.md · AGENTS.md
├── docker-compose.yml        # 开发/单机编排（api + postgres + redis）
├── docker-compose.prod.yml   # 生产编排（构建镜像，不挂载源码）
├── docker/                   # api.Dockerfile · 镜像保存/拉取脚本 · MCP shim
├── server/                   # FastAPI 服务端
│   ├── main.py               # 应用入口（lifespan：DB/Redis 预热、调度器、清理）
│   ├── routers/              # API 路由：auth / chat / models / tasks
│   ├── middleware/           # 请求 ID、审计日志、限流
│   └── utils/                # 认证依赖（get_required_user / get_current_user 等）
├── src/                      # 核心 Python 包（以 src.* 导入，容器挂载 /app/src）
│   ├── agents/               # Agent 系统：common / master_agent / subagents
│   ├── services/             # 业务服务（SSE、对话流、存储桥接、记忆、任务执行器、MCP）
│   ├── repositories/         # PostgreSQL 仓储（conversation、operation_log …）
│   ├── storage/              # DB 会话、业务模型（SQLAlchemy 表定义）
│   ├── knowledge/            # 知识库（Chroma RAG）
│   ├── config/ · models/ · utils/ · plugins/ · jd/
├── web-v2/                   # Vue 3 前端
├── scripts/                  # 运维/初始化脚本（init.sh、pull_image.sh 等）
├── docs/                     # 📚 团队文档（从此处开始阅读）
├── test/                     # 测试与调试脚本
├── saves/                    # 运行时数据（users.json、日志、Chroma，已 gitignore）
└── models/                   # 本地模型权重（运行时挂载）
```

## 文档导航

| 读者 | 入口 |
| --- | --- |
| 新成员，先看哪里？ | [docs/index.md](docs/index.md)（文档总导航） |
| 系统是怎么设计的？ | [ARCHITECTURE.md](ARCHITECTURE.md) |
| 怎么跑起来？ | [快速开始](docs/intro/quick-start.md) |
| 数据怎么存？ | [存储与持久化](docs/architecture/storage.md) |
| 接口怎么调？ | [API 约定](docs/api/index.md) · [对话接口](docs/api/chat.md) |
| 怎么改代码？ | [后端指南](docs/development/backend-guide.md) · [前端指南](docs/development/frontend-guide.md) |
| 怎么上线 / 排障？ | [部署运维](docs/operations/deployment.md) · [故障手册](docs/operations/troubleshooting.md) |
| 怎么参与贡献？ | [CONTRIBUTING.md](CONTRIBUTING.md) |

## 开发速查

```bash
docker compose up -d                     # 启动全栈（代码热重载：server/src 已挂载）
docker compose logs -f api               # 看 API 日志
sudo docker compose restart api          # 改挂载/compose 后重启
curl http://localhost:5050/api/system/health   # 健康检查
cd web-v2 && npm run dev                 # 前端开发（VITE_API_URL 可覆盖后端地址）
```

## 许可与致谢

实现参考了 DeepAgents（Agent 中间件/沙盒）、ScienceClaw（SSE 事件协议）等开源项目；
MCP 生态基于 sinataoke_cn（淘宝联盟/多多进宝）。
