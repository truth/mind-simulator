"""仿真世界：障碍物、挑战卡（Mission Pad）、起飞点。

坐标系（单位 cm）：X 向前（偏航 0° 时的机头方向），Y 向左，Z 向上。
角度 yaw 与飞机一致：俯视顺时针为正（度）。

场景中的障碍物类型（编辑器可见的"对象"）：
  box       长方体 / 墙：中心 (x, y)，底面高度 z，尺寸 w(沿自身 X) × d(沿自身 Y) × h，可绕 Z 轴旋转 yaw
  cylinder  圆柱：中心 (x, y)，底面高度 z，半径 r，高 h
  gate      门框：两根立柱 + 横梁，门洞宽 w、高 h、框粗 t，门洞朝自身 X 方向（偏航 0° 时沿 X 穿过）
物理计算时统一拆成"图元"：旋转长方体（OBB）与竖直圆柱。
"""

import math
import re

DRONE_RADIUS = 12.0  # 碰撞半径（含桨叶）
DRONE_HEIGHT = 10.0  # 机身高度；飞机位置 z 取机身底部，可以停在障碍物顶面上

PALETTE = ["#e4572e", "#29335c", "#f3a712", "#669bbc", "#8a817c", "#2a9d8f"]
OBSTACLE_TYPES = ("box", "cylinder", "gate")
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# 各类型字段默认值 / 取值范围
_FIELDS = {
    "box": {"w": (60, 1, 5000), "d": (60, 1, 5000), "h": (100, 1, 5000)},
    "cylinder": {"r": (20, 1, 2500), "h": (150, 1, 5000)},
    "gate": {"w": (100, 20, 2000), "h": (150, 20, 2000), "t": (8, 2, 100)},
}
_COORD = (0, -100000, 100000)


def _num(v, default, lo, hi):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return float(default)
    if math.isnan(v) or math.isinf(v):
        return float(default)
    return float(max(lo, min(hi, v)))


def normalize_obstacle(o, idx=0):
    """校验并补全一个障碍物定义，非法输入返回 None。"""
    if not isinstance(o, dict):
        return None
    t = o.get("type", "box")
    if t not in OBSTACLE_TYPES:
        return None
    out = {"type": t,
           "x": _num(o.get("x"), *_COORD), "y": _num(o.get("y"), *_COORD),
           "z": _num(o.get("z"), 0, 0, 10000),
           "yaw": _num(o.get("yaw"), 0, -360, 360) if t != "cylinder" else 0.0}
    for k, (default, lo, hi) in _FIELDS[t].items():
        out[k] = _num(o.get(k), default, lo, hi)
    c = o.get("color")
    out["color"] = c if isinstance(c, str) and _COLOR_RE.match(c) else PALETTE[idx % len(PALETTE)]
    return out


def normalize_pad(p):
    if not isinstance(p, dict):
        return None
    return {"id": int(_num(p.get("id"), 1, 1, 8)),
            "x": _num(p.get("x"), *_COORD), "y": _num(p.get("y"), *_COORD),
            "z": _num(p.get("z"), 0, 0, 10000)}


def normalize_scene(data):
    """把外部 JSON（文件 / Web 编辑器）规范成场景内容。"""
    if not isinstance(data, dict):
        raise ValueError("场景必须是 JSON 对象")
    obstacles = data.get("obstacles") or []
    pads = data.get("pads") or []
    if not isinstance(obstacles, list) or not isinstance(pads, list):
        raise ValueError("obstacles / pads 必须是数组")
    if len(obstacles) > 500 or len(pads) > 64:
        raise ValueError("对象数量过多")
    start = data.get("start") or {}
    if not isinstance(start, dict):
        start = {}
    title = str(data.get("title") or "未命名场景").strip()[:40] or "未命名场景"
    return {
        "title": title,
        "description": str(data.get("description") or "")[:200],
        "start": {"x": _num(start.get("x"), *_COORD), "y": _num(start.get("y"), *_COORD),
                  "yaw": _num(start.get("yaw"), 0, -360, 360)},
        "obstacles": [n for n in (normalize_obstacle(o, i) for i, o in enumerate(obstacles)) if n],
        "pads": [n for n in (normalize_pad(p) for p in pads) if n],
    }


