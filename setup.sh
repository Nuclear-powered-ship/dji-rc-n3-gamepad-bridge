#!/usr/bin/env bash
# =============================================================================
#  RC-N3 Gamepad Bridge - One-Shot Installer
#  DJI RC-N3 遥控器转 Xbox 360 手柄 —— 一键部署脚本
#
#  用法 / Usage:
#     bash setup.sh            自动安装全部依赖
#     bash setup.sh --check    只做环境体检，不安装
#
#  Windows 用户请双击 run_setup.bat
# =============================================================================

set -u

RED='\033[0;31m'
GRN='\033[0;32m'
YEL='\033[0;33m'
CYN='\033[0;36m'
NC='\033[0m'

CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

say()  { printf "${CYN}==>${NC} %s\n" "$1"; }
ok()   { printf "${GRN}  [OK]${NC} %s\n" "$1"; }
warn() { printf "${YEL}  [!]${NC} %s\n" "$1"; }
err()  { printf "${RED}  [X]${NC} %s\n" "$1"; }

echo ""
echo "============================================================"
echo "  RC-N3 Gamepad Bridge  环境检查 / Environment Check"
echo "============================================================"
echo ""

# ---------------------------------------------------------------- Python
say "检查 Python / Checking Python"
PY=""
for c in python3 python py; do
    if command -v "$c" >/dev/null 2>&1; then
        v=$("$c" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)
        if [ -n "$v" ]; then
            major=$(echo "$v" | cut -d. -f1)
            minor=$(echo "$v" | cut -d. -f2)
            if [ "$major" -eq 3 ] && [ "$minor" -le 12 ]; then
                PY="$c"
                ok "Python $v  ($c)"
                break
            fi
        fi
    fi
done

if [ -z "$PY" ]; then
    err "未找到 Python 3.9 ~ 3.12"
    err "Python 3.9-3.12 not found. 请从 https://www.python.org/downloads/ 安装"
    err "注意：vgamepad 在 Python 3.13+ 上无法安装"
    exit 1
fi

# ---------------------------------------------------------------- 依赖
say "检查依赖库 / Checking dependencies"
MISSING=""
"$PY" -c "import serial"  2>/dev/null && ok "pyserial"  || { warn "缺少 pyserial / missing"; MISSING="$MISSING pyserial"; }
"$PY" -c "import vgamepad" 2>/dev/null && ok "vgamepad"  || { warn "缺少 vgamepad / missing"; MISSING="$MISSING vgamepad"; }

# ---------------------------------------------------------------- ViGEmBus
say "检查虚拟手柄驱动 / Checking ViGEmBus driver"
if [ -f "/c/Windows/System32/drivers/ViGEmBus.sys" ]; then
    ok "ViGEmBus 驱动已安装 / driver present"
elif [ -f "/mnt/c/Windows/System32/drivers/ViGEmBus.sys" ]; then
    ok "ViGEmBus 驱动已安装 / driver present"
else
    warn "未检测到 ViGEmBus 驱动"
    warn "ViGEmBus not detected — 需要手动安装"
    warn "下载 / Download: https://github.com/nefarius/ViGEmBus/releases"
    warn "安装后必须重启 / reboot required after install"
fi

# ---------------------------------------------------------------- 串口
say "检查遥控器串口 / Checking RC-N3 serial port"
if command -v powershell.exe >/dev/null 2>&1; then
    PORTINFO=$(powershell.exe -NoProfile -Command \
        "Get-CimInstance Win32_SerialPort -ErrorAction SilentlyContinue | Where-Object { \$_.Name -match 'COM' } | ForEach-Object { \$_.Name }" 2>/dev/null | tr -d '\r')
else
    PORTINFO=""
fi

if echo "$PORTINFO" | grep -q .; then
    echo "$PORTINFO" | while read -r p; do ok "发现 $p"; done
    if "$PY" -c "
import serial.tools.list_ports as lp
raise SystemExit(0 if any('For Protocol' in (p.description or '') for p in lp.comports()) else 1)
" 2>/dev/null; then
        ok "找到数据口 For Protocol / data port found"
    else
        warn "未找到 For Protocol 口。请确认插的是底部 Type-C 口且遥控器已开机"
        warn "No 'For Protocol' port. Check the bottom Type-C port and power state"
    fi
else
    warn "没有串口。请插好数据线并开机 / No serial port. Plug in and power on"
fi

# ---------------------------------------------------------------- 结论
echo ""
echo "============================================================"
if [ "$CHECK_ONLY" -eq 1 ]; then
    echo "  体检模式结束 / Check-only mode done"
elif [ -n "$MISSING" ]; then
    echo "  需要安装依赖 / Missing dependencies:$MISSING"
    echo ""
    say "正在安装 / Installing"
    if "$PY" -m pip install --upgrade pip >/dev/null 2>&1; then
        ok "pip 已更新 / pip updated"
    fi
    if "$PY" -m pip install vgamepad pyserial; then
        ok "依赖安装完成 / dependencies installed"
    else
        err "依赖安装失败，请手动执行 / install failed, run manually:"
        err "    $PY -m pip install vgamepad pyserial"
        exit 1
    fi
    echo ""
    echo "重新运行体检确认 / Re-run check:"
    echo "    $PY scripts/check_env.py"
else
    echo "  一切就绪 / All good"
fi
echo "============================================================"
echo ""
echo "下一步 / Next:"
echo "  1. 遥控器开机，插底部 Type-C 口"
echo "     Power on the remote, plug the bottom Type-C port"
echo "  2. 运行 / Run:  $PY scripts/main_fast.py --rate 2"
echo "  3. 保持窗口开启，再启动游戏"
echo "     Keep the window open, then launch the game"
echo ""
