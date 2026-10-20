"""RoboMaster TT（Tello EDU + ESP32 扩展模块）飞行器模型与 SDK 3.0 指令解析。

所有方法都在 Simulator 的全局锁内调用，内部不再加锁。
"""

import math
import random
import re
import time
from collections import deque

from .matrix import COLORS, Matrix, TopLed, valid_pattern
from .world import DRONE_HEIGHT, DRONE_RADIUS

TAKEOFF_HEIGHT = 80.0   # cm
TAKEOFF_SPEED = 70.0    # cm/s
LAND_SPEED = 60.0
YAW_RATE = 90.0         # deg/s
RC_MAX_SPEED = 100.0    # rc 杆量 100 对应的速度 cm/s
RC_MAX_YAW = 100.0      # deg/s
MIN_FLY_HEIGHT = 20.0   # 飞行时距支撑面的最低高度
TOF_MAX_MM = 1200       # 前向 ToF 量程，超出返回 8192
TOF_OUT_OF_RANGE = 8192
GRAVITY = 980.0
RE_PREFIX = re.compile(r"^Re([0-9a-fA-F]{2})([0-9a-fA-F]{2})\s+(.+)$")


def _deg_norm(a):
    return (a + 180.0) % 360.0 - 180.0


def _vsub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _vadd(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _vmul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    return math.sqrt(_dot(a, a))


class CmdError(Exception):
    """指令参数/状态错误，消息即回复给客户端的文本。"""


# ---------------------------------------------------------------- 运动片段
# 每个片段 step(drone, dt) 返回 (done, error)。error 非空时中止整个任务并回复该错误。

class MoveSeg:
    def __init__(self, target, speed):
        self.target, self.speed = target, max(speed, 1.0)

    def step(self, d, dt):
        delta = _vsub(self.target, d.pos)
        dist = _norm(delta)
        stepd = self.speed * dt
        if dist <= stepd:
            return d.try_move(self.target), None
        return d.try_move(_vadd(d.pos, _vmul(delta, stepd / dist))) and False, None


class RotateSeg:
    def __init__(self, delta, rate=YAW_RATE):
        self.left, self.rate = delta, rate

    def step(self, d, dt):
        s = self.rate * dt
        if abs(self.left) <= s:
            d.yaw += self.left
            return True, None
        sgn = 1 if self.left > 0 else -1
        d.yaw += sgn * s
        self.left -= sgn * s
        return False, None


class ArcSeg:
    """沿圆弧飞行：center + r*(cos θ·u + sin θ·v)，θ 从 0 到 theta_end。"""

    def __init__(self, center, u, v, r, theta_end, speed):
        self.c, self.u, self.v, self.r = center, u, v, r
        self.end, self.w, self.th = theta_end, speed / r, 0.0

    def step(self, d, dt):
        self.th = min(self.end, self.th + self.w * dt)
        p = _vadd(self.c, _vadd(_vmul(self.u, self.r * math.cos(self.th)),
                                _vmul(self.v, self.r * math.sin(self.th))))
        return d.try_move(p) and self.th >= self.end, None


class FlipSeg:
    DURATION = 0.9

    def __init__(self, direction):
        self.dir, self.t = direction, 0.0
        self.base_z = None

    def step(self, d, dt):
        if self.base_z is None:
            self.base_z = d.pos[2]
        self.t = min(self.DURATION, self.t + dt)
        p = self.t / self.DURATION
        axis = "roll" if self.dir in ("l", "r") else "pitch"
        sign = 1 if self.dir in ("r", "f") else -1
        d.flip = {"axis": axis, "sign": sign, "angle": 360.0 * p}
        d.pos = (d.pos[0], d.pos[1], self.base_z + 30.0 * math.sin(math.pi * p))
        if p >= 1.0:
            d.flip = None
            return True, None
        return False, None


class WaitSeg:
    def __init__(self, t):
        self.t = t

    def step(self, d, dt):
        self.t -= dt
        return self.t <= 0, None


class CallSeg:
    """瞬时执行 fn(drone)，返回非空字符串则作为错误中止任务。"""

    def __init__(self, fn):
        self.fn = fn

    def step(self, d, dt):
        return True, self.fn(d)


# ---------------------------------------------------------------- 飞行器

class Drone:
    def __init__(self, index, ip, world, logger):
        self.index = index
        self.ip = ip
        self.world = world
        self.logger = logger
        self.sn = "0TQZK7SIM%05d" % (index + 1)
        self.ssid = "RMTT-SIM%03d" % (index + 1)
        self.matrix = Matrix()
        self.led = TopLed()
        self.client = None
        self.auto_land_timeout = 0.0
        self.peers = []  # 同一世界中的其他飞机（多机模式下互相碰撞）
        self.reset()

    # ---- 生命周期 ----
    def reset(self):
        # 起飞点取自场景；多架飞机依次排在起飞点左侧，间隔 1m
        s = self.world.start
        r = math.radians(s["yaw"])
        off = self.index * 100.0
        self.home = (s["x"] + math.sin(r) * off, s["y"] + math.cos(r) * off)
        floor = self.world.floor_height(*self.home)
        self.pos = (self.home[0], self.home[1], floor)
        self.yaw = _deg_norm(s["yaw"])
        self.vel = (0.0, 0.0, 0.0)
        self.tilt = [0.0, 0.0]  # 视觉倾角：[前倾, 右倾] deg
        self.flip = None
        self.flying = False
        self.motors = False     # 桨叶是否转动
        self.falling = False
        self.battery = 100.0
        self.temp = 40.0
        self.motor_time = 0.0
        self.speed = 60.0
        self.rc = (0.0, 0.0, 0.0, 0.0)
        self.sdk = False
        self.stream = False
        self.mon = False
        self.mdirection = 0
        self.task = None
        self.last_cmd_t = time.time()
        self.re_tag = None
        self.collision_t = 0.0
        self._collided = False
        self._landing = False
        self.matrix.reset()
        self.led.reset()

    def log(self, kind, text):
        self.logger(self.index, kind, text)

    # ---- 坐标辅助 ----
    def forward(self):
        r = math.radians(self.yaw)
        return (math.cos(r), -math.sin(r), 0.0)

    def left(self):
        r = math.radians(self.yaw)
        return (math.sin(r), math.cos(r), 0.0)

    def body_to_world(self, x, y, z):
        """机体系 (x 前, y 左, z 上) 的位移 → 世界系位移。"""
        f, l = self.forward(), self.left()
        return (f[0] * x + l[0] * y, f[1] * x + l[1] * y, z)

    def floor(self):
        return self.world.floor_height(self.pos[0], self.pos[1])

    def try_move(self, p):
        """移动到 p，撞到障碍物或其他飞机则不移动并返回 False（由 update 判定为碰撞）。"""
        if self.world.collides(p):
            self._collided = True
            return False
        for other in self.peers:
            if (math.hypot(p[0] - other.pos[0], p[1] - other.pos[1]) < 2 * DRONE_RADIUS
                    and abs(p[2] - other.pos[2]) < DRONE_HEIGHT):
                self._collided = True
                other.collision_t = time.time()
                other.log("warn", "被 #%d 撞到" % (self.index + 1))
                return False
        floor = self.world.floor_height(p[0], p[1])
        if p[2] < floor + MIN_FLY_HEIGHT and self.flying and not self._landing:
            p = (p[0], p[1], max(p[2], floor + MIN_FLY_HEIGHT))
        self.pos = p
        return True

    # ---- 传感器 ----
    def tof_front_mm(self):
        f = self.forward()
        origin = _vadd(self.pos, (f[0] * 6, f[1] * 6, 2.0))
        dist = self.world.raycast(origin, f, TOF_MAX_MM / 10.0)
        if dist is None:
            return TOF_OUT_OF_RANGE
        return max(0, int(dist * 10))

    def tof_down_cm(self):
        h = self.pos[2] - self.floor()
        return 10 if h < 10 else int(h)

    def pad(self, wanted=None):
        if not self.mon:
            return None
        return self.world.detect_pad(self.pos, wanted)

    def _pad_rel(self, pad):
        return (int(self.pos[0] - pad["x"]), int(self.pos[1] - pad["y"]), int(self.pos[2] - pad["z"]))

    # ---- 仿真步进 ----
    def update(self, dt):
        self._collided = False
        self._landing = bool(self.task and self.task.get("landing"))
        prev = self.pos

        if self.task:
            seg = self.task["segs"][0]
            done, err = seg.step(self, dt)
            if self._collided:
                self.collision_t = time.time()
                self.log("warn", "碰撞！指令 [%s] 中止" % self.task["cmd"])
                self._finish("error Collision")
            elif err:
                self._finish(err)
            elif done:
                self.task["segs"].popleft()
                if not self.task["segs"]:
                    self._finish("ok")
        elif self.flying and any(self.rc):
            a, b, c, dyaw = self.rc
            v = self.body_to_world(b / 100 * RC_MAX_SPEED, -a / 100 * RC_MAX_SPEED, c / 100 * RC_MAX_SPEED)
            if not self.try_move(_vadd(self.pos, _vmul(v, dt))):
                self.collision_t = time.time()
            self.yaw += dyaw / 100 * RC_MAX_YAW * dt

        # 急停后自由落体
        if not self.flying:
            floor = self.floor()
            if self.pos[2] > floor + 0.01:
                self.falling = True
                vz = self.vel[2] - GRAVITY * dt
                self.pos = (self.pos[0], self.pos[1], max(floor, self.pos[2] + vz * dt))
            else:
                self.falling = False
                self.pos = (self.pos[0], self.pos[1], floor)

        self.yaw = _deg_norm(self.yaw)
        if dt > 0:
            self.vel = _vmul(_vsub(self.pos, prev), 1.0 / dt)
        self._update_tilt(dt)
        self._update_power(dt)
        self.matrix.update(dt)

        if (self.auto_land_timeout and self.flying and not self.task
                and time.time() - self.last_cmd_t > self.auto_land_timeout):
            self.log("warn", "%.0f 秒未收到指令，自动降落" % self.auto_land_timeout)
            self.rc = (0.0, 0.0, 0.0, 0.0)
            self._start_task("auto-land", self._land_segs(), None, landing=True)

    def _update_tilt(self, dt):
        f, l = self.forward(), self.left()
        vf, vl = _dot(self.vel, f), _dot(self.vel, l)
        target = [max(-20, min(20, vf / 100 * 15)), max(-20, min(20, -vl / 100 * 15))]
        k = min(1.0, dt * 6)
        for i in range(2):
            self.tilt[i] += (target[i] - self.tilt[i]) * k

    def _update_power(self, dt):
        if self.motors or self.flying:
            self.motor_time += dt
            self.battery -= dt / (12.0 if self.flying else 30.0)
            self.temp = min(80.0, self.temp + dt * 0.15)
        else:
            self.battery -= dt / 300.0
            self.temp = max(40.0, self.temp - dt * 0.1)
        self.battery = max(0.0, self.battery)
        if self.battery <= 0 and self.flying and not (self.task and self.task.get("landing")):
            self.log("warn", "电量耗尽，强制降落")
            self._start_task("auto-land", self._land_segs(), None, landing=True)

    # ---- 任务 ----
    def _start_task(self, cmd, segs, reply, landing=False):
        if self.task and self.task["reply"]:
            self.task["reply"]("error Interrupted")
        self.task = {"cmd": cmd, "segs": deque(segs), "reply": reply, "landing": landing}

    def _finish(self, result):
        task, self.task = self.task, None
        self.flip = None
        if task["reply"]:
            task["reply"](result)

    def _land_segs(self):
        def touchdown(d):
            d.flying = False
            d.motors = False
            d.rc = (0.0, 0.0, 0.0, 0.0)
        target = (self.pos[0], self.pos[1], self.floor())
        return [MoveSeg(target, LAND_SPEED), CallSeg(touchdown)]

    # ---- 指令入口 ----
    def handle(self, raw, reply, source="udp"):
        """处理一条 SDK 文本指令。reply(text) 可能立即调用，也可能在动作完成后调用。"""
        cmd = raw.strip()
        if not cmd:
            return
        self.last_cmd_t = time.time()

        # 防丢包序号 "Re[tag][id] 指令"（Mind+ 实时模式每条指令以同一 tag 连发 5 遍）：
        # 同一 tag 只执行一次；ok / error 回复带上 "Re[tag][id] " 前缀，查询结果原样返回
        m = RE_PREFIX.match(cmd)
        if m:
            tag, seq, cmd = m.group(1), m.group(1) + m.group(2), m.group(3)
            if tag == self.re_tag:
                return
            self.re_tag = tag
            plain_reply = reply

            def reply(text):
                if text == "ok" or text.startswith("error"):
                    text = "Re%s %s" % (seq, text)
                plain_reply(text)

        parts = cmd.split()
        key = parts[0].lower()

        # 运动中重发的同一条指令视为 UDP 重传，忽略
        if self.task and self.task["cmd"] == cmd and key not in ("stop", "emergency"):
            return
        try:
            if key == "ext":
                res = self._ext(cmd[3:].strip())
            elif key.endswith("?"):
                res = self._read(key)
            else:
                handler = getattr(self, "_c_" + key, None)
                if handler is None:
                    raise CmdError("unknown command: " + key)
                args = parts[1:]
                if self.task and key not in self.IMMEDIATE:
                    raise CmdError("error Not joystick")
                if not self.sdk and key != "command" and source == "udp":
                    self.log("warn", "尚未发送 command 进入 SDK 模式，仍按 SDK 模式处理")
                    self.sdk = True
                res = handler(args, cmd, reply)
        except CmdError as e:
            res = str(e)
        except (ValueError, IndexError):
            res = "error"
        if res is not None:
            reply(res)

    IMMEDIATE = {"command", "emergency", "stop", "rc", "speed", "mon", "moff", "mdirection",
                 "streamon", "streamoff", "wifi", "ap", "multiwifi", "port", "setfps",
                 "setbitrate", "setresolution", "wifisetchannel", "land"}

    # ---- 读取类指令 ----
    def _read(self, key):
        tof = self.tof_down_cm()
        t = int(self.temp)
        table = {
            "speed?": "%.1f" % self.speed,
            "battery?": str(int(self.battery)),
            "time?": "%ds" % int(self.motor_time),
            "wifi?": "90",
            "sdk?": "30",
            "sn?": self.sn,
            "hardware?": "RMTT",
            "wifiversion?": "1.4.0.0",
            "ap?": "%s 12345678" % self.ssid,
            "ssid?": self.ssid,
            "height?": "%ddm" % int(round((self.pos[2] - self.home_floor()) / 10)),
            "temp?": "%d~%dC" % (t, t + 2),
            "attitude?": "pitch:%d;roll:%d;yaw:%d;" % (self._pitch(), self._roll(), int(self.yaw)),
            "baro?": "%.2f" % self._baro(),
            "acceleration?": "agx:0.00;agy:0.00;agz:-999.00;",
            "tof?": "%dmm" % (tof * 10),
        }
        if key not in table:
            raise CmdError("unknown command: " + key)
        return table[key]

    def home_floor(self):
        return self.world.floor_height(*self.home)

    def _pitch(self):
        return int(-self.tilt[0])

    def _roll(self):
        return int(self.tilt[1])

    def _baro(self):
        return 50.0 + self.pos[2] / 100.0

    # ---- 控制类指令 ----
    def _require_flying(self):
        if not self.flying:
            raise CmdError("error Motor stop")

    @staticmethod
    def _num(s, lo=None, hi=None):
        v = float(s)
        if (lo is not None and v < lo) or (hi is not None and v > hi):
            raise CmdError("error Out of range")
        return v

    def _c_command(self, a, cmd, reply):
        self.sdk = True
        return "ok"

    def _c_takeoff(self, a, cmd, reply):
        if self.flying:
            raise CmdError("error Already flying")
        if self.battery < 10:
            raise CmdError("error Battery low")
        self.flying = True
        self.motors = True
        self.falling = False
        target = (self.pos[0], self.pos[1], self.floor() + TAKEOFF_HEIGHT)
        self._start_task(cmd, [WaitSeg(0.6), MoveSeg(target, TAKEOFF_SPEED)], reply)
        return None

    _c_throwfly = _c_takeoff

    def _c_land(self, a, cmd, reply):
        if not self.flying:
            self.motors = False
            return "ok"
        self.rc = (0.0, 0.0, 0.0, 0.0)
        self._start_task(cmd, self._land_segs(), reply, landing=True)
        return None

    def _c_emergency(self, a, cmd, reply):
        if self.task:
            self._finish("error Interrupted")
        self.flying = False
        self.motors = False
        self.rc = (0.0, 0.0, 0.0, 0.0)
        return "ok"

    def _c_stop(self, a, cmd, reply):
        self.rc = (0.0, 0.0, 0.0, 0.0)
        if self.task and not self.task.get("landing"):
            self._finish("error Interrupted")
        return "ok"

    def _c_motoron(self, a, cmd, reply):
        if not self.flying:
            self.motors = True
        return "ok"

    def _c_motoroff(self, a, cmd, reply):
        if not self.flying:
            self.motors = False
        return "ok"

    def _move(self, cmd, reply, dx, dy, dz):
        self._require_flying()
        start = self.pos
        delta = self.body_to_world(dx, dy, dz)
        target = _vadd(start, delta)
        target = (target[0], target[1],
                  max(target[2], self.world.floor_height(target[0], target[1]) + MIN_FLY_HEIGHT))
        self._start_task(cmd, [MoveSeg(target, self.speed)], reply)

    def _dist(self, a):
        return self._num(a[0], 20, 500)

    def _c_up(self, a, cmd, reply):
        self._move(cmd, reply, 0, 0, self._dist(a))

    def _c_down(self, a, cmd, reply):
        self._move(cmd, reply, 0, 0, -self._dist(a))

    def _c_left(self, a, cmd, reply):
        self._move(cmd, reply, 0, self._dist(a), 0)

    def _c_right(self, a, cmd, reply):
        self._move(cmd, reply, 0, -self._dist(a), 0)

    def _c_forward(self, a, cmd, reply):
        self._move(cmd, reply, self._dist(a), 0, 0)

    def _c_back(self, a, cmd, reply):
        self._move(cmd, reply, -self._dist(a), 0, 0)

    def _c_cw(self, a, cmd, reply):
        self._require_flying()
        self._start_task(cmd, [RotateSeg(self._num(a[0], 1, 3600))], reply)

    def _c_ccw(self, a, cmd, reply):
        self._require_flying()
        self._start_task(cmd, [RotateSeg(-self._num(a[0], 1, 3600))], reply)

    def _c_flip(self, a, cmd, reply):
        self._require_flying()
        if a[0] not in ("l", "r", "f", "b"):
            raise CmdError("error")
        if self.battery < 50:
            raise CmdError("error Low battery")
        self._start_task(cmd, [FlipSeg(a[0])], reply)

    def _resolve_pad(self, mid):
        """mid: m1~m8 指定卡；m-1/m-2 任意已识别的卡。"""
        if not mid.lower().startswith("m"):
            raise CmdError("error")
        n = int(mid[1:])
        if n in (-1, -2):
            pad = self.pad()
        elif 1 <= n <= 8:
            pad = self.pad(n)
        else:
            raise CmdError("error")
        if pad is None:
            raise CmdError("error No valid marker")
        return pad

    def _c_go(self, a, cmd, reply):
        self._require_flying()
        x, y, z = (self._num(v, -500, 500) for v in a[:3])
        speed = self._num(a[3], 10, 100)
        if len(a) >= 5:
            pad = self._resolve_pad(a[4])
            target = (pad["x"] + x, pad["y"] + y, pad["z"] + z)
        else:
            if max(abs(x), abs(y), abs(z)) < 20:
                raise CmdError("error Out of range")
            target = _vadd(self.pos, self.body_to_world(x, y, z))
        self._start_task(cmd, [MoveSeg(target, speed)], reply)

    def _c_curve(self, a, cmd, reply):
        self._require_flying()
        x1, y1, z1, x2, y2, z2 = (self._num(v, -500, 500) for v in a[:6])
        speed = self._num(a[6], 10, 60)
        if len(a) >= 8:
            pad = self._resolve_pad(a[7])
            base = (pad["x"], pad["y"], pad["z"])
            p1, p2 = _vadd(base, (x1, y1, z1)), _vadd(base, (x2, y2, z2))
        else:
            p1 = _vadd(self.pos, self.body_to_world(x1, y1, z1))
            p2 = _vadd(self.pos, self.body_to_world(x2, y2, z2))
        seg = self.make_arc(self.pos, p1, p2, speed)
        self._start_task(cmd, [seg], reply)

    @staticmethod
    def make_arc(A, B, C, speed):
        """过 A、B、C 三点的圆弧（从 A 经 B 到 C）。半径须在 0.5~10m。"""
        a, b = _vsub(B, A), _vsub(C, A)
        axb = _cross(a, b)
        n2 = _dot(axb, axb)
        if n2 < 1e-6:
            raise CmdError("error Radius is too large")
        k = _vsub(_vmul(b, _dot(a, a)), _vmul(a, _dot(b, b)))
        center = _vadd(A, _vmul(_cross(k, axb), 1.0 / (2 * n2)))
        r = _norm(_vsub(A, center))
        if not 50 <= r <= 1000:
            raise CmdError("error Radius is out of range")
        u = _vmul(_vsub(A, center), 1.0 / r)
        n = _vmul(axb, 1.0 / math.sqrt(n2))
        v = _cross(n, u)

        def ang(P, v):
            w = _vsub(P, center)
            return math.atan2(_dot(w, v), _dot(w, u)) % (2 * math.pi)

        if not ang(B, v) < ang(C, v):
            v = _vmul(v, -1)
        return ArcSeg(center, u, v, r, ang(C, v), speed)

    def _c_jump(self, a, cmd, reply):
        self._require_flying()
        x, y, z = (self._num(v, -500, 500) for v in a[:3])
        speed = self._num(a[3], 10, 100)
        yaw = self._num(a[4], -360, 360)
        pad1 = self._resolve_pad(a[5])
        mid2 = int(a[6][1:])
        target = (pad1["x"] + x, pad1["y"] + y, pad1["z"] + z)

        def check(d):
            if d.pad(None if mid2 in (-1, -2) else mid2) is None:
                return "error No valid marker"
            return None
        segs = [MoveSeg(target, speed),
                CallSeg(lambda d: setattr(d, "_jump_rot", _deg_norm(yaw - d.yaw))),
                _LazyRotate(), CallSeg(check)]
        self._start_task(cmd, segs, reply)

    def _c_setyaw(self, a, cmd, reply):
        """setyaw yaw mid：旋转到挑战卡坐标系下的航向 yaw（挑战卡坐标系与世界坐标系同向，同 jump）。"""
        self._require_flying()
        yaw = self._num(a[0], -360, 360)
        self._resolve_pad(a[1])
        self._start_task(cmd, [RotateSeg(_deg_norm(yaw - self.yaw))], reply)

    def _c_rc(self, a, cmd, reply):
        vals = tuple(max(-100.0, min(100.0, float(v))) for v in a[:4])
        if len(vals) != 4:
            raise ValueError
        self.rc = vals
        return None  # rc 指令无回复

    def _c_speed(self, a, cmd, reply):
        self.speed = self._num(a[0], 10, 100)
        return "ok"

    def _c_streamon(self, a, cmd, reply):
        self.stream = True
        return "ok"

    def _c_streamoff(self, a, cmd, reply):
        self.stream = False
        return "ok"

    def _c_mon(self, a, cmd, reply):
        self.mon = True
        return "ok"

    def _c_moff(self, a, cmd, reply):
        self.mon = False
        return "ok"

    def _c_mdirection(self, a, cmd, reply):
        self.mdirection = int(self._num(a[0], 0, 2))
        return "ok"

    def _c_ok(self, a, cmd, reply):
        return "ok"

    _c_wifi = _c_ap = _c_multiwifi = _c_port = _c_setfps = _c_ok
    _c_setbitrate = _c_setresolution = _c_wifisetchannel = _c_ok

    # ---- EXT：转发给 ESP32 扩展模块（出厂固件行为） ----
    def _ext(self, body):
        parts = body.split()
        if not parts:
            return "error"
        key = parts[0].lower()
        if key == "tof?":
            return "tof %d" % self.tof_front_mm()
        if key == "version?":
            return "version=v1.0.0.4"
        if key == "led":
            return self._ext_led(parts[1:])
        if key == "mled":
            try:
                ok = self._ext_mled(body.split(None, 1)[1] if len(parts) > 1 else "")
            except (ValueError, IndexError):
                ok = False
            return "mled ok" if ok else "mled error"
        return "unknown command: EXT " + parts[0]

    def _ext_led(self, a):
        try:
            if a[0] == "br":
                t = float(a[1])
                c = tuple(int(v) for v in a[2:5])
                if not 0.1 <= t <= 2.5 or len(c) != 3:
                    return "led error"
                self.led.set("breath", t, c)
            elif a[0] == "bl":
                t = float(a[1])
                c1, c2 = tuple(int(v) for v in a[2:5]), tuple(int(v) for v in a[5:8])
                if not 0.1 <= t <= 10 or len(c1) != 3 or len(c2) != 3:
                    return "led error"
                self.led.set("blink", t, c1, c2)
            else:
                c = tuple(int(v) for v in a[0:3])
                if len(c) != 3:
                    return "led error"
                self.led.set("solid", 0, c)
        except (ValueError, IndexError):
            return "led error"
        if not all(0 <= v <= 255 for v in self.led.c1 + self.led.c2):
            self.led.reset()
            return "led error"
        return "led ok"

    def _ext_mled(self, body):
        parts = body.split()
        sub = parts[0]
        m = self.matrix
        if sub == "g":
            pat = parts[1].lower()[:64].ljust(64, "0")
            if not valid_pattern(pat):
                return False
            m.show(pat)
        elif sub == "s":
            color, text = parts[1], body.split(None, 2)[2]
            if color not in COLORS:
                return False
            m.show_char(color, text)
        elif sub in ("l", "r", "u", "d"):
            color, rate = parts[1], float(parts[2])
            payload = body.split(None, 3)[3]
            if not 0.1 <= rate <= 2.5:
                return False
            if color == "g":
                pat = payload.lower()[:64].ljust(64, "0")
                if not valid_pattern(pat):
                    return False
                m.scroll_pattern(sub, rate, pat)
            elif color in COLORS:
                if len(payload) >= 70:
                    return False
                m.scroll_text(sub, color, rate, payload)
            else:
                return False
        elif sub == "sg":
            pat = parts[1].lower()[:64].ljust(64, "0")
            if not valid_pattern(pat):
                return False
            m.boot = pat
            m.show(pat)
        elif sub == "sc":
            m.boot = "0" * 64
            m.show(m.boot)
        elif sub == "sl":
            n = int(parts[1])
            if not 0 <= n <= 255:
                return False
            m.brightness = n
        else:
            return False
        return True

    # ---- 状态输出 ----
    def state_string(self):
        pad = self.pad()
        if not self.mon:
            mid, px, py, pz = -1, -100, -100, -100
        elif pad is None:
            mid, px, py, pz = -1, 0, 0, 0
        else:
            mid = pad["id"]
            px, py, pz = self._pad_rel(pad)
        t = int(self.temp)
        vx, vy, vz = (int(v / 10) for v in self.vel)
        return ("mid:%d;x:%d;y:%d;z:%d;mpry:0,0,%d;pitch:%d;roll:%d;yaw:%d;vgx:%d;vgy:%d;vgz:%d;"
                "templ:%d;temph:%d;tof:%d;h:%d;bat:%d;baro:%.2f;time:%d;"
                "agx:0.00;agy:0.00;agz:-999.00;\r\n") % (
            mid, px, py, pz, int(self.yaw), self._pitch(), self._roll(), int(self.yaw),
            vx, vy, vz, t, t + 2, self.tof_down_cm(),
            int(self.pos[2] - self.home_floor()), int(self.battery), self._baro(),
            int(self.motor_time))

    def to_dict(self):
        pad = self.pad()
        return {
            "index": self.index, "ip": self.ip, "sn": self.sn, "ssid": self.ssid,
            "pos": [round(v, 1) for v in self.pos], "yaw": round(self.yaw, 1),
            "tilt": [round(v, 2) for v in self.tilt], "flip": self.flip,
            "flying": self.flying, "motors": self.motors or self.flying, "falling": self.falling,
            "battery": int(self.battery), "temp": int(self.temp), "speed": self.speed,
            "height": int(self.pos[2] - self.home_floor()), "tof_front": self.tof_front_mm(),
            "tof_down": self.tof_down_cm(), "time": int(self.motor_time),
            "mon": self.mon, "mid": pad["id"] if pad else -1,
            "pad_rel": self._pad_rel(pad) if pad else None,
            "rc": self.rc, "task": self.task["cmd"] if self.task else None,
            "sdk": self.sdk, "stream": self.stream,
            "client": "%s:%d" % self.client if self.client else None,
            "collision_age": round(time.time() - self.collision_t, 2) if self.collision_t else None,
            "matrix": self.matrix.to_dict(), "led": self.led.to_dict(),
        }


class _LazyRotate(RotateSeg):
    """jump 指令：到达目标点后才知道需要转多少度。"""

    def __init__(self):
        super().__init__(0.0)
        self._init = False

    def step(self, d, dt):
        if not self._init:
            self.left, self._init = getattr(d, "_jump_rot", 0.0), True
        return super().step(d, dt)
