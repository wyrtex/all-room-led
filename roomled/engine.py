"""Движок: крутит эффекты и пишет кадры в устройства."""
from __future__ import annotations

import logging
import threading
import time

from .backends import Backend, Device, Zone
from .effects import Color, Effect, make_effect, scale

log = logging.getLogger("roomled.engine")


def apply_order(c: Color, order: str) -> Color:
    """order — порядок каналов, который ждёт железо. «GRB»: красный надо слать вторым байтом."""
    if order == "RGB" or len(order) != 3:
        return c
    return tuple(c["RGB".index(ch)] for ch in order)  # type: ignore[return-value]


class Engine:
    def __init__(self, backend: Backend, fps: int = 30):
        self.backend = backend
        self.fps = fps
        self.devices: dict[str, Device] = {}
        self.zones: dict[str, Zone] = {}
        self.effects: dict[str, tuple[Effect, dict]] = {}   # zone key -> (effect, spec)
        self.orders: dict[str, str] = {}
        self.brightness = 1.0
        self._buffers: dict[str, list[Color]] = {}
        self._dirty: set[str] = set()
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._running = False
        self._t0 = time.monotonic()

    # --- устройства ---
    def rescan(self) -> None:
        with self._lock:
            devs = self.backend.scan()
            self.devices = {d.key: d for d in devs}
            self.zones = {z.key: z for d in devs for z in d.zones}
            self._buffers = {d.key: [(0, 0, 0)] * d.led_count for d in devs}
            self.effects = {k: v for k, v in self.effects.items() if k in self.zones}

    # --- управление ---
    def assign(self, zone_keys: list[str], effect: str, palette: list[str], speed: float = 1.0) -> None:
        with self._lock:
            for k in zone_keys:
                z = self.zones.get(k)
                if z:
                    self.effects[k] = (make_effect(effect, z.count, palette, speed),
                                       {"effect": effect, "palette": palette, "speed": speed})

    def all_off(self) -> None:
        with self._lock:
            self.assign(list(self.zones), "off", ["#000000"])

    def set_order(self, zone_key: str, order: str) -> None:
        with self._lock:
            self.orders[zone_key] = order.upper()

    def identify(self, zone_key: str, seconds: float = 2.0) -> None:
        """Подсветить зону белым на пару секунд, чтобы понять, что это."""
        with self._lock:
            old = self.effects.get(zone_key)
            self.assign([zone_key], "static", ["#ffffff"])
        threading.Timer(seconds, self._restore, args=(zone_key, old)).start()

    def _restore(self, key, old):
        with self._lock:
            if old:
                self.effects[key] = old
            else:
                self.assign([key], "off", ["#000000"])

    # --- цикл ---
    def start(self) -> None:
        if self._thread:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def tick(self, t: float | None = None) -> None:
        t = time.monotonic() - self._t0 if t is None else t
        with self._lock:
            touched: set[str] = set()
            for key, (eff, _spec) in self.effects.items():
                z = self.zones[key]
                order = self.orders.get(key, "RGB")
                frame = eff.render(t)
                buf = self._buffers[z.device_key]
                for i, c in enumerate(frame):
                    buf[z.offset + i] = apply_order(scale(c, self.brightness), order)
                touched.add(z.device_key)
            for dk in touched:
                try:
                    self.backend.write(dk, self._buffers[dk])
                except Exception:
                    log.exception("Ошибка записи в %s", dk)

    def _loop(self):
        while self._running:
            start = time.monotonic()
            self.tick()
            time.sleep(max(0.0, 1.0 / self.fps - (time.monotonic() - start)))
