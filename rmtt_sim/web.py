"""Web 界面后端：静态文件 + SSE 状态推送 + JSON API。"""

import json
import mimetypes
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
FRAME_HZ = 30

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")


def make_handler(sim):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/events":
                return self._events()
            if path == "/api/world":
                with sim.lock:
                    return self._json(sim.world.to_dict())
            if path == "/api/scenes":
                with sim.lock:
                    current = sim.world.scene_id
                return self._json({"scenes": sim.library.list(), "current": current})
            if path == "/":
                path = "/index.html"
            full = os.path.normpath(os.path.join(WEB_DIR, path.lstrip("/")))
            if not full.startswith(WEB_DIR) or not os.path.isfile(full):
                self.send_error(404)
                return
            with open(full, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(full)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)

        def _events(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            seq = 0
            try:
                while sim.running:
                    logs = sim.logs_since(seq)
                    if logs:
                        seq = logs[-1]["seq"]
                    payload = sim.snapshot()
                    payload["logs"] = logs
                    self.wfile.write(b"data: " + json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n\n")
                    self.wfile.flush()
                    time.sleep(1.0 / FRAME_HZ)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def do_POST(self):
            path = urlparse(self.path).path
            n = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._json({"error": "bad json"}, 400)
            try:
                if path == "/api/command":
                    res = sim.run_command(int(data.get("drone", 0)), str(data["cmd"]))
                    return self._json({"reply": res})
                if path == "/api/reset":
                    sim.reset()
                elif path == "/api/scene":
                    try:
                        sim.load_scene(str(data["name"]))
                    except KeyError:
                        return self._json({"error": "场景不存在：%s" % data["name"]}, 404)
                elif path == "/api/scene/new":
                    sim.new_scene()
                elif path == "/api/world":
                    return self._json({"ok": True, "version": sim.edit_world(data)})
                elif path == "/api/scenes/save":
                    try:
                        sid = sim.save_scene(str(data["title"]).strip()[:40] or "未命名场景",
                                             overwrite=bool(data.get("overwrite")),
                                             save_as=bool(data.get("save_as")))
                    except FileExistsError:
                        return self._json({"error": "exists"}, 409)
                    return self._json({"ok": True, "id": sid})
                elif path == "/api/scenes/delete":
                    try:
                        sim.delete_scene(str(data["id"]))
                    except KeyError:
                        return self._json({"error": "场景不存在"}, 404)
                elif path == "/api/timescale":
                    with sim.lock:
                        sim.time_scale = max(0.1, min(10.0, float(data["value"])))
                elif path == "/api/pause":
                    with sim.lock:
                        sim.paused = bool(data["paused"])
                elif path == "/api/drones":
                    return self._json({"ok": True, "count": sim.set_drone_count(data["count"])})
                elif path == "/api/battery":
                    with sim.lock:
                        for d in sim.drones:
                            d.battery = 100.0
                elif path == "/api/obstacle":
                    with sim.lock:
                        sim.world.add_obstacle(dict(data, type=data.get("type", "box")))
                elif path == "/api/obstacles/clear":
                    with sim.lock:
                        sim.world.clear_obstacles()
                else:
                    return self._json({"error": "not found"}, 404)
            except (KeyError, ValueError, IndexError, TypeError) as e:
                return self._json({"error": str(e)}, 400)
            except OSError as e:
                return self._json({"error": "文件操作失败：%s" % e}, 500)
            return self._json({"ok": True})

    return Handler


def serve(sim, host, port):
    httpd = ThreadingHTTPServer((host, port), make_handler(sim))
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True, name="http").start()
    return httpd
