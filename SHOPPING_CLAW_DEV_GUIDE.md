# ShoppingClaw - 智能购物 Agent 平台开发文档

**文档版本**：v1.1  
**编制日期**：2026-04-01  
**适用范围**：基于 LangGraph + deepagents 的多 Agent 电商购物助手开发  

---

## 目录

1. [项目概述](#1-项目概述)  
2. [技术架构](#2-技术架构)  
3. [开发规范](#3-开发规范)  
4. [核心模块设计](#4-核心模块设计)  
5. [接口设计规范](#5-接口设计规范)  
6. [数据模型设计](#6-数据模型设计)  
7. [部署与运维](#7-部署与运维)  
8. [附录](#8-附录)  

---

## 1. 项目概述

### 1.1 项目背景

本项目旨在构建一个基于 **LangGraph + deepagents** 框架的智能购物助手平台，通过多 Agent 协作系统实现跨平台商品搜索、智能数据分析、个性化推荐等功能。平台采用前后端分离架构，专注于 Agent 原生能力开发，不依赖传统的 RAG 检索增强生成技术。

### 1.2 核心目标

- **多 Agent 协作**：支持主 Agent 协调研究、分析、推荐等多个子 Agent 协同工作
- **工具扩展性**：提供标准化的工具开发框架，支持电商爬虫、数据分析等自定义工具
- **浏览器自动化**：集成 OpenClaw 能力，支持浏览器控制和桌面操作
- **持久化记忆**：基于文件系统和数据库的记忆存储机制
- **流式响应**：实时的对话流式输出，提升用户体验
- **生产可靠**：完整的错误处理、日志记录、中间件机制

### 1.3 术语定义

| 术语 | 定义 |
|------|------|
| Agent | 基于大语言模型的智能代理，具备推理、规划、工具使用能力 |
| MainAgent | 主智能体，负责协调各个子 Agent 的工作流 |
| SubAgent | 子智能体（如 ResearchAgent、AnalysisAgent、RecommendationAgent） |
| Thread | 对话线程，用于维护多轮对话的上下文 |
| Checkpointer | LangGraph 的状态持久化组件，存储每个 Thread 的历史消息 |
| Middleware | LangGraph 中间件，用于扩展 Agent 的行为和能力 |
| Backend | deepagents 的后端抽象层，提供文件系统和数据存储接口 |
| Skill | Agent 的技能包，通过中间件注入特定能力 |

---

## 2. 技术架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                     前端层 (Streamlit / Vue 3)               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │ 对话界面  │  │ 商品展示  │  │ 数据可视化 │                  │
│  └──────────┘  └──────────┘  └──────────┘                  │
└─────────────────────────────────────────────────────────────┘
                          ↓ HTTPS
┌─────────────────────────────────────────────────────────────┐
│                   API 网关层 (FastAPI)                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 中间件：CORS / Auth / RateLimit / AccessLog         │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 路由层：/chat /agent /search /analyze /recommend   │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                  业务服务层 (Services)                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ ChatSvc  │  │SearchSvc │  │Analysis  │  │Recommend │   │
│  │          │  │          │  │  Service │  │  Service │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│              智能体层 (LangGraph + deepagents)               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ MainAgent (协调器，管理所有子 Agent)                 │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │Research  │  │Analysis  │  │Recommend │  │Custom    │   │
│  │  Agent   │  │  Agent   │  │  Agent   │  │  Agent   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│                                                              │
│  中间件链：Filesystem → Memory → Skills → SubAgents       │
│            → Summarization → PatchToolCalls                │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                   数据存储层                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │PostgreSQL│  │  MinIO   │  │  Redis   │                  │
│  │(业务数据)│  │(文件存储)│  │(缓存)    │                  │
│  └──────────┘  └──────────┘  └──────────┘                  │
│  ┌──────────┐  ┌──────────┐                                │
│  │Checkpoint│  │  Browser │                                │
│  │(状态持久化)│  │(浏览器控制)│                               │
│  └──────────┘  └──────────┘                                │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 核心技术栈

#### 后端技术栈
| 组件 | 技术选型 | 版本 | 用途 |
|------|---------|------|------|
| Web 框架 | FastAPI | 0.135+ | 高性能异步 API |
| Agent 框架 | LangGraph + deepagents | 1.2+ / 1.1+ | 状态机和工作流引擎 |
| LLM 模型 | Ollama (DeepSeek/Qwen) | Latest | 本地大模型推理 |
| 主数据库 | PostgreSQL / SQLite | 16 / 3.x | 业务数据存储 |
| 缓存 | Redis | 7 | 任务队列和缓存 |
| 对象存储 | MinIO / 文件系统 | Latest | 文件存储 |
| 浏览器自动化 | Playwright / Selenium | 1.40+ / 4.15+ | 网页爬虫和控制 |
| HTTP 客户端 | httpx / aiohttp | 0.25+ / 3.9+ | 异步 HTTP 请求 |

#### 前端技术栈
| 组件 | 技术选型 | 版本 |
|------|---------|------|
| 快速原型 | Streamlit | 1.28+ |
| 生产前端 | Vue 3 + Vite | 3.5+ / 7.3+ |
| UI 库 | Ant Design Vue | 4.2+ |
| 状态管理 | Pinia | 3.0+ |
| 可视化 | ECharts | Latest |

### 2.3 实际项目结构

```
ShoppingClaw/
├── app/                          # FastAPI 应用入口
│   ├── main.py                   # FastAPI 主应用（已实现基础路由）
│   └── web/
│       └── streamlit_app.py      # Streamlit Web 界面（待完善）
│
├── agents/                       # 顶层 Agent 定义（核心实现层）
│   ├── main_agent.py             # 主 Agent（协调器，已实现）
│   ├── research_agent.py         # 研究 Agent（商品搜集，待完善）
│   ├── analysis_agent.py         # 分析 Agent（数据分析，待完善）
│   └── recommendation_agent.py   # 推荐 Agent（个性化推荐，待完善）
│
├── src/                          # 核心业务逻辑层（框架层）
│   ├── agents/                   # Agent 底层框架实现
│   │   ├── common/               # 公共基类
│   │   │   ├── base.py           # BaseAgent 抽象基类
│   │   │   └── context.py        # BaseContext 上下文定义
│   │   ├── graph.py              # Agent 图构建（34KB 核心代码，LangGraph 深度定制）
│   │   ├── agent_demo.py         # Agent 使用示例
│   │   └── BASE_PROMPT.md        # Agent 基础提示词模板
│   │
│   ├── services/                 # 业务服务层
│   │   ├── chat_stream_service.py # 流式对话服务（SSE 流生成）
│   │   └── agent_run_service.py  # Agent 运行服务（任务管理）
│   │
│   ├── model/                    # LLM 模型封装
│   │   └── __init__.py           # 模型初始化和配置
│   │
│   ├── config/                   # 配置管理
│   │   └── __init__.py           # 全局配置加载
│   │
│   └── utils/                    # 工具函数
│       ├── infra/                # 基础设施封装
│       │   ├── agent_factory.py  # Agent 工厂（单例模式，自动发现）
│       │   ├── config.py         # 环境变量配置管理
│       │   └── llm_provider.py   # LLM 提供者（Ollama 封装）
│       └── __init__.py
│
├── deepagents/                   # deepagents 框架封装（核心中的核心）
│   ├── backends/                 # 后端抽象层
│   │   ├── protocol.py           # Backend 协议定义
│   │   ├── state.py              # StateBackend 实现（状态持久化）
│   │   └── utils.py              # 后端工具函数
│   │
│   ├── middlleware/              # 中间件系统（能力扩展层）
│   │   ├── filesystem.py         # 文件系统中间件（Agent 工作空间）
│   │   ├── memory.py             # 记忆中间件（长期记忆存储）
│   │   ├── skills.py             # Skills 中间件（技能包注入）
│   │   ├── subagent.py           # 子 Agent 中间件（子 Agent 调度）
│   │   ├── summarization.py      # 摘要压缩中间件（上下文压缩）
│   │   └── patch_tool_calls.py   # 工具调用补丁（兼容性修复）
│   │
│   └── graph.py                  # Agent 图构建主逻辑（create_main_agent）
│
├── server/                       # 服务端（待完善）
│   ├── routers/                  # API 路由层
│   │   ├── __init__.py
│   │   └── chat_router.py        # 对话接口（流式响应）
│   │
│   ├── utils/                    # 服务端工具
│   │   └── lifespan.py           # 生命周期管理（数据库连接等）
│   │
│   └── main.py                   # 服务端入口文件
│
├── scrapers/                     # 电商爬虫（待实现）
│   ├── jd_scraper.py             # 京东爬虫（Selenium/Playwright）
│   ├── taobao_scraper.py         # 淘宝爬虫
│   └── pdd_scraper.py            # 拼多多爬虫
│
├── tools/                        # Agent 工具（待实现）
│   ├── search_tools.py           # 搜索工具（ProductSearchTool）
│   ├── analysis_tools.py         # 分析工具（PriceComparisonTool）
│   ├── compare_tools.py          # 对比工具（ProductCompareTool）
│   └── memory_tools.py           # 记忆工具（用户偏好记录）
│
├── computer/                     # OpenClaw 能力（待实现）
│   ├── browser_controller.py     # 浏览器控制器（Playwright）
│   └── desktop_controller.py     # 桌面控制器（PyAutoGUI）
│
├── middleware/                   # 自定义中间件（待实现）
│   ├── logging.py                # 日志中间件（彩色日志）
│   └── retry.py                  # 重试中间件（请求重试）
│
├── workspace/                    # Agent 工作空间（文件系统持久化）
│   └── AGENT.md                  # Agent 配置文件（Skills/Memory 源）
│
├── tests/                        # 测试用例（待完善）
│
├── .env                          # 环境变量配置（敏感信息）
├── requirements.txt              # Python 依赖列表
├── setup.py                      # 安装脚本（可选）
├── langgraph.json                # LangGraph 配置文件
├── main.py                       # 根目录入口（简单示例，测试用）
└── README.md                     # 项目说明文档
```

---

## 3. 开发规范

### 3.1 代码规范

#### Python 代码规范
```python
# ✅ 推荐：类型注解 + 异步编程
async def create_agent_run_view(
    *,
    agent_id: str,
    query: str,
    config: dict,
    current_user_id: str,
    db: AsyncSession,
) -> dict:
    """创建 Agent 运行任务
    
    Args:
        agent_id: 智能体 ID
        query: 用户查询
        config: 配置信息（包含 thread_id）
        current_user_id: 当前用户 ID
        db: 数据库会话
        
    Returns:
        包含 run_id 和 stream_url 的字典
    """
    if not query:
        raise HTTPException(status_code=422, detail="query 不能为空")
    
    # 业务逻辑...
```

**关键要求**：
- 所有公共方法必须添加类型注解
- 异步方法使用 `async/await`
- 必须编写 Docstring（Google 风格）
- 异常处理要明确，不吞掉任何错误

### 3.2 命名规范

| 类型 | 命名规则 | 示例 |
|------|---------|------|
| 变量/函数 | camelCase | `handleSendMessage`, `threadState` |
| 组件名 | PascalCase | `AgentChatComponent.vue` |
| 文件名 | snake_case (后端) / kebab-case (前端) | `chat_router.py`, `agent-input.vue` |
| 常量 | UPPER_SNAKE_CASE | `RATE_LIMIT_MAX_ATTEMPTS` |
| 类名 | PascalCase | `ConversationRepository`, `BaseAgent` |

### 3.3 Git 提交规范

```bash
# 格式：<type>(<scope>): <subject>

# 示例
feat(search): 添加京东商品搜索功能
fix(agent): 修复中断后状态不同步问题
docs(readme): 更新开发文档
refactor(service): 重构流式响应生成逻辑
test(api): 添加对话接口的集成测试
```

**Type 类型**：
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档更新
- `style`: 代码格式调整
- `refactor`: 重构
- `test`: 测试相关
- `chore`: 构建/工具配置

---

## 4. 核心模块设计（基于现有代码）

### 4.1 Agent 模块设计

#### 4.1.1 MainAgent 实现解析

**文件位置**：`agents/main_agent.py`

```python
# agents/main_agent.py - 实际实现
class MainAgent:
    """主 Agent 类（已实现）"""
    
    def __init__(self, persistence: bool = False) -> None:
        """初始化主 Agent"""
        self._memory = ["./AGENT.md"]  # 记忆源（文件路径）
        self._skill = ["./skill"]      # 技能源（文件夹路径）
        self._tools = []               # 工具列表（待添加）
        self.persistence = persistence # 是否启用 Checkpointer 持久化
        self._subagents = self.load_subagents()  # 待实现
        self._backend = None
        self._agent = self.create_agent()
    
    def create_agent(self):
        """创建 Agent 实例（调用 deepagents/graph.py）"""
        config = {
            "model": "qwen2.5:3b",  # 使用 Ollama Qwen 模型
        }
        if self.persistence:
            from langgraph.checkpoint.memory import MemorySaver
            config["checkpointer"] = MemorySaver()
        
        # 调用 deepagents/graph.py 的 create_main_agent
        return create_main_agent(**config)
    
    def invoke(self, user_input: str, thread_id: str = "default"):
        """同步调用 Agent"""
        messages = {"messages": [HumanMessage(content=user_input)]}
        config = {"configurable": {"thread_id": thread_id}}
        result = self._agent.invoke(messages, config)
        return result
    
    def load_subagents(self):
        """加载子 Agent（TODO: 待实现）"""
        pass
```

**关键特性**：
- ✅ **单例模式**：通过 `src/utils/infra/agent_factory.py` 的 `get_agent()` 获取全局唯一实例
- ✅ **可配置持久化**：通过 `persistence` 参数控制是否使用 LangGraph Checkpointer
- ✅ **Ollama 本地模型**：默认使用 `qwen2.5:3b`，支持配置其他模型
- ⏳ **子 Agent 管理**：`load_subagents()` 方法待实现
- ⏳ **工具和技能**：`_tools` 和 `_skill` 已预留位置

#### 4.1.2 Agent 工厂（单例模式）

**文件位置**：`src/utils/infra/agent_factory.py`

```python
# src/utils/infra/agent_factory.py
from agents.main_agent import MainAgent

_agent_instance = None  # 全局单例


def get_agent() -> MainAgent | None:
    """获取 Agent 单例实例（懒汉式单例）"""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = MainAgent()
    
    return _agent_instance
```

**设计动机**：
1. **避免重复初始化**：Agent 初始化涉及模型加载、中间件构建等耗时操作
2. **共享状态**：多个请求可以共享同一个 Agent 实例的状态
3. **资源优化**：减少内存占用和模型加载时间

**使用方式**：
```python
# app/main.py 中使用
from src.utils.infra.agent_factory import get_agent

@app.post("/chat/agent/{agent_id}")
async def stream_agent_chat(...):
    agent = get_agent()  # 获取单例
    # ...
```

#### 4.1.3 deepagents 中间件架构

**文件位置**：`deepagents/graph.py`

`create_main_agent()` 函数的中间件构建流程：

```python
# deepagents/graph.py - create_main_agent 核心逻辑
def create_main_agent(
    model: str | BaseChatModel | None = None,
    tools: Sequence[BaseTool | Callable] | None = None,
    *,
    system_prompt: str | SystemMessage | None = None,
    middleware: Sequence[AgentMiddleware] = (),
    subagents: list[SubAgent] | None = None,
    skills: list[str] | None = None,
    memory: list[str] | None = None,
    response_format: ResponseFormat | None = None,
    context_schema: type[Any] | None = None,
    checkpointer: Checkpointer | None = None,
    store: BaseStore | None = None,
    backend: BackendProtocol | BackendFactory | None = None,
    interrupt_on: dict[str, bool | InterruptOnConfig] = None,
    debug: bool = False,
    name: str | None = None,
    cache: BaseCache | None = None,
) -> CompiledStateGraph:
    
    # 1. 模型初始化（支持字符串和 BaseChatModel）
    if model is None:
        model = get_default_model()  # 默认：ChatOllama(deepseek-r1:1.5b)
    elif isinstance(model, str):
        if model.startswith("qwen:"):
            model_init_params = {"temperature": 0.1, "top_p": 0.8}
        else:
            model_init_params = {}
        model = init_chat_model(model, configurable_fields=("model", "temperature"), **model_init_params)
    
    # 2. 通用目的中间件（所有子 Agent 共享）
    gp_middleware: list[AgentMiddleware[Any, Any, Any]] = [
        TodoListMiddleware(),  # 待办事项管理
        FilesystemMiddleware(backend=backend),  # 文件系统操作
        DeepAgentsSummarizationMiddleWare(
            model=model,
            backend=backend,
            trigger=summarization_defaults,
            keep=summarization_defaults,
            trim_tokens_to_summarize=None,
            truncate_args_settings=summarization_defaults,
        ),  # 上下文压缩
        PatchToolCallsMiddleware(),  # 工具调用补丁
    ]
    
    # 3. 可选中间件（条件添加）
    if skills is not None:
        gp_middleware.append(SkillsMiddleware(backend=backend, sources=skills))
    if interrupt_on is not None:
        gp_middleware.append(HumanInTheLoopMiddleware(interrupt_on=interrupt_on))
    
    # 4. 子 Agent 处理（通用目的子 Agent + 自定义子 Agent）
    general_purpose_spec: SubAgent = {
        **GENERAL_PURPOSE_SUBAGENT,
        "model": model,
        "tools": tools or [],
        "middleware": gp_middleware,
    }
    processed_subagents: list[SubAgent | CompiledSubAgent] = []
    for spec in subagents or []:
        # 处理每个子 Agent 的配置...
        processed_subagents.append(processed_spec)
    
    all_subagents: list[SubAgent | CompiledSubAgent] = [general_purpose_spec, *processed_subagents]
    
    # 5. 主 Agent 专属中间件
    mainagent_middleware: list[AgentMiddleware[Any, Any, Any]] = [
        TodoListMiddleware(),
    ]
    if memory is not None:
        mainagent_middleware.append(MemoryMiddleware(backend=backend, sources=memory))
    if skills is not None:
        mainagent_middleware.append(SkillsMiddleware(backend=backend, sources=skills))
    
    mainagent_middleware.extend([
        FilesystemMiddleware(backend=backend),
        SubAgentMiddleware(backend=backend, subagents=all_subagents),  # ← 子 Agent 管理核心
        DeepAgentsSummarizationMiddleWare(...),
        PatchToolCallsMiddleware(),
    ])
    
    if middleware:
        mainagent_middleware.extend(middleware)
    if interrupt_on is not None:
        mainagent_middleware.append(HumanInTheLoopMiddleware(interrupt_on=interrupt_on))
    
    # 6. 系统提示词合并
    if system_prompt is None:
        final_system_prompt = BASE_AGENT_PROMPT
    elif isinstance(system_prompt, SystemMessage):
        final_system_prompt = SystemMessage(
            content_blocks=[*system_prompt.content_blocks, {"type": "text", "text": f"\n\n{BASE_AGENT_PROMPT}"}])
    else:
        final_system_prompt = system_prompt + "\n\n" + BASE_AGENT_PROMPT
    
    # 7. 创建并编译图
    return create_agent(
        model,
        system_prompt=final_system_prompt,
        tools=tools,
        middleware=mainagent_middleware,
        response_format=response_format,
        context_schema=context_schema,
        checkpointer=checkpointer,
        store=store,
        debug=debug,
        name=name,
        cache=cache,
    ).with_config({"recursion_limit": 1000})
```

**中间件执行流程**：

```
用户输入 → START
           ↓
    [TodoList.before_agent]  ← 分析是否需要创建待办
           ↓
    [Filesystem.before_agent] ← 准备工作空间
           ↓
    [Summarization.before_model] ← 检查是否需要压缩历史
           ↓
    [PatchToolCalls.before_model] ← 修复工具调用格式
           ↓
         MODEL (LLM 推理)
           ↓
    [PatchToolCalls.after_model] ← 后处理模型输出
           ↓
    [Summarization.after_model] ← 更新摘要
           ↓
    [SubAgentMiddleware.after_agent] ← 调度子 Agent
           ↓
    [Filesystem.after_agent] ← 保存文件变更
           ↓
    [TodoList.after_agent] ← 更新待办状态
           ↓
         END (返回结果)
```

#### 4.1.2 子 Agent 设计

每个子 Agent 专注于特定任务领域：

```python
# agents/research_agent.py - 研究 Agent
class ResearchAgent:
    """商品信息搜集专家"""
    
    capabilities = [
        "web_search",      # 网络搜索
        "product_scraping", # 商品爬虫
        "price_tracking"   # 价格追踪
    ]
    
    async def search_products(self, query: str, platforms: list[str]):
        """跨平台搜索商品"""
        tasks = []
        for platform in platforms:
            scraper = self._get_scraper(platform)
            tasks.append(scraper.search(query))
        
        results = await asyncio.gather(*tasks)
        return self._merge_results(results)

# agents/analysis_agent.py - 分析 Agent
class AnalysisAgent:
    """数据分析专家"""
    
    capabilities = [
        "price_comparison",  # 价格对比
        "trend_analysis",    # 趋势分析
        "feature_extraction" # 特征提取
    ]
    
    async def compare_products(self, product_ids: list[str]):
        """对比多个商品"""
        products = await self._fetch_products(product_ids)
        comparison_matrix = self._build_comparison_matrix(products)
        return self._generate_insights(comparison_matrix)

# agents/recommendation_agent.py - 推荐 Agent
class RecommendationAgent:
    """个性化推荐专家"""
    
    capabilities = [
        "user_profiling",     # 用户画像
        "collaborative_filter", # 协同过滤
        "content_based_rec"   # 基于内容推荐
    ]
    
    async def recommend(self, user_id: str, context: dict):
        """生成个性化推荐"""
        user_profile = await self._get_user_profile(user_id)
        candidates = await self._retrieve_candidates(context)
        ranked = self._rank_candidates(user_profile, candidates)
        return ranked[:10]
```

**子 Agent 协作流程**：
1. **用户提问** → MainAgent 接收请求
2. **任务分解** → MainAgent 分析需要哪些子 Agent 参与
3. **并行执行** → ResearchAgent 搜索商品，AnalysisAgent 分析数据
4. **结果汇总** → RecommendationAgent 生成最终推荐
5. **响应返回** → MainAgent 整合所有结果返回给用户

#### 4.1.3 deepagents 中间件架构

deepagents 提供了一套完整的中间件系统来扩展 Agent 能力：

```python
# deepagents/graph.py - create_main_agent 函数节选
def create_main_agent(
    model: str | BaseChatModel | None = None,
    tools: Sequence[BaseTool | Callable] | None = None,
    middleware: Sequence[AgentMiddleware] = (),
    subagents: list[SubAgent] | None = None,
    skills: list[str] | None = None,
    memory: list[str] | None = None,
    # ... 其他参数
) -> CompiledStateGraph:
    
    # 通用目的中间件（所有子 Agent 共享）
    gp_middleware = [
        TodoListMiddleware(),  # 待办事项管理
        FilesystemMiddleware(backend=backend),  # 文件系统操作
        DeepAgentsSummarizationMiddleWare(...),  # 上下文压缩
        PatchToolCallsMiddleware(),  # 工具调用补丁
    ]
    
    # 可选中间件
    if skills is not None:
        gp_middleware.append(SkillsMiddleware(backend=backend, sources=skills))
    if interrupt_on is not None:
        gp_middleware.append(HumanInTheLoopMiddleware(interrupt_on=interrupt_on))
    
    # 主 Agent 专属中间件
    mainagent_middleware = [
        TodoListMiddleware(),
    ]
    if memory is not None:
        mainagent_middleware.append(MemoryMiddleware(backend=backend, sources=memory))
    if skills is not None:
        mainagent_middleware.append(SkillsMiddleware(backend=backend, sources=skills))
    
    mainagent_middleware.extend([
        FilesystemMiddleware(backend=backend),
        SubAgentMiddleware(backend=backend, subagents=all_subagents),  # ← 子 Agent 管理
        DeepAgentsSummarizationMiddleWare(...),
        PatchToolCallsMiddleware(),
    ])
    
    return create_agent(
        model=model,
        middleware=mainagent_middleware,
        # ...
    )
```

**核心中间件说明**：

| 中间件 | 功能 | 使用场景 |
|--------|------|----------|
| `TodoListMiddleware` | 待办事项管理 | 复杂任务拆解和跟踪 |
| `FilesystemMiddleware` | 文件系统操作 | Agent 工作空间管理 |
| `MemoryMiddleware` | 长期记忆存储 | 用户偏好、历史对话记录 |
| `SkillsMiddleware` | 技能包注入 | 动态加载特定领域技能 |
| `SubAgentMiddleware` | 子 Agent 调度 | MainAgent 协调子 Agent |
| `SummarizationMiddleware` | 上下文压缩 | 长对话历史摘要生成 |
| `PatchToolCallsMiddleware` | 工具调用修复 | 兼容不同 LLM 的工具调用格式 |
| `HumanInTheLoopMiddleware` | 人工介入 | 需要用户确认的关键决策 |

### 4.2 对话流程设计

#### 4.2.1 流式对话流程

**步骤 1：前端发起请求**
```javascript
// app/web/streamlit_app.py 或前端 Vue 组件
async def send_message(query, thread_id):
    response = await fetch(f'/api/chat/agent/{agent_id}', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: json.dumps({
            'query': query,
            'config': {'thread_id': thread_id}
        })
    })
    return response.body  # ReadableStream
```

**步骤 2：后端路由处理**
```python
# app/main.py
@app.post("/chat/agent/{agent_id}")
async def stream_agent_chat(
    agent_id: str,
    query: str = Body(...),
    config: dict = Body({}),
):
    # 1. 校验参数
    if not query:
        raise HTTPException(status_code=422, detail="query 不能为空")
    
    # 2. 获取 Agent 实例
    agent = get_agent()
    
    # 3. 返回流式响应
    return StreamingResponse(
        stream_agent_chat_service(agent, query, config),
        media_type="application/json"
    )
```

**步骤 3：服务层流式生成**
```python
# src/services/chat_stream_service.py
async def stream_agent_chat_service(agent, query, config):
    # 1. 构建 HumanMessage
    human_message = HumanMessage(content=query)
    messages = [human_message]
    
    # 2. 流式执行
    async for msg, metadata in agent._agent.stream(
        {"messages": messages},
        config={"configurable": config}
    ):
        # 3. 逐块返回
        if isinstance(msg, AIMessageChunk):
            yield make_chunk(content=msg.content, status="loading")
    
    # 4. 完成信号
    yield make_chunk(status="finished")
```

**步骤 4：前端接收并显示**
```javascript
// 前端处理流式响应
const reader = response.body.getReader()

while (true) {
    const { done, value } = await reader.read()
    if (done) break
    
    const chunk = decoder.decode(value)
    const lines = chunk.split('\n')
    
    for (const line of lines) {
        const data = JSON.parse(line)
        
        switch (data.status) {
            case 'loading':
                appendToTypingQueue(data.content)  // 打字机效果
                break
            case 'finished':
                resetOnGoingConv(threadId)  // 完成清理
                break
        }
    }
}
```

#### 4.2.2 多轮对话机制

**关键点**：通过 `thread_id` 维护对话上下文

```python
# LangGraph Checkpointer 自动管理历史
async def stream_agent_chat_service(...):
    langgraph_config = {
        "configurable": {
            "thread_id": thread_id,  # ← 唯一标识
            "user_id": user_id
        }
    }
    
    # 每次调用 astream_messages 时：
    # 1. Checkpointer 从数据库加载该 thread_id 的所有历史消息
    # 2. 将新的 messages 追加到历史末尾
    # 3. 执行推理生成响应
    # 4. 将新的 AI 响应保存到 Checkpointer
    
    async for msg in graph.astream_messages(messages, config=langgraph_config):
        yield msg
```

**数据结构**：
```python
# Checkpointer 表结构（PostgreSQL）
checkpoint = {
    "thread_id": "xxx",
    "checkpoint_ns": "",
    "checkpoint_id": "uuid",
    "parent_checkpoint_id": "parent_uuid",
    "channel_values": {
        "messages": [  # 历史消息列表
            {"role": "user", "content": "第一句话"},
            {"role": "assistant", "content": "回答 1"},
            {"role": "user", "content": "继续问"},
            # ... 新消息会追加到这里
        ]
    }
}
```

### 4.3 工具系统设计

#### 4.3.1 工具分类与注册

工具是 Agent 执行具体任务的能力单元：

```python
# tools/search_tools.py - 搜索工具示例
from langchain_core.tools import BaseTool
from typing import List, Dict
import asyncio

class ProductSearchTool(BaseTool):
    """商品搜索工具"""
    
    name = "product_search"
    description = "在电商平台搜索商品"
    
    def _run(self, query: str, platforms: List[str] = ["jd", "taobao"]) -> Dict:
        """同步搜索实现"""
        return asyncio.run(self._async_search(query, platforms))
    
    async def _arun(self, query: str, platforms: List[str] = ["jd", "taobao"]) -> Dict:
        """异步搜索实现"""
        return await self._async_search(query, platforms)
    
    async def _async_search(self, query: str, platforms: List[str]) -> Dict:
        """执行跨平台搜索"""
        tasks = []
        for platform in platforms:
            scraper = self._get_scraper(platform)
            tasks.append(scraper.search_async(query))
        
        results = await asyncio.gather(*tasks)
        return {
            "query": query,
            "platforms": platforms,
            "results": self._merge_and_rank(results)
        }
```

**工具类型**：
- **搜索工具**：商品搜索、店铺搜索、品牌搜索
- **分析工具**：价格对比、趋势分析、参数提取
- **对比工具**：多商品对比、相似度计算
- **辅助工具**：记忆管理、文件操作、浏览器控制

#### 4.3.2 电商爬虫系统

爬虫是获取商品信息的核心组件：

```python
# scrapers/jd_scraper.py - 京东爬虫示例
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from typing import List, Dict
import asyncio

class JDScraper:
    """京东爬虫"""
    
    def __init__(self, headless: bool = True):
        """初始化爬虫"""
        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument("--headless")
        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 10)
    
    async def search_async(self, query: str) -> List[Dict]:
        """异步搜索商品"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._search_sync, query)
    
    def _search_sync(self, query: str) -> List[Dict]:
        """同步搜索实现"""
        try:
            # 1. 打开搜索页面
            search_url = f"https://search.jd.com/Search?keyword={query}"
            self.driver.get(search_url)
            
            # 2. 等待商品列表加载
            products = self.wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".gl-item"))
            )
            
            # 3. 提取商品信息
            results = []
            for product in products[:20]:  # 只取前 20 个
                try:
                    title_el = product.find_element(By.CSS_SELECTOR, ".p-name em")
                    price_el = product.find_element(By.CSS_SELECTOR, ".p-price i")
                    
                    results.append({
                        "platform": "jd",
                        "title": title_el.text,
                        "price": float(price_el.text),
                        "url": product.find_element(By.TAG_NAME, "a").get_attribute("href"),
                        "image": product.find_element(By.TAG_NAME, "img").get_attribute("data-lazy-img"),
                        "shop": product.find_element(By.CSS_SELECTOR, ".p-shop-name").text if \
                               product.find_elements(By.CSS_SELECTOR, ".p-shop-name") else "自营"
                    })
                except Exception as e:
                    logging.warning(f"解析单个商品失败：{e}")
                    continue
            
            return results
            
        except Exception as e:
            logging.error(f"京东搜索失败：{e}")
            return []
    
    def close(self):
        """关闭爬虫"""
        self.driver.quit()
```

**爬虫特性**：
- **异步并发**：使用 `async/await` 实现高并发爬取
- **反反爬虫**：IP 代理池、User-Agent 轮换、请求限流
- **数据清洗**：HTML 解析、字段提取、数据标准化
- **错误处理**：超时重试、异常捕获、日志记录

### 4.4 数据存储设计

#### 4.4.1 业务数据模型

```python
# src/storage/postgres/models.py
from sqlalchemy import Column, String, DateTime, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Conversation(Base):
    """对话线程表"""
    __tablename__ = "conversations"
    
    id = Column(String(50), primary_key=True)
    thread_id = Column(String(50), unique=True, index=True)
    user_id = Column(String(50), nullable=False, index=True)
    agent_id = Column(String(50), nullable=False)
    title = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    status = Column(String(20), default="active")
    metadata = Column(JSON)  # 额外元数据


class Message(Base):
    """消息表"""
    __tablename__ = "messages"
    
    id = Column(String(50), primary_key=True)
    conversation_id = Column(String(50), ForeignKey("conversations.id"), index=True)
    role = Column(String(20), nullable=False)  # user/assistant/system
    content = Column(String)  # 支持长文本
    message_type = Column(String(20), default="text")  # text/image/tool_call
    extra_metadata = Column(JSON)  # 存储工具调用结果、图片 URL 等
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class Product(Base):
    """商品缓存表"""
    __tablename__ = "products"
    
    id = Column(String(50), primary_key=True)
    platform = Column(String(20), nullable=False)  # jd/taobao/pdd
    product_id = Column(String(100), nullable=False)  # 平台商品 ID
    title = Column(String(500))
    price = Column(String(20))
    original_price = Column(String(20))
    image_url = Column(String(500))
    detail_url = Column(String(500))
    shop_name = Column(String(200))
    category = Column(String(100))
    brand = Column(String(100))
    specs = Column(JSON)  # 规格参数
    crawled_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('platform', 'product_id', name='uix_platform_product'),
    )
```

#### 4.4.2 Checkpointer 持久化

LangGraph Checkpointer 使用 PostgreSQL 或 SQLite 存储对话状态：

```sql
-- LangGraph Checkpoint 表（PostgreSQL）
CREATE TABLE checkpoint (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    channel_values JSONB,  -- 存储实际的消息历史和状态
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

-- 创建索引加速查询
CREATE INDEX idx_checkpoint_thread ON checkpoint(thread_id);
CREATE INDEX idx_checkpoint_parent ON checkpoint(parent_checkpoint_id);
```

**Checkpointer 工作机制**：
1. **自动保存**：每次 Agent 执行完毕后自动保存状态
2. **历史加载**：下次调用时自动加载该 `thread_id` 的所有历史消息
3. **分支管理**：支持对话分支（用于探索不同可能性）
4. **压缩策略**：当消息过长时自动触发摘要压缩

### 4.5 浏览器自动化系统

#### 4.5.1 Playwright 控制器

```python
# computer/browser_controller.py
from playwright.async_api import async_playwright
from typing import Optional, Dict, List
import asyncio

class BrowserController:
    """异步浏览器控制器"""
    
    def __init__(self, headless: bool = True):
        """初始化浏览器"""
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None
    
    async def start(self):
        """启动浏览器"""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(
            headless=self.headless,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080}
        )
        self.page = await self.context.new_page()
    
    async def navigate(self, url: str):
        """导航到页面"""
        await self.page.goto(url, wait_until='networkidle')
    
    async def click(self, selector: str):
        """点击元素"""
        await self.page.click(selector)
    
    async def type_text(self, selector: str, text: str):
        """输入文本"""
        await self.page.fill(selector, text)
    
    async def extract_products(self, selector: str) -> List[Dict]:
        """提取商品信息"""
        elements = await self.page.query_selector_all(selector)
        products = []
        
        for el in elements:
            try:
                title = await el.query_selector('.p-name em')
                price = await el.query_selector('.p-price i')
                
                if title and price:
                    products.append({
                        'title': await title.inner_text(),
                        'price': await price.inner_text(),
                        'url': await (await el.query_selector('a')).get_attribute('href')
                    })
            except Exception as e:
                print(f"解析失败：{e}")
                continue
        
        return products
    
    async def close(self):
        """关闭浏览器"""
        if self.browser:
            await self.browser.close()
```

**应用场景**：
- **复杂网页交互**：登录验证、滑块验证、验证码识别
- **跨应用操作**：从浏览器复制数据到 Excel
- **自动化测试**：UI 测试、回归测试
- **数据采集**：动态加载内容爬取、反爬虫绕过

---

## 5. 接口设计规范

### 5.1 RESTful API 规范

#### 5.1.1 通用响应格式

```json
// 成功响应
{
  "code": 200,
  "data": { ... },
  "message": "success"
}

// 错误响应
{
  "code": 400,
  "data": null,
  "message": "参数错误"
}
```

#### 5.1.2 核心接口定义

**1. 发送对话消息**
```http
POST /api/chat/agent/{agent_id}
Content-Type: application/json
Authorization: Bearer {token}

{
  "query": "用户问题",
  "config": {
    "thread_id": "对话线程 ID",
    "agent_config_id": "配置 ID（可选）"
  },
  "image_content": "base64 图片（可选）"
}

// 响应：SSE 流
data: {"status":"loading","content":"部分回答"}
data: {"status":"finished","meta":{}}
```

**2. 创建异步任务（Run 模式）**
```http
POST /api/chat/runs
Content-Type: application/json

{
  "agent_id": "智能体 ID",
  "query": "复杂任务描述",
  "config": {
    "thread_id": "线程 ID"
  }
}

// 响应
{
  "run_id": "uuid",
  "thread_id": "xxx",
  "status": "pending",
  "stream_url": "/api/chat/runs/{run_id}/events?after_seq=0"
}
```

**3. 监听任务事件（SSE）**
```http
GET /api/chat/runs/{run_id}/events?after_seq=0

// 响应流
event: message
data: {"seq":"1","event_type":"tool_call","payload":{...}}

event: close
data: {"status":"completed","last_seq":"10"}
```

### 5.2 错误码规范

| 错误码 | 含义 | 处理建议 |
|--------|------|----------|
| 200 | 成功 | - |
| 400 | 请求参数错误 | 检查请求体和参数 |
| 401 | 未授权 | 重新登录 |
| 403 | 权限不足 | 联系管理员 |
| 404 | 资源不存在 | 检查 ID 是否正确 |
| 409 | 资源冲突 | 检查重复提交 |
| 422 | 参数验证失败 | 查看 validation detail |
| 429 | 请求过于频繁 | 等待后重试 |
| 500 | 服务器内部错误 | 查看日志 |

---

## 6. 数据模型设计

### 6.1 ER 图

```
┌─────────────────┐       ┌─────────────────┐
│   User          │       │   Department    │
├─────────────────┤       ├─────────────────┤
│ id (PK)         │       │ id (PK)         │
│ username        │       │ name            │
│ email           │       │ parent_id       │
│ department_id(FK)──────▶│ created_at      │
└─────────────────┘       └─────────────────┘
         │
         │ 1:N
         ▼
┌─────────────────┐       ┌─────────────────┐
│  Conversation   │       │    Agent        │
├─────────────────┤       ├─────────────────┤
│ id (PK)         │       │ id (PK)         │
│ thread_id (UK)  │       │ name            │
│ user_id (FK)    │       │ module_name     │
│ agent_id (FK)   │◀──────│ config_json     │
│ title           │       └─────────────────┘
│ status          │
└─────────────────┘
         │
         │ 1:N
         ▼
┌─────────────────┐
│    Message      │
├─────────────────┤
│ id (PK)         │
│ conversation_id │
│ role            │
│ content         │
│ extra_metadata  │
│ created_at      │
└─────────────────┘
```

### 6.2 索引设计

```sql
-- 高频查询字段添加索引
CREATE INDEX idx_conversation_user_id ON conversations(user_id);
CREATE INDEX idx_conversation_thread_id ON conversations(thread_id);
CREATE INDEX idx_message_conversation_id ON messages(conversation_id);
CREATE INDEX idx_message_created_at ON messages(created_at DESC);

-- 复合索引（常用查询组合）
CREATE INDEX idx_conv_user_status ON conversations(user_id, status);
```

---

## 7. 部署与运维

### 7.1 Docker Compose 部署

```yaml
# docker-compose.yml
services:
  api:
    build:
      context: .
      dockerfile: docker/api.Dockerfile
    container_name: api-server
    ports:
      - "5050:5050"
    environment:
      - POSTGRES_URL=postgresql+asyncpg://user:pass@postgres:5432/db
      - REDIS_URL=redis://redis:6379/0
    volumes:
      - ./server:/app/server
      - ./src:/app/src
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
  
  web:
    build:
      context: ./web
      dockerfile: ../docker/web.Dockerfile
    container_name: web-server
    ports:
      - "5173:5173"
    environment:
      - VITE_API_URL=http://api:5050
  
  postgres:
    image: postgres:16
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=db
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
  
  redis:
    image: redis:7-alpine
    volumes:
      - ./data/redis:/data
```

### 7.2 环境变量配置

```bash
# .env.example
# 数据库配置
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
POSTGRES_DB=shopping_claw
POSTGRES_URL=postgresql+asyncpg://postgres:password@localhost:5432/shopping_claw

# Redis 配置
REDIS_URL=redis://localhost:6379/0

# MinIO 配置
MINIO_URI=http://localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# LLM 配置（Ollama 本地部署）
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_MODEL=qwen2.5:3b

# 安全配置
JWT_SECRET_KEY=your_jwt_secret
YUXI_SUPER_ADMIN_NAME=admin
YUXI_SUPER_ADMIN_PASSWORD=your_admin_password
```

### 7.3 日志规范

```python
# src/utils/logging_config.py
import logging
from colorlog import ColoredFormatter

def setup_logging():
    """设置日志配置"""
    log_format = "%(log_color)s%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    
    formatter = ColoredFormatter(
        log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold_red',
        }
    )
    
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    
    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)  # 生产环境调整为 WARNING
```

### 7.4 健康检查

```python
# server/routers/system_router.py
@system.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": __version__
    }

@system.get("/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """就绪检查（检查依赖服务）"""
    checks = {
        "database": False,
        "redis": False,
    }
    
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = True
    except:
        pass
    
    # 检查 Redis...
    
    all_healthy = all(checks.values())
    
    return {
        "ready": all_healthy,
        "checks": checks
    }
```

---

## 8. 附录

### 8.1 开发命令速查

```bash
# 启动开发环境（如果有 Docker）
docker compose up -d

# 查看日志
docker logs api --tail 100 -f

# 进入容器调试
docker compose exec api bash

# 代码检查（如果配置了 lint 工具）
make lint

# 代码格式化（如果配置了 black）
black agents/ src/ deepagents/

# 运行测试
docker compose exec api uv run pytest test/ -v

# 数据库迁移（如果有脚本）
docker compose exec api uv run python scripts/migrate.py
```

### 8.2 当前开发状态

#### ✅ 已完成模块

1. **Agent 框架层** (`src/agents/`)
   - [x] `base.py`: BaseAgent 抽象基类
   - [x] `context.py`: BaseContext 上下文定义
   - [x] `graph.py`: Agent 图构建（34KB，LangGraph 深度定制）
   - [x] `agent_demo.py`: 使用示例
   - [x] `BASE_PROMPT.md`: 基础提示词模板

2. **deepagents 框架** (`deepagents/`)
   - [x] `backends/protocol.py`: Backend 协议定义
   - [x] `backends/state.py`: StateBackend 实现
   - [x] `middlleware/filesystem.py`: 文件系统中间件
   - [x] `middlleware/memory.py`: 记忆中间件
   - [x] `middlleware/skills.py`: Skills 中间件
   - [x] `middlleware/subagent.py`: 子 Agent 中间件
   - [x] `middlleware/summarization.py`: 摘要压缩中间件
   - [x] `middlleware/patch_tool_calls.py`: 工具调用补丁
   - [x] `graph.py`: create_main_agent 主逻辑

3. **Agent 实例** (`agents/`)
   - [x] `main_agent.py`: MainAgent 主协调器（已实现基础功能）
   - [x] `research_agent.py`: ResearchAgent 框架（待完善）
   - [x] `analysis_agent.py`: AnalysisAgent 框架（待完善）
   - [x] `recommendation_agent.py`: RecommendationAgent 框架（待完善）

4. **基础设施** (`src/utils/infra/`)
   - [x] `agent_factory.py`: Agent 工厂（单例模式）
   - [x] `config.py`: 配置管理
   - [x] `llm_provider.py`: LLM 提供者封装

5. **服务层** (`src/services/`)
   - [x] `chat_stream_service.py`: 流式对话服务框架
   - [x] `agent_run_service.py`: Agent 运行服务框架

#### 🚧 进行中模块

1. **API 路由** (`server/routers/`)
   - [ ] `chat_router.py`: 对话接口（需要完善流式响应处理）
   - [ ] `agent_router.py`: Agent 管理接口

2. **前端界面** (`app/web/`)
   - [ ] `streamlit_app.py`: Streamlit 原型界面

3. **子 Agent 实现**
   - [ ] ResearchAgent: 商品搜索逻辑
   - [ ] AnalysisAgent: 数据分析逻辑
   - [ ] RecommendationAgent: 推荐算法

#### 📋 计划中模块

1. **电商爬虫** (`scrapers/`)
   - [ ] `jd_scraper.py`: 京东爬虫
   - [ ] `taobao_scraper.py`: 淘宝爬虫
   - [ ] `pdd_scraper.py`: 拼多多爬虫

2. **工具系统** (`tools/`)
   - [ ] `search_tools.py`: ProductSearchTool
   - [ ] `analysis_tools.py`: PriceComparisonTool
   - [ ] `compare_tools.py`: ProductCompareTool
   - [ ] `memory_tools.py`: UserPreferenceTool

3. **浏览器自动化** (`computer/`)
   - [ ] `browser_controller.py`: Playwright 控制器
   - [ ] `desktop_controller.py": PyAutoGUI 桌面控制

4. **自定义中间件** (`middleware/`)
   - [ ] `logging.py`: 彩色日志中间件
   - [ ] `retry.py`: 请求重试中间件

### 8.3 常见问题排查

#### Q1: Agent 无法加载历史对话
**检查点**：
1. `thread_id` 是否正确传递到 `config={"configurable": {"thread_id": "xxx"}}`
2. Checkpointer 是否正常连接数据库（如果使用持久化）
3. 查询 `checkpoint` 表确认数据存在

**解决方案**：
```python
# 检查 MainAgent 初始化
agent = MainAgent(persistence=True)  # ← 必须设置为 True

# 检查调用时的 config
config = {"configurable": {"thread_id": "user_123"}}
result = agent.invoke("你好", config=config)
```

#### Q2: 流式响应中断
**检查点**：
1. 前端是否正确处理 `ReadableStream`
2. 网络是否稳定
3. 后端是否有异常抛出（查看日志）

**解决方案**：
```python
# app/main.py 确保返回 StreamingResponse
from fastapi.responses import StreamingResponse

@app.post("/chat")
async def stream_chat(query: str):
    async def generate():
        async for chunk in chat_stream_service(query):
            yield f"data: {json.dumps(chunk)}\n"
    
    return StreamingResponse(generate(), media_type="application/json")
```

#### Q3: Ollama 模型加载失败
**检查点**：
1. Ollama 服务是否启动：`ollama ps`
2. 模型是否已下载：`ollama pull qwen2.5:3b`
3. 端口是否可访问：`http://localhost:11434`

**解决方案**：
```bash
# 启动 Ollama 服务
ollama serve

# 下载模型
ollama pull qwen2.5:3b

# 验证模型
ollama run qwen2.5:3b "你好"
```

#### Q4: deepagents 中间件不生效
**检查点**：
1. 中间件是否正确添加到 `middleware` 参数
2. 中间件的 `before_*` / `after_*` 方法是否重写
3. Backend 是否正确初始化

**调试技巧**：
```python
# 在 deepagents/graph.py 中添加调试日志
import logging
logger = logging.getLogger(__name__)

def create_main_agent(...):
    logger.info(f"Creating main agent with middleware: {middleware}")
    # ...
    
    # 打印每个中间件的名称
    for m in mainagent_middleware:
        logger.info(f"Added middleware: {m.name}")
```

### 8.4 性能优化建议

1. **数据库优化**
   - 为 `conversations(thread_id, user_id)` 添加复合索引
   - 定期清理过期对话（如 3 个月前的数据）
   - 使用连接池（asyncpg 默认已优化）

2. **缓存策略**
   - Agent 配置使用 Redis 缓存（避免重复加载）
   - 热门商品信息缓存 5 分钟
   - 用户会话信息缓存 30 分钟

3. **异步处理**
   - 长时间任务使用 ARQ 队列异步处理
   - 文件上传和解析异步执行
   - 批量操作使用事务批处理

4. **模型优化**
   - 本地部署：使用 Ollama + Qwen/DeepSeek
   - 云端 API：使用 OpenAI/Azure（生产环境）
   - 混合模式：简单任务本地，复杂任务云端

---

## 文档变更记录

| 版本 | 日期 | 修改人 | 变更内容 |
|------|------|--------|----------|
| v1.0 | 2026-03-31 | AI Assistant | 初始版本（基于通用 Agent 平台） |
| v1.1 | 2026-04-01 | AI Assistant | 针对 ShoppingClaw 项目定制，移除 RAG 内容，强化多 Agent 协作和电商爬虫 |

---

**文档结束**
