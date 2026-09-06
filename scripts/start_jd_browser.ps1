# 启动京东采集专用浏览器（端口9333）
# 首次运行需要手动登录京东

Write-Host "正在启动京东采集专用浏览器..." -ForegroundColor Green

$chromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$userDataDir = "D:\ShoppingClaw\saves\jd_chrome"
$port = 9333

# 确保用户数据目录存在
if (-not (Test-Path $userDataDir)) {
    New-Item -ItemType Directory -Path $userDataDir -Force | Out-Null
    Write-Host "创建用户数据目录: $userDataDir" -ForegroundColor Yellow
}

# 启动Chrome（远程调试模式）
Start-Process -FilePath $chromePath -ArgumentList @(
    "--remote-debugging-port=$port",
    "--user-data-dir=$userDataDir",
    "--no-first-run",
    "--no-default-browser-check"
)

Write-Host "`n浏览器已启动（端口: $port）" -ForegroundColor Green
Write-Host "`n请在打开的浏览器窗口中：" -ForegroundColor Cyan
Write-Host "  1. 访问 https://www.jd.com" -ForegroundColor White
Write-Host "  2. 完成登录" -ForegroundColor White
Write-Host "  3. 必要时手动过验证" -ForegroundColor White
Write-Host "`n登录完成后即可使用爬虫工具访问详情页" -ForegroundColor Cyan
