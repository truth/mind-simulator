"""视频流自检：模拟客户端向模拟器发 command / streamon，起飞旋转一周后降落，接收 UDP 11111 的 H.264 并用 ffmpeg 检查。

需要：模拟器已启动、3D 界面已在浏览器中打开（视频由 3D 界面编码）；可选 ffmpeg（检查解码错误、导出截图）。

用法：
  python tools/video_check.py                       # 默认监听 127.0.0.1:11111，飞机 192.168.10.1:8889
  python tools/video_check.py --png frame.png       # 另存第 60 帧为图片，肉眼确认画面
  python tools/video_check.py --packets cap.bin     # 保存分片（含边界），供 tools/mindplus_wfs_test 回放

说明：
  - 运行期间本脚本成为飞机的客户端（视频与状态改发给本脚本），请勿与 Mind+ 同时操作同一架飞机；
  - 接收线程独立持续读取。若在等待指令回复期间不读取，64KB 默认缓冲区会溢出丢包，造成"解码错误"的假象；
  - 统计时去掉最后一帧（收包结束时可能只收到一半）；
  - Mind+ 占用 0.0.0.0:11111 时，本脚本绑定 127.0.0.1:11111 仍可工作（具体地址优先于通配地址）。
"""

import argparse
import re
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time

AUD = re.compile(rb"\x00\x00\x00\x01\x09")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--drone", default="192.168.10.1", help="飞机地址（默认 192.168.10.1）")
    ap.add_argument("--listen", default="127.0.0.1", help="本机接收视频的地址（默认 127.0.0.1）")
    ap.add_argument("--rcvbuf", type=int, default=0, help="接收缓冲区字节数，0 为系统默认")
    ap.add_argument("--out", default="video_check.h264", help="保存的 H.264 文件")
    ap.add_argument("--packets", help="另存原始分片（4 字节小端长度 + 数据）")
    ap.add_argument("--png", help="用 ffmpeg 导出第 60 帧")
    args = ap.parse_args()

    v = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if args.rcvbuf:
        v.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, args.rcvbuf)
    v.bind((args.listen, 11111))
    v.settimeout(0.5)
    packets, running = [], [True]

    def reader():
        while running[0]:
            try:
                packets.append(v.recvfrom(2048)[0])
            except socket.timeout:
                pass

    th = threading.Thread(target=reader, daemon=True)
    th.start()

    c = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    c.bind((args.listen, 0))
    c.settimeout(20)

    def cmd(x):
        c.sendto(x.encode(), (args.drone, 8889))
        res = c.recvfrom(256)[0].decode(errors="replace")
        print("  %-10s -> %s" % (x, res))
        return res

    t0 = time.time()
    try:
        cmd("command")
        cmd("streamon")
        took_off = cmd("takeoff") == "ok"     # 已在空中（error Already flying）时不负责降落
        cmd("cw 360")
        if took_off:
            cmd("land")
        cmd("streamoff")
    except socket.timeout:
        print("指令超时：模拟器是否在运行？")
        return 1
    dur = time.time() - t0
    running[0] = False
    th.join()

    data = b"".join(packets)
    starts = [m.start() for m in AUD.finditer(data)]
    if len(starts) < 2:
        print("没有收到视频：确认 3D 界面已用 http://127.0.0.1:8080 打开（画中画标签显示「推流中」）")
        return 1
    body = data[:starts[-1]]   # 去掉可能不完整的最后一帧
    open(args.out, "wb").write(body)
    if args.packets:
        with open(args.packets, "wb") as f:
            for p in packets:
                f.write(struct.pack("<I", len(p)) + p)
    frames = len(starts) - 1
    nal = {}
    for m in re.finditer(rb"\x00\x00\x01", body):
        if m.end() < len(body):
            t = body[m.end()] & 0x1F
            nal[t] = nal.get(t, 0) + 1
    print("分片 %d，帧 %d，%.1f 秒，约 %.1f fps，NAL 类型 %s -> %s"
          % (len(packets), frames, dur, frames / dur, dict(sorted(nal.items())), args.out))

    if not shutil.which("ffmpeg"):
        print("未安装 ffmpeg，跳过解码检查")
        return 0
    err = subprocess.run(["ffmpeg", "-v", "error", "-i", args.out, "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    n = err.count("error while decoding")
    print("ffmpeg 解码错误：%d" % n)
    if args.png:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", args.out, "-vf", r"select=eq(n\,60)",
                        "-frames:v", "1", "-update", "1", args.png])
        print("截图：%s" % args.png)
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())
