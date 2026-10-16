# RoboMaster TT 模拟器（兼容 Mind+ 实时模式）

在电脑上模拟一台 **RoboMaster TT（Tello EDU + ESP32 扩展模块）**。Mind+ 实时模式编写的程序可以直接连接本模拟器，
在 3D 场景中看到飞行、翻滚、点阵屏、顶部 RGB 灯、ToF 测距与挑战卡识别的效果，无需真机、无炸机风险。

![3D 界面](docs/screenshot.png)

## 原理

Mind+ 实时模式通过 **Tello SDK 3.0** 文本协议控制飞机：

| 方向 | 地址 | 内容 |
|---|---|---|
| Mind+ → 飞机 | `192.168.10.1:8889` UDP | `command`、`takeoff`、`EXT mled …` 等指令 |
| 飞机 → Mind+ | 原路返回 | `ok` / `error …` / 查询结果 |
| 飞机 → Mind+ | 电脑 `:8890` UDP，10Hz | 状态字符串 `mid:..;h:..;bat:..;` |

模拟器在本机环回接口上添加虚拟地址 `192.168.10.1`（飞机）与 `192.168.10.2`（Mind+ 的源地址），
并监听 `192.168.10.1:8889`，所以 **Mind+ 不需要任何修改**，以为自己连上了真飞机。
虚拟地址只存在于内存中，重启电脑后自动消失，不影响真实网卡。

## 快速开始

环境：Windows 10/11、Python 3.8+（只用标准库，无需 pip 安装任何东西）。

1. 双击 **`start.bat`**
   - 首次运行会弹出 UAC 提权窗口，用于添加虚拟 IP（`tools\setup_network.ps1`）；
   - 随后自动打开浏览器 3D 界面 <http://127.0.0.1:8080/>。
2. 打开 Mind+ → **实时模式** → 扩展 → 功能模块 → 加载 **RoboMaster TT（单机）**。
3. 编写程序并点击运行，在 3D 界面观察效果，右侧日志会显示收发的每条 SDK 指令。

> 不用 Mind+ 也能体验：在界面右下角的 **SDK 控制台** 输入指令，或运行
> `python examples/mindplus_like_demo.py`（它发出的 UDP 报文与 Mind+ 程序相同）。

### 命令行参数

```bash
python -m rmtt_sim [--scene 场景id] [--drones N]
                   [--auto-land 15] [--web-port 8080] [--no-browser]
```

| 参数 | 说明 |
|---|---|
| `--scene` | 初始场景 id（`scenes/builtin` 或 `scenes/user` 下的文件名）：`empty` `pads`（默认）`obstacles` `course` `pillars` `room`，或你保存的场景 |
| `--drones N` | 模拟多架飞机：#1 为 `192.168.10.1`，#2 起为 `192.168.10.11`、`.12`…（网络脚本默认已准备 4 架） |
| `--auto-land S` | 超过 S 秒没收到指令自动降落（真机为 15 秒，默认关闭） |
| `--ip A` | 自定义飞机绑定地址，可重复 |
| `--no-lan` | 不在局域网地址上监听（默认监听，供手机 App 连接） |

## 3D 界面

- **视角**：环绕（鼠标左键旋转 / 右键平移 / 滚轮缩放）、跟随、第一视角；左下角始终显示机载摄像头画面。
- **飞机模型**：机身、桨叶（起桨/飞行时转动）、桨保护罩、扩展模块、**8×8 红蓝点阵**、**顶部 RGB 灯**、前向 ToF 光束、机头状态灯（SDK 模式紫色闪烁）。
- **场景**：障碍物会挡住飞行（碰撞时飞机闪红、当前指令返回 `error Collision`），也会被 ToF 测到，飞机可以降落在障碍物顶面上。顶部「场景」下拉框切换场景，「俯视 / 全景」快速调整视角。
- **其他**：飞行轨迹、0.5×~4× 仿真速度、暂停、重置、充满电、键盘遥控（W/S/A/D 平移、↑/↓ 升降、Q/E 旋转、T 起飞、L 降落）。

## 场景库与场景编辑器

点击顶部 **✎ 编辑场景** 进入编辑模式（右侧切换为编辑面板）：

