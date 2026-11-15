"""Бэкенды: связь с реальным железом (через OpenRGB SDK) или симулятор."""
from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field

from .effects import Color

log = logging.getLogger("roomled.backend")


@dataclass
class Zone:
    key: str          # стабильный ключ «устройство::зона»
    device_key: str
    name: str
    offset: int       # смещение первого светодиода в буфере устройства
    count: int


@dataclass
class Device:
    key: str
    name: str
    kind: str
    led_count: int
    zones: list[Zone] = field(default_factory=list)


class Backend:
    def scan(self) -> list[Device]:
        raise NotImplementedError

    def write(self, device_key: str, colors: list[Color]) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


class FakeBackend(Backend):
    """Симулятор без железа: для разработки и тестов."""

    def __init__(self):
        self.frames: dict[str, list[Color]] = {}

    def scan(self):
        spec = [
            ("ASRock B650 Steel Legend WiFi", "motherboard",
             [("Addressable Header 1", 24), ("Addressable Header 2", 12), ("Addressable Header 3/Audio", 12), ("PCH", 1)]),
            ("Valkyrie VK99", "keyboard", [("Keyboard", 99)]),
            ("Keychron Gaming Keyboard 1", "keyboard", [("Keyboard", 87)]),
        ]
        devices = []
        for name, kind, zones in spec:
            d = Device(name, name, kind, sum(c for _, c in zones))
            off = 0
            for zn, c in zones:
                d.zones.append(Zone(f"{name}::{zn}", name, zn, off, c))
                off += c
            devices.append(d)
        return devices

    def write(self, device_key, colors):
        self.frames[device_key] = list(colors)


class OpenRGBBackend(Backend):
    def __init__(self, address="127.0.0.1", port=6742, exe_path: str | None = None):
        self.address, self.port, self.exe_path = address, port, exe_path
        self.client = None
        self._devs: dict[str, object] = {}
        self._proc = None

    def _port_open(self) -> bool:
        try:
            with socket.create_connection((self.address, self.port), timeout=0.5):
                return True
        except OSError:
            return False

    def _ensure_server(self):
        if self._port_open():
            return
        if self.exe_path and os.path.exists(self.exe_path):
            log.info("Запускаю OpenRGB: %s", self.exe_path)
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
            self._proc = subprocess.Popen(
                [self.exe_path, "--server", "--startminimized"], creationflags=flags)
            for _ in range(60):
                if self._port_open():
                    time.sleep(1.0)
                    return
                time.sleep(0.5)
        raise ConnectionError(
            "OpenRGB не найден. Запусти OpenRGB с включённым SDK Server "
            "(вкладка SDK Server → Start Server) или укажи openrgb_path в config.json.")

    def scan(self):
        from openrgb import OpenRGBClient

        self._ensure_server()
        if self.client:
            try:
                self.client.disconnect()
            except Exception:
                pass
        self.client = OpenRGBClient(self.address, self.port, name="RoomLED")
        self._devs.clear()
        seen: dict[str, int] = {}
        devices = []
        for dev in self.client.devices:
            seen[dev.name] = seen.get(dev.name, 0) + 1
            key = dev.name if seen[dev.name] == 1 else f"{dev.name} #{seen[dev.name]}"
            try:
                dev.set_mode("direct")
            except Exception:
                try:
                    dev.set_mode("Direct")
                except Exception:
                    log.warning("У %s нет режима Direct, эффекты могут не работать", dev.name)
            d = Device(key, dev.name, dev.type.name.lower(), len(dev.leds))
            off = 0
            for z in dev.zones:
                n = len(z.leds)
                if n == 0:
                    continue
                zoff = z.leds[0].id if z.leds[0].id is not None else off
                d.zones.append(Zone(f"{key}::{z.name}", key, z.name, zoff, n))
                off = zoff + n
            self._devs[key] = dev
            devices.append(d)
        return devices

    def write(self, device_key, colors):
        from openrgb.utils import RGBColor

        dev = self._devs.get(device_key)
        if dev is None:
            return
        data = [RGBColor(*c) for c in colors]
        try:
            dev.set_colors(data, fast=True)
        except TypeError:
            dev.set_colors(data)

    def close(self):
        if self.client:
            try:
                self.client.disconnect()
            except Exception:
                pass
