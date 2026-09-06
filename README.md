# ShoppingClaw

Shopping Agent — 智能购物助手

## 项目简介

基于 LangGraph 框架的多 Agent 电商智能消费决策平台，通过主 Agent 协调 Research/Critic/Analyst 等多个子 Agent 协作，实现商品搜索、智能数据分析和个性化推荐。前端采用 Vue 3 + Ant Design Vue，后端基于 FastAPI 提供 SSE 流式响应。

## 核心特性

- 🤖 **多 Agent 协作系统**：Master Agent 通过 SubAgentMiddleware 协调 Researcher/Critic/Analyst/Memory 子 Agent
- 🔍 **京东商品搜索**：集成 JD SDK（234 个 REST API），支持商品搜索、详情查询等
- 📊 **SSE 流式响应**：自研 SSE 协议（sse_adapter/sse_protocol/sse_session_manager），支持打字机效果
- 💬 **思考过程可视化**：ThinkingProcessSidebar 实时展示 Agent 推理链路与工具调用
- 💾 **双存储架构**：PostgreSQL（Checkpointer + 业务数据）+ Redis（消息存储 / 速率限制 / 商品缓存）
- 🔐 **用户认证**：JWT 登录注册，审计日志中间件
- 🐳 **Docker 一键部署**：docker-compose 编排 API + PostgreSQL + Redis 三服务

## 实际项目结构

```
ShoppingClaw/
├── server/                         # FastAPI 服务端
│   ├── main.py                     # 应用入口（lifespan 管理）
│   ├── routers/
│   │   ├── chat_rounter.py         # 对话接口（SSE 流式 + 速率限制）
│   │   ├── auth_router.py          # 用户认证（JWT 注册/登录）
│   │   └── models_router.py        # 模型管理接口
│   ├── middleware/
│   │   ├── rate_limiter.py         # 滑动窗口速率限制（Redis）
│   │   └── audit.py                # 审计日志中间件
│   └── utils/                      # 服务端工具（lifespan 等）
│
├── src/                            # 核心业务逻辑
│   ├── agents/
│   │   ├── master_agent/           # 主 Agent
│   │   │   ├── factory.py          # create_main_agent 核心工厂 (66KB)
│   │   │   ├── graph.py            # 决策图扩展（Gap Detector + 条件路由）
│   │   │   ├── context.py          # DecisionState 显式决策状态
│   │   │   ├── agent_demo.py       # Agent 使用示例
│   │   │   └── BASE_PROMPT.md      # 基础提示词模板
│   │   ├── subagents/              # 子 Agent 定义
│   │   │   ├── subagents.yaml      # 子 Agent 配置（15KB）
│   │   │   └── factory.py          # 子 Agent 工厂
│   │   └── common/                 # 公共模块
│   │       ├── base.py             # BaseAgent 抽象基类
│   │       ├── context.py          # BaseContext 上下文
│   │       ├── toolkits/           # 工具包系统
│   │       │   ├── research/       # 研报搜索工具（JD 商品搜索等）
│   │       │   ├── critic/         # 评估反馈工具
│   │       │   ├── analyst/        # 数据分析工具
│   │       │   ├── memory/         # 记忆存储工具
│   │       │   ├── buildin/        # 内置通用工具
│   │       │   └── registry.py     # 工具注册中心
│   │       ├── middleware/         # 中间件系统
│   │       ├── backends/           # 后端抽象层
│   │       └── model/              # LLM 模型封装
│   │
│   ├── services/                   # 业务服务层
│   │   ├── chat_stream_service.py  # 流式对话服务 (40KB)
│   │   ├── redis_store.py          # Redis 消息存储 + MemoryStore 桥接
│   │   ├── redis_cache.py          # Redis 缓存管理
│   │   ├── cache_decorator.py      # @redis_cache 装饰器（SHA256 键值）
│   │   ├── sse_adapter.py          # SSE 协议适配器
│   │   ├── sse_protocol.py         # SSE 协议定义
│   │   ├── sse_session_manager.py  # SSE 会话生命周期管理
│   │   ├── intent_service.py       # 意图识别服务（JointBERT）
│   │   ├── joint_intent_model.py   # JointBERT 模型封装
│   │   ├── conversation_service.py # 对话管理
│   │   ├── history_manager.py      # 历史记录管理
│   │   ├── tool_registry.py        # 工具动态注册
│   │   ├── mcp_service.py          # MCP 服务集成
│   │   └── gap/                    # Gap Detector (LightGBM 模型)
│   │
│   ├── jd/                         # 京东 SDK 集成
│   │   ├── api/                    # JD API 封装
│   │   │   ├── base.py             # API 基类
│   │   │   └── rest/               # 234 个 REST API 接口
│   │   └── security/               # 加密/解密模块
│   │
│   ├── knowledge/                  # RAG 知识库（LlamaIndex）
│   │   ├── manager.py              # 知识管理器（对外统一接口）
│   │   ├── llama/                  # LlamaIndex 集成层
│   │   │   ├── embedding.py        # DashScope Embedding 工厂
│   │   │   ├── loader.py           # Markdown 加载 + frontmatter 解析
│   │   │   ├── indexer.py          # LlamaIndex 索引 + ChromaDB 持久化
│   │   │   └── retriever.py        # MetadataFilters 语义检索
│   │   ├── core/models.py          # KnowledgeItem / SourceType 数据结构
│   │   ├── fusion/                 # 结果融合排序
│   │   └── lifecycle/              # 检索遥测（EvalMonitor）
│   │
│   ├── repositories/               # 数据访问层
│   │   ├── conversation_repository.py
│   │   ├── agent_config_repository.py
│   │   ├── user_repository.py
│   │   ├── skill_repository.py
│   │   └── ...
│   │
│   ├── plugins/                    # 插件系统
│   ├── storage/                    # PostgreSQL 存储管理
│   ├── config/                     # 配置管理
│   ├── models/                     # ML 模型定义
│   └── utils/                      # 工具函数
│
├── web-v2/                         # Vue 3 前端
│   ├── src/
│   │   ├── views/                  # 页面
│   │   │   ├── HomeView.vue        # 首页
│   │   │   ├── LoginView.vue       # 登录页
│   │   │   ├── AgentView.vue       # Agent 对话页
│   │   │   └── TestProductCard.vue # 商品卡片测试
│   │   ├── components/             # 组件
│   │   │   ├── AgentChatComponent.vue    # 对话核心组件 (45KB)
│   │   │   ├── ThinkingProcessSidebar.vue # 思考过程侧边栏
│   │   │   ├── AgentFlowPanel.vue        # Agent 流程面板
│   │   │   ├── ToolCallCard.vue          # 工具调用卡片
│   │   │   ├── MarkdownContentViewer.vue  # Markdown 渲染
│   │   │   ├── ChatSidebarComponent.vue  # 对话列表
│   │   │   └── AgentMessageComponent.vue # 消息组件
│   │   ├── stores/                 # Pinia 状态管理
│   │   ├── apis/                   # API 调用层
│   │   ├── router/                 # Vue Router
│   │   └── utils/                  # 前端工具函数
│   ├── package.json                # pnpm 依赖 (Vue 3 + AntDV + ECharts)
│   └── vite.config.js
│
├── deepagents/                     # deepagents 框架封装
│   ├── backends/                   # Backend 抽象（protocol/state/utils）
│   ├── middlleware/                # 中间件系统（6 个中间件）
│   └── graph.py                    # Agent 图构建主逻辑
│
├── docker/                         # Docker 配置
│   ├── api.Dockerfile              # API 镜像
│   ├── volumes/                    # 数据持久化
│   ├── pull_image.ps1 / .sh        # 镜像拉取脚本
│   └── save_docker_images.ps1 / .sh # 镜像导出脚本
│
├── scripts/                        # 工具脚本
│   ├── init.ps1 / init.sh          # 项目初始化
│   ├── train_intent_bert.py        # JointBERT 训练
│   ├── train_gap_detector.py       # Gap Detector 训练
│   └── ...
│
├── model/                          # 训练好的模型文件
├── saves/                          # 运行时数据（配置/知识库/用户）
├── docker-compose.yml              # 开发环境编排
├── docker-compose.prod.yml         # 生产环境编排
├── langgraph.json                  # LangGraph 配置
├── pyproject.toml                  # UV 依赖管理
└── .env.template                   # 环境变量模板
```

