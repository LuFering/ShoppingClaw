<div align="center">

<img src="docs/assets/logo.png" alt="ShoppingClaw" width="220">

# ShoppingClaw · 购物抓虾

**用一句自然语言，完成从「想买什么」到「买哪个、什么时候买、买了之后」的全过程。**

[![License](https://img.shields.io/badge/license-MIT-178a67?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-3776ab?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3-42b883?style=flat-square&logo=vuedotjs&logoColor=white)](https://vuejs.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-1c3c3c?style=flat-square)](https://github.com/langchain-ai/langgraph)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.121+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)

[快速开始](#快速开始) · [核心能力](#核心能力) · [架构](#架构) · [文档](#文档) · [FAQ](#faq)

</div>

---

> [!WARNING]
> **部署前请知悉**
> - 本项目会调用**真实电商联盟 API**（淘宝联盟 / 多多进宝）与**真实 LLM**，请自行申请密钥，**切勿把 `.env` 提交到仓库**。
> - 定时监控任务会**周期性发起外部请求**，请注意接口配额与平台规则。
> - 商品价格、库存等数据来自第三方接口，**仅供参考**，下单前请以平台页面为准。

<!--
  ═══════════════════════════════════════════════════════════
  截图占位：图片补好后，删掉本段注释的首尾两行（HTML 注释标记），即可显示
  建议放 2 张：
    ① screenshot-chat.png  对话主界面（SSE 流式 + 思考可视化 + 编排状态）
    ② screenshot-graph.png 决策图（采购规划的实时生长图）
  放到 docs/assets/ 目录下，宽度 1600px 左右即可
  ═══════════════════════════════════════════════════════════

<p align="center">
  <img src="docs/assets/screenshot-chat.png" alt="对话主界面" width="49%">
  <img src="docs/assets/screenshot-graph.png" alt="决策图" width="49%">
</p>

-->

---

## 💡 它解决什么问题

购物决策的难处不在「搜不到商品」，而在**信息散、比不动、记不住**：

| 痛点 | 现状 | ShoppingClaw 的做法 |
| --- | --- | --- |
| **信息散** | 价格、券、库存、评价散在多个平台，来回切换 | 主智能体编排子智能体，**一轮对话内并行取数** |
| **比不动** | 参数表看不懂，不知道哪个差异真正影响体验 | 子智能体把参数**翻译成场景收益**，按用户约束动态加权 |
| **记不住** | 上次看到的好价、定过的预算，过两天就忘 | **购物档案**五阶段沉淀 + **定时监控**持续盯价 |
| **买了之后** | 无追踪、无复盘，下次还是从零开始 | 购后助手负责归档 → 阶段 → 提醒 → 复盘 |

一句话：**不是问答机器人，是带记忆和持续跟踪的决策闭环。**

---

## 🌟 核心能力

### 🛒 购前顾问 —— 找货、取舍、排雷

`pre_purchase` 子智能体独立完成完整闭环：搜索实时商品 → 整理规格 → 按硬约束筛选 → 专业取舍 → 风险提示。
**零幻觉红线**：工具没返回的字段一律留空，宁可少推荐一款，也不编造一款。

### 📦 购后助手 —— 把决策沉淀下来

`post_purchase` 子智能体负责**购物档案**（归档 / 推进阶段 / 设提醒 / 写复盘）与**创建定时监控任务**。
说「帮我盯一下降到 1800」时，它真的会建出一条会跑的任务 —— 不是口头答应。

### 📋 采购规划 —— 一整套采购，不是一个商品

装修、搬家、开学这类**成套采购**：需求澄清 → 决策图实时生长 → 交付物（完整报告 / 采购清单 / 预算分配，**可导出 PDF**）。

### 🎁 代购送礼 —— 从「给谁买」开始

先建**人物档案**（关系 / 在意什么 / 送礼往来 / 禁忌），再据此选礼、搭组合、写祝福语。
礼盒组合与文案由 agent 逐步写出，不是固定模板。

### ⏰ 主动助理 —— 用户不在线时，系统替你盯着

定时任务命中 → 事件流 → 聚合为简报 / 情报流 / 待办。**全链路真实**：任务真的跑、结果真的推、卡片真的可点。

## 🖥️ 功能导航

| 区域 | 页面 | 说明 |
| --- | --- | --- |
| **主区** | 主页 `/agent` | 对话主界面：SSE 流式 + 思考过程 + 工具调用 + 编排状态 |
| | 主动助理 `/assistant` | 简报 / 情报流 / 待办，定时任务命中实时上报 |
| | 代购送礼 `/proxy` | 人物档案 → 选礼 → 交付，三栏工作台 |
| | 采购规划 `/planning` | 需求 → 决策图 → 交付物，可导出 PDF |
| | 购物档案 `/decisions` | 需求池 / 候选 / 已决策 / 使用中 / 已复盘 |
| **系统区** | 智能体管理 `/agents` | Agent 配置与模型绑定 |
| | 监控任务 `/tasks` | 定时任务 CRUD + 执行日志 + 价格历史曲线 |
| | MCP 数据源 `/mcps` | MCP 服务器管理与工具发现 |

---

## 🔎 架构

<!--
  ═══════════════════════════════════════════════════════════
  架构图占位：图片补好后，删掉本段注释的首尾两行即可显示。

  为什么用静态图而不是 Mermaid：调研 8 个标杆仓库（LangGraph / OpenHands /
  RAGFlow / FastGPT / crewAI 等），Mermaid 使用率 0/8 —— 它依赖客户端 JS
  渲染，在镜像站、爬虫、部分移动端看不到。可用 draw.io / Excalidraw 画好导出。
  ═══════════════════════════════════════════════════════════

<p align="center">
  <img src="docs/assets/architecture.png" alt="系统架构" width="100%">
</p>

-->

### 分层职责

```
┌─────────────┐   HTTP /api   ┌──────────────────────┐
│   web-v2    │ ────────────▶ │  FastAPI (server/)    │
│ (Vue 3,5173)│ ◀───── SSE ── │  :5050, uvicorn 单进程│
└─────────────┘               └──────────┬───────────┘
                                         │
                        ┌────────────────┼─────────────────┐
                        ▼                ▼                 ▼
              ┌────────────────┐ ┌────────────┐  ┌───────────────────┐
              │   PostgreSQL    │ │   Redis    │  │  外部系统          │
              │ (主真相存储)     │ │ (影子/加速) │  │ LLM · MCP 数据源   │
              │ 会话/用户/任务   │ │ 缓存/限流   │  │ (淘宝联盟/多多进宝) │
              └────────────────┘ └────────────┘  └───────────────────┘
```

### 主智能体的中间件栈

主智能体**不持有任何业务工具**，只负责编排 —— 业务能力全在子智能体。这让它可以被一层中间件链完整治理：

| # | 中间件 | 职责 |
| --- | --- | --- |
| 0 | `DynamicModelMiddleware` | 按请求动态切换模型 |
| 1 | `SSEMonitoringMiddleware` | 工具调用监控（最外层，捕获所有调用） |
| 2 | `ContentGuardMiddleware` | 内容安全审查 |
| 3 | `PatchToolCallsMiddleware` | 修复模型输出的工具调用格式 |
| 4 | `ToolResultOffloadMiddleware` | 大型工具结果卸载，避免撑爆上下文 |
| 5 | `ToolCallLimitMiddleware` | 调用次数限制（单轮 10 次 / 线程 20 次） |
| 6 | `TodoListMiddleware` | 任务拆解 |
| 7 | `FilesystemMiddleware` | 文件读写能力 |
| 8 | `SubAgentMiddleware` | 子智能体调度（以 Tool 形式暴露） |
| 9 | `ThinkingProcessMiddleware` | 思考过程提取，供前端可视化 |

---

## ⏰ 定时监控

主动助理的核心。7 类执行器，全部走真实数据源：

| 执行器 | 监控内容 | 触发条件 |
| --- | --- | --- |
| `price` | 商品价格 | 降至目标价，或 7 天跌幅 ≥5% |
| `stock` | 库存状态 | 缺货 → 有货（或反之）翻转 |
| `coupon` | 优惠券 | 出现异常大额券（> 商品价 50%） |
| `deal` | 优惠到期 | 券/活动即将失效 |
| `rank` | 榜单排名 | 变动 ≥3 位 |
| `shop` | 店铺活动 | 深度折扣（> 30%） |
| `agent` | AI 汇总 | 按 prompt 跑一次完整对话并汇报 |

**通知是克制的**：价格没变不推、排名微动不推 —— 每次都推「无变化」会让通知变成噪音。但**执行失败必推**：用户配了监控却悄悄不跑了，比不推更糟。

---

## 🔧 技术栈

| 层 | 技术 |
| --- | --- |
| **后端** | Python 3.12 · FastAPI ≥0.121 · LangChain ≥1.2 · LangGraph · SQLAlchemy(async) · APScheduler · uv |
| **前端** | Vue 3 · Vite 7 · Ant Design Vue 4 · ECharts 6 · AntV G6 5 · Sigma · Graphology · Less |
| **存储** | PostgreSQL（主真相，JSONB 事件溯源） · Redis（影子/缓存/限流） · Chroma（向量库） |
| **外部** | 多 LLM Provider · MCP（stdio，淘宝联盟 / 多多进宝） · 淘宝开放平台 |
| **部署** | Docker Compose · Nginx 反代 |

### 项目规模

| 项 | 数值 |
| --- | --- |
| 后端 | 447 个 Python 文件 / 约 5.4 万行 |
| 前端 | 158 个 Vue + JS 文件 / 约 4.2 万行 |
| 数据库表 | 19 张 |
| 注册工具 | 33 个 |
| 子智能体 | 2 个（购前 / 购后） |
| 独立 Agent | 2 个（采购规划 / 代购送礼） |
| 技能（SKILL.md） | 13 个 |

---

## 🚀 快速开始

### 前置条件

- Docker Engine + Docker Compose v2
- 至少一个可用的 LLM API Key（支持 OpenAI 兼容接口的均可）
- 可选：淘宝联盟 / 多多进宝的 MCP 凭据（用于真实商品数据）

### Option 1 · Docker 一键启动（推荐）

```bash
git clone https://github.com/LuFering/ShoppingClaw.git
cd ShoppingClaw
cp .env.template .env        # 填写 API Keys（至少一个 LLM）
docker compose up -d         # 启动 api + postgres + redis
docker compose ps            # 等待 api 变为 healthy
```

启动后：

- API 文档：http://localhost:5050/docs
- 健康检查：http://localhost:5050/api/system/health

**首次使用**需创建管理员：

```bash
curl -X POST http://localhost:5050/api/auth/initialize \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"your-password"}'
```

### Option 2 · 前端开发模式

后端跑在 Docker 里，前端本地热更新：

```bash
cd web-v2
npm ci
npm run dev                  # http://localhost:5173（/api 代理到 5050）
```

### Option 3 · 不用 Docker，直接跑后端

需要 Python 3.12+ 与 [uv](https://docs.astral.sh/uv/)，以及本机可达的 PostgreSQL / Redis：

```bash
uv sync
uv run --no-dev uvicorn server.main:app --host 0.0.0.0 --port 5050
```

> 注意：容器外的环境需自行保证 `.env` 里的 `POSTGRES_HOST` / `REDIS_URL` 指向可达地址
> （容器内用的是 compose 服务名 `postgres` / `redis`）。

> [!TIP]
> 代码以 bind mount 挂载进容器（`server/`、`src/`、`docs/`），**改代码只需重启 api 容器**，不必重建镜像：
> ```bash
> docker compose restart api
> ```

---

## ❓ FAQ

<details>
<summary><b>和 Dify / Coze / FastGPT 这类平台有什么区别？</b></summary>

那些是**通用 Agent 编排平台**，你用它搭任何应用；ShoppingClaw 是**垂直的电商决策系统**，开箱就是购物场景。

具体差异：
- **决策闭环而非问答**：购物档案五阶段状态机 + 定时监控，商品会被持续跟踪到「买了、用了、复盘了」
- **主从双层编排**：主智能体零业务工具（只编排），业务能力全在子智能体，避免主智能体被工具细节淹没
- **真实数据源**：通过 MCP 接入淘宝联盟/多多进宝，不是 mock
</details>

<details>
<summary><b>主智能体、子智能体、独立 Agent 三者怎么分工？</b></summary>

三层，各有明确边界：

| 角色 | 数量 | 职责 | 何时使用 |
| --- | --- | --- | --- |
| **主智能体** | 1 | 理解意图、编排调度、汇总输出。**不持有任何业务工具** | 所有对话的入口 |
| **子智能体** | 2 | 领域专家，以 Tool 形式被主智能体调用。购前找货取舍 / 购后归档监控 | 主智能体判断需要时派遣 |
| **独立 Agent** | 2 | 独立完整的图，**不经过主智能体**。采购规划 / 代购送礼 | 用户直接进入对应页面 |

为什么不全都做成子智能体？因为采购规划、代购送礼是**多轮长流程**（有自己的技能库、决策图、交付物），塞进对话里会被主智能体的单轮节奏切碎。
</details>

<details>
<summary><b>支持哪些 LLM？能本地跑吗？</b></summary>

任何 **OpenAI 兼容接口**的模型都可以：OpenAI、DeepSeek、通义千问、智谱、商汤、OpenRouter，以及 Ollama 本地模型。

在 `.env` 配置 provider 的 `base_url` 与 key，模型在「智能体管理」页按 Agent 分别绑定。**支持按请求切换模型**（`DynamicModelMiddleware`）。
</details>

<details>
<summary><b>数据存在哪里？会上传到云端吗？</b></summary>

**全部存在你自己的 PostgreSQL 里**，不经过任何第三方服务器：

- 会话消息：`conversations` 表（JSONB 事件溯源）
- 购物档案：`shopping_decisions` 表
- 定时任务：`task_records` + `task_execution_logs`
- 向量知识库：本地 Chroma

唯一的外部调用是你自己配置的 LLM API 与电商数据接口。
</details>

<details>
<summary><b>为什么用 MCP 而不是直接集成电商 SDK？</b></summary>

MCP（Model Context Protocol）把数据源变成**可插拔的独立进程**：

- **加数据源不用改代码**：新增一个 MCP server 即可，工具自动发现并注册
- **凭据隔离**：密钥在 MCP 子进程的环境变量里，不进主进程
- **故障隔离**：MCP 挂了不影响核心对话

项目早期确实直接集成过京东 SDK，但价格接口无授权、返回字段缺价格，最终整体下架改为 MCP。代码保留在 `src/jd/` 供参考。
</details>

---

## 📚 文档

| 我想… | 去哪里 |
| --- | --- |
| 先跑起来 | [快速开始](docs/intro/quick-start.md) |
| 了解系统全貌 | [项目概览](docs/intro/overview.md) |
| 看后端怎么分层 | [后端架构](docs/architecture/backend.md) |
| 理解数据怎么存 | [存储与持久化](docs/architecture/storage.md) |
| 对接接口 | [API 约定](docs/api/index.md) · [对话接口](docs/api/chat.md) |
| 改代码 | [后端指南](docs/development/backend-guide.md) · [前端指南](docs/development/frontend-guide.md) |
| 部署 / 排障 | [部署运维](docs/operations/deployment.md) · [故障手册](docs/operations/troubleshooting.md) |
| 全部文档导航 | [docs/index.md](docs/index.md) |

---

## 🤝 贡献

欢迎提交 Issue 与 PR。动手前请先读 [CONTRIBUTING.md](CONTRIBUTING.md) 与 [AGENTS.md](AGENTS.md)（后者是给 AI 编码助手与人类协作者的硬性规则，含架构铁律与高频修改点对照）。

```bash
# 开发环境
docker compose up -d          # 全栈启动（代码热重载）
docker compose logs -f api    # 看日志
```

---

## 📜 许可

[MIT License](LICENSE) © 2026 LuFering

### 致谢

实现参考了以下开源项目：

- [DeepAgents](https://github.com/langchain-ai/deepagents) —— Agent 中间件链与沙盒设计
- [LangGraph](https://github.com/langchain-ai/langgraph) —— 多智能体图编排
- [MCP](https://modelcontextprotocol.io/) 生态，电商数据源基于 [sinataoke](https://mcp.sinataoke.cn/docs)（淘宝联盟 / 多多进宝）

<div align="right"><a href="#shoppingclaw-购物抓虾">↑ 回到顶部</a></div>
