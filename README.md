<div align="center">

<img src="docs/assets/logo.png" alt="ShoppingClaw" width="200">

# ShoppingClaw

电商购物决策智能体。用自然语言提需求，系统负责找货、比价、取舍、归档、盯价。

[![License](https://img.shields.io/badge/license-MIT-178a67?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-3776ab?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3-42b883?style=flat-square&logo=vuedotjs&logoColor=white)](https://vuejs.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-1c3c3c?style=flat-square)](https://github.com/langchain-ai/langgraph)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.121+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)

[界面一览](#界面一览) · [快速开始](#快速开始) · [架构](#架构) · [文档](#文档) · [FAQ](#faq)

</div>

---

> [!WARNING]
> - 会调用真实电商联盟 API（淘宝联盟 / 多多进宝）和真实 LLM，密钥写进 `.env`，别提交。
> - 定时监控会周期性发外部请求，注意接口配额和平台规则。
> - 价格、库存来自第三方接口，下单前以平台页面为准。

## 这是什么

基于 LangGraph 的多智能体系统，覆盖购物的完整生命周期。

买之前，购前子智能体搜实时商品、整理规格、按预算和硬约束筛选，给出取舍建议和风险提示。工具没返回的字段一律留空——宁可少推一款，不编造一款。

买之后，购后子智能体把结论存进购物档案，按需建盯价任务、设提醒、写复盘。档案分五个阶段（需求池 → 候选中 → 已决策 → 使用中 → 已复盘），下次聊到同一件商品时它记得。

成套采购（装修、搬家、开学）和代购送礼是两个独立 Agent，各自有技能库和交付物，不走主对话。

商品数据通过 MCP 接入淘宝联盟和多多进宝，实时抓取。

## 快速开始

前置：Docker Engine + Docker Compose v2，以及至少一个 OpenAI 兼容的 LLM API Key。

```bash
git clone https://github.com/LuFering/ShoppingClaw.git
cd ShoppingClaw
cp .env.template .env        # 至少填一个 LLM key
docker compose up -d
docker compose ps            # 等 api 变成 healthy
```

API 文档 http://localhost:5050/docs，健康检查 http://localhost:5050/api/system/health。

首次启动数据库是空的，先建管理员：

```bash
curl -X POST http://localhost:5050/api/auth/initialize \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"your-password"}'
```

前端开发模式（后端仍在 Docker 里）：

```bash
cd web-v2
npm ci && npm run dev        # http://localhost:5173
```

不用 Docker 也行，需要本机 Python 3.12+ 和 uv：

```bash
uv sync
uv run --no-dev uvicorn server.main:app --host 0.0.0.0 --port 5050
```

`server/`、`src/`、`docs/` 是 bind mount 进容器的，改完代码 `docker compose restart api` 生效，不用重建镜像。

---

## 界面一览

六个主要界面，覆盖从提问到复盘的完整链路。

| 模块 | 解决什么 | 代表能力 |
| --- | --- | --- |
| [01 · 对话主界面](#01-对话主界面) | 一句话说清需求，剩下的交给系统 | 流式输出、思考可视化、商品卡片、随时打断 |
| [02 · 主动助理](#02-主动助理) | 用户不在线时，系统继续盯着 | 定时监控、命中通知、简报与待办 |
| [03 · 购物档案](#03-购物档案) | 买过什么、想到哪一步，不用记在脑子里 | 五阶段状态机、候选对比、提醒与复盘 |
| [04 · 采购规划](#04-采购规划) | 成套采购（装修、搬家）怎么拆 | 决策图实时生长、多份交付物、导出 PDF |
| [05 · 代购送礼](#05-代购送礼) | 给别人买，比给自己买难 | 人物档案、礼盒组合、祝福语 |
| [06 · 监控任务与数据源](#06-监控任务与数据源) | 在盯什么、数据从哪来 | 任务 CRUD、价格历史曲线、MCP 管理 |

### 01 · 对话主界面

主入口。提一个需求，主智能体判断该派哪个子智能体，然后把过程实时铺开——模型在想什么、调了什么工具、拿到什么结果，都在同一条时间线上。

- **流式输出与思考过程** —— SSE 推送，正文与思考分开展示。支持推理模型的 `reasoning_content`，思考是逐块冒出来的，不是最后一次性蹦出来
- **工具调用可视化** —— 每次调用显示参数、耗时、结果。商品卡片由购前子智能体的返回直接合成，不是从自由文本里二次抽取
- **随时打断与恢复** —— 跑到一半可以停；刷新页面能接回未完成的流，不丢上下文

<img src="docs/assets/shot-chat.png" alt="对话主界面">

<details>
<summary>展开更多截图：思考过程、工具调用、商品卡片</summary>

**思考过程**

模型推理按块流式展示，与正文交错出现。

<img src="docs/assets/shot-thinking.png" alt="思考过程">

**工具调用**

参数、耗时、返回结果都可以展开看。

<img src="docs/assets/shot-tools.png" alt="工具调用">

**商品卡片**

价格、店铺、券信息来自实时抓取。

<img src="docs/assets/shot-cards.png" alt="商品卡片">

</details>

### 02 · 主动助理

用户不在线的时候，系统继续跑。定时任务命中后，结果进事件流，再聚合成简报、情报流和待办。

- **七类监控执行器** —— 降价、库存、优惠券、优惠到期、榜单排名、店铺活动、AI 汇总
- **通知是克制的** —— 价格没变不推、排名微动不推；但执行失败一定推，配了监控却悄悄不跑了比不推更糟
- **命中可回溯** —— 每条通知能查到是哪次执行产生的，可跳转到任务或档案

<img src="docs/assets/shot-assistant.png" alt="主动助理">

### 03 · 购物档案

每个想法从「先记下来」到「用完了复盘」的完整轨迹。五个阶段：需求池 → 候选中 → 已决策 → 使用中 → 已复盘。

- **需求可逐步补全** —— 刚记下时可能只有一句话，之后慢慢补上预算、给谁买、什么场景
- **候选对比** —— 同一条需求下挂多个候选，标出选了哪个、为什么
- **提醒与复盘** —— 使用中的记录可以挂提醒（换耗材、保修到期），买完可以写使用感受

<img src="docs/assets/shot-decisions.png" alt="购物档案">

### 04 · 采购规划

装修、搬家、开学这类成套采购。需求澄清后，决策图随执行过程长出来，最后产出可导出的交付物。

- **决策图实时生长** —— 每跑完一步，节点和连线就多一条。不是跑完才画
- **交付物分四类** —— 完整报告、采购清单、对比表、预算分配，内容各不相同
- **可导出** —— 报告支持 Markdown 和 PDF，清单支持 CSV

<img src="docs/assets/shot-planning.png" alt="采购规划">

<details>
<summary>展开更多截图：决策图、交付物</summary>

**决策图**

节点按品类归纳，可缩放拖拽。

<img src="docs/assets/shot-graph.png" alt="决策图">

**交付物**

报告正文、清单、预算表都可就地预览。

<img src="docs/assets/shot-deliverables.png" alt="交付物">

</details>

### 05 · 代购送礼

给别人买东西，难在不知道对方要什么。这个界面先建人物档案，再据此选礼。

- **人物档案** —— 关系、在意什么、送礼往来、禁忌，由 agent 从对话里逐步提取，可以逐条确认或修改
- **礼盒组合** —— 主礼 + 搭配，不是单件推荐
- **祝福语** —— 结合人物档案写，不是套模板

<img src="docs/assets/shot-gift.png" alt="代购送礼">

### 06 · 监控任务与数据源

定时任务的配置面板，以及 MCP 数据源的管理。

- **任务管理** —— 创建、暂停、手动触发，看执行日志
- **价格历史** —— 每次执行落一条快照，可看折线图
- **MCP 管理** —— 数据源作为独立进程接入，加数据源不用改代码，凭据留在子进程里

<img src="docs/assets/shot-tasks.png" alt="监控任务">

---

## 架构

<p align="center">
  <img src="docs/assets/architecture.png" alt="系统架构" width="100%">
</p>

前端 Vue 3，后端 FastAPI 单进程，PostgreSQL 存会话/用户/任务/档案，Redis 做缓存和限流，Chroma 存向量知识库。

### 主智能体和它的中间件

主智能体不持有任何业务工具——搜索、出卡、归档都在子智能体里。它只做三件事：理解意图、派发子智能体、汇总结果。所以身上可以挂一层完整的中间件链，每层管一件事：

| 顺序 | 中间件 | 作用 |
| --- | --- | --- |
| 0 | `DynamicModelMiddleware` | 按请求切模型 |
| 1 | `SSEMonitoringMiddleware` | 捕获所有工具调用，供前端展示 |
| 2 | `ContentGuardMiddleware` | 内容安全审查 |
| 3 | `PatchToolCallsMiddleware` | 修模型输出的工具调用格式 |
| 4 | `ToolResultOffloadMiddleware` | 大结果卸载，避免撑爆上下文 |
| 5 | `ToolCallLimitMiddleware` | 调用次数限制（单轮 10 次 / 线程 20 次） |
| 6 | `TodoListMiddleware` | 任务拆解 |
| 7 | `FilesystemMiddleware` | 文件读写 |
| 8 | `SubAgentMiddleware` | 子智能体调度 |
| 9 | `ThinkingProcessMiddleware` | 提取思考过程，前端可视化 |

### 三层 Agent

| | 数量 | 职责 | 入口 |
| --- | --- | --- | --- |
| 主智能体 | 1 | 理解意图、编排、汇总。不持有业务工具 | 所有对话 |
| 子智能体 | 2 | 购前找货取舍 / 购后归档盯价，以 Tool 形式被调用 | 主智能体按需派发 |
| 独立 Agent | 2 | 采购规划 / 代购送礼，有各自的图和技能库 | 用户直接进页面 |

采购规划和代购送礼没做成子智能体，因为它们是长流程（多轮澄清、决策图、多份交付物），塞进对话会被主智能体的单轮节奏切碎。

### 定时监控

| 执行器 | 监控什么 | 什么时候通知 |
| --- | --- | --- |
| `price` | 商品价格 | 降到目标价，或 7 天跌超 5% |
| `stock` | 库存 | 缺货 ↔ 有货 状态翻转 |
| `coupon` | 优惠券 | 出现超过商品价 50% 的大额券 |
| `deal` | 优惠到期 | 券或活动快失效 |
| `rank` | 榜单排名 | 变动 3 位以上 |
| `shop` | 店铺活动 | 折扣超过 30% |
| `agent` | AI 汇总 | 按 prompt 跑一轮完整对话 |

### 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.12 · FastAPI · LangChain / LangGraph · SQLAlchemy(async) · APScheduler · uv |
| 前端 | Vue 3 · Vite 7 · Ant Design Vue 4 · ECharts 6 · AntV G6 5 · Sigma · Graphology |
| 存储 | PostgreSQL（主，JSONB 事件溯源） · Redis（缓存 / 限流） · Chroma（向量库） |
| 外部 | 多 LLM Provider · MCP（淘宝联盟 / 多多进宝） |
| 部署 | Docker Compose · Nginx |

规模：后端 447 个 Python 文件约 5.4 万行，前端 158 个文件约 4.2 万行，19 张表，33 个注册工具，13 个技能。

---

## 文档

| 我想… | 去哪 |
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

## FAQ

<details>
<summary>和 Dify / Coze / FastGPT 有什么区别？</summary>

那些是通用 Agent 编排平台，用来搭任何应用；这个是垂直的电商系统，开箱就是购物场景。

差别主要在两处：购物档案有五阶段状态机，商品会被跟踪到「买了、用了、复盘了」；定时监控持续盯价，用户不在线也在跑。这两套在通用平台上要自己搭。
</details>

<details>
<summary>支持哪些模型？能本地跑吗？</summary>

任何 OpenAI 兼容接口的都可以：OpenAI、DeepSeek、通义千问、智谱、商汤、OpenRouter，Ollama 本地模型也行。

在 `.env` 配 provider 的 `base_url` 和 key，然后在「智能体管理」页给每个 Agent 分别绑定。也支持按请求临时切模型。
</details>

<details>
<summary>数据存在哪？会上传到云端吗？</summary>

全部在你自己的 PostgreSQL 里，不经过第三方服务器：

- 会话消息 `conversations`
- 购物档案 `shopping_decisions`
- 定时任务 `task_records` / `task_execution_logs`
- 向量库本地 Chroma

唯一的外部调用是你自己配的 LLM API 和电商数据接口。
</details>

<details>
<summary>为什么用 MCP 而不是直接集成电商 SDK？</summary>

MCP 把数据源做成可插拔的独立进程：加数据源不用改代码，凭据留在子进程的环境变量里不进主进程，MCP 挂了也不影响核心对话。

早期确实直接集成过京东 SDK，但价格接口无授权、返回字段里没有价格，最后整体下架改成 MCP。代码还留在 `src/jd/` 供参考。
</details>

---

## 贡献

欢迎提 Issue 和 PR。动手前先读 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [AGENTS.md](AGENTS.md)——后者是给 AI 编码助手与人类协作者的硬性规则，含架构铁律和高频修改点对照。

```bash
docker compose up -d          # 全栈启动，代码热重载
docker compose logs -f api    # 看日志
```

---

## 许可

[MIT License](LICENSE) © 2026 LuFering

致谢：

- [DeepAgents](https://github.com/langchain-ai/deepagents) —— Agent 中间件链与沙盒设计
- [LangGraph](https://github.com/langchain-ai/langgraph) —— 多智能体图编排
- [MCP](https://modelcontextprotocol.io/) 生态，电商数据源基于 [sinataoke](https://mcp.sinataoke.cn/docs)（淘宝联盟 / 多多进宝）

<div align="right"><a href="#shoppingclaw">↑ 回到顶部</a></div>
