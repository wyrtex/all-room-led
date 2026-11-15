"""Настройки, группы и сцены (JSON-файл)."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

DEFAULT = {
    "openrgb_path": r"C:\Program Files\OpenRGB\OpenRGB.exe",
    "wallpaper_engine_path": r"C:\Program Files (x86)\Steam\steamapps\common\wallpaper_engine\wallpaper64.exe",
    "brightness": 1.0,
    "orders": {},          # ключ зоны -> порядок каналов (RGB/GRB/BRG...)
    "groups": {},          # имя -> список ключей зон (свои группы)
    "scenes": {
        "Новый год": {
            "wallpaper": "",
            "assignments": [
                {"targets": ["@motherboard"], "effect": "garland",
                 "palette": ["#ff0000", "#00ff00"], "speed": 1.0},
                {"targets": ["@keyboards"], "effect": "twinkle",
                 "palette": ["#ff0000", "#00ff00"], "speed": 1.0},
            ],
        },
        "Радуга": {
            "wallpaper": "",
            "assignments": [{"targets": ["@all"], "effect": "rainbow", "palette": ["#ff0000"], "speed": 1.0}],
        },
        "Тёплый вечер": {
            "wallpaper": "",
            "assignments": [{"targets": ["@all"], "effect": "wave",
                             "palette": ["#ff5a00", "#ffb000", "#ff2a00"], "speed": 0.5}],
        },
        "Выключить всё": {
            "wallpaper": "",
            "assignments": [{"targets": ["@all"], "effect": "off", "palette": ["#000000"], "speed": 1.0}],
        },
    },
}


def default_path() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home() / ".config") / "RoomLED"
    return base / "config.json"


class Config:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else default_path()
        self.data = copy.deepcopy(DEFAULT)
        if self.path.exists():
            self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
        else:
            self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def __getitem__(self, k):
        return self.data[k]


def resolve_targets(targets, engine, groups: dict[str, list[str]]) -> list[str]:
    """@all, @motherboard, @keyboards, имя своей группы или ключ зоны -> список ключей зон."""
    out: list[str] = []
    for t in targets:
        if t == "@all":
            out += list(engine.zones)
        elif t == "@motherboard":
            out += [z.key for d in engine.devices.values() if d.kind == "motherboard" for z in d.zones]
        elif t == "@keyboards":
            out += [z.key for d in engine.devices.values() if d.kind == "keyboard" for z in d.zones]
        elif t in groups:
            out += groups[t]
        elif t in engine.zones:
            out.append(t)
    return list(dict.fromkeys(out))