# ---------------------------------------------------------------- 物理图元

class _Obb:
    """绕 Z 轴旋转的长方体。"""

    def __init__(self, cx, cy, z0, z1, w, d, yaw):
        r = math.radians(yaw)
        self.cx, self.cy, self.z0, self.z1 = cx, cy, z0, z1
        self.hw, self.hd = w / 2.0, d / 2.0
        self.c, self.s = math.cos(r), math.sin(r)

    def _local(self, x, y):
        # 自身 X 轴在世界中的方向为 (c, -s)，自身 Y 轴为 (s, c)
        dx, dy = x - self.cx, y - self.cy
        return dx * self.c - dy * self.s, dx * self.s + dy * self.c

    def _local_dir(self, dx, dy):
        return dx * self.c - dy * self.s, dx * self.s + dy * self.c

    def contains(self, x, y, z, inflate_xy=0.0, inflate_z=0.0):
        """inflate_z 只向下扩展：z 是飞机底部，高于顶面即不相交。"""
        lx, ly = self._local(x, y)
        return (abs(lx) < self.hw + inflate_xy and abs(ly) < self.hd + inflate_xy
                and self.z0 - inflate_z < z < self.z1)

    def covers(self, x, y, inflate):
        lx, ly = self._local(x, y)
        return abs(lx) < self.hw + inflate and abs(ly) < self.hd + inflate

    def raycast(self, origin, direction, max_dist):
        ox, oy = self._local(origin[0], origin[1])
        dx, dy = self._local_dir(direction[0], direction[1])
        o = (ox, oy, origin[2])
        d = (dx, dy, direction[2])
        lo = (-self.hw, -self.hd, self.z0)
        hi = (self.hw, self.hd, self.z1)
        tmin, tmax = 0.0, max_dist
        for a in range(3):
            if abs(d[a]) < 1e-9:
                if o[a] < lo[a] or o[a] > hi[a]:
                    return None
                continue
            t1, t2 = (lo[a] - o[a]) / d[a], (hi[a] - o[a]) / d[a]
            if t1 > t2:
                t1, t2 = t2, t1
            tmin, tmax = max(tmin, t1), min(tmax, t2)
            if tmin > tmax:
                return None
        return tmin


class _Cylinder:
    """竖直圆柱。"""

    def __init__(self, cx, cy, z0, z1, r):
        self.cx, self.cy, self.z0, self.z1, self.r = cx, cy, z0, z1, r

    def contains(self, x, y, z, inflate_xy=0.0, inflate_z=0.0):
        return (math.hypot(x - self.cx, y - self.cy) < self.r + inflate_xy
                and self.z0 - inflate_z < z < self.z1)

    def covers(self, x, y, inflate):
        return math.hypot(x - self.cx, y - self.cy) < self.r + inflate

    def raycast(self, origin, direction, max_dist):
        ox, oy, oz = origin[0] - self.cx, origin[1] - self.cy, origin[2]
        dx, dy, dz = direction
        best = None

        def consider(t):
            nonlocal best
            if 0 <= t <= max_dist and (best is None or t < best):
                best = t

        if self.contains(origin[0], origin[1], oz):
            return 0.0
        # 侧面：|o + t d|² = r²（仅水平分量）
        a = dx * dx + dy * dy
        if a > 1e-12:
            b = 2 * (ox * dx + oy * dy)
            c = ox * ox + oy * oy - self.r * self.r
            disc = b * b - 4 * a * c
            if disc >= 0:
                sq = math.sqrt(disc)
                for t in ((-b - sq) / (2 * a), (-b + sq) / (2 * a)):
                    if self.z0 <= oz + t * dz <= self.z1:
                        consider(t)
        # 顶面 / 底面
        if abs(dz) > 1e-12:
            for zc in (self.z0, self.z1):
                t = (zc - oz) / dz
                if math.hypot(ox + t * dx, oy + t * dy) <= self.r:
                    consider(t)
        return best


