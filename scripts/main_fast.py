# -*- coding: utf-8 -*-
"""
RC-N3 -> Xbox 360 手柄   低延迟版本
==================================
针对原版 main.py 的 ~1 秒延迟做了根本性重写。

原版的三个延迟来源：
  1. read_duml_packet 用 s.read(1) 阻塞式逐字节找起始符，超时 100ms
  2. 每轮发 2 个请求只读 1 个包，响应在缓冲区里堆积导致读写错位
  3. 错位后疯狂扫 0x55，每次都可能踩满超时，累积成秒级延迟

本版的做法：
  1. 串口超时降到 1ms，改用 in_waiting 非阻塞一次性读全部
  2. 滚动缓冲区解析，积压的包一次性全部处理完
  3. 单线程主循环，无 GIL 竞争，发送/解析/手柄更新零 sleep 竞争
  4. 实时显示 延迟 / 包率 / 轴值，可直接看到优化效果

用法：
    python main_fast.py
    python main_fast.py -p COM6
    python main_fast.py --invert lv
"""

import argparse
import struct
import time
import sys

import serial
import serial.tools.list_ports
import vgamepad as vg

# ================================================================ 参数
parser = argparse.ArgumentParser(description="RC-N3 -> Xbox360 低延迟桥接")
parser.add_argument("-p", "--port", default=None, help="串口，默认自动找 For Protocol")
parser.add_argument("--invert", nargs="*", default=[],
                    help="要反转的轴，如 --invert lv rh")
parser.add_argument("--deadzone", type=int, default=0, help="死区，默认 0")
parser.add_argument("--scale", type=float, default=1.0, help="幅度缩放，默认 1.0")
parser.add_argument("--rate", type=int, default=0, help="显示刷新间隔秒，0=不刷新")
parser.add_argument("--selftest", action="store_true",
                    help="自检模式：跑若干秒后自动退出并报告")
parser.add_argument("--selftest-seconds", type=int, default=8,
                    help="自检持续秒数，默认 8")
args = parser.parse_args()

INVERT = {a.lower() for a in args.invert}

# ================================================================ 状态
st = {
    "rh": 0, "rv": 0,          # 右摇杆 横 / 纵
    "lh": 0, "lv": 0,          # 左摇杆 横 / 纵
    "b1": 0, "b2": 0,          # 物理按键
    "b3": 0, "b4": 0,
    "camera": 0,
}
prev_b = {}

# ================================================================ 找串口
def find_port():
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("[错误] 没有任何串口。请检查遥控器是否开机、数据线是否插好。")
        sys.exit(1)

    print("可用串口：")
    for p in ports:
        print(f"   {p.device:<8} {p.description}")

    if args.port:
        for p in ports:
            if p.device.upper() == args.port.upper():
                return p.device
        print(f"[错误] 找不到指定的串口 {args.port}")
        sys.exit(1)

    for p in ports:
        if "For Protocol" in (p.description or ""):
            return p.device

    print("[错误] 未找到 For Protocol 串口（COM3 是调试口，不可用）")
    sys.exit(1)


PORT = find_port()

# ================================================================ 开串口
# timeout=1ms：绝大多数情况下 0 或极短等待，不阻塞
s = serial.Serial(
    port=PORT,
    baudrate=115200,
    timeout=0.001,
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    xonxoff=False,
    rtscts=False,
)
print(f"\n[连接] 已打开 {PORT}")
time.sleep(0.2)
try:
    s.reset_input_buffer()
except Exception:
    pass

# ================================================================ 虚拟手柄
gamepad = vg.VX360Gamepad()
gamepad.reset()
time.sleep(0.5)
print("[手柄] 虚拟 Xbox 360 已注册")
print("[手柄] 窗口请保持开启，关闭即手柄消失")
print()

# ================================================================ DUML
seq = [0x34EB]