## 快速开始

### 方式一：Docker Compose（推荐）

**前置要求**：Docker Desktop + Ollama

```powershell
# 1. 克隆项目
git clone <repository-url> && cd ShoppingClaw

# 2. 配置环境变量
cp .env.template .env
# 编辑 .env，确保 OLLAMA_BASE_URL=http://host.docker.internal:11434

# 3. 拉取 Ollama 模型
ollama pull qwen2.5:3b

# 4. 一键启动（API + PostgreSQL + Redis）
docker-compose up -d

# 5. 查看日志
docker-compose logs -f api
```

访问：
- API: http://localhost:5050
- API 文档: http://localhost:5050/docs

### 方式二：本地开发

**前置要求**：Python 3.12+、UV、PostgreSQL 16+、Redis 7+、Ollama

```bash
# 1. 安装 UV
pip install uv

# 2. 创建虚拟环境并安装依赖
uv sync

# 3. 配置环境变量
cp .env.template .env

# 4. 启动基础设施
docker-compose up -d postgres redis

# 5. 启动 API（热重载）
uv run uvicorn server.main:app --reload --port 5050
```

### 启动前端

```bash
cd web-v2
pnpm install
pnpm dev          # → http://localhost:5173
```

## 技术架构

### 核心技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| **Web 框架** | FastAPI 0.121+ | 高性能异步 API + SSE 流式 |
| **Agent 框架** | LangGraph 1.0+ / deepagents 0.2.5+ | 状态机工作流引擎 |
| **LLM** | Ollama (Qwen/DeepSeek) | 本地大模型推理 |
| **前端** | Vue 3.5 + Vite 7 + Ant Design Vue 4 | 现代 SPA 界面 |
| **状态管理** | Pinia 3 | 前端状态管理 |
| **可视化** | ECharts 6 + AntV G6 + D3 | 图表与流程图 |
| **数据库** | PostgreSQL 16 (asyncpg) | Checkpointer + 业务数据 |
| **缓存** | Redis 7 (redis-py 5.2+) | 消息存储 / 速率限制 / API 缓存 |
| **JWT 认证** | python-jose + passlib | 用户认证 |
| **ML 模型** | JointBERT + LightGBM | 意图识别 + Gap 检测 |
| **知识库** | LlamaIndex + ChromaDB + DashScope Embedding | RAG 检索（metadata 过滤 + 融合排序） |

