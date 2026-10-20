"""从 Mind+ 1.x 的 app.asar 提取其内置的 H.264 播放器 wfs.js，生成 wfs_mod.js 供 index.html 在浏览器中复现 Mind+ 的视频解码。

用法：
  python tools/mindplus_wfs_test/build.py "F:/hos/tool/MindPlus_Win_V1.8.1_RC3.0"
  python tools/video_check.py --packets tools/mindplus_wfs_test/cap.bin
  python -m http.server 8099 --bind 127.0.0.1 -d tools/mindplus_wfs_test
  浏览器打开 http://127.0.0.1:8099/ ，左侧 <video> 与右侧 canvas 出画面即说明码流可被 Mind+ 解码。

wfs_mod.js 与 cap.bin 为本地生成文件，已在 .gitignore 中排除（wfs.js 属于 Mind+，不随本项目分发）。
"""

import os
import re
import sys


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    asar = os.path.join(sys.argv[1], "resources", "app.asar")
    data = open(asar, "rb").read()
    # TelloVideoServer 中 `var Wfs = __webpack_require__(N);`，N 为 wfs.js 的 webpack 模块号
    m = re.search(rb"var Wfs = __webpack_require__\((\d+)\);", data)
    if not m:
        print("未找到 Wfs 模块引用，Mind+ 版本不匹配")
        return 1
    mid = m.group(1)
    start = data.find(b"/* " + mid + b" */", m.end())
    end = data.find(b"/* " + str(int(mid) + 1).encode() + b" */", start)
    if start < 0 or end < 0:
        print("未找到模块 %s 的边界" % mid.decode())
        return 1
    src = data[start:end].decode("utf-8")
    # webpack 模块形如 `/***/ (function(module, exports, __webpack_require__) { ... \n/***/ }),`，
    # 函数的收尾 `})` 在最后的 `/***/ })` 行上，截取后补回
    body = src[src.index("(function(module, exports, __webpack_require__)"):src.rindex("/***/ })")]
    body = body.rstrip() + "\n})"
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wfs_mod.js")
    with open(out, "w", encoding="utf-8") as f:
        f.write("// 由 build.py 从 Mind+ app.asar 提取（webpack 模块 %s），勿提交\n" % mid.decode())
        f.write("window.__wfsFactory = " + body + ";\n")
    print("已生成 %s（模块 %s，%d 字节）" % (out, mid.decode(), len(body)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
