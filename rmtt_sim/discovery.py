"""局域网自动发现：手机 App 广播搜索，模拟器回复自己的飞机列表，用户无需手动输入电脑 IP。

协议（UDP，纯文本，UTF-8）：
  请求  → 广播到 255.255.255.255:8899（或子网广播地址）：
        RMTT-DISCOVER 1
  回复  ← 单播回请求方：
        RMTT-SIM 1
        name=DESKTOP-075FDC7
        ips=192.168.0.107,172.17.64.1
        drone=1;port=8889;sn=0TQZK7SIM00001;flying=0;client=-
        drone=2;port=8989;sn=0TQZK7SIM00002;flying=1;client=192.168.0.106
App 连接回复包的来源 IP（若不在 ips 中则用 ips 的第一个）加上 drone 行的端口。
client 为最近 15 秒内控制该飞机的客户端 IP（pc = 本机 Mind+ / 脚本），"-" 表示空闲。
"""

import socket
import threading
import time

DISCOVERY_PORT = 8899
REQUEST = "RMTT-DISCOVER"
RESPONSE = "RMTT-SIM 1"
ACTIVE_SECONDS = 15.0   # App 空闲时每 10 秒保活一次，15 秒内有收包即视为已连接


class DiscoveryResponder:
    def __init__(self, sim, port=DISCOVERY_PORT):
        self.sim = sim
        self.closed = False
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.bind(("", port))  # 绑定通配地址才能收到广播
        threading.Thread(target=self._loop, daemon=True, name="discovery").start()

    def _loop(self):
        while not self.closed and self.sim.running:
            try:
                data, addr = self.sock.recvfrom(512)
            except ConnectionResetError:
                continue
            except OSError:
                if self.closed:
                    return
                continue
            if not data.decode("utf-8", "replace").strip().startswith(REQUEST):
                continue
            try:
                self.sock.sendto(self.describe().encode("utf-8"), addr)
            except OSError:
                pass

    def describe(self):
        sim = self.sim
        now = time.time()
        with sim.lock:
            ips = []
            for _, ip, _ in sim.lan_endpoints:
                if ip != "127.0.0.1" and ip not in ips:
                    ips.append(ip)
            lines = [RESPONSE, "name=%s" % socket.gethostname(), "ips=%s" % ",".join(ips)]
            for d in sim.drones:
                ports = sorted({port for i, ip, port in sim.lan_endpoints if i == d.index and ip != "127.0.0.1"})
                if not ports:
                    continue
                client = "-"
                for ep in sim.endpoints:
                    if ep.drone is d and ep.client and now - ep.last_rx < ACTIVE_SECONDS:
                        client = "pc" if ep.self_addr[0] == d.ip else ep.client[0]
                        break
                lines.append("drone=%d;port=%d;sn=%s;flying=%d;client=%s"
                             % (d.index + 1, ports[0], d.sn, 1 if d.flying else 0, client))
        return "\n".join(lines) + "\n"

    def close(self):
        self.closed = True
        try:
            self.sock.close()
        except OSError:
            pass
