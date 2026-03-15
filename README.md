# ShoppingClaw

Deep Agents Shopping Agent - 智能购物助手

## 项目结构

```
ShoppingClaw/
├── app/                     # 应用入口
│   ├── main.py             # FastAPI 主应用
│   └── web/
│       └── streamlit_app.py # Streamlit Web 界面
├── agents/                  # Agent 定义
│   ├── main_agent.py       # 主 Agent
│   ├── research_agent.py   # 研究 Agent
│   ├── analysis_agent.py   # 分析 Agent
│   └── recommendation_agent.py  # 推荐 Agent
├── tools/                   # Agent 工具
│   ├── search_tools.py     # 搜索工具
│   ├── analysis_tools.py   # 分析工具
│   ├── compare_tools.py    # 对比工具
│   └── memory_tools.py     # 记忆工具
├── scrapers/                # 电商爬虫
│   ├── jd_scraper.py       # 京东爬虫
│   ├── taobao_scraper.py   # 淘宝爬虫
│   └── pdd_scraper.py      # 拼多多爬虫
├── computer/                # OpenClaw 能力
│   ├── browser_controller.py    # 浏览器控制器
│   └── desktop_controller.py    # 桌面控制器
├── middleware/              # 中间件
│   ├── logging.py          # 日志中间件
│   └── retry.py            # 重试中间件
├── infra/                   # 基础设施
│   ├── llm_provider.py     # LLM 提供者
│   ├── vector_store.py     # 向量存储
│   └── config.py           # 配置管理
├── workspace/               # Agent 文件系统
├── tests/                   # 测试文件
├── requirements.txt         # 依赖列表
└── README.md               # 项目说明
```

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行 API 服务

```bash
cd app
uvicorn main:app --reload
```

### 运行 Web 界面

```bash
cd app/web
streamlit run streamlit_app.py
```

## 功能特性

- 🤖 多 Agent 协作系统
- 🔍 跨平台商品搜索（京东、淘宝、拼多多）
- 📊 智能数据分析与对比
- 💡 AI 驱动的商品推荐
- 🖥️ OpenClaw 浏览器自动化能力
- 💾 持久化记忆存储

## 开发中

本项目框架已搭建完成，具体功能实现正在进行中...

## License

MIT License
