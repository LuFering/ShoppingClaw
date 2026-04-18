# ShoppingClaw 初始化脚本 (Windows PowerShell)
# 用途: 帮助新人快速配置开发环境

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  ShoppingClaw 环境初始化" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查1: Docker Desktop
Write-Host "[1/5] 检查 Docker Desktop..." -ForegroundColor Yellow
try {
    $dockerVersion = docker --version
    Write-Host "  ✓ Docker 已安装: $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Docker 未安装或未启动" -ForegroundColor Red
    Write-Host "  请安装 Docker Desktop: https://www.docker.com/products/docker-desktop/" -ForegroundColor Red
    exit 1
}

# 检查2: Ollama
Write-Host "`n[2/5] 检查 Ollama..." -ForegroundColor Yellow
try {
    $ollamaVersion = ollama --version
    Write-Host "  ✓ Ollama 已安装: $ollamaVersion" -ForegroundColor Green
    
    # 检查 Ollama 监听地址
    Write-Host "  ⚙ 检查 Ollama 监听配置..." -ForegroundColor Cyan
    $listeningAddresses = netstat -ano | Select-String ":11434.*LISTENING"
    if ($listeningAddresses -match "0\.0\.0\.0:11434") {
        Write-Host "  ✓ Ollama 监听所有接口 (0.0.0.0:11434)" -ForegroundColor Green
    } elseif ($listeningAddresses -match "127\.0\.0\.1:11434") {
        Write-Host "  ⚠ Ollama 仅监听本地 (127.0.0.1:11434)" -ForegroundColor Yellow
        Write-Host "  ⚠ Docker 容器可能无法访问!" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  建议配置:" -ForegroundColor Cyan
        Write-Host "  1. 停止当前 Ollama 服务" -ForegroundColor White
        Write-Host "  2. 设置环境变量: `$env:OLLAMA_HOST = '0.0.0.0:11434'" -ForegroundColor White
        Write-Host "  3. 重新启动: ollama serve" -ForegroundColor White
        Write-Host ""
        $continue = Read-Host "  是否继续? (y/n)"
        if ($continue -ne 'y') { exit 0 }
    } else {
        Write-Host "  ✗ Ollama 未监听 11434 端口" -ForegroundColor Red
        Write-Host "  请启动 Ollama: ollama serve" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "  ✗ Ollama 未安装" -ForegroundColor Red
    Write-Host "  请安装 Ollama: https://ollama.com/" -ForegroundColor Red
    exit 1
}

# 检查3: 环境变量文件
Write-Host "`n[3/5] 检查环境变量配置..." -ForegroundColor Yellow
if (Test-Path ".env") {
    Write-Host "  ✓ .env 文件已存在" -ForegroundColor Green
} else {
    Write-Host "  ⚙ 从模板创建 .env 文件..." -ForegroundColor Cyan
    Copy-Item ".env.template" ".env"
    Write-Host "  ✓ 已创建 .env 文件" -ForegroundColor Green
    Write-Host "  ⚠ 请编辑 .env 文件,确认以下配置:" -ForegroundColor Yellow
    Write-Host "     - OLLAMA_BASE_URL=http://host.docker.internal:11434" -ForegroundColor White
}

# 检查4: Ollama 模型
Write-Host "`n[4/5] 检查 Ollama 模型..." -ForegroundColor Yellow
$modelExists = ollama list | Select-String "qwen2.5:3b"
if ($modelExists) {
    Write-Host "  ✓ 模型 qwen2.5:3b 已存在" -ForegroundColor Green
} else {
    Write-Host "  ⚙ 下载模型 qwen2.5:3b (约 2GB,请耐心等待)..." -ForegroundColor Cyan
    ollama pull qwen2.5:3b
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ 模型下载完成" -ForegroundColor Green
    } else {
        Write-Host "  ✗ 模型下载失败" -ForegroundColor Red
        exit 1
    }
}

# 检查5: Docker Compose 服务
Write-Host "`n[5/5] 启动 Docker 服务..." -ForegroundColor Yellow
$servicesRunning = docker-compose ps --services --filter "status=running"
if ($servicesRunning -contains "api") {
    Write-Host "  ✓ API 服务已在运行" -ForegroundColor Green
} else {
    Write-Host "  ⚙ 启动所有服务 (API + PostgreSQL + Redis)..." -ForegroundColor Cyan
    docker-compose up -d
    
    Write-Host "  ⚙ 等待服务健康检查..." -ForegroundColor Cyan
    $maxAttempts = 30
    $attempt = 0
    while ($attempt -lt $maxAttempts) {
        Start-Sleep -Seconds 5
        $healthStatus = docker-compose ps api --format json | ConvertFrom-Json
        if ($healthStatus.Status -like "*healthy*") {
            Write-Host "  ✓ 所有服务启动成功" -ForegroundColor Green
            break
        }
        $attempt++
        Write-Host "  ... 等待中 ($attempt/$maxAttempts)" -ForegroundColor Gray
    }
    
    if ($attempt -eq $maxAttempts) {
        Write-Host "  ⚠ 服务启动超时,请查看日志: docker-compose logs -f api" -ForegroundColor Yellow
    }
}

# 完成
Write-Host "`n========================================" -ForegroundColor Green
Write-Host "  初始化完成!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "下一步操作:" -ForegroundColor Cyan
Write-Host "  1. 查看实时日志: docker-compose logs -f api" -ForegroundColor White
Write-Host "  2. 测试 API: curl http://localhost:5050/api/system/health" -ForegroundColor White
Write-Host "  3. 发送测试请求:" -ForegroundColor White
Write-Host '     curl -X POST http://localhost:5050/api/chat/agent/MainAgent \' -ForegroundColor Gray
Write-Host '       -H "Content-Type: application/json" \' -ForegroundColor Gray
Write-Host '       -d "{\"query\": \"你好\", \"thread_id\": \"test-001\"}"' -ForegroundColor Gray
Write-Host ""
Write-Host "文档参考:" -ForegroundColor Cyan
Write-Host "  - DOCKER_DEPLOYMENT.md" -ForegroundColor White
Write-Host "  - docs/SHOPPING_CLAW_DEV_GUIDE.md" -ForegroundColor White
Write-Host ""