CRC_TABLE = [
    0x0000,0x1189,0x2312,0x329b,0x4624,0x57ad,0x6536,0x74bf,
    0x8c48,0x9dc1,0xaf5a,0xbed3,0xca6c,0xdbe5,0xe97e,0xf8f7,
    0x1081,0x0108,0x3393,0x221a,0x56a5,0x472c,0x75b7,0x643e,
    0x9cc9,0x8d40,0xbfdb,0xae52,0xdaed,0xcb64,0xf9ff,0xe876,
    0x2102,0x308b,0x0210,0x1399,0x6726,0x76af,0x4434,0x55bd,
    0xad4a,0xbcc3,0x8e58,0x9fd1,0xeb6e,0xfae7,0xc87c,0xd9f5,
    0x3183,0x200a,0x1291,0x0318,0x77a7,0x662e,0x54b5,0x453c,
    0xbdcb,0xac42,0x9ed9,0x8f50,0xf3af,0xe226,0xd0bd,0xc134,
    0x4204,0x538d,0x6116,0x709f,0x0420,0x15a9,0x2732,0x36bb,
    0xce4c,0xdfc5,0xed5e,0xfcd7,0x8868,0x99e1,0xab7a,0xbaf3,
    0x5285,0x430c,0x7197,0x601e,0x14a1,0x0528,0x37b3,0x263a,
    0xdecd,0xcf44,0xfddf,0xec56,0x98e9,0x8960,0xbbfb,0xaa72,
    0x6306,0x728f,0x4014,0x519d,0x2522,0x34ab,0x0630,0x17b9,
    0xef4e,0xfec7,0xcc5c,0xddd5,0xa96a,0xb8e3,0x8a78,0x9bf1,
    0x7387,0x620e,0x5095,0x411c,0x35a3,0x242a,0x16b1,0x0738,
    0xffcf,0xee46,0xdcdd,0xcd54,0xb9eb,0xa862,0x92b9,0x8330,
    0x8408,0x9581,0xa71a,0xb693,0xc22c,0xd3a5,0xe13e,0xf0b7,
    0x0840,0x19c9,0x2b52,0x3adb,0x4e64,0x5fed,0x6d76,0x7cff,
    0x9489,0x8500,0xb79b,0xa612,0xd2ad,0xc324,0xf1bf,0xe036,
    0x18c1,0x0948,0x3bd3,0x2a5a,0x5ee5,0x4f6c,0x7df7,0x6c7e,
    0xa50a,0xb483,0x8618,0x9791,0xe32e,0xf2a7,0xc03c,0xd1b5,
    0x2942,0x38cb,0x0a50,0x1bd9,0x6f66,0x7eef,0x4c74,0x5dfd,
    0xb58b,0xa402,0x9699,0x8710,0xf3af,0xe226,0xd0bd,0xc134,
    0x39c3,0x284a,0x1ad1,0x0b58,0x7fe7,0x6e6e,0x5cf5,0x4d7c,
    0xc60c,0xd785,0xe51e,0xf497,0x8028,0x91a1,0xa33a,0xb2b3,
    0x4a44,0x5bcd,0x6956,0x78df,0x0c60,0x1de9,0x2f72,0x3efb,
    0xd68d,0xc704,0xf59f,0xe416,0x90a9,0x8120,0xb3bb,0xa232,
    0x5ac5,0x4b4c,0x79d7,0x685e,0x1ce1,0x0d68,0x3ff3,0x2e7a,
    0xe70e,0xf687,0xc41c,0xd595,0xa12a,0xb0a3,0x8238,0x93b1,
    0x6b46,0x7acf,0x4854,0x59dd,0x2d62,0x3ceb,0x0e70,0x1ff9,
    0xf78f,0xe606,0xd49d,0xc514,0xb1ab,0xa022,0x92b9,0x8330,
    0x7bc7,0x6a4e,0x58d5,0x495c,0x3de3,0x2c6a,0x1ef1,0x0f78,
]

