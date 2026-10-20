"""给 Mind+ 1.x 打补丁，使实时模式「RoboMaster TT（单机）」无需真实 WiFi 即可连接本机模拟器。

Mind+ 1.x 的 TT 扩展连接流程：扫描电脑周围名称含 TELLO / RMTT 的 WiFi → 用户选择 →
电脑连上该 WiFi → 向 192.168.10.1:8889 发 command。模拟器没有真实热点，列表永远为空。

补丁内容（只改 resources/app.asar 中 TT 扩展的三处代码，等长原地替换，不改 asar 文件头）：
  1. WiFi 扫描出错（如电脑没有无线网卡）时不再重试报错；
  2. 扫描结果中固定加入虚拟热点 RMTT-SIM；
  3. 选择 RMTT-SIM 时跳过连接 WiFi，直接向 192.168.10.1:8889 发 command（即模拟器）。
选择真实的 RMTT / TELLO 热点时行为不变，打补丁后仍可连接真机。

用法（先关闭 Mind+）：
  python tools/patch_mindplus1x.py "F:/hos/tool/MindPlus_Win_V1.8.1_RC3.0"
  python tools/patch_mindplus1x.py "F:/hos/tool/MindPlus_Win_V1.8.1_RC3.0" --restore
首次打补丁会备份为 resources/app.asar.bak。已在 Mind+ V1.8.1 RC3.0 上验证。
"""

import argparse
import os
import shutil
import sys

FAKE_SSID = "RMTT-SIM"

# (原文, 替换文本)：替换文本不长于原文，不足部分以空格补齐
PATCHES = [
    (
        "        if (err) {\n"
        "          setTimeout(function () {\n"
        "            // 扫描超时",
        "        if (false) {\n"
        "          setTimeout(function () {\n",
    ),
    (
        "          networks = networks || [];\n"
        "          // 去除多网卡扫描的重复的网络",
        "          networks = (networks || []).concat([{ssid: \"%s\", signal_level: -40}]);" % FAKE_SSID,
    ),
    (
        "        if (_this.currentConnections && _this.currentConnections.length) {\n"
        "          // 多个网卡连接热点，逐一判断手动连接的热点",
        "        if (ssid == \"%s\") return _this.connectTello();\n"
        "        if (_this.currentConnections && _this.currentConnections.length) {" % FAKE_SSID,
    ),
]


def pad(old: bytes, new: bytes) -> bytes:
    if len(new) > len(old):
        raise ValueError("替换文本比原文长 %d 字节" % (len(new) - len(old)))
    return new + b" " * (len(old) - len(new))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mindplus_dir", help="Mind+ 1.x 安装 / 解压目录（含 Mind+.exe）")
    ap.add_argument("--restore", action="store_true", help="从 app.asar.bak 还原")
    args = ap.parse_args()

    asar = os.path.join(args.mindplus_dir, "resources", "app.asar")
    bak = asar + ".bak"
    if not os.path.isfile(asar):
        print("找不到 %s" % asar)
        return 1

    if args.restore:
        if not os.path.isfile(bak):
            print("没有备份文件 %s" % bak)
            return 1
        shutil.copyfile(bak, asar)
        print("已还原 %s" % asar)
        return 0

    with open(asar, "rb") as f:
        data = f.read()

    patched = [pad(o.encode(), n.encode()) for o, n in PATCHES]
    if all(data.count(p) == 1 for p in patched):
        print("已经打过补丁，无需重复操作")
        return 0
    for (old, _), new in zip(PATCHES, patched):
        n = data.count(old.encode())
        if n != 1:
            print("补丁点出现 %d 次（应为 1 次），Mind+ 版本不匹配，未做任何修改：\n%s" % (n, old))
            return 1
        data = data.replace(old.encode(), new)

    if not os.path.isfile(bak):
        shutil.copyfile(asar, bak)
        print("已备份 %s" % bak)
    try:
        with open(asar, "r+b") as f:
            f.write(data)
    except PermissionError:
        print("写入失败：请先关闭 Mind+ 再运行")
        return 1
    print("补丁完成。Mind+ 实时模式加载「RoboMaster TT（单机）」后，在连接列表中选择 %s 即连接本机模拟器" % FAKE_SSID)
    return 0


if __name__ == "__main__":
    sys.exit(main())
