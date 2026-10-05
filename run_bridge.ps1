# =============================================================================
#  RC-N3 Gamepad Bridge - PowerShell Launcher
#  RC-N3 手柄桥接 —— PowerShell 版启动器
#
#  用法 / Usage:
#     双击本文件，或在 PowerShell 中执行：
#     & ".\run_bridge.ps1"
#
#  若提示禁止运行脚本，先执行一次：
#     Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
# =============================================================================

$ErrorActionPreference = "Continue"
chcp 65001 | Out-Null

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

try { $Host.UI.RawUI.WindowTitle = "RC-N3 Bridge  low-latency bridge  do not close" } catch { }

# ---------------------------------------------------------------- 找 Python
$PyExe = $null
$candidates = @(
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python39\python.exe"
)
foreach ($c in $candidates) {
    if (Test-Path $c) { $PyExe = $c; break }
}
if (-not $PyExe) {
    $found = Get-Command python -ErrorAction SilentlyContinue
    if ($found) { $PyExe = $found.Source }
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  RC-N3 to Xbox 360 Gamepad   low-latency bridge" -ForegroundColor Cyan
Write-Host "  latency ~1-5 ms" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

if (-not $PyExe) {
    Write-Host ""
    Write-Host "[ERROR] Python 3.9 - 3.12 not found" -ForegroundColor Red
    Write-Host "Install from https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "Tick 'Add Python to PATH' during install" -ForegroundColor Yellow
    Write-Host "Note: vgamepad does not build on Python 3.13+" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host "Using / 使用: $PyExe" -ForegroundColor DarkGray
Write-Host ""

# ---------------------------------------------------------------- 清理残留进程
Write-Host "Releasing COM6 / 正在释放 COM6 端口..." -ForegroundColor Cyan
try {
    $stale = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
             Where-Object { $_.CommandLine -like "*main_fast*" }
    foreach ($p in $stale) {
        Write-Host "   killing stale PID $($p.ProcessId)" -ForegroundColor DarkGray
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
} catch {
    Write-Host "   skip cleanup / 跳过清理" -ForegroundColor DarkGray
}
Write-Host ""

# ---------------------------------------------------------------- 检查依赖
& $PyExe -c "import serial, vgamepad" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARN] Missing dependencies, installing / 缺少依赖，正在安装" -ForegroundColor Yellow
    & $PyExe -m pip install vgamepad pyserial
    Write-Host ""
}

# ---------------------------------------------------------------- 提示
Write-Host "------------------------------------------------------------" -ForegroundColor Cyan
Write-Host "  Closing this window removes the virtual gamepad" -ForegroundColor Yellow
Write-Host "  关闭窗口 = 虚拟手柄消失，游戏会变回无手柄" -ForegroundColor Yellow
Write-Host "------------------------------------------------------------" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Optional flags / 可选参数:" -ForegroundColor DarkGray
Write-Host "    --invert lv rh     invert axes" -ForegroundColor DarkGray
Write-Host "    --deadzone 300     kill centre drift" -ForegroundColor DarkGray
Write-Host "    --scale 0.8        lower sensitivity" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Self-test / 自检:  & '.\run_bridge.ps1' --selftest" -ForegroundColor DarkGray
Write-Host "  Ctrl+C to stop" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------- 主循环
$SelfTest = $false
if ($args -contains "--selftest") { $SelfTest = $true }

$scriptArgs = @("scripts\main_fast.py", "--rate", "2")
if ($SelfTest) { $scriptArgs += @("--selftest", "--selftest-seconds", "8") }

while ($true) {
    Write-Host "[start] $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Green

    & $PyExe @scriptArgs
    $code = $LASTEXITCODE

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  Bridge stopped.  Exit code / 退出码 $code" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan

    if ($code -eq 0) {
        Write-Host "Normal exit / 正常结束" -ForegroundColor Green
        if ($SelfTest) {
            Write-Host ""
            Write-Host "Environment is ready. Use run_bridge.ps1 normally." -ForegroundColor Green
            Write-Host "环境可用，可以正常使用了。" -ForegroundColor Green
        }
        Read-Host "Press Enter to close / 按回车关闭"
        exit 0
    }

    if ($SelfTest) {
        Write-Host ""
        Write-Host "[FAIL] Self-test failed. Check the messages above." -ForegroundColor Red
        Write-Host "[失败] 自检未通过，请对照上方提示排查" -ForegroundColor Red
        Read-Host "Press Enter to close / 按回车关闭"
        exit $code
    }

    Write-Host ""
    Write-Host "Retrying in 5 s / 5 秒后自动重试..." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "If it keeps failing / 若反复失败请检查:" -ForegroundColor Yellow
    Write-Host "  1. Is the remote on? Cable in the BOTTOM Type-C port?" -ForegroundColor Yellow
    Write-Host "  2. Is DJI Assistant 2 running in the background?" -ForegroundColor Yellow
    Write-Host "  3. Does COM6 still exist in Device Manager?" -ForegroundColor Yellow
    Write-Host ""
    Start-Sleep -Seconds 5
}