HDR_CHECKSUM_TABLE = [
    0x00,0x5E,0xBC,0xE2,0x61,0x3F,0xDD,0x83,0xC2,0x9C,0x7E,0x20,0xA3,0xFD,0x1F,0x41,
    0x9D,0xC3,0x21,0x7F,0xFC,0xA2,0x40,0x1E,0x5F,0x01,0xE3,0xBD,0x3E,0x60,0x82,0xDC,
    0x23,0x7D,0x9F,0xC1,0x42,0x1C,0xFE,0xA0,0xE1,0xBF,0x5D,0x03,0x80,0xDE,0x3C,0x62,
    0xBE,0xE0,0x02,0x5C,0xDF,0x81,0x63,0x3D,0x7C,0x22,0xC0,0x9E,0x1D,0x43,0xA1,0xFF,
    0x46,0x18,0xFA,0xA4,0x27,0x79,0x9B,0xC5,0x84,0xDA,0x38,0x66,0xE5,0xBB,0x59,0x07,
    0xDB,0x85,0x67,0x39,0xBA,0xE4,0x06,0x58,0x19,0x47,0xA5,0xFB,0x78,0x26,0xC4,0x9A,
    0x65,0x3B,0xD9,0x87,0x04,0x5A,0xB8,0xE6,0xA7,0xF9,0x1B,0x45,0xC6,0x98,0x7A,0x24,
    0xF8,0xA6,0x44,0x1A,0x99,0xC7,0x25,0x7B,0x3A,0x64,0x86,0xD8,0x5B,0x05,0xE7,0xB9,
    0x8C,0xD2,0x30,0x6E,0xED,0xB3,0x51,0x0F,0x4E,0x10,0xF2,0xAC,0x2F,0x71,0x93,0xCD,
    0x11,0x4F,0xAD,0xF3,0x70,0x2E,0xCC,0x92,0xD3,0x8D,0x6F,0x31,0xB2,0xEC,0x0E,0x50,
    0xAF,0xF1,0x13,0x4D,0xCE,0x90,0x72,0x2C,0x6D,0x33,0xD1,0x8F,0x0C,0x52,0xB0,0xEE,
    0x32,0x6C,0x8E,0xD0,0x53,0x0D,0xEF,0xB1,0xF0,0xAE,0x4C,0x12,0x91,0xCF,0x2D,0x73,
    0xCA,0x94,0x76,0x28,0xAB,0xF5,0x17,0x49,0x08,0x56,0xB4,0xEA,0x69,0x37,0xD5,0x8B,
    0x57,0x09,0xEB,0xB5,0x36,0x68,0x8A,0xD4,0x95,0xCB,0x29,0x77,0xF4,0xAA,0x48,0x16,
    0xE9,0xB7,0x55,0x0B,0x88,0xD6,0x34,0x6A,0x2B,0x75,0x97,0xC9,0x4A,0x14,0xF6,0xA8,
    0x74,0x2A,0xC8,0x96,0x15,0x4B,0xA9,0xF7,0xB6,0xE8,0x0A,0x54,0xD7,0x89,0x6B,0x35,
]


def calc_checksum(packet):
    v = 0x3692
    for b in packet:
        v = (v >> 8) ^ CRC_TABLE[((b ^ v) & 0xFF)]
    return v


def build_duml(source, target, cmd_type, cmd_set, cmd_id, payload=None):
    packet = bytearray([0x55])
    length = 13 + (len(payload) if payload else 0)
    packet += struct.pack('B', length & 0xff)
    packet += struct.pack('B', (length >> 8) | 0x4)

    chk = 0x77
    for b in packet[:3]:
        chk = HDR_CHECKSUM_TABLE[((b ^ chk) & 0xFF)]
    packet += struct.pack('B', chk)

    packet += struct.pack('BB', source, target)
    packet += struct.pack('<H', seq[0])
    packet += struct.pack('BBB', cmd_type, cmd_set, cmd_id)
    if payload:
        packet += payload
    packet += struct.pack('<H', calc_checksum(packet))
    seq[0] = (seq[0] + 1) & 0xFFFF
    return packet


def parse_input(b):
    raw = int.from_bytes(b, 'little')
    v = (raw - 1024) * 50.97
    v = int(max(-32767, min(32767, v)))
    return v


# ================================================================ 启用模拟模式
try:
    s.write(build_duml(0x0a, 0x06, 0x40, 0x06, 0x24, bytearray.fromhex('01')))
    time.sleep(0.1)
    print("[模式] 遥控器已切换到模拟器模式")
except Exception as e:
    print(f"[警告] 切换模拟器模式失败: {e}")

if args.invert:
    print(f"[设置] 反转轴: {', '.join(sorted(INVERT))}")
if args.deadzone:
    print(f"[设置] 死区: {args.deadzone}")
if args.scale != 1.0:
    print(f"[设置] 缩放: {args.scale}")
print()
print("-" * 62)
print("  运行中  Ctrl+C 停止")
if args.rate:
    print(f"  延迟刷新: {args.rate} 秒")
print("-" * 62)

