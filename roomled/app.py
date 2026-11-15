"""Связка: конфиг + движок + сцены + HTTP API."""
from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .backends import Backend
from .config import Config, resolve_targets
from .effects import EFFECTS
from .engine import Engine
from .wallpaper import set_wallpaper

log = logging.getLogger("roomled.app")
WEB = Path(__file__).parent / "web"


class App:
    def __init__(self, backend: Backend, config: Config):
        self.cfg = config
        self.engine = Engine(backend)
        self.engine.orders = dict(config["orders"])
        self.engine.brightness = float(config["brightness"])
        self.active_scene = ""
        self.error = ""

    def start(self):
        try:
            self.engine.rescan()
            self.error = ""
        except Exception as e:  # сервер OpenRGB не запущен и т.п.
            self.error = str(e)
            log.error("%s", e)
        self.engine.start()

    def rescan(self):
        self.engine.rescan()
        self.error = ""

    def state(self):
        e = self.engine
        return {
            "error": self.error,
            "brightness": e.brightness,
            "active_scene": self.active_scene,
            "effects": {k: v.label for k, v in EFFECTS.items()},
            "devices": [{"key": d.key, "name": d.name, "kind": d.kind,
                         "zones": [{"key": z.key, "name": z.name, "count": z.count,
                                    "order": e.orders.get(z.key, "RGB"),
                                    "effect": e.effects[z.key][1] if z.key in e.effects else None}
                                   for z in d.zones]} for d in e.devices.values()],
            "groups": self.cfg["groups"],
            "scenes": list(self.cfg["scenes"]),
        }

    def apply(self, targets, effect, palette, speed):
        keys = resolve_targets(targets, self.engine, self.cfg["groups"])
        self.engine.assign(keys, effect, palette, speed)

    def run_scene(self, name: str):
        sc = self.cfg["scenes"][name]
        for a in sc["assignments"]:
            self.apply(a["targets"], a["effect"], a["palette"], a.get("speed", 1.0))
        if sc.get("wallpaper"):
            set_wallpaper(self.cfg["wallpaper_engine_path"], sc["wallpaper"])
        self.active_scene = name

    def save_scene(self, name: str, wallpaper: str = ""):
        """Сохраняет текущие эффекты всех зон как сцену."""
        by_spec: dict[str, dict] = {}
        for key, (_eff, spec) in self.engine.effects.items():
            sig = json.dumps(spec, sort_keys=True)
            by_spec.setdefault(sig, {"targets": [], **spec})["targets"].append(key)
        self.cfg["scenes"][name] = {"wallpaper": wallpaper, "assignments": list(by_spec.values())}
        self.cfg.save()

    def set_order(self, zone, order):
        self.engine.set_order(zone, order)
        self.cfg["orders"][zone] = order.upper()
        self.cfg.save()

    def set_brightness(self, v: float):
        self.engine.brightness = max(0.0, min(1.0, v))
        self.cfg.data["brightness"] = self.engine.brightness
        self.cfg.save()

    def save_group(self, name, zones):
        self.cfg["groups"][name] = zones
        self.cfg.save()

    def delete(self, kind, name):
        self.cfg[kind].pop(name, None)
        self.cfg.save()


def make_handler(app: App):
    routes = {
        "/api/apply": lambda b: app.apply(b["targets"], b["effect"], b["palette"], b.get("speed", 1.0)),
        "/api/scene": lambda b: app.run_scene(b["name"]),
        "/api/scene/save": lambda b: app.save_scene(b["name"], b.get("wallpaper", "")),
        "/api/scene/delete": lambda b: app.delete("scenes", b["name"]),
        "/api/order": lambda b: app.set_order(b["zone"], b["order"]),
        "/api/brightness": lambda b: app.set_brightness(float(b["value"])),
        "/api/group": lambda b: app.save_group(b["name"], b["zones"]),
        "/api/group/delete": lambda b: app.delete("groups", b["name"]),
        "/api/identify": lambda b: app.engine.identify(b["zone"]),
        "/api/rescan": lambda b: app.rescan(),
        "/api/off": lambda b: app.engine.all_off(),
    }

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body: bytes, ctype="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/api/state":
                return self._send(200, json.dumps(app.state(), ensure_ascii=False).encode())
            if self.path in ("/", "/index.html"):
                return self._send(200, (WEB / "index.html").read_bytes(), "text/html")
            self._send(404, b"{}")

        def do_POST(self):
            fn = routes.get(self.path)
            if not fn:
                return self._send(404, b"{}")
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                fn(body)
                self._send(200, b'{"ok":true}')
            except Exception as e:
                log.exception("API error")
                self._send(500, json.dumps({"error": str(e)}, ensure_ascii=False).encode())

    return H


def serve(app: App, host="127.0.0.1", port=8765) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer((host, port), make_handler(app))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
