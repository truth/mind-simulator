"""场景几何与场景库测试：python -m unittest discover tests"""

import math
import shutil
import tempfile
import unittest

from rmtt_sim.drone import Drone
from rmtt_sim.scenes import SceneLibrary
from rmtt_sim.world import World, normalize_scene


def world(*obstacles, **kw):
    return World(dict({"obstacles": list(obstacles)}, **kw))


class GeometryTest(unittest.TestCase):
    def test_rotated_box(self):
        # 200×20 的墙绕 Z 顺时针转 90°：变成沿世界 Y 方向 20 宽、沿 X 方向 200 长 → 实际占据 x∈[-10,10], y∈[-100,100]
        w = world({"type": "box", "x": 0, "y": 0, "w": 200, "d": 20, "h": 100, "yaw": 90})
        self.assertIsNotNone(w.collides((0, 90, 50)))
        self.assertIsNone(w.collides((90, 0, 50)))
        self.assertAlmostEqual(w.raycast((-100, 50, 50), (1, 0, 0), 500), 90, delta=0.01)
        self.assertIsNone(w.raycast((-100, 150, 50), (1, 0, 0), 500))

    def test_box_45deg_raycast(self):
        w = world({"type": "box", "x": 100, "y": 0, "w": 100, "d": 100, "h": 100, "yaw": 45})
        # 旋转 45° 后最近的是棱角，位于 x = 100 - 50√2
        self.assertAlmostEqual(w.raycast((0, 0, 50), (1, 0, 0), 500), 100 - 50 * math.sqrt(2), delta=0.01)

    def test_cylinder(self):
        w = world({"type": "cylinder", "x": 100, "y": 0, "r": 20, "h": 150})
        self.assertAlmostEqual(w.raycast((0, 0, 50), (1, 0, 0), 500), 80, delta=0.01)
        self.assertAlmostEqual(w.raycast((100, 0, 300), (0, 0, -1), 500), 150, delta=0.01)  # 顶面
        self.assertIsNone(w.raycast((0, 30, 50), (1, 0, 0), 500))
        self.assertIsNotNone(w.collides((100, 25, 50)))  # 含飞机半径
        self.assertEqual(w.floor_height(100, 0), 150)

    def test_gate_fly_through(self):
        w = world({"type": "gate", "x": 150, "y": 0, "w": 100, "h": 150, "t": 8})
        self.assertIsNone(w.raycast((0, 0, 80), (1, 0, 0), 500))      # 门洞中央畅通
        self.assertIsNotNone(w.raycast((0, 54, 80), (1, 0, 0), 500))  # 打在立柱上
        self.assertIsNotNone(w.raycast((0, 0, 155), (1, 0, 0), 500))  # 打在横梁上
        self.assertIsNone(w.collides((150, 0, 80)))
        self.assertIsNotNone(w.collides((150, 50, 80)))

    def test_drone_lands_on_table_and_flies_through_gate(self):
        w = world({"type": "box", "x": 100, "y": 0, "w": 80, "d": 80, "h": 75},
                  {"type": "gate", "x": 300, "y": 0, "w": 100, "h": 150})
        d = Drone(0, "127.0.0.1", w, lambda *a: None)
        out = []
        def send(c):
            out.clear(); d.handle(c, out.append)
            for _ in range(20000):
                if out: break
                d.update(0.02)
            return out[0]
        self.assertEqual(send("takeoff"), "ok")
        self.assertEqual(send("up 50"), "ok")
        self.assertEqual(send("forward 100"), "ok")
        self.assertEqual(send("land"), "ok")
        self.assertAlmostEqual(d.pos[2], 75, delta=0.5)  # 落在桌面上
        self.assertEqual(send("takeoff"), "ok")
        self.assertEqual(send("down 40"), "ok")
        self.assertEqual(send("forward 300"), "ok")     # 从门洞穿过
        self.assertGreater(d.pos[0], 390)

    def test_start_pose(self):
        w = World({"start": {"x": 50, "y": -20, "yaw": 90}})
        d0 = Drone(0, "a", w, lambda *a: None)
        d1 = Drone(1, "b", w, lambda *a: None)
        self.assertEqual((d0.pos[0], d0.pos[1], d0.yaw), (50, -20, 90))
        # 第二架在起飞点左侧 1m：机头朝 -Y 时左侧是 +X
        self.assertAlmostEqual(d1.pos[0], 150, delta=0.01)
        self.assertAlmostEqual(d1.pos[1], -20, delta=0.01)


class SceneTest(unittest.TestCase):
    def test_normalize_rejects_and_clamps(self):
        sc = normalize_scene({"obstacles": [{"type": "box", "w": -5, "x": "abc", "color": "red"},
                                            {"type": "ufo"}, "junk"],
                              "pads": [{"id": 99, "x": 10}]})
        self.assertEqual(len(sc["obstacles"]), 1)
        o = sc["obstacles"][0]
        self.assertEqual((o["w"], o["x"]), (1, 0))
        self.assertTrue(o["color"].startswith("#"))
        self.assertEqual(sc["pads"][0]["id"], 8)
        with self.assertRaises(ValueError):
            normalize_scene([1, 2])

    def test_builtin_scenes_load(self):
        lib = SceneLibrary()
        ids = [s["id"] for s in lib.list() if s["builtin"]]
        self.assertEqual(ids[:4], ["empty", "pads", "obstacles", "course"])
        for sid in ids:
            content, builtin = lib.load(sid)
            self.assertTrue(builtin)
            World(content)

    def test_user_library_roundtrip(self):
        tmp = tempfile.mkdtemp()
        try:
            shutil.copytree(SceneLibrary().builtin_dir, tmp + "/builtin")
            lib = SceneLibrary(tmp)
            content, _ = lib.load("course")
            sid = lib.save(content, "我的赛道/v1")
            self.assertEqual(sid, "我的赛道_v1")
            loaded, builtin = lib.load(sid)
            self.assertFalse(builtin)
            self.assertEqual(loaded["title"], "我的赛道/v1")
            self.assertEqual(len(loaded["obstacles"]), len(content["obstacles"]))
            with self.assertRaises(FileExistsError):
                lib.save(content, "我的赛道/v1")
            with self.assertRaises(ValueError):
                lib.save(content, "course")            # 不能覆盖内置
            with self.assertRaises(ValueError):
                lib.delete("course")
            with self.assertRaises(KeyError):
                lib.load("../builtin/course")          # 路径穿越
            lib.delete(sid)
            self.assertNotIn(sid, [s["id"] for s in lib.list()])
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()


