# ShoppingClaw 开发文档

**文档版本**：v2.0  
**更新日期**：2026-05-23  
**适用范围**：基于 LangGraph + deepagents 的多 Agent 智能购物助手

---

## 目录

1. [项目概述](#1-项目概述)
2. [技术架构](#2-技术架构)
3. [核心模块设计](#3-核心模块设计)
4. [API 接口规范](#4-api-接口规范)
5. [数据模型设计](#5-数据模型设计)
6. [部署与运维](#6-部署与运维)
7. [开发规范](#7-开发规范)

---

## 1. 项目概述

### 1.1 项目背景

ShoppingClaw 是一个基于 LangGraph + deepagents 框架的智能购物助手平台。通过 Master Agent 协调 Researcher / Critic / Analyst / Memory 四个子 Agent 协作，实现跨平台商品搜索、智能数据分析和个性化推荐。

### 1.2 核心目标

- **多 Agent 协作**：Master Agent 通过 SubAgentMiddleware 调度子 Agent 协同工作
- **JD 商品搜索**：集成 JD SDK（234 个 REST API），支持商品搜索、详情查询
- **意图识别**：JointBERT 多标签分类 + LightGBM 置信度评估
- **SSE 流式响应**：自研 SSE 协议栈，支持实时打字机效果
- **Redis 多用途**：消息存储桥接、滑动窗口速率限制、API 缓存装饰器
- **知识库管理**：多后端存储（ChromaDB / 文件系统），生命周期管理

### 1.3 术语定义

| 术语 | 定义 |
|------|------|
| Master Agent | 主智能体，协调子 Agent 工作流，维护 DecisionState |
| SubAgent | 子智能体（Researcher / Critic / Analyst / Memory），封装为 LangChain Tool |
| DecisionState | 显式决策状态：intent、evidence_log、information_gaps、confidence_score、decision_path |
| Gap Detector | LightGBM 模型节点，评估证据质量并决定是否继续搜索 |
| Thread | 对话线程，通过 thread_id 维护多轮上下文 |
| Checkpointer | LangGraph 状态持久化（PostgreSQL / SQLite） |
| SSE | Server-Sent Events，用于流式推送 Agent 响应和工具调用 |

---

## 2. 技术架构

### 2.1 整体架构

```
┌────────────────────────────────────────────────────────┐
│                前端层 (Vue 3 + Ant Design Vue)          │
│  AgentChatComponent / ThinkingProcessSidebar           │
│  ToolCallCard / MarkdownContentViewer / AgentFlowPanel │
└────────────────────────┬───────────────────────────────┘
                         │ HTTP + SSE
┌────────────────────────┴───────────────────────────────┐
│              API 网关层 (FastAPI)                       │
│  中间件：CORS / Audit / RateLimiter                    │
│  路由：/chat / auth / models / system                  │
└────────────────────────┬───────────────────────────────┘
                         │
┌────────────────────────┴───────────────────────────────┐
│              服务层 (src/services/)                     │
│  chat_stream_service / sse_session_manager             │
│  intent_service (JointBERT) / gap (LightGBM)           │
│  redis_store / redis_cache / cache_decorator           │
│  conversation_service / history_manager                │
└────────────────────────┬───────────────────────────────┘
                         │
┌────────────────────────┴───────────────────────────────┐
│         Agent 层 (LangGraph + deepagents)              │
│  Master Agent (factory.py 66KB + graph.py)            │
│  ├─ DecisionState (intent/gaps/confidence/path)        │
│  ├─ Gap Detector Node (LightGBM)                       │
│  └─ SubAgentMiddleware → Researcher/Critic/Analyst     │
└────────────────────────┬───────────────────────────────┘
                         │
┌────────────────────────┴───────────────────────────────┐
│                 数据存储层                              │
│  PostgreSQL (Checkpointer + 业务表)                     │
│  Redis (消息存储 / 速率限制 / 缓存)                      │
│  ChromaDB / 文件系统 (知识库)                            │
│  JD SDK (234 REST API)                                │
└────────────────────────────────────────────────────────┘
```

### 2.2 核心技术栈

| 组件 | 技术 | 版本 |
|------|------|------|
| Web 框架 | FastAPI | 0.121+ |
| Agent 框架 | LangGraph + deepagents | 1.0+ / 0.2.5+ |
| LLM | Ollama (DeepSeek/Qwen) | Latest |
| 数据库 | PostgreSQL (asyncpg) | 16 |
| 缓存 | Redis (redis-py) | 7 / 5.2+ |
| 前端 | Vue 3 + Vite | 3.5 / 7.3 |
| UI 库 | Ant Design Vue | 4.2 |
| 状态管理 | Pinia | 3.0 |
| 可视化 | ECharts + AntV G6 + D3 | 6 / 5 / 7 |
| ML 模型 | JointBERT + LightGBM | — |
| 知识库 | ChromaDB | 0.5+ |
| 包管理 | UV (Python) / pnpm (前端) | Latest |

---

## 3. 核心模块设计

### 3.1 Master Agent

**文件**：`src/agents/master_agent/factory.py` (66KB) + `graph.py`

Master Agent 是整个系统的决策核心，基于 deepagents 的 `create_agent` 引擎构建，并在 `graph.py` 中扩展决策节点：

```
用户输入 → Model Node (LLM 推理 + Tool Calling)
         → Gap Detector Node (LightGBM 评估证据质量)
         → 条件路由：
           ├─ confidence < 0.7 → 继续搜索（回到 Model）
           ├─ gaps 包含 "human_input" → interrupt（人机协同）
           └─ 否则 → END（输出决策报告）
```

**DecisionState**（`src/agents/master_agent/context.py`）：

```python
class DecisionState:
    messages: List[AnyMessage]       # 对话历史
    intent: str                      # 用户意图
    constraints: dict                # 约束条件（预算/品牌等）
    evidence_log: List[str]          # 已收集证据摘要
    information_gaps: List[str]      # 待填补信息缺口
    confidence_score: float          # 决策置信度 (0.0-1.0)
    decision_path: List[str]         # 决策轨迹（前端可视化）
```

**中间件链**：
```
TodoListMiddleware → FilesystemMiddleware → MemoryMiddleware
→ SkillsMiddleware → SubAgentMiddleware → SummarizationMiddleware
→ PatchToolCallsMiddleware
```

### 3.2 子 Agent 系统

**文件**：`src/agents/subagents/subagents.yaml` (15KB)

子 Agent 作为 LangChain Tool 封装，由 Master Agent 通过 `tool_calls` 调度：

| 子 Agent | 职责 | 工具包 |
|----------|------|--------|
| Researcher | 跨平台商品搜索 | `toolkits/research/`（JD SDK 集成） |
| Critic | 评估搜索结果质量 | `toolkits/critic/` |
| Analyst | 数据对比与分析 | `toolkits/analyst/` |
| Memory | 用户偏好存取 | `toolkits/memory/` |

### 3.3 JD SDK 集成

**文件**：`src/jd/api/rest/` (234 个 API)

```python
# 核心使用方式
from src.jd import JdApiClient

client = JdApiClient(app_key="...", app_secret="...")
result = client.call("jd.union.open.goods.query", {...})
```

集成了京东联盟完整 API 体系，包括商品查询、优惠券查询、转链接口等。

### 3.4 意图识别

**文件**：`src/services/intent_service.py` + `joint_intent_model.py`

双阶段流水线：
1. **JointBERT**：多标签意图分类（如 search_product / compare_price / ask_recommend）
2. **LightGBM**：Gap Detector 置信度评估，判断信息是否充分

### 3.5 SSE 流式协议

**文件**：`src/services/sse_protocol.py` + `sse_adapter.py` + `sse_session_manager.py`

自研三层架构：
- **协议层**（`sse_protocol.py`）：定义帧格式（loading / thinking / tool_call / finished）
- **适配层**（`sse_adapter.py`）：LangGraph 输出 → SSE 帧转换
- **会话层**（`sse_session_manager.py`）：会话生命周期管理、1 小时自动清理

### 3.6 Redis 应用

**文件**：`src/services/redis_store.py` + `redis_cache.py` + `cache_decorator.py` + `server/middleware/rate_limiter.py`

| 模块 | 功能 | 数据结构 |
|------|------|----------|
| MessageStoreBridge | Redis 优先消息存储，自动降级 MemoryStore | Hash + Sorted Set |
| RateLimiter | 滑动窗口速率限制（FastAPI 依赖注入） | Sorted Set |
| @redis_cache | API 结果缓存装饰器（SHA256 键值） | String |

### 3.7 知识库系统

**文件**：`src/knowledge/`

```
manager.py          # 统一入口
core/               # 核心 CRUD
stores/             # 后端适配（ChromaDB / 文件系统）
indexers/           # 索引构建
lifecycle/          # 创建-激活-归档-删除 生命周期
fusion/             # 多源知识融合
```

---

## 4. API 接口规范

### 4.1 通用规范

- **Base URL**：`http://localhost:5050/api`
- **Content-Type**：`application/json`
- **认证**：Bearer Token（JWT）

### 4.2 核心接口

#### 发送对话（SSE 流式）

```
POST /api/chat/agent/{agent_id}
Content-Type: application/json
Authorization: Bearer {token}

{
  "query": "帮我找一款性价比高的蓝牙耳机",
  "config": { "thread_id": "conv-001" }
}

// 响应：SSE 流
event: message
data: {"status":"loading","content":"好的，我来帮你搜索..."}

event: tool_call
data: {"status":"loading","tool_name":"jd_search","args":{...}}

event: message
data: {"status":"finished","meta":{"thread_id":"conv-001"}}
```

#### 对话历史

```
GET /api/chat/history/{thread_id}
Authorization: Bearer {token}

Response:
{
  "conversation": { "id": "...", "title": "...", "messages": [...] }
}
```

#### 速率限制状态

```
GET /api/chat/rate-limit-status

Response:
{
  "limit": 30, "remaining": 28, "reset_after_seconds": 42
}
```

#### 用户认证

```
POST /api/auth/login     → { "username": "...", "password": "..." }
POST /api/auth/register  → { "username": "...", "password": "..." }
```

#### 系统

```
GET /api/system/health   → { "status": "ok" }
GET /api/models/list     → { "models": [...] }
```

### 4.3 错误码

| 码 | 含义 | 处理建议 |
|----|------|----------|
| 200 | 成功 | — |
| 400 | 参数错误 | 检查请求体 |
| 401 | 未授权 | 重新登录 |
| 404 | 资源不存在 | 检查 ID |
| 422 | 参数验证失败 | 查看 detail |
| 429 | 请求过于频繁 | 等待 rate-limit-status 提示的秒数 |
| 500 | 服务器错误 | 查看日志 |

---

## 5. 数据模型设计

### 5.1 核心表

```sql
-- 对话线程
conversations (
    id UUID PK,
    thread_id VARCHAR(50) UNIQUE,
    user_id UUID FK,
    agent_id VARCHAR(50),
    title VARCHAR(255),
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP,
    updated_at TIMESTAMP
)

-- 消息
messages (
    id UUID PK,
    conversation_id UUID FK,
    role VARCHAR(20),        -- user / assistant / tool
    content TEXT,
    message_type VARCHAR(20), -- text / tool_call / thinking
    extra_metadata JSONB,
    created_at TIMESTAMP
)
```

### 5.2 LangGraph Checkpointer

```sql
checkpoint (
    thread_id TEXT,
    checkpoint_ns TEXT DEFAULT '',
    checkpoint_id TEXT,
    parent_checkpoint_id TEXT,
    channel_values JSONB,    -- 消息历史 + State
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
)
```

---

## 6. 部署与运维

### 6.1 Docker Compose（开发）

```bash
docker-compose up -d
# 启动 API(5050) + PostgreSQL(5432) + Redis(6379)
```

### 6.2 本地开发

```bash
uv sync                        # 安装 Python 依赖
docker-compose up -d postgres redis  # 仅基础设施
uv run uvicorn server.main:app --reload  # API 热重载
```

### 6.3 前端开发

```bash
cd web-v2
pnpm install
pnpm dev    # → http://localhost:5173
```

### 6.4 环境变量

```bash
# .env 关键配置
OLLAMA_BASE_URL=http://host.docker.internal:11434
POSTGRES_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/shoppingclaw
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=your_secret
```

详细部署说明见 [Docker 部署指南](DOCKER_DEPLOYMENT.md)。

---

## 7. 开发规范

### 7.1 Python 规范

- 所有公共函数必须添加类型注解
- 异步方法使用 `async/await`
- Docstring 使用 Google 风格（Args / Returns / Raises）
- 异常处理要明确，使用 `src/services/error_handler.py` 统一格式

### 7.2 前端规范

- 组件用 PascalCase，文件名 kebab-case
- 使用 Pinia 管理跨组件状态
- API 调用统一通过 `src/apis/` 封装
- SSE 流式响应统一通过 `composables/` 中的 hook 处理

### 7.3 Git 提交规范

```
feat(agent): 添加 Gap Detector 节点
fix(chat): 修复 SSE 流中断问题
docs(readme): 更新项目结构说明
refactor(service): 重构意图识别流水线
```

### 7.4 常见问题

**Q: Agent 无法加载历史对话？**
检查 `thread_id` 是否正确传递，PostgreSQL Checkpointer 是否正常连接。

**Q: SSE 流中断？**
检查 `sse_session_manager` 会话是否超时（1 小时自动清理），前端是否正确处理 `ReadableStream`。

**Q: Ollama 连接失败？**
确认 Ollama 已启动且 `OLLAMA_BASE_URL` 配置正确。Docker 内需使用 `host.docker.internal`。

**Q: Redis 连接失败？**
检查 `REDIS_URL` 配置，确认 Redis 服务已启动。代码层已实现自动降级到 MemoryStore。

---

## 文档变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0 | 2026-03-31 | 初始版本 |
| v1.1 | 2026-04-01 | 项目定制 |
| v2.0 | 2026-05-23 | 全面重写：对齐实际项目结构，移除过时/不存在的模块，补充 Redis/SSE/JD SDK/知识库等实际实现 |
