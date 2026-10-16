"""仿真器主体：世界 + 多架飞机 + 仿真循环 + UDP 端点。"""

import socket
import threading
import time
from collections import deque

from .drone import Drone
from .scenes import SceneLibrary
from .world import World

CMD_PORT = 8889
STATE_PORT = 8890
SIM_HZ = 60
STATE_HZ = 10


def lan_port(index):
    """局域网端点的端口：#1 用 8889，#2 起依次 8989、9089 …（同一 IP 上不能重复使用 8889）。"""
    return CMD_PORT + 100 * index


def detect_lan_ips():
    """本机可供手机 / 模拟器访问的 IPv4 地址。

    排除 192.168.10.x（模拟器自己的虚拟地址）、198.18.0.0/15（代理软件 TUN 网卡）和 169.254.x（链路本地）；
    额外加入 127.0.0.1，供 Android 模拟器通过 10.0.2.2 访问。
    """
    ips = []
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        infos = []
    for info in infos:
        ip = info[4][0]
        if ip.startswith(("127.", "192.168.10.", "198.18.", "198.19.", "169.254.")) or ip in ips:
            continue
        ips.append(ip)
    return ips + ["127.0.0.1"]


class UdpEndpoint:
    """飞机的一个 UDP 指令端口：绑定在 ip:port，向该端口最近的客户端 ip:8890 推送状态。

    每架飞机有一个主端点（192.168.10.x:8889，给本机 Mind+ 用），以及若干局域网端点（给手机 App 用）。
    """

    def __init__(self, sim, drone, ip, port=CMD_PORT):
        self.sim, self.drone = sim, drone
        self.client = None
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((ip, port))
        self.self_addr = (ip, port)
        threading.Thread(target=self._recv_loop, daemon=True, name="udp-%s:%d" % (ip, port)).start()

    def _recv_loop(self):
        while self.sim.running:
            try:
                data, addr = self.sock.recvfrom(2048)
            except ConnectionResetError:
                # Windows：上次发送的目标端口不可达时，下一次 recvfrom 会抛出该异常，忽略
                continue
            except OSError:
                if not self.sim.running:
                    return
                continue
            if addr == self.self_addr:
                continue  # 自己发给自己的包（客户端与模拟器同 IP 同端口），丢弃防止回环
            text = data.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            reply = self._make_reply(addr)
            with self.sim.lock:
                d = self.drone
                if self.client != addr:
                    self.sim.log(d.index, "info", "客户端 %s:%d 已连接（经 %s:%d）" % (addr + self.self_addr))
                    self.client = addr
                d.client = addr
                if not text.lower().startswith("rc "):
                    self.sim.log(d.index, "in", text)
                d.handle(text, reply)

    def _make_reply(self, addr):
        def reply(text):
            self.sim.log(self.drone.index, "out", text)
            try:
                self.sock.sendto(text.encode("utf-8"), addr)
            except OSError as e:
                self.sim.log(self.drone.index, "warn", "回复发送失败: %s" % e)
        return reply

    def send_state(self, state):
        c = self.client
        if c:
            try:
                self.sock.sendto(state.encode("ascii"), (c[0], STATE_PORT))
            except OSError:
                pass

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class Simulator:
    def __init__(self, ips, scene="empty", udp=True, auto_land=0.0, lan_ips=(), library=None):
        self.lock = threading.RLock()
        self.running = True
        self.time_scale = 1.0
        self.paused = False
        self.reset_id = 0
        self.logs = deque(maxlen=500)
        self.log_seq = 0
        self.library = library or SceneLibrary()
        content, builtin = self.library.load(scene)
        self.world = World(content, scene_id=scene, builtin=builtin)
        self.drones = []
        for i, ip in enumerate(ips):
            d = Drone(i, ip, self.world, self.log)
            d.auto_land_timeout = auto_land
            self.drones.append(d)
        for d in self.drones:
            d.peers = [o for o in self.drones if o is not d]
        self.endpoints = [UdpEndpoint(self, d, d.ip) for d in self.drones] if udp else []
        self.lan_endpoints = []  # [(drone_index, ip, port)]
        if udp:
            for ip in lan_ips:
                for d in self.drones:
                    try:
                        self.endpoints.append(UdpEndpoint(self, d, ip, lan_port(d.index)))
                    except OSError as e:
                        print("  [提示] 无法绑定局域网地址 %s:%d（%s），已跳过" % (ip, lan_port(d.index), e))
                        continue
                    self.lan_endpoints.append((d.index, ip, lan_port(d.index)))
        threading.Thread(target=self._sim_loop, daemon=True, name="sim").start()
        if udp:
            threading.Thread(target=self._state_loop, daemon=True, name="state").start()

    # ---- 日志 ----
    def log(self, drone_index, kind, text):
        with self.lock:
            self.log_seq += 1
            self.logs.append({"seq": self.log_seq, "t": time.time(), "drone": drone_index,
                              "kind": kind, "text": text})
        tag = {"in": "<<", "out": ">>", "warn": "!!", "info": "--"}.get(kind, "  ")
        print("[%s] #%d %s %s" % (time.strftime("%H:%M:%S"), drone_index + 1, tag, text), flush=True)

    def logs_since(self, seq):
        with self.lock:
            return [e for e in self.logs if e["seq"] > seq]

    # ---- 循环 ----
    def _sim_loop(self):
        last = time.perf_counter()
        period = 1.0 / SIM_HZ
        while self.running:
            now = time.perf_counter()
            dt = min(now - last, 0.1)
            last = now
            if not self.paused:
                with self.lock:
                    for d in self.drones:
                        d.update(dt * self.time_scale)
            time.sleep(max(0.0, period - (time.perf_counter() - now)))

    def _state_loop(self):
        while self.running:
            with self.lock:
                states = [(ep, ep.drone.state_string()) for ep in self.endpoints]
            for ep, s in states:
                ep.send_state(s)
            time.sleep(1.0 / STATE_HZ)

    # ---- 供 Web 界面调用 ----
    def snapshot(self):
        with self.lock:
            return {"t": time.time(), "time_scale": self.time_scale, "paused": self.paused,
                    "world_version": self.world.version, "reset_id": self.reset_id,
                    "drones": [d.to_dict() for d in self.drones],
                    "lan": [{"drone": i, "addr": "%s:%d" % (ip, port)} for i, ip, port in self.lan_endpoints
                            if ip != "127.0.0.1"]}

    def run_command(self, index, cmd, timeout=120.0):
        """从 Web 控制台执行指令，阻塞直到收到回复（rc 等无回复指令立即返回）。"""
        done = threading.Event()
        result = {}

        def reply(text):
            self.log(index, "out", text)
            result["text"] = text
            done.set()

        with self.lock:
            d = self.drones[index]
            self.log(index, "in", "[控制台] " + cmd)
            d.handle(cmd, reply, source="web")
            d.sdk = True
        if cmd.strip().lower().startswith("rc "):
            return ""
        if not done.wait(timeout):
            return "(timeout)"
        return result["text"]

    def reset(self):
        with self.lock:
            for d in self.drones:
                if d.task and d.task["reply"]:
                    d.task["reply"]("error Interrupted")
                client = d.client
                d.reset()
                d.client = client
            self.reset_id += 1
        self.log(0, "info", "已重置所有飞机")

    # ---- 场景库 ----
    def load_scene(self, scene_id):
        content, builtin = self.library.load(scene_id)
        with self.lock:
            self.world.set_content(content, scene_id=scene_id, builtin=builtin, dirty=False)
        self.reset()
        self.log(0, "info", "已加载场景「%s」" % self.world.title)

    def new_scene(self):
        with self.lock:
            self.world.set_content({"title": "新场景"}, scene_id="", builtin=False, dirty=True)
        self.reset()

    def edit_world(self, data):
        """编辑器提交的场景内容：替换障碍物 / 挑战卡 / 起飞点，不重置飞机。"""
        with self.lock:
            self.world.set_content(data, dirty=True)
            return self.world.version

    def save_scene(self, title, overwrite=False, save_as=False):
        """保存当前场景。当前是用户场景且未"另存为"时覆盖原文件，否则按标题新建。"""
        with self.lock:
            w = self.world
            content = w.content()
            same = not save_as and w.scene_id and not w.builtin
            sid = self.library.save(content, title, scene_id=w.scene_id if same else None,
                                    overwrite=overwrite or same)
            w.scene_id, w.builtin, w.dirty, w.title = sid, False, False, title
            w.version += 1
        self.log(0, "info", "场景已保存为「%s」" % title)
        return sid

    def delete_scene(self, scene_id):
        self.library.delete(scene_id)
        with self.lock:
            if self.world.scene_id == scene_id:
                self.world.scene_id, self.world.dirty = "", True
                self.world.version += 1

    def shutdown(self):
        self.running = False
        for ep in self.endpoints:
            ep.close()
