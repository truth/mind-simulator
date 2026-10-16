"""仿真世界：障碍物（轴对齐长方体）、挑战卡（Mission Pad）、预设场景。

坐标系（单位 cm）：X 向前（飞机初始机头方向），Y 向左，Z 向上，原点在起飞点地面。
"""

import math

DRONE_RADIUS = 12.0  # 碰撞半径（含桨叶）
DRONE_HALF_H = 5.0

PALETTE = ["#e4572e", "#29335c", "#f3a712", "#669bbc", "#8a817c", "#2a9d8f"]


def box(x, y, w, d, h, z=0.0, color=None):
    """以底面中心 (x, y, z) 定义长方体，w 为 X 方向尺寸、d 为 Y 方向尺寸、h 为高度。"""
    return {"x": x, "y": y, "z": z, "w": w, "d": d, "h": h, "color": color}


def gate(x, y, width=100, height=160, along_x=True, color="#f3a712"):
    """由两根立柱 + 横梁组成的门框，飞机需从中间穿过。"""
    t = 8
    if along_x:  # 门洞朝 X 方向
        return [box(x, y + width / 2, t, t, height, color=color),
                box(x, y - width / 2, t, t, height, color=color),
                box(x, y, t, width + t, t, z=height, color=color)]
    return [box(x + width / 2, y, t, t, height, color=color),
            box(x - width / 2, y, t, t, height, color=color),
            box(x, y, width + t, t, t, z=height, color=color)]


def _pads_grid():
    pads = []
    for i in range(8):
        row, col = divmod(i, 4)
        pads.append({"id": i + 1, "x": col * 100.0, "y": -row * 100.0, "z": 0.0})
    return pads


SCENES = {
    "empty": {"title": "空旷场地", "obstacles": [], "pads": []},
    "pads": {"title": "挑战卡 (m1-m8)", "obstacles": [], "pads": _pads_grid()},
    "obstacles": {
        "title": "障碍物 / ToF 测试",
        "obstacles": [
            box(200, 0, 20, 160, 200, color=PALETTE[0]),
            box(100, 150, 60, 60, 120, color=PALETTE[3]),
            box(-120, -100, 40, 40, 80, color=PALETTE[2]),
            box(0, -250, 300, 20, 150, color=PALETTE[4]),
        ],
        "pads": [],
    },
    "course": {
        "title": "穿越门框赛道",
        "obstacles": (gate(150, 0) + gate(300, -150, along_x=False)
                      + gate(150, -300) + [box(400, 100, 40, 40, 200, color=PALETTE[0])]),
        "pads": [{"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
                 {"id": 2, "x": 300.0, "y": 0.0, "z": 0.0},
                 {"id": 3, "x": 300.0, "y": -300.0, "z": 0.0},
                 {"id": 4, "x": 0.0, "y": -300.0, "z": 0.0}],
    },
}


class World:
    def __init__(self, scene="empty"):
        self.version = 0
        self.load_scene(scene)

    def load_scene(self, name):
        sc = SCENES.get(name)
        if sc is None:
            raise KeyError(name)
        self.scene = name
        self.obstacles = [dict(o, id=i) for i, o in enumerate(sc["obstacles"])]
        for o in self.obstacles:
            o["color"] = o["color"] or PALETTE[o["id"] % len(PALETTE)]
        self.pads = [dict(p) for p in sc["pads"]]
        self.version += 1

    def add_obstacle(self, o):
        o = dict(o)
        o["id"] = max([b["id"] for b in self.obstacles], default=-1) + 1
        o.setdefault("z", 0.0)
        o["color"] = o.get("color") or PALETTE[o["id"] % len(PALETTE)]
        self.obstacles.append(o)
        self.version += 1

    def clear_obstacles(self):
        self.obstacles = []
        self.version += 1

    def to_dict(self):
        return {"version": self.version, "scene": self.scene,
                "obstacles": self.obstacles, "pads": self.pads,
                "scenes": {k: v["title"] for k, v in SCENES.items()}}

    # ---- 几何查询 ----
    @staticmethod
    def _bounds(o, inflate_xy=0.0, inflate_z=0.0):
        return (o["x"] - o["w"] / 2 - inflate_xy, o["x"] + o["w"] / 2 + inflate_xy,
                o["y"] - o["d"] / 2 - inflate_xy, o["y"] + o["d"] / 2 + inflate_xy,
                o["z"] - inflate_z, o["z"] + o["h"] + inflate_z)

    def collides(self, p):
        x, y, z = p
        for o in self.obstacles:
            x0, x1, y0, y1, z0, z1 = self._bounds(o, DRONE_RADIUS, DRONE_HALF_H)
            if x0 < x < x1 and y0 < y < y1 and z0 < z < z1:
                return o
        return None

    def raycast(self, origin, direction, max_dist):
        """返回射线到最近障碍物的距离（cm），未命中返回 None。"""
        best = None
        for o in self.obstacles:
            b = self._bounds(o)
            tmin, tmax = 0.0, max_dist
            hit = True
            for axis in range(3):
                lo, hi = b[axis * 2], b[axis * 2 + 1]
                d, s = direction[axis], origin[axis]
                if abs(d) < 1e-9:
                    if s < lo or s > hi:
                        hit = False
                        break
                    continue
                t1, t2 = (lo - s) / d, (hi - s) / d
                if t1 > t2:
                    t1, t2 = t2, t1
                tmin, tmax = max(tmin, t1), min(tmax, t2)
                if tmin > tmax:
                    hit = False
                    break
            if hit and (best is None or tmin < best):
                best = tmin
        return best

    def floor_height(self, x, y):
        """(x, y) 正下方最高的支撑面高度（地面或障碍物顶面）。"""
        h = 0.0
        for o in self.obstacles:
            x0, x1, y0, y1, z0, z1 = self._bounds(o, DRONE_RADIUS * 0.5)
            if x0 < x < x1 and y0 < y < y1:
                h = max(h, z1)
        return h

    def detect_pad(self, p, wanted=None):
        """下视摄像头识别挑战卡：高度 20~300cm、水平偏移在视野内。"""
        x, y, z = p
        best = None
        for pad in self.pads:
            dz = z - pad["z"]
            if not 20 <= dz <= 300:
                continue
            dist = math.hypot(x - pad["x"], y - pad["y"])
            if dist > max(40.0, dz * 0.6):
                continue
            if wanted is not None and pad["id"] != wanted:
                continue
            if best is None or dist < best[1]:
                best = (pad, dist)
        return best[0] if best else None
