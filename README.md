# ShoppingClaw

Deep Agents Shopping Agent - 智能购物助手

## 项目简介

基于 LangGraph + deepagents 框架的多 Agent 智能购物平台，通过多 Agent 协作实现跨平台商品搜索、数据分析和个性化推荐。

## 核心特性

- 🤖 **多 Agent 协作系统**：MainAgent 协调 Research/Analysis/Recommendation 子 Agent
- 🔍 **跨平台商品搜索**：京东、淘宝、拼多多一站式搜索
- 📊 **智能数据分析**：价格对比、趋势分析、参数提取
- 💡 **AI 驱动推荐**：基于用户画像和协同过滤的个性化推荐
- 🖥️ **浏览器自动化**：集成 Playwright/Selenium 网页爬取能力
- 💾 **持久化记忆**：基于文件系统和数据库的长期记忆存储

## 项目结构（实际）

```
ShoppingClaw/
├── app/                          # FastAPI 应用入口
│   ├── main.py                   # FastAPI 主应用
│   └── web/
│       └── streamlit_app.py      # Streamlit Web 界面
│
├── agents/                       # 顶层 Agent 定义（已实现）
│   ├── main_agent.py             # 主 Agent（协调器）
│   ├── research_agent.py         # 研究 Agent（商品搜集）
│   ├── analysis_agent.py         # 分析 Agent（数据分析）
│   └── recommendation_agent.py   # 推荐 Agent（个性化推荐）
│
├── src/                          # 核心业务逻辑层
│   ├── agents/                   # Agent 底层框架
│   │   ├── common/               # 公共基类
│   │   │   ├── base.py           # BaseAgent 抽象基类
│   │   │   └── context.py        # BaseContext 上下文
│   │   ├── graph.py              # Agent 图构建（34KB 核心代码）
│   │   ├── agent_demo.py         # Agent 示例
│   │   └── BASE_PROMPT.md        # 基础提示词
│   │
│   ├── services/                 # 业务服务层
│   │   ├── chat_stream_service.py # 流式对话服务
│   │   └── agent_run_service.py  # Agent 运行服务
│   │
│   ├── model/                    # LLM 模型封装
│   │   └── __init__.py
│   │
│   ├── config/                   # 配置管理
│   │   └── __init__.py
│   │
│   └── utils/                    # 工具函数
│       ├── infra/                # 基础设施
│       │   ├── agent_factory.py  # Agent 工厂（单例模式）
│       │   ├── config.py         # 配置管理
│       │   └── llm_provider.py   # LLM 提供者
│       └── __init__.py
│
├── deepagents/                   # deepagents 框架封装
│   ├── backends/                 # 后端抽象层
│   │   ├── protocol.py           # Backend 协议定义
│   │   ├── state.py              # StateBackend 实现
│   │   └── utils.py              # 工具函数
│   │
│   ├── middlleware/              # 中间件系统
│   │   ├── filesystem.py         # 文件系统中间件
│   │   ├── memory.py             # 记忆中间件
│   │   ├── skills.py             # Skills 中间件
│   │   ├── subagent.py           # 子 Agent 中间件
│   │   ├── summarization.py      # 摘要压缩中间件
│   │   └── patch_tool_calls.py   # 工具调用补丁
│   │
│   └── graph.py                  # Agent 图构建主逻辑
│
├── server/                       # 服务端（待完善）
│   ├── routers/                  # API 路由
│   │   ├── __init__.py
│   │   └── chat_router.py        # 对话接口
│   │
│   ├── utils/                    # 服务端工具
│   │   └── lifespan.py           # 生命周期管理
│   │
│   └── main.py                   # 服务端入口
│
├── scrapers/                     # 电商爬虫（待实现）
│   ├── jd_scraper.py             # 京东爬虫
│   ├── taobao_scraper.py         # 淘宝爬虫
│   └── pdd_scraper.py            # 拼多多爬虫
│
├── tools/                        # Agent 工具（待实现）
│   ├── search_tools.py           # 搜索工具
│   ├── analysis_tools.py         # 分析工具
│   ├── compare_tools.py          # 对比工具
│   └── memory_tools.py           # 记忆工具
│
├── computer/                     # OpenClaw 能力（待实现）
│   ├── browser_controller.py     # 浏览器控制器
│   └── desktop_controller.py     # 桌面控制器
│
├── middleware/                   # 自定义中间件（待实现）
│   ├── logging.py                # 日志中间件
│   └── retry.py                  # 重试中间件
│
├── workspace/                    # Agent 工作空间（文件系统）
│   └── AGENT.md                  # Agent 配置文件
│
├── tests/                        # 测试用例（待完善）
│
├── .env                          # 环境变量配置
├── requirements.txt              # Python 依赖
├── setup.py                      # 安装脚本
├── langgraph.json                # LangGraph 配置
├── main.py                       # 根目录入口（简单示例）
└── README.md                     # 项目说明
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 到 `.env` 并配置：

```bash
# LLM 配置（Ollama 本地部署）
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_MODEL=qwen2.5:3b

