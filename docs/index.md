# ShoppingClaw 团队文档

ShoppingClaw（智能购物助手）的完整开发资料库。按阅读场景组织：

| 场景 | 入口 |
| --- | --- |
| 我还没跑起来过 | [快速开始](intro/quick-start.md) |
| 我想了解系统全貌 / 能做什么 | [项目概览](intro/overview.md) |
| 我要看后端代码 | [后端架构](architecture/backend.md) |
| 我想理解数据怎么存、怎么保证不丢 | [存储与持久化](architecture/storage.md) |
| 我要对接/调试接口 | [API 通用约定](api/index.md) → [对话接口](api/chat.md) |
| 我要加新功能、改代码 | [后端开发指南](development/backend-guide.md) / [前端开发指南](development/frontend-guide.md) |
| 我要部署 / 排查线上问题 | [部署运维](operations/deployment.md) / [故障手册](operations/troubleshooting.md) |

## 文档目录

```text
docs/
├── index.md                     # 本页（导航）
├── intro/
│   ├── overview.md              # 项目概览：背景、能力、术语
│   └── quick-start.md           # 快速开始：环境、启动、环境变量
├── architecture/
│   ├── backend.md               # 后端分层、生命周期、模块地图、Agent 系统
│   └── storage.md               # 存储架构与对话持久化（重点必读）
├── api/
│   ├── index.md                 # API 约定：认证、错误、限流、SSE 基础
│   ├── chat.md                  # 对话/线程/会话/记忆/历史（含 SSE 协议）
│   ├── auth.md                  # 认证接口
│   ├── models.md                # 模型配置管理
│   ├── tasks.md                 # 定时任务
│   └── system.md                # 系统端点
├── development/
│   ├── backend-guide.md         # 后端开发指南（分层/规范/加接口步骤）
│   └── frontend-guide.md        # 前端开发指南（web-v2）
└── operations/
    ├── deployment.md            # Docker 部署 / 升级 / 备份恢复
    └── troubleshooting.md       # 常见故障排查手册
```

## 文档维护规范

- 所有文档使用中文；代码标识符、命令保持原文。
- 文档必须与代码事实一致：接口文档以 `server/routers/` 与 `docs/api/` 为准，
  `src/` 行为描述以实际实现为准；发现不一致时**先改文档，或先改代码并同步文档**。
- 新增/修改 API 时，必须同步更新 `docs/api/` 对应文件（OpenAPI 可在
  `http://<host>:5050/docs` 查看字段级 schema，docs 负责语义与调用约定）。
- 故障处理经验请沉淀到 `operations/troubleshooting.md`，供团队复用。
