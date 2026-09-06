# ShoppingClaw Docker 部署指南

## 前置要求

1. **Docker & Docker Compose**：确保已安装 Docker Desktop (Windows/Mac) 或 Docker Engine + Docker Compose (Linux)
2. **Ollama**：项目依赖本地 Ollama 服务提供大模型能力
   - 安装：https://ollama.com/
   - 启动服务：`ollama serve`
   - 默认地址：`http://127.0.0.1:11434`

## 快速开始

### 1. 环境配置

```bash
# 复制环境配置模板
cp .env.template .env

# 编辑 .env 文件，填写必要的 API Keys
```

### 2. 配置 Ollama

**Windows：**

```powershell
# 拉取项目所需模型
ollama pull qwen2.5:3b

# 配置监听地址（Docker 容器通过 host.docker.internal 访问）
$env:OLLAMA_HOST = "0.0.0.0:11434"
ollama serve

# 验证监听地址
netstat -ano | findstr "11434.*LISTENING"
# 应显示：TCP 0.0.0.0:11434 ... LISTENING
```

**验证连通性：**
```bash
# 宿主机测试
curl http://localhost:11434/api/tags

# Docker 容器内测试
docker-compose exec api curl http://host.docker.internal:11434/api/tags
```

### 3. 启动服务

```bash
# 构建并启动所有服务（API + PostgreSQL + Redis）
docker-compose up -d

# 查看日志
docker-compose logs -f api

# 停止服务
docker-compose down
```

访问：
- API：http://localhost:5050
- API 文档：http://localhost:5050/docs

### 4. 生产环境

```bash
docker-compose -f docker-compose.prod.yml up -d
```

## 架构说明

### 服务组成

| 服务 | 镜像 | 端口 | 说明 |
|------|------|------|------|
| api | shoppingclaw-api:latest | 5050 | FastAPI 后端 |
| postgres | postgres:16 | 5432 | 业务数据 + Checkpointer |
| redis | redis:7-alpine | 6379 | 消息存储 / 速率限制 / 缓存 |

### 数据持久化

```
docker/volumes/
├── postgresql/    # PostgreSQL 数据
└── redis/         # Redis 持久化 (AOF)
```

### 网络通信

- 容器间通过 `app-network` 通信
- API 通过 `host.docker.internal` 访问宿主机 Ollama
- 外部通过 `localhost:5050` 访问 API

## 常见问题

### 1. Ollama 连接失败

**症状**：API 报错 `httpx.ConnectError`

**诊断**：
```bash
# 检查 Ollama 是否运行
ollama list
# 检查监听地址
netstat -ano | findstr "11434.*LISTENING"
# 测试容器内访问
docker-compose exec api curl http://host.docker.internal:11434/api/tags
```

**解决**：确保设置了 `OLLAMA_HOST=0.0.0.0:11434`（参考上方配置步骤）。

### 2. 数据库连接失败

**诊断**：
```bash
docker-compose ps postgres      # 应显示 "Up (healthy)"
docker-compose logs postgres    # 查看 PostgreSQL 日志
```

**解决**：
```bash
# 首次启动数据库初始化需要时间，等待健康检查通过
docker-compose logs -f postgres
# 看到 "database system is ready to accept connections" 后继续
docker-compose restart api
```

### 3. Agent 初始化失败

**症状**：报错 `'NoneType' object has no attribute 'astream'`

**解决**：
```bash
# 查看完整日志
docker-compose logs api | tail -n 50

# 重新构建
docker-compose down
docker-compose up -d --build api
```

### 4. 首次启动慢

**原因**：需要下载镜像、安装 Python 依赖、加载 Ollama 模型。

**加速建议**：
```bash
# 预热 Ollama 模型
ollama run qwen2.5:3b <<< "hello"

# 使用国内镜像加速（已在 Dockerfile 中配置清华源）
```

### 5. 修改代码不生效

**开发模式**：代码通过 volume 挂载，修改后自动生效（使用 uvicorn --reload）。

**生产模式**：需要重新构建镜像：
```bash
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml up -d
```

## 开发工作流

```bash
# 仅启动基础设施
docker-compose up -d postgres redis

# 本地运行 API（便于调试）
uv run uvicorn server.main:app --reload

# 容器内运行
docker-compose up -d api
```

### 调试

```bash
docker exec -it shoppingclaw-api bash    # 进入容器
docker-compose logs -f api               # 实时日志
docker-compose logs --since 10m api      # 最近 10 分钟日志
docker-compose restart api               # 重启
```

## 清理与维护

```bash
# 停止并删除容器和网络
docker-compose down

# 删除所有数据卷（⚠️ 会丢失数据）
docker-compose down -v

# 清理未使用镜像
docker image prune -a
```

### 备份数据

```bash
# 备份 PostgreSQL
docker exec shoppingclaw-postgres pg_dump -U postgres shoppingclaw > backup.sql

# 备份整个数据目录
tar -czf docker-volumes-backup.tar.gz docker/volumes/
```

## 高级配置

### 自定义端口

编辑 `docker-compose.yml`：
```yaml
services:
  api:
    ports:
      - "8080:5050"  # 外部端口改为 8080
```

### 使用远程 Ollama

编辑 `.env`：
```env
OLLAMA_BASE_URL=http://your-ollama-server:11434
```

### 资源限制

编辑 `docker-compose.yml`：
```yaml
services:
  api:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '1.0'
```

## 健康检查

项目已配置健康检查，相关参数：

| 服务 | interval | timeout | retries | start_period |
|------|----------|---------|---------|-------------|
| api | 60s | 15s | 5 | 120s |
| postgres | 5s | 3s | 30 | — |
| redis | 10s | 5s | 10 | — |

## Ollama 性能优化

**首次调用慢**（8-10 秒模型加载）：
```bash
# 预热模型
ollama run qwen2.5:3b <<< "hello"
```

**推理速度**：
- `qwen2.5:3b` CPU 推理约 3 tokens/秒
- 如有 GPU，确保 Ollama 启用 CUDA/ROCm 加速
