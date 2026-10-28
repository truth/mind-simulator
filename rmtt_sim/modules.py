"""外接传感器模组：模拟一块装了自定义固件的 RMTT 扩展板，通过 EXT 指令读取 / 控制。

真机上，超声波、HuskyLens 等模组接在扩展板引脚上，需要在 ESP32 上运行自己的程序才能使用；
模拟器约定一组 EXT 指令（见 README「外接传感器模组」），Python / App / 网页控制台都可以直接调用：

  EXT ultrasonic?            → ultrasonic 123              前向超声波距离（cm，2~400，超量程 999）
  EXT husky mode color|tag|face → husky ok                 切换 HuskyLens 识别模式
  EXT husky mode?            → husky mode color
  EXT husky?                 → husky 2 1,160,120,40,40 3,80,100,30,30   数量 + 每个目标 id,x,y,w,h（320×240 画面）
  EXT husky id 3?            → husky 3,160,120,40,40 / husky none
  EXT light?                 → light 523                   环境光（lux）
  EXT color?                 → color 230 57 46 red         正下方表面颜色（RGB + 颜色名，离表面超过 150cm 时为 0 0 0 none）
  EXT gesture?               → gesture up / gesture none   取出最早一个未读手势
  EXT ir?                    → ir FD08F7 / ir none         取出最早一个未读红外编码
  EXT servo 90               → servo ok                    舵机转到 0~180°
  EXT servo?                 → servo 90
"""

import colorsys
import math
import random
import time
from collections import deque

ULTRA_MIN, ULTRA_MAX, ULTRA_NONE = 2, 400, 999     # cm
ULTRA_RAYS = [(0, 0), (-10, 0), (10, 0), (0, 6), (-6, 4), (6, 4)]   # 波束内的采样方向（偏航°, 俯仰°），约 ±12° 锥形
HUSKY_MODES = ("color", "tag", "face")
HUSKY_RANGE = {"color": 250.0, "tag": 300.0, "face": 200.0}         # 各模式最远识别距离（cm）
COLOR_RANGE = 150.0                                                 # 颜色传感器离表面的最大距离（cm）
GESTURES = ("up", "down", "left", "right", "forward", "backward", "clockwise", "anticlockwise", "wave")
SERVO_SPEED = 300.0                                                 # °/s

# DFRobot 21 键红外遥控器（NEC 编码）
IR_KEYS = {
    "power": "FD00FF", "vol+": "FD807F", "func": "FD40BF", "prev": "FD20DF", "play": "FDA05F",
    "next": "FD609F", "down": "FD10EF", "vol-": "FD906F", "up": "FD50AF", "eq": "FDB04F",
    "rept": "FD708F", "0": "FD30CF", "1": "FD08F7", "2": "FD8877", "3": "FD48B7", "4": "FD28D7",
    "5": "FDA857", "6": "FD6897", "7": "FD18E7", "8": "FD9867", "9": "FD58A7",
}


def color_name(r, g, b):
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    if v < 0.18:
        return "black"
    if s < 0.18:
        return "white" if v > 0.8 else "gray"
    deg = h * 360
    for limit, name in ((15, "red"), (40, "orange"), (70, "yellow"), (160, "green"),
                        (200, "cyan"), (260, "blue"), (345, "purple")):
        if deg < limit:
            return name
    return "red"


def _hex_rgb(c):
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