| 功能 | 操作 |
|---|---|
| 添加对象 | 在「添加对象」中选择 **长方体 / 墙 / 圆柱 / 门框 / 挑战卡**，再到地面上单击放置（按住 Shift 连续放置） |
| 选中 | 在 3D 视图中单击对象，或在「对象列表」中点击；起飞点（蓝色圆环箭头）也可以选中移动 / 旋转 |
| 移动 / 旋转 | 拖动彩色手柄；`W` 移动、`E` 旋转；勾选「吸附」时按 10cm / 15° 对齐 |
| 精确调整 | 属性面板直接输入坐标、尺寸、离地高度、旋转角度、颜色、挑战卡编号（单位 cm） |
| 复制 / 删除 / 撤销 | `Ctrl+D` / `Delete` / `Ctrl+Z`，`Esc` 取消放置或取消选中 |
| 场景库 | 加载、新建空白、删除；保存、另存为；导出 / 导入 JSON 文件 |

- 编辑**实时生效**：飞机碰撞、ToF 测距、挑战卡识别立即使用新场景，可以边飞边改。
- 场景是 JSON 文件：内置场景在 `scenes/builtin/`（只读，修改后保存会提示另存），你的场景保存在 `scenes/user/`。
- 内置场景：空旷场地、挑战卡 m1-m8、障碍物 / ToF 测试、穿越门框赛道、圆柱森林、室内房间（带门和可降落的桌子）。
- 编辑时建议点「俯视」，从正上方摆放更直观。

场景文件格式（坐标单位 cm，X 前 / Y 左 / Z 上，`yaw` 俯视顺时针为正）：

```json
{
  "title": "我的赛道",
  "start": {"x": 0, "y": 0, "yaw": 0},
  "obstacles": [
    {"type": "box", "x": 200, "y": 0, "z": 0, "yaw": 30, "w": 20, "d": 160, "h": 200, "color": "#e4572e"},
    {"type": "cylinder", "x": 100, "y": 80, "z": 0, "r": 20, "h": 150, "color": "#669bbc"},
    {"type": "gate", "x": 300, "y": 0, "z": 0, "yaw": 0, "w": 100, "h": 150, "t": 8, "color": "#f3a712"}
  ],
  "pads": [{"id": 1, "x": 0, "y": 0, "z": 0}]
}
```

## 支持的指令

**控制**：`command` `takeoff` `land` `emergency` `stop` `motoron` `motoroff` `throwfly`
`up/down/left/right/forward/back x` `cw/ccw x` `flip l/r/f/b` `go x y z speed [mid]`
`curve x1 y1 z1 x2 y2 z2 speed [mid]` `jump x y z speed yaw mid1 mid2` `rc a b c d` `speed x`
`mon` `moff` `mdirection x` `streamon` `streamoff` `wifi` `ap` `multiwifi` `port` `setfps` `setbitrate` `setresolution` `wifisetchannel`

**查询**：`battery?` `speed?` `time?` `wifi?` `sdk?` `sn?` `hardware?`（返回 `RMTT`）`wifiversion?` `ap?` `ssid?`
以及旧版 `height?` `temp?` `attitude?` `baro?` `acceleration?` `tof?`

**扩展模块（EXT，按出厂固件行为模拟）**：

| 指令 | 回复 |
|---|---|
| `EXT tof?` | `tof 650`（mm，超出 1.2m 返回 `tof 8192`） |
| `EXT led r g b` / `EXT led br t r g b` / `EXT led bl t r1 g1 b1 r2 g2 b2` | `led ok` / `led error` |
| `EXT mled g <64位 0/r/b/p>` | `mled ok` / `mled error` |
| `EXT mled s r/b/p <字符或heart>` | 同上 |
| `EXT mled l/r/u/d r/b/p t <字符串>` 滚动文字；`EXT mled l/r/u/d g t <图案>` 滚动图案 | 同上 |
| `EXT mled sg <图案>` 开机图案 / `EXT mled sc` 清除 / `EXT mled sl n` 亮度 | 同上 |
| `EXT version?` | `version=v1.0.0.4` |

