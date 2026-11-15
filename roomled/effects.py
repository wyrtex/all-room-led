"""Эффекты подсветки. Каждый эффект рисует кадр для n светодиодов в момент t."""
from __future__ import annotations

import colorsys
import math
import random

Color = tuple[int, int, int]


def hex_to_rgb(value: str) -> Color:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def rgb_to_hex(c: Color) -> str:
    return "#%02x%02x%02x" % c


def scale(c: Color, k: float) -> Color:
    k = max(0.0, k)
    return tuple(min(255, int(v * k)) for v in c)  # type: ignore[return-value]


def lerp(a: Color, b: Color, t: float) -> Color:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


class Effect:
    label = ""

    def __init__(self, n: int, palette: list[str], speed: float = 1.0, seed: int | None = None):
        self.n = n
        self.palette: list[Color] = [hex_to_rgb(p) for p in palette] or [(255, 255, 255)]
        self.speed = max(0.05, float(speed))
        self.rng = random.Random(seed)

    def render(self, t: float) -> list[Color]:
        raise NotImplementedError


class Static(Effect):
    label = "Один цвет / чередование"

    def render(self, t):
        p = self.palette
        return [p[i % len(p)] for i in range(self.n)]


class Breathing(Effect):
    label = "Дыхание"

    def render(self, t):
        phase = t * self.speed * 0.4
        k = 0.5 - 0.5 * math.cos(2 * math.pi * phase)
        c = scale(self.palette[int(phase) % len(self.palette)], k)
        return [c] * self.n


class Rainbow(Effect):
    label = "Радуга"

    def render(self, t):
        out = []
        for i in range(self.n):
            h = (t * 0.1 * self.speed + i / max(1, self.n)) % 1.0
            r, g, b = colorsys.hsv_to_rgb(h, 1.0, 1.0)
            out.append((int(r * 255), int(g * 255), int(b * 255)))
        return out


class Garland(Effect):
    """Бегущая гирлянда: цвета палитры по очереди (красный-зелёный-красный...)."""

    label = "Гирлянда (бегущие цвета)"

    def render(self, t):
        shift = int(t * self.speed * 3)
        p = self.palette
        return [p[(i - shift) % len(p)] for i in range(self.n)]


class Twinkle(Effect):
    """Случайные вспышки с плавным появлением и затуханием, цвета только из палитры."""

    label = "Мерцание (случайные вспышки)"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.birth = [0.0] * self.n
        self.life = [0.0] * self.n
        self.col: list[Color] = [(0, 0, 0)] * self.n
        self.last_t = 0.0

    def render(self, t):
        dt = max(0.0, t - self.last_t)
        self.last_t = t
        rate = 0.15 * self.speed
        out = []
        for i in range(self.n):
            age = t - self.birth[i]
            if self.life[i] <= 0 or age >= self.life[i]:
                self.life[i] = 0.0
                if self.rng.random() < min(1.0, rate * dt * 4):
                    self.birth[i] = t
                    self.life[i] = self.rng.uniform(1.0, 2.5) / self.speed
                    self.col[i] = self.rng.choice(self.palette)
                    age = 0.0
            if self.life[i] > 0:
                k = math.sin(math.pi * min(1.0, age / self.life[i])) ** 2
                out.append(scale(self.col[i], k))
            else:
                out.append((0, 0, 0))
        return out


class GradientWave(Effect):
    label = "Плавная волна цветов"

    def render(self, t):
        p = self.palette
        if len(p) == 1:
            return [p[0]] * self.n
        out = []
        for i in range(self.n):
            pos = ((i / max(1, self.n)) + t * 0.15 * self.speed) % 1.0 * len(p)
            a = int(pos) % len(p)
            out.append(lerp(p[a], p[(a + 1) % len(p)], pos - int(pos)))
        return out


class Off(Effect):
    label = "Выключено"

    def render(self, t):
        return [(0, 0, 0)] * self.n


EFFECTS: dict[str, type[Effect]] = {
    "static": Static,
    "breathing": Breathing,
    "rainbow": Rainbow,
    "garland": Garland,
    "twinkle": Twinkle,
    "wave": GradientWave,
    "off": Off,
}


def make_effect(name: str, n: int, palette: list[str], speed: float = 1.0) -> Effect:
    return EFFECTS.get(name, Static)(n, palette, speed)