class ExtModules:
    COMMANDS = ("ultrasonic", "husky", "light", "color", "gesture", "ir", "servo")

    def __init__(self, drone):
        self.d = drone
        self.reset()

    def reset(self):
        self.servo = 90.0
        self.servo_target = 90.0
        self.husky_mode = "color"
        self.gestures = deque(maxlen=16)   # 未读的手势 / 红外事件
        self.ir_codes = deque(maxlen=16)
        self.last_gesture = None           # (名称, 时间)，供网页显示
        self.last_ir = None

    def handles(self, key):
        return key.rstrip("?") in self.COMMANDS

    def update(self, dt):
        diff = self.servo_target - self.servo
        step = SERVO_SPEED * dt
        self.servo = self.servo_target if abs(diff) <= step else self.servo + math.copysign(step, diff)

    # ---- 指令 ----
    def handle(self, parts):
        """parts 为 EXT 之后按空格拆分的参数；返回回复文本，不认识的指令返回 None。"""
        key = parts[0].lower()
        args = [a.lower() for a in parts[1:]]
        if key == "ultrasonic?":
            return "ultrasonic %d" % self.ultrasonic_cm()
        if key == "light?":
            return "light %d" % self.light()
        if key == "color?":
            r, g, b, name = self.color()
            return "color %d %d %d %s" % (r, g, b, name)
        if key == "gesture?":
            return "gesture %s" % (self.gestures.popleft() if self.gestures else "none")
        if key == "ir?":
            return "ir %s" % (self.ir_codes.popleft() if self.ir_codes else "none")
        if key == "servo?":
            return "servo %d" % round(self.servo_target)
        if key == "servo":
            try:
                angle = float(args[-1])     # 兼容 "EXT servo 90" 与 "EXT servo P1 90"
            except (IndexError, ValueError):
                return "servo error"
            if not 0 <= angle <= 180:
                return "servo error"
            self.servo_target = angle
            return "servo ok"
        if key == "husky?":
            found = self.husky()
            return "husky %d%s" % (len(found), "".join(" %d,%d,%d,%d,%d" % f for f in found))
        if key == "husky":
            if args[:1] == ["mode?"]:
                return "husky mode %s" % self.husky_mode
            if len(args) == 2 and args[0] == "mode":
                if args[1] not in HUSKY_MODES:
                    return "husky error"
                self.husky_mode = args[1]
                return "husky ok"
            if len(args) >= 1 and args[0].rstrip("?") == "id":
                try:
                    want = int((args[1] if len(args) > 1 else "").rstrip("?"))
                except ValueError:
                    return "husky error"
                for f in self.husky():
                    if f[0] == want:
                        return "husky %d,%d,%d,%d,%d" % f
                return "husky none"
            return "husky error"
        return None

    # ---- 网页 / App 注入的事件 ----
    def push_gesture(self, name):
        if name not in GESTURES:
            raise ValueError("未知手势：%s" % name)
        self.gestures.append(name)
        self.last_gesture = (name, time.time())

    def push_ir(self, code):
        code = IR_KEYS.get(code, code).upper()
        if not code or len(code) > 8 or any(c not in "0123456789ABCDEF" for c in code):
            raise ValueError("红外编码应为十六进制，如 FD08F7")
        self.ir_codes.append(code)
        self.last_ir = (code, time.time())

    # ---- 传感器读数 ----
    def _front_point(self, ahead, up):
        f = self.d.forward()
        p = self.d.pos
        return (p[0] + f[0] * ahead, p[1] + f[1] * ahead, p[2] + up)

    def ultrasonic_cm(self):
        """前向超声波：在约 ±12° 的锥形波束内取最近的回波。"""
        origin = self._front_point(6, 3)
        best = None
        for dyaw, dpitch in ULTRA_RAYS:
            yaw = math.radians(self.d.yaw + dyaw)
            pitch = math.radians(dpitch)
            direction = (math.cos(yaw) * math.cos(pitch), -math.sin(yaw) * math.cos(pitch), math.sin(pitch))
            t = self.d.world.raycast(origin, direction, ULTRA_MAX)
            if t is not None and (best is None or t < best):
                best = t
        if best is None:
            return ULTRA_NONE
        return int(max(ULTRA_MIN, round(best)))

    def husky(self):
        """HuskyLens（前视）：返回 [(id, x, y, w, h)]，坐标为 320×240 画面像素，近的在前。"""
        cam = self._front_point(8, 6)
        view = self.d.world.camera_view(cam, self.d.yaw, (self.husky_mode,), max_dist=HUSKY_RANGE[self.husky_mode])
        return [(t["id"], x, y, w, h) for t, x, y, w, h, _ in view]

    def light(self):
        lux = self.d.world.light_at(self.d.pos)
        return max(0, round(lux * random.uniform(0.98, 1.02)))

    def color(self):
        """朝下的颜色传感器：正下方最上层表面的颜色。"""
        x, y, z = self.d.pos
        h, c = self.d.world.surface_below(x, y, z + 0.5)
        if z - h > COLOR_RANGE:
            return 0, 0, 0, "none"
        r, g, b = (max(0, min(255, round(v * random.uniform(0.97, 1.03)))) for v in _hex_rgb(c))
        return r, g, b, color_name(r, g, b)

    def to_dict(self):
        now = time.time()
        return {
            "ultrasonic": self.ultrasonic_cm(),
            "husky_mode": self.husky_mode,
            "husky": [list(f) for f in self.husky()],
            "light": self.light(),
            "color": list(self.color()),
            "servo": round(self.servo, 1),
            "gesture": self.last_gesture[0] if self.last_gesture and now - self.last_gesture[1] < 3 else None,
            "ir": self.last_ir[0] if self.last_ir and now - self.last_ir[1] < 3 else None,
            "pending": {"gesture": len(self.gestures), "ir": len(self.ir_codes)},
        }
