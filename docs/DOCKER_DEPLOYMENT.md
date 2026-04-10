# ShoppingClaw Docker 部署指南

## 📋 前置要求

1. **Docker & Docker Compose**: 确保已安装 Docker Desktop (Windows/Mac) 或 Docker Engine + Docker Compose (Linux)
2. **Ollama**: 项目依赖本地 Ollama 服务提供大模型能力
   - 安装: https://ollama.com/
   - 启动服务: `ollama serve`
   - 默认地址: `http://127.0.0.1:11434`

## 🚀 快速开始

### 1. 环境配置

```bash
# 复制环境配置模板
cp .env.template .env

# 编辑 .env 文件,填写必要的 API Keys
# 至少需要配置:
# - SILICONFLOW_API_KEY (或使用其他模型提供商)
# - TAVILY_API_KEY (搜索服务,可选)
```

### 2. 启动 Ollama 服务

**Windows:**
```powershell
# 在后台启动 Ollama
ollama serve

# 拉取项目所需模型
ollama pull qwen2.5:3b
```

**重要配置**:
1. **确保 Ollama 服务在启动 Docker 容器前已经运行**
2. **配置监听地址**(Docker 容器需要通过 `host.docker.internal` 访问):
   ```powershell
   # 停止当前 Ollama 服务
   # (在系统托盘中退出或任务管理器结束进程)
   
   # 设置环境变量,允许所有接口访问
   $env:OLLAMA_HOST = "0.0.0.0:11434"
   
   # 重新启动
   ollama serve
   
   # 验证监听地址
   netstat -ano | findstr "11434.*LISTENING"
   # 应该看到: TCP 0.0.0.0:11434 ... LISTENING
   ```
3. **测试连通性**:
   ```powershell
   # 从宿主机测试
   curl http://localhost:11434/api/tags
   
   # 从 Docker 容器内测试
   docker-compose exec api curl http://host.docker.internal:11434/api/tags
   ```

### 3. 启动开发环境

```bash
# 构建并启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f api

# 停止服务
docker-compose down
```

访问 API: http://localhost:5050

### 4. 启动生产环境

```bash
# 使用生产配置
docker-compose -f docker-compose.prod.yml up -d

# 查看日志
docker-compose -f docker-compose.prod.yml logs -f api
```

## 🏗️ 架构说明

### 服务组成

**开发环境 (docker-compose.yml):**
- `api`: FastAPI 后端服务 (端口 5050)
- `postgres`: PostgreSQL 数据库 (端口 5432)
- `redis`: Redis 缓存 (端口 6379)

**生产环境 (docker-compose.prod.yml):**
- 相同的服务,但去除了代码挂载和热重载

### 数据持久化

所有数据存储在 `docker/volumes/` 目录:
```
docker/volumes/
├── postgresql/    # PostgreSQL 数据
└── redis/         # Redis 数据
```

### 网络通信

- 容器间通过 `app-network` 网络通信
- API 容器通过 `host.docker.internal` 访问宿主机的 Ollama 服务
- 外部通过 localhost:5050 访问 API

## 🔧 常见问题

### 1. Ollama 连接失败

**症状**: API 报错 `httpx.ConnectError: All connection attempts failed`

**诊断步骤**:
```bash
# 1. 检查 Ollama 是否运行
ollama list

# 2. 检查监听地址
netstat -ano | findstr "11434.*LISTENING"
# 应该看到 0.0.0.0:11434,如果是 127.0.0.1:11434 需要重新配置

# 3. 测试从容器内访问
docker-compose exec api curl http://host.docker.internal:11434/api/tags
```

**解决方案**:
```bash
# Windows/Mac: 确保设置了 OLLAMA_HOST=0.0.0.0:11434
# 参考上方"启动 Ollama 服务"章节的配置步骤

# Linux: 需要添加 extra_hosts 配置或使用 --network=host

# 验证 .env 中的配置
grep OLLAMA_BASE_URL .env
# 应该输出: OLLAMA_BASE_URL=http://host.docker.internal:11434
```

### 2. 数据库连接失败

**症状**: API 启动时报告 PostgreSQL 连接错误或日志显示 `Database not available`

**诊断步骤**:
```bash
# 1. 检查 PostgreSQL 容器状态
docker-compose ps postgres
# 应该看到 STATUS 为 "Up (healthy)"

# 2. 查看 PostgreSQL 日志
docker-compose logs postgres

# 3. 测试数据库连接
docker-compose exec postgres pg_isready -U postgres -d shoppingclaw
```

