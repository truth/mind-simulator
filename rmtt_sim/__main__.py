"""命令行入口：python -m rmtt_sim"""

import argparse
import sys
import time
import webbrowser

from . import __version__
from .discovery import DISCOVERY_PORT, DiscoveryResponder
from .simulator import CMD_PORT, Simulator, detect_lan_ips
from .web import serve
from .scenes import SceneLibrary


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    p = argparse.ArgumentParser(prog="rmtt_sim", description="RoboMaster TT 模拟器（兼容 Mind+ 实时模式）")
    p.add_argument("--ip", action="append",
                   help="飞机 UDP 地址池，可重复指定（默认 192.168.10.1、.11、.12、.13，与 setup_network.ps1 一致）")
    p.add_argument("--drones", type=int, default=None,
                   help="启动时的飞机数量（默认 1；指定 --ip 时默认用满地址池）。运行中可在网页上切换单机 / 双机")
    p.add_argument("--scene", default="pads",
                   help="初始场景 id（scenes/builtin 或 scenes/user 下的文件名，默认 pads）")
    p.add_argument("--web-host", default="127.0.0.1")
    p.add_argument("--web-port", type=int, default=8080)
    p.add_argument("--auto-land", type=float, default=0.0,
                   help="超过 N 秒未收到指令自动降落（真机为 15 秒，默认关闭）")
    p.add_argument("--no-lan", action="store_true",
                   help="不在局域网地址上监听（默认监听，供手机 App 连接）")
    p.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = p.parse_args()
    count = args.drones or (len(args.ip) if args.ip else 1)
    ips = args.ip or ["192.168.10.1"] + ["192.168.10.%d" % (9 + i) for i in range(2, max(4, count) + 1)]
    if not 1 <= count <= len(ips):
        p.error("--drones 需在 1 ~ %d 之间" % len(ips))

    print("RoboMaster TT 模拟器 v%s" % __version__)
    library = SceneLibrary()
    ids = [x["id"] for x in library.list()]
    if args.scene not in ids:
        print("[错误] 场景「%s」不存在，可用：%s" % (args.scene, ", ".join(ids)))
        sys.exit(1)
    try:
        sim = Simulator(ips, scene=args.scene, auto_land=args.auto_land, library=library, count=count,
                        lan_ips=[] if args.no_lan else detect_lan_ips())
    except OSError as e:
        print("\n[错误] 无法绑定 UDP 地址 %s:%d —— %s" % (", ".join(ips), CMD_PORT, e))
        print("请先以管理员身份运行 tools\\setup_network.ps1 为本机添加 192.168.10.1 地址，")
        print("或检查是否已有另一个模拟器实例在运行。")
        sys.exit(1)

    try:
        serve(sim, args.web_host, args.web_port)
    except OSError as e:
        print("[错误] Web 端口 %d 被占用：%s（可用 --web-port 更换）" % (args.web_port, e))
        sys.exit(1)
    discovery = None
    if not args.no_lan:
        try:
            discovery = DiscoveryResponder(sim)
        except OSError as e:
            print("  [提示] 自动发现端口 UDP %d 被占用（%s），手机 App 需手动输入地址" % (DISCOVERY_PORT, e))
    url = "http://%s:%d/" % ("127.0.0.1" if args.web_host == "0.0.0.0" else args.web_host, args.web_port)
    for d in sim.drones:
        print("  飞机 #%d  UDP %s:%d  SN=%s" % (d.index + 1, d.ip, CMD_PORT, d.sn))
    for i, ip, port in sim.lan_endpoints:
        if ip == "127.0.0.1":
            print("  飞机 #%d  Android 模拟器请填 10.0.2.2:%d" % (i + 1, port))
        else:
            print("  飞机 #%d  手机 App 请填 %s:%d" % (i + 1, ip, port))
    if discovery:
        print("  自动发现 UDP %d 已开启：手机 App 连接页点「搜索模拟器」即可找到本机" % DISCOVERY_PORT)
    print("  3D 界面  %s（顶部「飞机」可随时切换单机 / 双机）" % url)
    print("在 Mind+ 实时模式中加载「RoboMaster TT（单机）」扩展并连接即可。Ctrl+C 退出。\n")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        if discovery:
            discovery.close()
        sim.shutdown()


if __name__ == "__main__":
    main()