# ================================================================ 主循环
buf = bytearray()
last_send = 0.0
last_stick_ts = 0.0
last_report = 0.0

lat_ms = 0.0
pkt_count = 0
loop_count = 0
in_buf_max = 0

SEND_INTERVAL = 0.004      # 4ms 发一次请求，约 250Hz
REPORT_INTERVAL = 1.0

t_start = time.perf_counter()

# 自检模式：记录统计后自动退出
selftest_deadline = None
if args.selftest:
    selftest_deadline = t_start + args.selftest_seconds
    print(f"[自检] 将运行 {args.selftest_seconds} 秒后自动退出")
    print(f"[selftest] will exit after {args.selftest_seconds} s")
    print()

stick_pkt = 0          # 收到的 38 字节摇杆包数
btn_pkt = 0            # 收到的 58 字节按键包数

try:
    while True:
        now = time.perf_counter()

        # ---- 1. 定时发请求
        if now - last_send >= SEND_INTERVAL:
            try:
                s.write(build_duml(0x0a, 0x06, 0x40, 0x06, 0x01, bytearray()))
                s.write(build_duml(0x0a, 0x06, 0x40, 0x06, 0x27, bytearray()))
            except Exception as e:
                print(f"\n[错误] 串口写入失败: {e}")
                break
            last_send = now

        # ---- 2. 非阻塞一次性读走全部数据
        try:
            waiting = s.in_waiting
            if waiting:
                if waiting > 4096:
                    waiting = 4096
                chunk = s.read(waiting)
                if chunk:
                    buf.extend(chunk)
                    if len(buf) > in_buf_max:
                        in_buf_max = len(buf)
        except Exception as e:
            print(f"\n[错误] 串口读取失败: {e}")
            break

        # ---- 3. 解析缓冲区里所有完整包
        got_stick = False
        while True:
            # 找起始符
            i = buf.find(0x55)
            if i < 0:
                buf.clear()
                break
            if i > 0:
                del buf[:i]
            if len(buf) < 3:
                break

            length = buf[1] | ((buf[2] & 0x03) << 8)
            if length < 3 or length > 512:
                del buf[0]
                continue
            if len(buf) < length:
                break

            pkt = bytes(buf[:length])
            del buf[:length]
            pkt_count += 1

            if length == 38:
                st["rh"] = parse_input(pkt[13:15])
                st["rv"] = parse_input(pkt[16:18])
                st["lv"] = parse_input(pkt[19:21])
                st["lh"] = parse_input(pkt[22:24])
                st["camera"] = parse_input(pkt[25:27])
                last_stick_ts = time.perf_counter()
                lat_ms = (last_stick_ts - last_send) * 1000.0
                got_stick = True
                stick_pkt += 1

            elif length == 58:
                ival = int.from_bytes(pkt[28:30], 'big')
                st['b1'] = 1 if (ival & 0x1060) == 0x1060 else 0
                st['b2'] = 1 if (ival & 0x1080) == 0x1080 else 0
                st['b3'] = 1 if (ival & 0x1004) == 0x1004 else 0
                st['b4'] = 1 if (ival & 0x1002) == 0x1002 else 0
                btn_pkt += 1

        # ---- 4. 更新虚拟手柄（只在有新数据时才写，避免空转）
        if got_stick:
            lh, lv, rh, rv = st["lh"], st["lv"], st["rh"], st["rv"]

            if "lh" in INVERT: lh = -lh
            if "lv" in INVERT: lv = -lv
            if "rh" in INVERT: rh = -rh
            if "rv" in INVERT: rv = -rv

            if args.deadzone:
                for nm, val in (("lh", lh), ("lv", lv), ("rh", rh), ("rv", rv)):
                    if abs(val) < args.deadzone:
                        val = 0
                    elif val > 0:
                        val = int((val - args.deadzone) * 32767 / (32767 - args.deadzone))
                    else:
                        val = -int((-val - args.deadzone) * 32767 / (32767 - args.deadzone))
                    if nm == "lh": lh = val
                    elif nm == "lv": lv = val
                    elif nm == "rh": rh = val
                    else: rv = val

            if args.scale != 1.0:
                lh = int(lh * args.scale)
                lv = int(lv * args.scale)
                rh = int(rh * args.scale)
                rv = int(rv * args.scale)

            def clamp(v):
                return int(max(-32767, min(32767, v)))

            gamepad.left_joystick(clamp(lh), clamp(lv))
            gamepad.right_joystick(clamp(rh), clamp(rv))

            # 按键：边沿触发，只在变化时动作
            def set_btn(key, vg_btn):
                cur = st[key]
                old = prev_b.get(key, 0)
                if cur and not old:
                    gamepad.press_button(vg_btn)
                elif not cur and old:
                    gamepad.release_button(vg_btn)
                prev_b[key] = cur

            set_btn("b1", vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
            set_btn("b3", vg.XUSB_BUTTON.XUSB_GAMEPAD_X)
            set_btn("b4", vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER)

            if st["b2"]:
                gamepad.right_trigger(255)
            else:
                gamepad.right_trigger(0)

            cam = st["camera"]
            if cam > 32000:
                gamepad.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP)
                gamepad.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN)
            elif cam < -32000:
                gamepad.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP)
                gamepad.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN)
            else:
                gamepad.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP)
                gamepad.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN)

            gamepad.update()

        loop_count += 1

        # ---- 5. 状态显示
        if args.rate and now - last_report >= args.rate:
            last_report = now
            elapsed = time.perf_counter() - t_start
            pps = pkt_count / elapsed if elapsed > 0 else 0
            lps = loop_count / elapsed if elapsed > 0 else 0

            def bar(v):
                n = int(abs(v) / 32767 * 20)
                c = "-" if v >= 0 else ""
                return c + ("#" * n).ljust(20, " ")

            sys.stdout.write(
                f"\r延迟 {lat_ms:6.1f}ms  包 {pps:5.0f}/s  循环 {lps:6.0f}/s  "
                f"积压 {len(buf):3d}B  "
                f"油门[{bar(st['lv'])}]  横滚[{bar(st['rh'])}]   "
            )
            sys.stdout.flush()

        # 让出 CPU，但不引入可感知延迟
        time.sleep(0)

        # 自检模式：到时间自动退出
        if selftest_deadline is not None and now >= selftest_deadline:
            break

