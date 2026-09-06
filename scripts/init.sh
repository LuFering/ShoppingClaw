#!/bin/bash
# ShoppingClaw 初始化脚本 (Linux/Mac)
# 用途: 帮助新人快速配置开发环境

set -e  # 遇到错误立即退出

echo "========================================"
echo "  ShoppingClaw 环境初始化"
echo "========================================"
echo ""

# 检查1: Docker
echo "[1/5] 检查 Docker..."
if command -v docker &> /dev/null; then
    docker_version=$(docker --version)
    echo "  ✓ Docker 已安装: $docker_version"
else
    echo "  ✗ Docker 未安装"
    echo "  请安装 Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# 检查2: Ollama
echo ""
echo "[2/5] 检查 Ollama..."
if command -v ollama &> /dev/null; then
    ollama_version=$(ollama --version)
    echo "  ✓ Ollama 已安装: $ollama_version"
    
    # 检查 Ollama 监听地址
    echo "  ⚙ 检查 Ollama 监听配置..."
    if netstat -tuln 2>/dev/null | grep -q "0.0.0.0:11434"; then
        echo "  ✓ Ollama 监听所有接口 (0.0.0.0:11434)"
    elif netstat -tuln 2>/dev/null | grep -q "127.0.0.1:11434"; then
        echo "  ⚠ Ollama 仅监听本地 (127.0.0.1:11434)"
        echo "  ⚠ Docker 容器可能无法访问!"
        echo ""
        echo "  建议配置:"
        echo "  1. 停止当前 Ollama 服务"
        echo "  2. 设置环境变量: export OLLAMA_HOST=0.0.0.0:11434"
        echo "  3. 重新启动: ollama serve"
        echo ""
        read -p "  是否继续? (y/n): " continue_choice
        if [ "$continue_choice" != "y" ]; then
            exit 0
        fi
    else
        echo "  ✗ Ollama 未监听 11434 端口"
        echo "  请启动 Ollama: ollama serve"
        exit 1
    fi
else
    echo "  ✗ Ollama 未安装"
    echo "  请安装 Ollama: https://ollama.com/"
    exit 1
fi

# 检查3: 环境变量文件
echo ""
echo "[3/5] 检查环境变量配置..."
if [ -f ".env" ]; then
    echo "  ✓ .env 文件已存在"
else
    echo "  ⚙ 从模板创建 .env 文件..."
    cp .env.template .env
    echo "  ✓ 已创建 .env 文件"
    echo "  ⚠ 请编辑 .env 文件,确认以下配置:"
    echo "     - OLLAMA_BASE_URL=http://host.docker.internal:11434"
fi

# 检查4: Ollama 模型
echo ""
echo "[4/5] 检查 Ollama 模型..."
if ollama list | grep -q "qwen2.5:3b"; then
    echo "  ✓ 模型 qwen2.5:3b 已存在"
else
    echo "  ⚙ 下载模型 qwen2.5:3b (约 2GB,请耐心等待)..."
    ollama pull qwen2.5:3b
    if [ $? -eq 0 ]; then
        echo "  ✓ 模型下载完成"
    else
        echo "  ✗ 模型下载失败"
        exit 1
    fi
fi

# 检查5: Docker Compose 服务
echo ""
echo "[5/5] 启动 Docker 服务..."
if docker-compose ps --services --filter "status=running" | grep -q "api"; then
    echo "  ✓ API 服务已在运行"
else
    echo "  ⚙ 启动所有服务 (API + PostgreSQL + Redis)..."
    docker-compose up -d
    
    echo "  ⚙ 等待服务健康检查..."
    max_attempts=30
    attempt=0
    while [ $attempt -lt $max_attempts ]; do
        sleep 5
        health_status=$(docker-compose ps api --format json 2>/dev/null | python3 -c "import sys, json; print(json.load(sys.stdin)['Status'])" 2>/dev/null || echo "")
        if [[ "$health_status" == *"healthy"* ]]; then
            echo "  ✓ 所有服务启动成功"
            break
        fi
        attempt=$((attempt + 1))
        echo "  ... 等待中 ($attempt/$max_attempts)"
    done
    
    if [ $attempt -eq $max_attempts ]; then
        echo "  ⚠ 服务启动超时,请查看日志: docker-compose logs -f api"
    fi
fi

# 完成
echo ""
echo "========================================"
echo "  初始化完成!"
echo "========================================"
echo ""
echo "下一步操作:"
echo "  1. 查看实时日志: docker-compose logs -f api"
echo "  2. 测试 API: curl http://localhost:5050/api/system/health"
echo "  3. 发送测试请求:"
echo '     curl -X POST http://localhost:5050/api/chat/agent/MainAgent \'
echo '       -H "Content-Type: application/json" \'
echo '       -d "{\"query\": \"你好\", \"thread_id\": \"test-001\"}"'
echo ""
echo "文档参考:"
echo "  - DOCKER_DEPLOYMENT.md"
echo "  - docs/SHOPPING_CLAW_DEV_GUIDE.md"
echo ""