def obstacle_primitives(o):
    """把一个（已规范化的）障碍物拆成物理图元。"""
    t = o["type"]
    if t == "box":
        return [_Obb(o["x"], o["y"], o["z"], o["z"] + o["h"], o["w"], o["d"], o["yaw"])]
    if t == "cylinder":
        return [_Cylinder(o["x"], o["y"], o["z"], o["z"] + o["h"], o["r"])]
    # gate：立柱位于自身 Y 轴两侧，横梁架在门洞上方
    r = math.radians(o["yaw"])
    vx, vy = math.sin(r), math.cos(r)  # 自身 Y 轴（左）在世界中的方向
    th, w, h, z = o["t"], o["w"], o["h"], o["z"]
    off = w / 2 + th / 2
    prims = [_Obb(o["x"] + vx * s * off, o["y"] + vy * s * off, z, z + h, th, th, o["yaw"]) for s in (1, -1)]
    prims.append(_Obb(o["x"], o["y"], z + h, z + h + th, th, w + 2 * th, o["yaw"]))
    return prims


# ---------------------------------------------------------------- 世界

class World:
    def __init__(self, content=None, scene_id="", builtin=False):
        self.version = 0
        self.set_content(content or {"title": "空旷场地"}, scene_id=scene_id, builtin=builtin, dirty=False)

    def set_content(self, data, scene_id=None, builtin=None, dirty=True):
        """替换场景内容（加载场景 / 编辑器提交）。"""
        sc = normalize_scene(data)
        self.title = sc["title"]
        self.description = sc["description"]
        self.start = sc["start"]
        self.obstacles = sc["obstacles"]
        self.pads = sc["pads"]
        if scene_id is not None:
            self.scene_id = scene_id
        if builtin is not None:
            self.builtin = builtin
        self.dirty = dirty
        self._rebuild()

    def _rebuild(self):
        self._prims = [p for o in self.obstacles for p in obstacle_primitives(o)]
        self.version += 1

    def content(self):
        return {"title": self.title, "description": self.description, "start": dict(self.start),
                "obstacles": [dict(o) for o in self.obstacles], "pads": [dict(p) for p in self.pads]}

    def add_obstacle(self, o):
        n = normalize_obstacle(o, len(self.obstacles))
        if n:
            self.obstacles.append(n)
            self.dirty = True
            self._rebuild()

    def clear_obstacles(self):
        self.obstacles = []
        self.dirty = True
        self._rebuild()

    def to_dict(self):
        d = self.content()
        d.update({"version": self.version, "scene": self.scene_id, "builtin": self.builtin, "dirty": self.dirty})
        return d

    # ---- 几何查询 ----
    def collides(self, p):
        x, y, z = p
        for prim in self._prims:
            if prim.contains(x, y, z, DRONE_RADIUS, DRONE_HEIGHT):
                return prim
        return None

    def raycast(self, origin, direction, max_dist):
        """返回射线到最近障碍物的距离（cm），未命中返回 None。"""
        best = None
        for prim in self._prims:
            t = prim.raycast(origin, direction, max_dist)
            if t is not None and (best is None or t < best):
                best = t
        return best

    def floor_height(self, x, y, z=None):
        """(x, y) 正下方最高的支撑面高度（地面或障碍物顶面）。

        给定 z（机身底部高度）时只计入不高于 z 的顶面，悬在头顶的结构（如门框横梁）不算支撑面。"""
        h = 0.0
        for prim in self._prims:
            if z is not None and prim.z1 > z + 1.0:
                continue
            if prim.covers(x, y, DRONE_RADIUS * 0.5):
                h = max(h, prim.z1)
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


def box(x, y, w, d, h, z=0.0, color=None, yaw=0.0):
    """便捷构造：长方体障碍物（测试 / 脚本使用）。"""
    return normalize_obstacle({"type": "box", "x": x, "y": y, "z": z, "w": w, "d": d, "h": h,
                               "yaw": yaw, "color": color})