### Agent 架构

```
┌──────────────────────────────────────────────────┐
│              Master Agent (协调器)                │
│  ┌────────────────────────────────────────────┐  │
│  │  DecisionState                             │  │
│  │  - intent / constraints / evidence_log     │  │
│  │  - information_gaps / confidence_score     │  │
│  │  - decision_path（决策链路追踪）             │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  Middleware Chain:                               │
│  TodoList → Filesystem → Memory → Skills         │
│  → SubAgent → Summarization → PatchToolCalls     │
│                                                  │
│  Gap Detector Node ──── ML 模型置信度评估 ────── │
└──────────────────┬───────────────────────────────┘
                   │ tool_calls
    ┌──────────────┼──────────────┬──────────────┐
    ▼              ▼              ▼              ▼
Researcher      Critic        Analyst        Memory
(商品搜索)     (质量评估)     (数据分析)     (记忆存取)
```

### 数据流

```
Vue 3 前端 ──HTTP POST──▶ FastAPI ──▶ chat_stream_service
                                  ▶ Master Agent (LangGraph)
                                      ▶ SubAgentMiddleware
                                          ▶ Researcher (JD SDK)
                                          ▶ Critic (评估反馈)
                                          ▶ Analyst (数据对比)
                                  ◀ SSE Stream (打字机效果)
◀── SSE (text/event-stream) ── 前端渲染 Markdown + 工具卡片
```

## 开发进度

### ✅ 已完成

- [x] 项目框架搭建（FastAPI + LangGraph + deepagents）
- [x] Master Agent 实现（DecisionState + Gap Detector + 条件路由）
- [x] 子 Agent 系统（Researcher / Critic / Analyst / Memory）
- [x] 工具包系统（research / critic / analyst / memory / buildin 五大工具包）
- [x] JD SDK 集成（234 个 REST API + 加密安全模块）
- [x] SSE 流式响应（自研协议 + 会话管理 + 适配器）
- [x] LangGraph Checkpointer（PostgreSQL + SQLite 双后端）
- [x] Redis 三优先应用（消息存储 / 滑动窗口速率限制 / API 缓存装饰器）
- [x] 知识库系统（LlamaIndex + ChromaDB + DashScope Embedding，metadata 过滤检索）
- [x] Vue 3 前端（Agent 对话 / 思考过程可视化 / 工具调用卡片 / Markdown 渲染）
- [x] JWT 用户认证（注册 / 登录 / 审计日志）
- [x] Docker 容器化部署（API + PostgreSQL + Redis）
- [x] MCP 服务集成
- [x] 商品推荐业务功能开发

### 🚧 进行中

- [ ] 前端增强（首页产品卡片、用户偏好设置）
- [ ] RAG 检索增强（reranker、混合检索、语义缓存）
- [ ] Agent 流程面板可视化增强
- [ ] 多轮对话中断恢复优化
- [ ] LightGBM Gap Detector 模型和JointBERT 意图识别模型（多标签分类 + 置信度）适配


### 📋 计划中

- [ ] 商品对比功能前端落地
- [ ] 个性化推荐算法
- [ ] 语音输入支持
- [ ] 移动端适配

## 开发指南

| 文档 | 说明 |
|------|------|
| [Agent 设计原则](docs/AGENT_DESIGN_PRINCIPLES.md) | Master Agent 架构、DecisionState、条件路由设计 |
| [Docker 部署指南](docs/DOCKER_DEPLOYMENT.md) | Docker Compose 部署、环境配置、常见问题 |
| [开发文档](docs/SHOPPING_CLAW_DEV_GUIDE.md) | 项目总览、模块设计、API 规范 |

## API 概览

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/chat/agent/{agent_id}` | POST | SSE 流式对话 |
| `/api/chat/history/{thread_id}` | GET | 获取对话历史 |
| `/api/chat/conversations` | GET | 对话列表 |
| `/api/chat/rate-limit-status` | GET | 速率限制状态 |
| `/api/auth/login` | POST | 用户登录 |
| `/api/auth/register` | POST | 用户注册 |
| `/api/models/list` | GET | 可用模型列表 |
| `/api/system/health` | GET | 健康检查 |

## License

MIT License
