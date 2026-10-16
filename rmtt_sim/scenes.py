"""场景库：内置场景（scenes/builtin，只读）+ 用户场景（scenes/user，可编辑）。

每个场景是一个 JSON 文件，文件名（不含扩展名）即场景 id：
{
  "title": "穿越门框赛道",
  "description": "……",
  "order": 4,                                  // 仅内置场景使用，决定排序
  "start": {"x": 0, "y": 0, "yaw": 0},         // 起飞点
  "obstacles": [{"type": "box", "x": 200, "y": 0, "z": 0, "yaw": 0, "w": 20, "d": 160, "h": 200, "color": "#e4572e"},
                {"type": "cylinder", "x": 100, "y": 50, "z": 0, "r": 20, "h": 150, "color": "#669bbc"},
                {"type": "gate", "x": 150, "y": 0, "z": 0, "yaw": 0, "w": 100, "h": 150, "t": 8, "color": "#f3a712"}],
  "pads": [{"id": 1, "x": 0, "y": 0, "z": 0}]
}
"""

import json
import os
import re

from .world import normalize_scene

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scenes")
_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def make_id(title):
    """由标题生成可作文件名的 id（保留中文）。"""
    s = _BAD_CHARS.sub("_", str(title)).strip(" ._")[:40]
    return s or "scene"


class SceneLibrary:
    def __init__(self, root=ROOT):
        self.builtin_dir = os.path.join(root, "builtin")
        self.user_dir = os.path.join(root, "user")
        os.makedirs(self.user_dir, exist_ok=True)

    def _path(self, scene_id, builtin):
        if not scene_id or scene_id != make_id(scene_id) or scene_id.startswith("."):
            raise KeyError(scene_id)
        return os.path.join(self.builtin_dir if builtin else self.user_dir, scene_id + ".json")

    @staticmethod
    def _read(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _scan(self, folder):
        if not os.path.isdir(folder):
            return []
        out = []
        for name in os.listdir(folder):
            if not name.endswith(".json"):
                continue
            try:
                out.append((name[:-5], self._read(os.path.join(folder, name))))
            except (OSError, ValueError):
                continue  # 损坏的文件不出现在列表里
        return out

    def list(self):
        builtin = sorted(self._scan(self.builtin_dir), key=lambda kv: (kv[1].get("order", 99), kv[0]))
        user = sorted(self._scan(self.user_dir), key=lambda kv: str(kv[1].get("title", kv[0])))
        return ([{"id": k, "title": v.get("title", k), "description": v.get("description", ""), "builtin": True}
                 for k, v in builtin]
                + [{"id": k, "title": v.get("title", k), "description": v.get("description", ""), "builtin": False}
                   for k, v in user])

    def is_builtin(self, scene_id):
        return os.path.isfile(self._path(scene_id, True))

    def load(self, scene_id):
        """返回 (规范化后的场景内容, 是否内置)。不存在时抛 KeyError。"""
        for builtin in (False, True):
            path = self._path(scene_id, builtin)
            if os.path.isfile(path):
                try:
                    return normalize_scene(self._read(path)), builtin
                except (OSError, ValueError) as e:
                    raise KeyError("%s: %s" % (scene_id, e))
        raise KeyError(scene_id)

    def save(self, content, title, scene_id=None, overwrite=False):
        """保存为用户场景，返回场景 id。内置场景不能被覆盖。"""
        sid = make_id(scene_id or title)
        if self.is_builtin(sid):
            raise ValueError("「%s」是内置场景，请换一个名称另存" % sid)
        path = self._path(sid, False)
        if os.path.exists(path) and not overwrite:
            raise FileExistsError(sid)
        data = normalize_scene(dict(content, title=title))
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return sid

    def delete(self, scene_id):
        if self.is_builtin(scene_id):
            raise ValueError("内置场景不能删除")
        path = self._path(scene_id, False)
        if not os.path.isfile(path):
            raise KeyError(scene_id)
        os.remove(path)