# 数据库配置
POSTGRES_URL=postgresql+asyncpg://user:pass@localhost:5432/shopping_claw
REDIS_URL=redis://localhost:6379/0
```

### 3. 运行 Agent（独立模式）

```bash
cd agents
python main_agent.py
```

### 4. 运行 API 服务

```bash
uvicorn app.main:app --reload
```

### 5. 运行 Web 界面

```bash
cd app/web
streamlit run streamlit_app.py
```

## 技术架构

### 核心技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| **Web 框架** | FastAPI 0.135+ | 高性能异步 API |
| **Agent 框架** | LangGraph 1.2+ / deepagents | 状态机和工作流引擎 |
| **LLM 模型** | Ollama (Qwen/DeepSeek) | 本地大模型推理 |
| **数据库** | PostgreSQL / SQLite | 业务数据存储 |
| **缓存** | Redis | 任务队列和缓存 |
| **浏览器** | Playwright / Selenium | 网页爬虫和控制 |
| **前端原型** | Streamlit | 快速原型验证 |

### Agent 架构图

```
┌─────────────────────────────────────────┐
│         MainAgent (协调器)               │
│  - TodoListMiddleware                   │
│  - MemoryMiddleware                     │
│  - SkillsMiddleware                     │
│  - FilesystemMiddleware                 │
│  - SubAgentMiddleware ← 管理子 Agent     │
│  - SummarizationMiddleware              │
└──────────────┬──────────────────────────┘
               │
    ┌──────────┼──────────┬──────────────┐
    │          │          │              │
    ▼          ▼          ▼              ▼
Research  Analysis  Recommendation  Custom
 Agent      Agent       Agent         Agent
(商品搜集)  (数据分析)  (个性化推荐)   (扩展)
```

## 开发进度

### ✅ 已完成
- [x] 项目框架搭建
- [x] MainAgent 基础实现
- [x] deepagents 中间件集成
- [x] LangGraph Checkpointer 状态管理
- [x] 流式对话基础架构

### 🚧 进行中
- [ ] ResearchAgent 实现（商品搜索）
- [ ] AnalysisAgent 实现（数据分析）
- [ ] RecommendationAgent 实现（个性化推荐）
- [ ] 电商爬虫系统（JD/Taobao/PDD）
- [ ] API 路由完善

### 📋 计划中
- [ ] 浏览器自动化（Playwright）
- [ ] 工具系统（搜索/分析/对比）
- [ ] 用户偏好记忆
- [ ] Streamlit 前端界面
- [ ] Docker 容器化部署

## 开发指南

详细开发文档请参考：[SHOPPING_CLAW_DEV_GUIDE.md](./SHOPPING_CLAW_DEV_GUIDE.md)

## License

MIT License