class DroneCountTest(unittest.TestCase):
    def test_switch_single_dual(self):
        from rmtt_sim.simulator import Simulator
        sim = Simulator(["10.0.0.1", "10.0.0.2", "10.0.0.3"], scene="empty", udp=False, count=1)
        try:
            self.assertEqual(len(sim.drones), 1)
            self.assertEqual(sim.drones[0].peers, [])
            self.assertEqual(sim.set_drone_count(2), 2)
            d0, d1 = sim.drones
            self.assertEqual((d1.index, d1.ip), (1, "10.0.0.2"))
            self.assertEqual(d0.peers, [d1])
            self.assertAlmostEqual(d1.pos[1], 100, delta=0.01)   # 新飞机在起飞点左侧 1m
            # 切回单机：正在执行的动作收到 error Interrupted
            out = []
            d1.handle("takeoff", out.append)
            self.assertEqual(sim.set_drone_count(1), 1)
            self.assertEqual(out, ["error Interrupted"])
            self.assertEqual(sim.drones, [d0])
            self.assertEqual(d0.peers, [])
            self.assertEqual(sim.snapshot()["max_drones"], 3)
            with self.assertRaises(ValueError):
                sim.set_drone_count(4)
            with self.assertRaises(ValueError):
                sim.set_drone_count(0)
        finally:
            sim.shutdown()


class DiscoveryTest(unittest.TestCase):
    def test_discover_lists_drones_and_clients(self):
        import socket
        from rmtt_sim.discovery import DiscoveryResponder
        from rmtt_sim.simulator import Simulator
        sim = Simulator(["127.0.0.2", "127.0.0.3"], scene="empty", lan_ips=["127.0.0.5"], count=2)
        disc = DiscoveryResponder(sim, port=0)
        port = disc.sock.getsockname()[1]
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(3)

        def ask():
            s.sendto(b"RMTT-DISCOVER 1", ("127.0.0.1", port))
            return s.recvfrom(2048)[0].decode().splitlines()

        try:
            lines = ask()
            self.assertEqual(lines[0], "RMTT-SIM 1")
            self.assertIn("ips=127.0.0.5", lines)
            drones = [l for l in lines if l.startswith("drone=")]
            self.assertEqual(drones[0], "drone=1;port=8889;sn=0TQZK7SIM00001;flying=0;client=-")
            self.assertTrue(drones[1].startswith("drone=2;port=8989;sn=0TQZK7SIM00002;"))
            # 客户端连上 #2 后，发现结果显示其已被占用
            c = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            c.settimeout(3)
            c.sendto(b"command", ("127.0.0.5", 8989))
            self.assertEqual(c.recvfrom(64)[0], b"ok")
            c.close()
            d2 = [l for l in ask() if l.startswith("drone=2")][0]
            self.assertNotIn("client=-", d2)
            # 非发现请求不回复
            s.sendto(b"hello", ("127.0.0.1", port))
            with self.assertRaises(socket.timeout):
                s.settimeout(0.5)
                s.recvfrom(2048)
        finally:
            s.close()
            disc.close()
            sim.shutdown()


class VideoTest(unittest.TestCase):
    def test_push_video_packets(self):
        import socket
        from rmtt_sim import simulator
        recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        recv.bind(("127.0.0.1", 0))
        recv.settimeout(2)
        old_port = simulator.VIDEO_PORT
        simulator.VIDEO_PORT = recv.getsockname()[1]
        sim = simulator.Simulator(["10.0.0.1"], scene="empty", udp=False, count=1)
        try:
            d = sim.drones[0]
            frame = bytes(range(256)) * 12   # 3072 字节 → 1460 + 1460 + 152
            self.assertFalse(sim.push_video(0, frame))   # 未 streamon：丢弃
            d.client = ("127.0.0.1", 8889)
            d.handle("streamon", lambda r: None)
            self.assertTrue(sim.push_video(0, frame))
            sizes = [len(recv.recvfrom(2048)[0]) for _ in range(3)]
            self.assertEqual(sizes, [1460, 1460, 152])
            # 帧长恰为 1460 的整数倍：补空包标记帧结束
            self.assertTrue(sim.push_video(0, b"x" * 1460))
            self.assertEqual([len(recv.recvfrom(2048)[0]) for _ in range(2)], [1460, 0])
            self.assertFalse(sim.push_video(5, frame))   # 不存在的飞机
        finally:
            simulator.VIDEO_PORT = old_port
            recv.close()
            sim.shutdown()

    def test_strip_svc_nal(self):
        from rmtt_sim.simulator import strip_svc_nal
        sps, prefix, idr = b"\x00\x00\x00\x01\x67AB", b"\x00\x00\x00\x01\x6e\x01\x02", b"\x00\x00\x01\x65CD"
        self.assertEqual(strip_svc_nal(sps + prefix + idr), sps + idr)
        self.assertEqual(strip_svc_nal(b"raw"), b"raw")
