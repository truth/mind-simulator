# Mind+ 对接说明：补丁、协议与问题排查

本文记录让 **Mind+ 实时模式**在本机连接 RoboMaster TT 模拟器的全部细节：为什么要给 Mind+ 打补丁、补丁原理与移植方法、
Mind+ 与飞机之间的协议要点、视频流链路，以及对接过程中遇到的问题和解决办法。用于后续扩展 Mind+ 积木支持或排查兼容性问题。

> 结论基于 **Mind+ V1.8.1 RC3.0 免安装版**（Electron 13.6.9）与 **Mind+ V2.0.7** 的源码分析和实测。
> 文中 `app.asar` 内的文件名是 1.8.1 RC3.0 的打包结果，其他版本会变化，按「[在 app.asar 中查找代码](#在-appasar-中查找代码)」重新定位即可。

## 目录

- [1. 选择 Mind+ 版本](#1-选择-mind-版本)
- [2. Mind+ 1.x 如何连接 TT](#2-mind-1x-如何连接-tt)
- [3. 连接补丁 patch_mindplus1x.py](#3-连接补丁-patch_mindplus1xpy)
- [4. 指令协议要点](#4-指令协议要点)
- [5. 视频流](#5-视频流)
- [6. 问题与解决办法](#6-问题与解决办法)
- [7. 扩展指南](#7-扩展指南)
- [8. 关键代码位置速查](#8-关键代码位置速查)

## 1. 选择 Mind+ 版本

| 版本 | 实时模式 TT | 说明 |
|---|---|---|
| **V1.x（推荐 V1.8.1 免安装版）** | 可用（需打连接补丁） | TT 扩展直接用 Node `dgram` 收发 UDP，模拟器完整支持 |
| V2.0.7 | **不可用** | 实时模式 TT 扩展的 78 个积木函数全部是空函数，连真机也控制不了 |

Mind+ 2.0 的证据：扩展下载到 `%LOCALAPPDATA%\mind+\download\realtime\extensions\ext-DFRobot-Tello@0.0.4\main.js`，
其中所有积木实现形如 `value: function telloTakeOff(args) {}`；实时模式前端 `realtime-gui` 与后台 `mind-link`
（WebSocket 19302 / 19303 转发 UDP）中都没有 Tello 执行逻辑。

**1.x 与 2.0 可以共存**：从[历史版本页](https://mindplus.dfrobot.com.cn/PreviousVersions)下载 1.x **免安装版**解压到单独目录即可，
不要用安装版（官方说明安装版会覆盖已有版本）。两个版本不要同时运行。

## 2. Mind+ 1.x 如何连接 TT

TT 扩展注册为「外设扩展」（`registerPeripheralExtension`），连接入口是**积木区「RoboMaster TT(单机)」标题旁的状态图标**
（未连接为橙色 **!**），**不是**顶部菜单「连接设备」（那只列串口）。点图标后：

1. **扫描 WiFi**：`wifiManager.scan()`（底层调用 `netsh`），只保留 SSID 匹配 `/TELLO|RMTT/i` 的热点；
   电脑当前连接的 WiFi 也会被列出。扫描出错或列表为空时每 1～1.5 秒重试，连续 6 次失败后提示「未找到 Tello」。
2. **选择热点**：若电脑**已连接**该 SSID，直接进入第 3 步；否则调用 `wifi.connect()` 让电脑连上这个热点。
3. **connectTello**：创建 UDP 套接字绑定 **`0.0.0.0:8889`**，2 秒后向 `192.168.10.1:8889` 发 `command`，
   等待回复 `ok`（回复 `unactive` 提示激活飞机，其他情况重试一次后断开）。
4. **状态通道**：再绑定 **`0.0.0.0:8890`** 接收状态字符串，作为心跳；长时间收不到则判定断线（图标变回 **!**）。

连接成功前所有积木都不发包（`clientSendMsg` 开头 `if (!this.status) return "请先连接 Tello"`）。

模拟器没有真实热点，第 1 步列表永远为空——这就是需要补丁的原因。网络层面（第 3、4 步）则无需任何修改：
`tools/setup_network.ps1` 把 `192.168.10.1` 加到本机环回接口，Mind+ 发往 `192.168.10.1:8889` 的包直接到达模拟器。

**组队扩展不可用**：「RoboMaster TT(组队)」通过 worker（`dist/static/child_worker/scan-tello/scan-tello-team.js`）
扫描本机各网卡所在 /24 网段，并**丢弃来自本机 IP 的回复**——而模拟器的 `192.168.10.x` 正是本机地址，所以永远扫描不到。

## 3. 连接补丁 patch_mindplus1x.py

### 用法

```bash
# 先关闭 Mind+（文件被占用时写入会失败）
python tools/patch_mindplus1x.py "F:/hos/tool/MindPlus_Win_V1.8.1_RC3.0"            # 打补丁，自动备份 app.asar.bak
python tools/patch_mindplus1x.py "F:/hos/tool/MindPlus_Win_V1.8.1_RC3.0" --restore  # 从备份还原
```

重复运行会提示「已经打过补丁」；补丁点与预期不符（Mind+ 版本不同）时不做任何修改并报告是哪一处。

### 改了什么

只改 `resources/app.asar` 中 TT 单机扩展（`dist/chunks/b6a636c5d1271bb37c97.chunk.js`）的三处代码：

| # | 位置 | 原代码 | 改为 | 作用 |
|---|---|---|---|---|
| 1 | `scan()` 扫描回调 | `if (err) {` | `if (false) {` | 没有无线网卡 / WLAN 服务时扫描出错，不再重试报错 |
| 2 | `scan()` 扫描回调 | `networks = networks \|\| [];` | `networks = (networks \|\| []).concat([{ssid: "RMTT-SIM", signal_level: -40}]);` | 列表固定出现虚拟热点 `RMTT-SIM` |
| 3 | `connect()` 的 `nextFun` 开头 | — | `if (ssid == "RMTT-SIM") return _this.connectTello();` | 选择 RMTT-SIM 时跳过连接 WiFi，直接走第 3 步连到 `192.168.10.1:8889` |

选择真实的 RMTT / TELLO 热点时行为不变，打补丁后仍可连接真机。

### 原理：等长原地替换

`app.asar` 是 Electron 的归档格式：文件头是一段 JSON，记录每个文件在归档中的偏移和长度，之后是各文件内容首尾相接。
如果解包、修改、重新打包，需要正确处理 `app.asar.unpacked` 中的原生模块，风险较大。补丁改用**等长替换**：

- 替换文本**不长于**原文，不足部分用空格补齐，整个文件长度、所有偏移都不变，文件头无需改动；
- 原文附近的中文注释（每个汉字 UTF-8 占 3 字节）被一并替换掉，腾出足够空间；空格在 JS 中无害；
- Electron 13 没有启用 asar 完整性校验（`Mind+.exe` 中没有 `ElectronAsarIntegrity` 资源），改动内容不会被拒绝加载。

替换后的代码片段（以第 1、2 处为例）：

```js
      this.wifi.scan(function (err, networks) {
        if (false) {                 // 原为 if (err) { ... // 扫描超时
          ...
        } else {
          networks = (networks || []).concat([{ssid: "RMTT-SIM", signal_level: -40}]);   ←原注释位置补空格
```

### 移植到其他 Mind+ 版本

1. 在 `app.asar` 中搜索 `TELLO|RMTT`（扫描过滤正则），定位 TT 扩展的 `scan` / `connect` 代码，
   方法见[在 app.asar 中查找代码](#在-appasar-中查找代码)；
2. 对照新版本代码修改 `tools/patch_mindplus1x.py` 中的 `PATCHES`（原文需与 asar 中**逐字节一致**，包括缩进与注释）；
3. **先在副本上验证**再改正式文件：
   ```bash
   mkdir -p /tmp/m/resources && cp ".../resources/app.asar" /tmp/m/resources/
   python tools/patch_mindplus1x.py /tmp/m              # 打补丁
   # 取出被修改的 webpack 模块，用 node --check 检查语法（示例见第 7 节）
   python tools/patch_mindplus1x.py /tmp/m --restore    # 还原
   cmp /tmp/m/resources/app.asar ".../resources/app.asar"  # 应完全一致
   ```
4. 启动 Mind+，加载扩展后点 **!** 图标，列表中出现 `RMTT-SIM` 且能连接即成功。

## 4. 指令协议要点

### 地址与端口

| 方向 | 地址 | 内容 |
|---|---|---|
| Mind+ → 飞机 | 本机 `0.0.0.0:8889` → `192.168.10.1:8889` | 指令 |
| 飞机 → Mind+ | `192.168.10.1:8889` → `192.168.10.2:8889` | 回复 |
| 飞机 → Mind+ | → `192.168.10.2:8890`，10 Hz | 状态字符串（兼作心跳） |
| 飞机 → Mind+ | → `192.168.10.2:11111`（`streamon` 后） | H.264 视频 |

- Mind+ 绑定通配地址 `0.0.0.0:8889`，模拟器绑定具体地址 `192.168.10.1:8889`，Windows 上二者可以共存；
- `192.168.10.1` 设置了 `SkipAsSource`，Mind+ 发包的源地址是 `192.168.10.2`，模拟器的回复发往 `192.168.10.2:8889`，
  只会被 Mind+ 的通配套接字收到，不会绕回模拟器自己。

### `Re` 防丢包序号

Mind+ 1.x 的动作类积木（以及部分查询）调用 `clientSendMsg(cmd, true)`，同一条指令**连发 5 遍**：

```
Re1001 takeoff   Re1002 takeoff   Re1003 takeoff   Re1004 takeoff   Re1005 takeoff
```

格式为 `Re` + 2 位 tag + 2 位 id + 空格 + 指令；tag 每条新指令递增（10~99 循环）。官方 ESP32 库
`RMTT_Protocol.cpp` 中的格式是 `Re%02x%02x`，回复为 `Re[tag][id] ok/error`。模拟器的处理（`rmtt_sim/drone.py`）：

- 与上一条 tag 相同的指令视为重发，**只执行一次**；
- `ok` / `error …` 回复加上 `Re[tag][id] ` 前缀，**只回复一次**（重复回复会被 Mind+ 当作下一条指令的结果）；
- 查询结果原样返回数值（真机是否带前缀未经核实）。

Mind+ 等待回复的逻辑：每 100 ms 检查一次，默认最多 20 秒；回复中含 `ok` 即视为成功。动作类积木会**阻塞**直到收到回复，
所以模拟器必须在动作完成后才回复 `ok`。

## 5. 视频流

### Mind+ 接收端

「开启 Tello 摄像头」积木 → `toggleVideo("on")` → 发 `streamon`，回复含 `ok` 后：

1. 弹出「Tello视频」窗口，`VideoProvider.openTelloVideo()` 创建 `TelloVideoServer`；
2. `TelloVideoServer` 绑定 **`0.0.0.0:11111`**，把收到的 UDP 分片累积，**遇到长度不等于 1460 的分片时**整体交给 `wfs.js`；
3. `wfs.js` 解析 H.264 Annex-B（以 AUD 分帧，取第一个 SPS 生成 `avc1.xxxxxx` 编码串），封装为 fMP4 交给 MSE 播放；
4. 每 33 ms 把 `<video>` 画到弹窗的 canvas 上。

### 模拟器发送端

```
3D 界面（浏览器）                              模拟器（Python）                 客户端
第一视角 960×720 渲染 → WebCodecs H.264 编码 → POST /api/video?drone=i → 1460 字节分片 → UDP :11111
```

- **编码**（`web/video.js`）：`avc1.42001f`（Constrained Baseline 3.1），Annex-B，每秒一个关键帧（SPS/PPS 在码流内），
  逐帧顺序 POST（并发请求在多线程 HTTP 服务端会乱序）；积压超过 8 帧时丢弃并等待下一个关键帧；
- **转发**（`Simulator.push_video`）：只在飞机 `streamon` 且有客户端时发送，目标为客户端 IP 的 11111 端口；
  - 按 1460 字节分片；帧长恰为 1460 整数倍时补一个**空包**标记帧结束；
  - 过滤 OpenH264 附带的 SVC 前缀 / 扩展 NAL（类型 14 / 20），真机码流中没有这类单元；
  - 每 8 个分片停顿约 1 ms，关键帧匀速发出；
- **后台推流**：页面被最小化或被 Mind+ 完全遮挡时，Chromium 将其视为隐藏，`requestAnimationFrame` 停止、
  普通定时器被节流到 1 次/秒。推流期间改由 **Worker 定时器**（40 ms）驱动飞机插值与编码，实测约 15 fps；
- **画面内容**：机载画面（画中画与视频流）隐藏本机模型、ToF 光束、飞行轨迹、编号标签、编辑手柄。

已在 Mind+ V1.8.1 中实测：「开启 Tello 摄像头」后「Tello视频」弹窗正常显示模拟器机载画面。

限制：必须保持 3D 界面打开；WebCodecs 只在安全上下文可用，须用 `http://127.0.0.1:8080` 打开（局域网 IP 不行）。

## 6. 问题与解决办法

| 现象 | 原因 | 解决办法 |
|---|---|---|
| Mind+ 2.0 加载 TT 扩展后积木无反应 | 2.0 实时模式 TT 扩展是空实现 | 改用 Mind+ 1.x 免安装版 |
| 「连接设备」弹窗只有串口，没有 TT | 该菜单只管串口主控板 | 点积木区 TT 标题旁的 **!** 图标 |
| 连接列表里没有 `RMTT-SIM` | 未打补丁 / 打补丁时 Mind+ 未关闭 / 版本不匹配 | 关闭 Mind+ 后运行补丁；版本不同按 3 节移植 |
| 积木点了没反应，日志 `unknown command: re1001` | 模拟器不认识 `Re` 序号前缀 | 更新模拟器（已支持） |
| 模拟器重启后积木失效、图标变回 **!** | 状态心跳中断，Mind+ 判定断线 | 重新点图标连接 RMTT-SIM |
| 提示 8889 端口被占用 | 其他程序绑定了 `0.0.0.0:8889`（如另一个 Mind+、旧测试脚本） | 关闭占用程序；`netstat -ano -p udp \| findstr 8889` 查 PID |
| 「Tello视频」弹窗没有画面 | ① 3D 界面未打开或用局域网 IP 打开；② **Mind+ 自身 bug**：开摄像头后若一直没收到视频就关闭弹窗，`closeVideoStream()` 因 `if (!this.status) return;` 提前返回，**不释放 11111 端口**，之后再开摄像头都绑定失败 | ① 用 `http://127.0.0.1:8080` 打开 3D 界面，画中画标签显示「推流中」；② **完全退出 Mind+ 再启动**，连接后只点一次「开启 Tello 摄像头」。`netstat -ano -p udp \| findstr 11111` 可查看谁占着端口 |
| 3D 界面被遮挡后视频卡住 | 隐藏页面 rAF 停止 | 已改为 Worker 定时器驱动（需刷新 3D 界面加载新代码） |
| 机载画面中间有一条竖线 | ToF 光束被渲染进了机载画面 | 已在机载画面中隐藏辅助图形 |
| 组队扩展扫描不到模拟器 | 组队扫描丢弃本机 IP 的回复 | 暂不支持；用单机扩展，或用 Python / djitellopy 控制多机 |
| 挑战卡航向旋转积木回复 `unknown command: setyaw` | 积木 `telloRotateWithYaw` 发送 `setyaw <航向> <mid>`（不带 `Re` 序号），旧版模拟器未实现 | 已实现，更新模拟器 |
| 挑战卡航向旋转积木回复 `error No valid marker` | 未开启挑战卡探测，或飞机下方 / 前方看不到指定的卡 | 先执行「开启挑战卡探测」（`mon`），飞到卡的上方 20～300 cm 处 |

### 旋转角速度

Tello SDK 没有设置旋转角速度的指令：「设置速度」积木（`speed x`）只影响平移速度，「顺时针 / 逆时针旋转 N 度」（`cw` / `ccw`）以固定角速度旋转（模拟器为 90°/s，`rmtt_sim/drone.py` 中的 `YAW_RATE`）。

需要控制角速度时，用「**设置遥控器四个通道杆量 横滚 俯仰 油门 偏航**」积木（发送 `rc a b c d`）的**偏航**通道：

```
设置遥控器四个通道杆量 横滚 0 俯仰 0 油门 0 偏航 50     ← 顺时针持续旋转；负数为逆时针
等待 2 秒
设置遥控器四个通道杆量 横滚 0 俯仰 0 油门 0 偏航 0      ← 停止旋转
```

- 偏航杆量范围 -100～100，模拟器中线性对应 -100～100 °/s（`RC_MAX_YAW`），上例约转 100°；真机的杆量与角速度对应关系未经测量，需要精确角度时仍应使用 `cw` / `ccw`；
- 杆量会一直保持，直到发送新的 `rc`，**一定要发一次全 0 停止**；
- 只在飞行中且没有执行其他动作时生效；`rc` 没有回复，Mind+ 中该积木立即返回，靠「等待」积木控制持续时间。

## 7. 扩展指南

### 支持一个新积木

1. 在 Mind+ 中点该积木，看模拟器网页日志收到的指令（`←`）和回复（`→`）；
2. 若回复是 `unknown command`，在 `app.asar` 中查该积木实现（搜索积木 opcode，如 `key: "telloTakeOff"`）确认发送的指令格式与
   对回复的处理（是否 `re = true`、是否只认 `ok`、是否解析数值）；
3. 在 `rmtt_sim/drone.py` 中实现：控制类指令写 `_c_<指令>(self, args, cmd, reply)`，查询类加到 `_read()` 的表中，
   `EXT` 扩展模块指令在 `_ext()` 中分派；耗时动作用 `_start_task()`，完成时回复 `ok`；
4. 在 `tests/test_drone.py` 中加测试（`Harness.send()` 会推进仿真直到收到回复），`python -m unittest discover tests`。

### 在 app.asar 中查找代码

`app.asar` 很大（1.8.1 约 400 MB），直接按字节搜索，再用文件头把偏移映射到文件名：

```python
import json, re, struct
b = open(r"...\resources\app.asar", "rb").read()
hsize = struct.unpack("<I", b[12:16])[0]
hdr = json.loads(b[16:16 + hsize])
base = 8 + struct.unpack("<I", b[4:8])[0]          # 文件内容区起点

def walk(n, p=""):
    for k, v in n.get("files", {}).items():
        if "files" in v:
            yield from walk(v, p + "/" + k)
        elif "offset" in v:
            yield p + "/" + k, base + int(v["offset"]), v["size"]

files = list(walk(hdr))
for m in re.finditer(rb'key: "telloTakeOff"', b):
    f = next(f for f, o, s in files if o <= m.start() < o + s)
    print(m.start(), f)
    print(b[m.start():m.start() + 600].decode("utf-8", "replace"))
```

检查补丁后某个 webpack 模块的语法：从匹配位置向前找 `/***/ (function(module`、向后找 `/***/ })`，
截取后包成 `(function(module, exports, __webpack_require__){ ... })` 写入文件，`node --check` 即可。

### 调试工具

| 工具 | 用途 |
|---|---|
| `tools/video_check.py` | 模拟客户端发 `command / streamon / 起飞旋转`，收 11111 视频并用 ffmpeg 检查解码错误、导出截图；`--packets` 保存分片供回放 |
| `tools/mindplus_wfs_test/` | 从 Mind+ 提取内置 `wfs.js`，在浏览器中按 Mind+ 相同的拆包逻辑回放码流，判断码流能否被 Mind+ 解码（见目录内 `build.py` 说明） |
| 模拟器网页日志 | 每条收发记录；`/events`（SSE）与 `/api/status` 可用脚本读取 |

模拟客户端的最小示例（Mind+ 未运行时也可以直接绑定 `0.0.0.0:8889`）：

```python
import socket
c = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
c.bind(("127.0.0.1", 0)); c.settimeout(20)
for cmd in [b"command", b"Re1001 takeoff", b"Re1101 land"]:
    c.sendto(cmd, ("192.168.10.1", 8889)); print(cmd, c.recvfrom(256)[0])
```

### 开发注意事项

- **测试脚本会抢占客户端**：模拟器把回复、状态和视频发给最近发指令的地址，用脚本测试时 Mind+ 会收不到数据，二者不要同时操作同一架飞机；
- **接收视频要独立线程持续读取**：在等待指令回复期间不读 UDP，64 KB 默认缓冲区会溢出丢包，表现为偶发解码错误；
  收包结束时最后一帧可能不完整，统计前应去掉（`video_check.py` 已处理）；
- **修改 3D 界面代码后要刷新浏览器**，修改 Python 后要重启模拟器，之后 Mind+ 需重新连接；
- 用 shell heredoc 生成含 `\x00` 等转义的源码时，转义可能被展开成原始控制字符（Python 报 `source code string cannot contain null bytes`），
  这类修改用编辑器或独立脚本文件完成。

## 8. 关键代码位置速查

Mind+ V1.8.1 RC3.0，`resources/app.asar` 内：

| 内容 | 文件 |
|---|---|
| TT 单机扩展 `Tello` 类：`scan` / `connect` / `connectTello` / `clientSendMsg` / `toggleVideo`（**补丁位置**） | `dist/chunks/b6a636c5d1271bb37c97.chunk.js` |
| TT 单机积木实现（`telloTakeOff` 等，指令格式） | `dist/chunks/01701d0c272eb292b0fa.chunk.js` |
| TT 组队扩展 `Tello` 类 | `dist/chunks/8f81035b2d2beb9cbb4d.chunk.js` |
| 组队扫描 worker | `dist/static/child_worker/scan-tello/scan-tello-team.js` |
| 扩展库条目、连接弹窗 `ScanningStep`、`VideoProvider`、`TelloVideoServer`、`wfs.js` | `dist/chunks/d499c0b3eabcd3c5bbad.chunk.js` |
| 官方 ESP32 协议库（`Re` 序号格式） | `Arduino/libraries/RMTT_Libs/RMTT_Protocol.cpp`（Mind+ 安装目录） |

本项目内：

| 内容 | 文件 |
|---|---|
| Mind+ 连接补丁 | `tools/patch_mindplus1x.py` |
| `Re` 序号处理 | `rmtt_sim/drone.py` → `Drone.handle()`、`RE_PREFIX` |
| 视频转发（分片 / 空包 / NAL 过滤 / 匀速） | `rmtt_sim/simulator.py` → `Simulator.push_video()`、`strip_svc_nal()` |
| 视频编码与后台推流 | `web/video.js`；`web/app.js` 中的 `ticker`（Worker 定时器）与 `renderOnboard()` |
| 虚拟 IP 与防火墙 | `tools/setup_network.ps1` |
