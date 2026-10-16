"""RMTT 扩展模块：8x8 红蓝点阵屏 + 顶部 RGB 灯 的状态模拟。

点阵每个像素取值：'0' 灭 / 'r' 红 / 'b' 蓝 / 'p' 紫（红蓝同亮）。
"""

from .font8x8 import FONT8X8

BLANK = "0" * 64
COLORS = ("r", "b", "p")

# 出厂固件开机后显示 "TT"
DEFAULT_BOOT = (
    "00000000"
    "ppp00ppp"
    "0p0000p0"
    "0p0000p0"
    "0p0000p0"
    "0p0000p0"
    "0p0000p0"
    "00000000"
)

HEART = (
    "00000000"
    "0rr00rr0"
    "rrrrrrrr"
    "rrrrrrrr"
    "0rrrrrr0"
    "00rrrr00"
    "000rr000"
    "00000000"
)


def char_bitmap(ch, color):
    """返回单个字符的 8x8 位图（8 行字符串）。"""
    rows = FONT8X8.get(ord(ch), FONT8X8[ord("?")])
    return ["".join(color if (bits >> x) & 1 else "0" for x in range(8)) for bits in rows]


def valid_pattern(s):
    return len(s) == 64 and all(c in "0rbp" for c in s)


class Matrix:
    def __init__(self):
        self.boot = DEFAULT_BOOT
        self.brightness = 255
        self.reset()

    def reset(self):
        self.frame = self.boot
        self.scroll = None  # dict(dir, rate, strip, length, offset)

    # ---- 指令 ----
    def show(self, pattern):
        self.scroll = None
        self.frame = pattern

    def show_char(self, color, text):
        self.scroll = None
        if text.lower() == "heart":
            self.frame = HEART.replace("r", color)
        else:
            self.frame = "".join(char_bitmap(text[0], color))

    def scroll_text(self, direction, color, rate, text):
        bitmaps = [char_bitmap(c, color) for c in text]
        self._start_scroll(direction, rate, bitmaps, gap=True)

    def scroll_pattern(self, direction, rate, pattern):
        rows = [pattern[i * 8:(i + 1) * 8] for i in range(8)]
        self._start_scroll(direction, rate, [rows], gap=False)

    def _start_scroll(self, direction, rate, bitmaps, gap):
        # 把所有字符拼成一条长带：水平滚动拼成 8 行宽带，垂直滚动拼成 8 列长带
        blank = ["0" * 8] * 8
        seq = ([blank] if gap else []) + bitmaps
        if direction in ("l", "r"):
            strip = ["".join(bm[y] for bm in seq) for y in range(8)]
            length = len(strip[0])
        else:
            strip = [row for bm in seq for row in bm]
            length = len(strip)
        self.scroll = {"dir": direction, "rate": rate, "strip": strip,
                       "length": length, "offset": 0.0}
        self._render_scroll()

    # ---- 动画 ----
    def update(self, dt):
        if not self.scroll:
            return
        s = self.scroll
        s["offset"] = (s["offset"] + dt * s["rate"] * 8) % s["length"]  # rate=每秒移动的整帧数
        self._render_scroll()

    def _render_scroll(self):
        s = self.scroll
        n, off = s["length"], int(s["offset"])
        strip = s["strip"]
        if s["dir"] == "l":
            rows = ["".join(strip[y][(off + x) % n] for x in range(8)) for y in range(8)]
        elif s["dir"] == "r":
            rows = ["".join(strip[y][(x - off) % n] for x in range(8)) for y in range(8)]
        elif s["dir"] == "u":
            rows = [strip[(off + y) % n] for y in range(8)]
        else:
            rows = [strip[(y - off) % n] for y in range(8)]
        self.frame = "".join(rows)

    def to_dict(self):
        return {"frame": self.frame, "brightness": self.brightness}


class TopLed:
    """顶部 RGB 灯。mode: solid / breath / blink，具体动画在前端按时间计算。"""

    def __init__(self):
        self.reset()

    def reset(self):
        self.mode = "solid"
        self.freq = 0.0
        self.c1 = (0, 0, 0)
        self.c2 = (0, 0, 0)

    def set(self, mode, freq, c1, c2=(0, 0, 0)):
        self.mode, self.freq, self.c1, self.c2 = mode, freq, c1, c2

    def to_dict(self):
        return {"mode": self.mode, "freq": self.freq, "c1": self.c1, "c2": self.c2}
