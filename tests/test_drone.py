"""核心逻辑单元测试（不依赖网络）：python -m unittest discover tests"""

import math
import unittest

from rmtt_sim.drone import Drone
from rmtt_sim.scenes import SceneLibrary
from rmtt_sim.world import World, box


class Harness:
    def __init__(self, scene="empty"):
        self.world = World(SceneLibrary().load(scene)[0], scene_id=scene)
        self.logs = []
        self.d = Drone(0, "127.0.0.1", self.world, lambda i, k, t: self.logs.append((k, t)))

    def send(self, cmd, max_t=120.0):
        out = []
        self.d.handle(cmd, out.append)
        t = 0.0
        while not out and self.d.task and t < max_t:
            self.d.update(0.02)
            t += 0.02
        return out[0] if out else None


class DroneTest(unittest.TestCase):
    def test_basic_flight(self):
        h = Harness()
        self.assertEqual(h.send("command"), "ok")
        self.assertEqual(h.send("forward 50"), "error Motor stop")
        self.assertEqual(h.send("takeoff"), "ok")
        self.assertAlmostEqual(h.d.pos[2], 80, delta=1)
        self.assertEqual(h.send("forward 100"), "ok")
        self.assertAlmostEqual(h.d.pos[0], 100, delta=1)
        self.assertEqual(h.send("cw 90"), "ok")
        self.assertAlmostEqual(h.d.yaw, 90, delta=0.1)
        self.assertEqual(h.send("forward 50"), "ok")  # 机头朝右 → 世界 -Y
        self.assertAlmostEqual(h.d.pos[1], -50, delta=1)
        self.assertEqual(h.send("up 40"), "ok")
        self.assertAlmostEqual(h.d.pos[2], 120, delta=1)
        self.assertEqual(h.send("land"), "ok")
        self.assertFalse(h.d.flying)
        self.assertAlmostEqual(h.d.pos[2], 0, delta=0.1)

    def test_reads_and_ranges(self):
        h = Harness()
        self.assertEqual(h.send("battery?"), "100")
        self.assertEqual(h.send("hardware?"), "RMTT")
        self.assertEqual(h.send("speed 30"), "ok")
        self.assertEqual(h.send("speed?"), "30.0")
        self.assertEqual(h.send("speed 300"), "error Out of range")
        h.send("takeoff")
        self.assertEqual(h.send("forward 5"), "error Out of range")
        self.assertEqual(h.send("forward abc"), "error")
        self.assertTrue(h.send("foo").startswith("unknown command"))

    def test_go_and_curve(self):
        h = Harness()
        h.send("takeoff")
        self.assertEqual(h.send("go 100 50 20 50"), "ok")
        self.assertAlmostEqual(h.d.pos[0], 100, delta=1)
        self.assertAlmostEqual(h.d.pos[1], 50, delta=1)
        start = h.d.pos
        self.assertEqual(h.send("curve 100 100 0 0 200 0 50"), "ok")
        self.assertAlmostEqual(h.d.pos[0], start[0], delta=1.5)
        self.assertAlmostEqual(h.d.pos[1], start[1] + 200, delta=1.5)
        self.assertEqual(h.send("curve 10 0 0 20 0 0 30"), "error Radius is too large")

    def test_arc_passes_through_middle_point(self):
        seg = Drone.make_arc((0, 0, 0), (100, 100, 0), (0, 200, 0), 50)
        pts = []
        while seg.th < seg.end:
            seg.th = min(seg.end, seg.th + 0.01)
            p = [seg.c[i] + seg.r * (math.cos(seg.th) * seg.u[i] + math.sin(seg.th) * seg.v[i]) for i in range(3)]
            pts.append(p)
        self.assertTrue(any(math.dist(p, (100, 100, 0)) < 2 for p in pts))
        self.assertLess(math.dist(pts[-1], (0, 200, 0)), 0.5)

    def test_collision_and_tof(self):
        h = Harness()
        h.world.add_obstacle(box(110, 0, 20, 100, 200))
        h.send("takeoff")
        self.assertEqual(h.send("EXT tof?"), "tof 940")  # 机头前 6cm 起算，墙面 x=100
        self.assertEqual(h.send("forward 200"), "error Collision")
        self.assertLess(h.d.pos[0], 100)
        h.send("cw 180")
        self.assertEqual(h.send("EXT tof?"), "tof 8192")

    def test_mission_pad(self):
        h = Harness("pads")
        h.send("takeoff")
        self.assertIn("mid:-1;x:-100", h.d.state_string())
        h.send("mon")
        self.assertTrue(h.d.state_string().startswith("mid:1;x:0;y:0;z:80"))
        self.assertEqual(h.send("go 0 0 100 50 m2"), "error No valid marker")
        self.assertEqual(h.send("go 100 0 100 50 m1"), "ok")
        self.assertTrue(h.d.state_string().startswith("mid:2;"))
        self.assertEqual(h.send("jump 100 0 100 50 90 m2 m3"), "ok")
        self.assertAlmostEqual(h.d.yaw, 90, delta=0.5)

    def test_ext_led_and_matrix(self):
        h = Harness()
        self.assertEqual(h.send("EXT led 255 0 0"), "led ok")
        self.assertEqual(h.d.led.c1, (255, 0, 0))
        self.assertEqual(h.send("EXT led br 1 0 255 0"), "led ok")
        self.assertEqual(h.send("EXT led 300 0 0"), "led error")
        self.assertEqual(h.send("EXT mled g " + "r" * 64), "mled ok")
        self.assertEqual(h.d.matrix.frame, "r" * 64)
        self.assertEqual(h.send("EXT mled g xyz"), "mled error")
        self.assertEqual(h.send("EXT mled s p heart"), "mled ok")
        self.assertIn("p", h.d.matrix.frame)
        self.assertEqual(h.send("EXT mled l r 1 Hello World"), "mled ok")
        first = h.d.matrix.frame
        h.d.update(0.5)
        self.assertNotEqual(first, h.d.matrix.frame)
        self.assertEqual(h.send("EXT mled sl 100"), "mled ok")
        self.assertEqual(h.send("EXT mled sc"), "mled ok")
        self.assertEqual(h.d.matrix.frame, "0" * 64)

    def test_flip_and_emergency(self):
        h = Harness()
        h.send("takeoff")
        self.assertEqual(h.send("flip f"), "ok")
        self.assertIsNone(h.d.flip)
        h.d.battery = 40
        self.assertEqual(h.send("flip l"), "error Low battery")
        self.assertEqual(h.send("emergency"), "ok")
        for _ in range(100):
            h.d.update(0.02)
        self.assertAlmostEqual(h.d.pos[2], 0, delta=0.1)

    def test_rc(self):
        h = Harness()
        h.send("takeoff")
        self.assertIsNone(h.send("rc 0 50 0 0"))
        for _ in range(50):
            h.d.update(0.02)
        self.assertAlmostEqual(h.d.pos[0], 50, delta=2)

    def test_busy_and_retransmit(self):
        h = Harness()
        h.send("takeoff")
        out = []
        h.d.handle("forward 200", out.append)
        h.d.handle("forward 200", out.append)   # 重传，忽略
        h.d.handle("cw 90", out.append)          # 运动中，拒绝
        h.d.handle("battery?", out.append)       # 读取，立即回复
        self.assertEqual(out[0], "error Not joystick")
        self.assertTrue(out[1].isdigit())
        self.assertEqual(len(out), 2)


if __name__ == "__main__":
    unittest.main()