行为细节尽量贴近真机：动作指令**完成后才回复** `ok`（Mind+ 积木是阻塞的）；运动中再发其他动作指令返回 `error Not joystick`，
重发同一条指令视为 UDP 重传会被忽略；未起飞时移动返回 `error Motor stop`；电量低于 50% 时 `flip` 返回错误；
挑战卡需在下视摄像头视野内（高度 0.2~3m）才能识别，`go/curve/jump … mN` 识别不到时返回 `error No valid marker`。

## Android 遥控 App

`android/` 是一个原生 Android App（Kotlin + Jetpack Compose），用 Tello SDK 3.0 协议控制无人机。
**同一个 App 既能连模拟器，也能连真实的 RoboMaster TT / Tello EDU。**

| 页面 | 功能 |
|---|---|
| 飞行 | 双虚拟摇杆（美国手：左 = 油门/偏航，右 = 前后/左右，20Hz 发送 `rc`）、起飞、降落、悬停、急停、四向翻滚、灵敏度 |
| 指令 | 按距离/角度执行 `up/down/forward/back/left/right/cw/ccw`、设置速度、挑战卡、查询类指令 |
| 扩展模块 | 8×8 点阵绘图（红/蓝/紫）、滚动文字、静态字符/爱心、点阵亮度、顶部 RGB 灯（常亮/呼吸/闪烁）、前向 ToF（可自动刷新） |
| 日志 | 收发记录 + 任意 SDK 指令输入框 |

顶部状态栏实时显示 8890 端口推送的电量、高度、ToF、航向、温度、挑战卡。

### 连接模拟器

1. 电脑运行 `start.bat`（会自动添加防火墙规则，放行 UDP 8889）。模拟器同时监听电脑的局域网地址，
   网页「连接 → 手机 App」一栏显示要填的地址，例如 `192.168.0.107:8889`（第 2 架飞机为 `:8989`，依此类推）。
2. 手机与电脑连接**同一个 WiFi**，安装 `dist/TTController-debug.apk`，填入上述地址点「连接」。
3. Android Studio 模拟器中运行时填 `10.0.2.2:8889`。

连接真机：手机连 `RMTT-xxxxxx` 热点，地址填 `192.168.10.1`。

### 编译

```bash
cd android
gradlew.bat assembleDebug          # 产物：app/build/outputs/apk/debug/app-debug.apk
```

需要 JDK 17+ 与 Android SDK 35（在 `android/local.properties` 写 `sdk.dir=D:/Android/Sdk`，或用 Android Studio 直接打开 `android/` 目录）。

### 发布版本（release）

```bash
cd android
gradlew.bat assembleRelease        # 产物：app/build/outputs/apk/release/app-release.apk（R8 压缩后约 1.1MB）
```

签名信息从 `android/keystore.properties` 读取（该文件和 `android/keystore/` 已被 `.gitignore` 排除，**不会进入 git**）：

```properties
storeFile=keystore/rmtt-release.jks
storePassword=******
keyAlias=rmtt
keyPassword=******
```

没有该文件时会生成未签名的 `app-release-unsigned.apk`。**请备份 keystore 和密码**：丢失后无法再给已安装的用户发布升级包。
release 与 debug 签名不同，手机上从 debug 版换成 release 版需要先卸载旧版。

联调测试（需模拟器在运行）：`set TT_SIM_HOST=192.168.0.107 && gradlew.bat testDebugUnitTest`，
会用 App 的网络层真实连接模拟器，验证指令、状态推送、rc 摇杆和急停打断；模拟器未运行时自动跳过。

## 双机模式：两部手机各控制一架

双击 **`start_dual.bat`**（等同 `python -m rmtt_sim --drones 2`），场景中出现两架飞机（#2 在起飞点左侧 1m）：

| 飞机 | 手机 App 地址 | 本机地址（Mind+ / 脚本） | SN |
|---|---|---|---|
| #1 | `电脑IP:8889` | `192.168.10.1:8889` | `0TQZK7SIM00001` |
| #2 | `电脑IP:8989` | `192.168.10.11:8889` | `0TQZK7SIM00002` |

