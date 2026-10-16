"""模拟 Mind+ 实时模式程序发出的 UDP 指令序列，用于端到端验证模拟器。

与 Mind+ 一样：向 192.168.10.1:8889 发送文本指令并等待回复，同时在本机 8890 端口接收状态。
用法：先运行模拟器（start.bat），再执行  python examples/mindplus_like_demo.py
"""

import socket
import sys
import threading
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TELLO = ("192.168.10.1", 8889)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("", 0))
sock.settimeout(60)

state = {}


def state_listener():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("", 8890))
    while True:
        data, _ = s.recvfrom(1024)
        for kv in data.decode().strip().strip(";").split(";"):
            k, _, v = kv.partition(":")
            state[k] = v


def send(cmd):
    sock.sendto(cmd.encode(), TELLO)
    reply = sock.recvfrom(1024)[0].decode().strip()
    print("%-34s -> %s" % (cmd, reply))
    return reply


threading.Thread(target=state_listener, daemon=True).start()

send("command")
send("battery?")
send("sn?")
send("hardware?")
send("EXT led 0 0 255")
send("EXT mled s p heart")
send("mon")
send("takeoff")
time.sleep(0.5)
print("状态推送:", {k: state.get(k) for k in ("mid", "h", "bat", "tof", "yaw")})

# 一边前进一边用前向 ToF 避障
send("EXT mled l b 1.5 GO!")
for _ in range(6):
    tof = int(send("EXT tof?").split()[1])
    if tof < 600:
        send("EXT led 255 0 0")
        send("cw 90")
    else:
        send("EXT led 0 255 0")
        send("forward 50")

send("flip b")
send("curve 60 60 0 0 120 0 40")
send("EXT mled g " + "0rr00rr0" "rrrrrrrr" "rrrrrrrr" "0rrrrrr0" "00rrrr00" "000rr000" "00000000" "00000000")
send("land")
print("最终状态:", {k: state.get(k) for k in ("mid", "x", "y", "z", "h", "bat", "yaw", "time")})
