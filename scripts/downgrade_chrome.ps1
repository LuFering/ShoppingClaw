# Chrome降级到131版本
# 131版本与DrissionPage 4.1.1.2兼容性良好

Write-Host "=== Chrome降级脚本 ===" -ForegroundColor Green

$chromePath = "C:\Program Files\Google\Chrome\Application"
$targetVersion = "131.0.6778.265"
$downloadUrl = "https://dl.google.com/tag/s/appguid%3D%7B8A69D345-D564-463C-AFF1-A69D9E530F96%7D%26iid%3D%7B1E39C50E-8642-5B99-C5A7-7F87A3C2C891%7D%26lang%3Dzh-CN%26browser%3D4%26usagestats%3D0%26appname%3DGoogle%2520Chrome%26needsadmin%3Dprefers%26ap%3Dx64-stable-statsdef_0%26brand%3DGCEB/dl/chrome/install/googlechromestandaloneenterprise64.msi"

Write-Host "`n当前版本: 147.0.7727.138" -ForegroundColor Yellow
Write-Host "目标版本: $targetVersion" -ForegroundColor Yellow

Write-Host "`n步骤1: 停止Chrome进程..." -ForegroundColor Cyan
Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
Write-Host "✓ Chrome进程已停止" -ForegroundColor Green

Write-Host "`n步骤2: 下载Chrome 131..." -ForegroundColor Cyan
$installer = "$env:TEMP\chrome_131.msi"
if (-not (Test-Path $installer)) {
    Write-Host "正在下载Chrome 131安装包..." -ForegroundColor Yellow
    try {
        Invoke-WebRequest -Uri $downloadUrl -OutFile $installer -UseBasicParsing
        Write-Host "✓ 下载完成" -ForegroundColor Green
    } catch {
        Write-Host "✗ 下载失败: $_" -ForegroundColor Red
        Write-Host "请手动下载: https://google-chrome.en.uptodown.com/windows/versions" -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "✓ 安装包已存在" -ForegroundColor Green
}

Write-Host "`n步骤3: 卸载Chrome 147..." -ForegroundColor Cyan
$uninstallCmd = "MsiExec.exe /X{GUID} /quiet /norestart"
Write-Host "请手动卸载Chrome 147（控制面板 -> 程序和功能）" -ForegroundColor Yellow
Write-Host "或者运行: Start-Process 'appwiz.cpl'" -ForegroundColor Cyan

Write-Host "`n步骤4: 安装Chrome 131..." -ForegroundColor Cyan
Write-Host "请运行: msiexec /i $installer /quiet /norestart" -ForegroundColor Cyan

Write-Host "`n⚠️ 重要提示:" -ForegroundColor Yellow
Write-Host "1. 请先手动卸载Chrome 147" -ForegroundColor White
Write-Host "2. 然后运行上述安装命令" -ForegroundColor White
Write-Host "3. 安装完成后禁止自动更新:" -ForegroundColor White
Write-Host "   - 创建目录: C:\Program Files (x86)\Google\Update" -ForegroundColor White
Write-Host "   - 创建文件: C:\Program Files (x86)\Google\Update\GoogleUpdate.exe (空文件)" -ForegroundColor White

Write-Host "`n禁用Chrome自动更新:" -ForegroundColor Cyan
$blockDir = "C:\Program Files (x86)\Google\Update"
if (Test-Path $blockDir) {
    Remove-Item -Path $blockDir -Recurse -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Path $blockDir -Force | Out-Null
New-Item -ItemType File -Path "$blockDir\GoogleUpdate.exe" -Force | Out-Null
Write-Host "✓ 自动更新已禁用" -ForegroundColor Green

Write-Host "`n=== 完成 ===" -ForegroundColor Green
Write-Host "请手动完成卸载和安装步骤" -ForegroundColor Cyan