**解决方案**:
```bash
# 等待数据库完全启动(首次启动可能需要 30-60 秒)
docker-compose logs -f postgres
# 看到 "database system is ready to accept connections" 后继续

# 如果仍然失败,重启 API 服务
docker-compose restart api

# 检查健康检查状态
docker inspect shoppingclaw-postgres | grep -A 10 Health
```

### 3. Agent 初始化失败

**症状**: 报错 `'NoneType' object has no attribute 'astream'` 或 `ModuleNotFoundError`

**原因**: Agent 的 graph 未正确初始化或缺少依赖

**解决方案**:
```bash
# 1. 查看完整错误日志
docker-compose logs api | tail -n 50

# 2. 检查代码是否正确挂载(开发模式)
docker-compose exec api ls -la /app/src/agents/master_agent/

# 3. 重启 API 服务
docker-compose restart api

# 4. 如果问题持续,重新构建镜像
docker-compose down
docker-compose up -d --build api
```

### 4. 首次启动很慢

**原因**: 需要下载 Docker 镜像、安装 Python 依赖、加载 Ollama 模型

**解决方案**:
```bash
# 预先拉取基础镜像
docker pull python:3.12-slim
docker pull postgres:16
docker pull redis:7-alpine

# 预热 Ollama 模型(避免首次调用慢)
ollama run qwen2.5:3b <<< "hello"

# 使用国内镜像加速(已在 Dockerfile 中配置清华源)
```

### 5. 修改代码后不生效

**开发模式**: 代码通过 volume 挂载,修改后自动生效(需重启 uvicorn)

**生产模式**: 需要重新构建镜像
```bash
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml up -d
```

## 📝 开发工作流

### 日常开发

```bash
# 1. 启动基础设施
docker-compose up -d postgres redis

# 2. 本地运行 API (便于调试)
uv run uvicorn server.main:app --reload

# 3. 或者在容器中运行
docker-compose up -d api
```

### 调试技巧

```bash
# 进入 API 容器
docker exec -it shoppingclaw-api bash

# 查看实时日志
docker-compose logs -f api

# 查看特定时间范围的日志
docker-compose logs --since 10m api

# 重启单个服务
docker-compose restart api
```

## 🧹 清理与维护

### 清理未使用的资源

```bash
# 停止并删除所有容器、网络
docker-compose down

# 删除卷(会丢失数据!)
docker-compose down -v

# 清理未使用的镜像
docker image prune -a
```

### 备份数据

```bash
# 备份 PostgreSQL 数据
docker exec shoppingclaw-postgres pg_dump -U postgres shoppingclaw > backup.sql

# 备份整个数据目录
tar -czf docker-volumes-backup.tar.gz docker/volumes/
```

## ⚙️ 高级配置

### 自定义端口

编辑 `docker-compose.yml`:
```yaml
services:
  api:
    ports:
      - "8080:5050"  # 将外部端口改为 8080
```

### 使用远程 Ollama

编辑 `.env`:
```env
OLLAMA_BASE_URL=http://your-ollama-server:11434
```

### 增加资源限制

编辑 `docker-compose.yml`:
```yaml
services:
  api:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '1.0'
```

## 📊 性能优化建议

### 健康检查调优

项目已配置健康检查机制,相关参数在 `docker-compose.yml` 中:
```yaml
healthcheck:
  interval: 60s      # 每 60 秒检查一次
  timeout: 15s       # 超时时间
  retries: 5         # 重试次数
  start_period: 120s # 启动宽限期(此期间失败不计入重试)
```

**作用**:
- Docker 自动监控服务健康状态
- 服务异常时自动重启(`restart: unless-stopped`)
- `docker-compose ps` 可查看健康状态

**调整建议**:
- 开发环境: 保持默认配置
- 生产环境: 可根据实际情况调整 `interval` 和 `retries`

### Ollama 性能优化

**问题**: 首次调用慢(8-10秒模型加载时间)

**解决**:
```bash
# 启动后立即预热模型
ollama run qwen2.5:3b <<< "hello"

# 后续调用速度会显著提升(模型已缓存到内存)
```

**推理速度慢**:
- `qwen2.5:3b` CPU 推理约 3 tokens/秒
- 如有 GPU,确保 Ollama 启用 CUDA/ROCm 加速
- 可尝试更大模型: `ollama pull qwen2.5:7b`(需要更多显存)

## 📞 技术支持

遇到问题?

1. **检查日志**: `docker-compose logs -f api`
2. **验证服务状态**: `docker-compose ps`
3. **查看健康检查**: `docker inspect <container_name>`
4. **测试 Ollama 连通性**: `docker-compose exec api curl http://host.docker.internal:11434/api/tags`
5. **参考项目文档**: `docs/SHOPPING_CLAW_DEV_GUIDE.md`
