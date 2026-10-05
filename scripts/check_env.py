# -*- coding: utf-8 -*-
"""
RC-N3 -> Xbox 360 手柄 环境体检脚本
==================================
在正式开飞之前，一次性检查整条链路上的每一环，
避免装完驱动才发现某个环节掉了。

用法：
    python check_env.py
"""

import sys
import time

# ---------------------------------------------------------------- 体检报告
OK = "[ 通过 ]"
NG = "[ 失败 ]"
WR = "[ 警告 ]"

results = []


def record(status, name, detail):
    results.append((status, name, detail))
    print(f"{status} {name}")
    print(f"           {detail}")
    print()


# ================================================================ 1. Python
print("=" * 64)
print("  RC-N3 手柄桥接  环境体检")
print("=" * 64)
print()

record(OK, "Python 版本", sys.version.split()[0])

# ================================================================ 2. 依赖库
print("-" * 64)
print("  检查依赖库")
print("-" * 64)
print()

try:
    import serial
    record(OK, "pyserial", f"版本 {serial.__version__}")
except ImportError:
    record(NG, "pyserial", "未安装，请运行 pip install pyserial")

try:
    import vgamepad as vg
    record(OK, "vgamepad", "导入成功")
except ImportError:
    record(NG, "vgamepad", "未安装，请运行 pip install vgamepad")

# ================================================================ 3. ViGEmBus
print("-" * 64)
print("  检查虚拟手柄驱动 ViGEmBus")
print("-" * 64)
print()

import winreg

VIGEM_REG = r"SOFTWARE\Nefarius Software Solutions e.U.\ViGEm Bus Driver"
vigem_version = None
try:
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, VIGEM_REG) as k:
        vigem_version = winreg.QueryValueEx(k, "Version")[0]
    record(OK, "ViGEmBus 注册表", f"版本 {vigem_version}")
except OSError:
    record(NG, "ViGEmBus 注册表", "未找到，需要安装 ViGEmBus 驱动")

# 驱动文件
import os

sys_file = r"C:\Windows\System32\drivers\ViGEmBus.sys"
if os.path.exists(sys_file):
    size_kb = os.path.getsize(sys_file) / 1024
    record(OK, "驱动文件", f"ViGEmBus.sys 存在 ({size_kb:.1f} KB)")
else:
    record(NG, "驱动文件", "ViGEmBus.sys 缺失，需要重新安装驱动")

# ================================================================ 4. 虚拟手柄
print("-" * 64)
print("  检查虚拟手柄能否创建")
print("-" * 64)
print()

gamepad = None
try:
    gamepad = vg.VX360Gamepad()
    time.sleep(0.4)
    record(OK, "虚拟 Xbox 手柄", "创建成功，游戏中应能看到 Xbox 360 Controller")
except Exception as e:
    record(NG, "虚拟 Xbox 手柄", f"创建失败: {e}")

# ================================================================ 5. 串口
print("-" * 64)
print("  检查 RC-N3 串口")
print("-" * 64)
print()

import serial.tools.list_ports

target_port = None
all_ports = list(serial.tools.list_ports.comports())

if not all_ports:
    record(NG, "RC-N3 串口", "没有任何串口，请检查数据线和遥控器是否开机")
else:
    print("  当前可用串口：")
    for p in all_ports:
        print(f"    - {p.device:<8} {p.description}")
    print()

    for p in all_ports:
        if "For Protocol" in (p.description or ""):
            target_port = p.device
            break

    if target_port:
        record(OK, "RC-N3 串口", f"找到数据口 {target_port} (For Protocol)")
    else:
        record(NG, "RC-N3 串口", "未找到 For Protocol 口，请确认插的是底部 Type-C 口")

# ================================================================ 6. 串口占用
if target_port:
    print("-" * 64)
    print("  检查串口是否被占用")
    print("-" * 64)
    print()
    print("  提示：如果这里失败，很可能是 DJI Assistant 2 在后台运行。")
    print("       关闭它，或从系统托盘右键退出。")
    print()

    s = None
    try:
        s = serial.Serial(target_port, 115200, timeout=0.2)
        time.sleep(0.3)
        record(OK, "串口占用检查", f"{target_port} 可以被打开，没有被其他程序占用")
    except Exception as e:
        record(NG, "串口占用检查", f"{target_port} 无法打开: {e}\n           大概率是 DJI Assistant 2 占着，关掉它")
    finally:
        if s is not None:
            try:
                s.close()
            except Exception:
                pass

# ================================================================ 7. 实际读数
if target_port:
    print("-" * 64)
    print("  尝试读取遥控器摇杆数据")
    print("-" * 64)
    print()
    print("  接下来 5 秒，请依次推动摇杆到四个方向和中心")
    print("  观察下方数值是否变化")
    print()

    try:
        s2 = serial.Serial(target_port, 115200, timeout=0.1)
        time.sleep(0.3)
        # 清空缓冲
        try:
            s2.reset_input_buffer()
        except Exception:
            pass

        seen = {}
        deadline = time.time() + 5
        packets = 0

        while time.time() < deadline:
            b = s2.read(1)
            if b and b == b"\x55":
                lb = s2.read(2)
                if len(lb) == 2:
                    ln = lb[0] | ((lb[1] & 0x03) << 8)
                    if 0 < ln < 200:
                        rest = s2.read(ln - 3)
                        if len(rest) == ln - 3:
                            packets += 1
                            if len(rest) + 3 == 38:
                                seen[38] = seen.get(38, 0) + 1
                            elif len(rest) + 3 == 58:
                                seen[58] = seen.get(58, 0) + 1
        s2.close()

        if packets > 0:
            detail = f"5 秒内收到 {packets} 个数据包"
            if seen:
                detail += f"，包长分布 {seen}"
            record(OK, "遥控器数据读取", detail)
        else:
            record(WR, "遥控器数据读取",
                   "5 秒内没收到数据包。\n           可能原因：遥控器没开机 / 插的是充电口 / 需要动一下摇杆唤醒")

    except Exception as e:
        record(NG, "遥控器数据读取", f"读取失败: {e}")

# ================================================================ 汇总
print()
print("=" * 64)
print("  体检汇总")
print("=" * 64)
print()

failed = [r for r in results if r[0] == NG]
warned = [r for r in results if r[0] == WR]

if not failed and not warned:
    print("  全部通过，可以直接运行 main_fast.py 起飞了。")
    print()
    print("  下一步：")
    print("     python scripts/main_fast.py --rate 2")
    print("  或双击 run_bridge.bat")
    print("  Or just double-click run_bridge.bat")
else:
    if failed:
        print(f"  {len(failed)} 项失败，需要先解决：")
        for _, name, _d in failed:
            print(f"     - {name}")
        print()
    if warned:
        print(f"  {len(warned)} 项警告，可以试试看：")
        for _, name, _d in warned:
            print(f"     - {name}")
        print()

REPORT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "check_report.txt")
print(f"  完整诊断报告已保存到 {os.path.normpath(REPORT_PATH)}")
print("=" * 64)

with open(REPORT_PATH, "w", encoding="utf-8") as f:
    f.write("RC-N3 手柄桥接环境体检报告\n")
    f.write("生成时间: " + time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
    f.write("=" * 60 + "\n\n")
    for status, name, detail in results:
        f.write(f"{status} {name}\n")
        f.write(f"       {detail}\n\n")
    f.write("=" * 60 + "\n")
    f.write(f"通过 {len(results) - len(failed) - len(warned)} / {len(results)}\n")
    f.write(f"失败 {len(failed)}  警告 {len(warned)}\n")