except KeyboardInterrupt:
    print("\n\n[停止] 用户中断")

finally:
    elapsed = time.perf_counter() - t_start
    try:
        s.close()
    except Exception:
        pass
    try:
        gamepad.reset()
    except Exception:
        pass
    print("[清理] 串口已关闭，手柄已重置")
    print("[cleanup] serial closed, gamepad reset")

# ================================================================ 自检报告
if args.selftest:
    print()
    print("=" * 62)
    print("  自检报告 / Self-test report")
    print("=" * 62)
    print()
    print(f"  运行时长 / Duration      {elapsed:.1f} s")
    print(f"  虚拟手柄 / Virtual pad   {'已创建 / created' if gamepad else '未创建 / none'}")
    print(f"  摇杆数据包 / Stick pkts   {stick_pkt}  ({stick_pkt/max(elapsed,0.01):.0f}/s)")
    print(f"  按键数据包 / Button pkts  {btn_pkt}  ({btn_pkt/max(elapsed,0.01):.0f}/s)")
    print(f"  总数据包 / Total pkts     {pkt_count}  ({pkt_count/max(elapsed,0.01):.0f}/s)")
    print(f"  缓冲区峰值 / Peak backlog {in_buf_max} B")
    print()

    if stick_pkt == 0:
        print("  [失败] 没有收到任何摇杆数据")
        print("  [FAIL]  No stick data received at all.")
        print("         请确认：遥控器已开机、数据线插在底部 Type-C 口、")
        print("         DJI Assistant 2 未在后台运行。")
        print()
        sys.exit(1)

    avg_pps = stick_pkt / max(elapsed, 0.01)
    print("  [通过] 摇杆数据正常 / stick data flowing")
    print(f"  [PASS] stick data flowing at {avg_pps:.0f}/s")
    if lat_ms < 0 or lat_ms > 200:
        print(f"  [警告] 最近一次延迟异常: {lat_ms:.1f} ms")
        print(f"  [WARN]  last latency looks odd: {lat_ms:.1f} ms")
    else:
        print(f"  [通过] 延迟正常 / latency nominal ({lat_ms:.1f} ms)")
    print()
    print("  环境可用，可以正常使用 run_bridge.bat")
    print("  Environment is ready. run_bridge.bat is good to go.")
    print("=" * 62)
    print()