1. 两部手机都连接与电脑相同的 WiFi，安装 App；
2. 在连接页的「模拟器飞机」里，手机 A 选 **#1**、手机 B 选 **#2**（会自动填好端口），点连接；
3. 连接后状态栏显示橙色编号和 SN，确认控制的是哪一架。

两架飞机完全独立：各自的指令、状态推送（8890）、点阵屏和 RGB 灯互不影响；它们之间**会发生碰撞**
（双方闪红，正在执行的指令返回 `error Collision`）。网页右侧标签页可切换查看每架飞机，`●` 表示已有客户端连接，
左上角 HUD 同时显示所有飞机的状态。

更多飞机：`python -m rmtt_sim --drones 4`，手机端口依次为 8889 / 8989 / 9089 / 9189
（`setup_network.ps1` 默认已为 4 架飞机准备好地址和防火墙规则，更多请加 `-Drones N`）。

**Mind+ 组队模式**：组队扩展会在电脑所在局域网中扫描飞机，能否扫描到环回接口上的 `192.168.10.x`
取决于 Mind+ 的扫描实现，目前未经验证；单机模式不受影响。

## 常见问题

- **Mind+ 提示连接失败 / 8889 端口访问失败**：确认模拟器窗口没有报错、界面右上角显示「模拟器在线」；
  确认电脑**没有**同时连接真实飞机的 WiFi（同为 192.168.10.x 网段会冲突）。
- **Mind+ 单机扩展里让选择 RMTT/Tello 开头的 WiFi**：模拟器没有真实 WiFi 热点，跳过 WiFi 选择、直接运行程序即可；
  Mind+ 发出的 UDP 指令会被本机虚拟地址接收。
- **开了代理软件（Clash 等 TUN 模式）**：一般不影响，因为 192.168.10.1 是本机地址；如有问题请把 `192.168.10.0/24` 加入直连规则。
- **重启后连不上**：虚拟 IP 已失效，重新运行 `start.bat` 会自动配置。手动移除：`tools\setup_network.ps1 -Remove`。

## 局限

- 只模拟 **实时模式**。上传模式（把 Arduino/MicroPython 程序烧录到 ESP32）需要模拟 ESP32 芯片本身，不在本项目范围内。
- `streamon` 只切换状态，不输出 11111 端口的 H.264 视频流（界面中有机载摄像头画面可代替）。
- 飞行动力学为运动学近似（匀速移动 + 视觉倾角），不模拟风、漂移与定位误差。
- 本项目依据官方 SDK 3.0 文档实现，未与 Mind+ 内部源码逐条比对；若发现某个积木的回复格式不被 Mind+ 接受，
  请查看界面日志中的收发记录并调整 `rmtt_sim/drone.py`。

## 目录

```
start.bat                 一键启动（自动配置虚拟 IP）
start_dual.bat            双机模式启动（两部手机各控制一架）
scenes/builtin/           内置场景（JSON）
scenes/user/              你保存的场景
rmtt_sim/                 模拟器（纯 Python 标准库）
  drone.py                飞行器模型 + SDK 3.0 / EXT 指令解析
  matrix.py               8×8 点阵与 RGB 灯
  world.py                场景几何：长方体 / 圆柱 / 门框、碰撞、ToF 射线检测
  scenes.py               场景库（加载 / 保存 / 删除）
  simulator.py            仿真循环、UDP 8889/8890
  web.py                  HTTP + SSE 推送给 3D 界面
web/                      Three.js 3D 前端（three r160 已内置于 web/vendor，离线可用）
  editor.js               场景编辑器
  world3d.js              场景对象 → 3D 模型
tools/setup_network.ps1   添加 / 移除虚拟 IP
examples/                 模拟 Mind+ 发包的示例程序
android/                  Android 遥控 App（Kotlin + Compose）
tests/                    单元测试：python -m unittest discover tests
```

参考：[Tello SDK 3.0 使用说明](https://dl.djicdn.com/downloads/RoboMaster%20TT/Tello_SDK_3.0_User_Guide_cn.pdf) ·
[Mind+ RoboMaster TT 教程](https://mindplus.dfrobot.com.cn/RMTT) · 点阵字库 [font8x8](https://github.com/dhepper/font8x8)（Public Domain）
