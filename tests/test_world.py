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
