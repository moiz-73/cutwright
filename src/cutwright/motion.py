"""Easing, timing and reveal primitives.

All curves take normalised time and return normalised progress. Everything is
clamped, so a scene can ask for `t=99` without exploding.
"""
from __future__ import annotations

import math


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def smoothstep(t: float) -> float:
    t = clamp(t)
    return t * t * (3 - 2 * t)


def out_expo(t: float) -> float:
    t = clamp(t)
    return 1.0 if t >= 1 else 1 - 2 ** (-10 * t)


def out_cubic(t: float) -> float:
    t = clamp(t)
    return 1 - (1 - t) ** 3


def out_quint(t: float) -> float:
    t = clamp(t)
    return 1 - (1 - t) ** 5


def in_out_cubic(t: float) -> float:
    t = clamp(t)
    return 4 * t**3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def in_out_quint(t: float) -> float:
    t = clamp(t)
    return 16 * t**5 if t < 0.5 else 1 - (-2 * t + 2) ** 5 / 2


def in_expo(t: float) -> float:
    t = clamp(t)
    return 0.0 if t <= 0 else 2 ** (10 * t - 10)


def spring(t: float, freq: float = 1.6, damping: float = 6.0) -> float:
    """Critically-ish damped spring settling at 1."""
    t = max(0.0, t)
    return 1 - math.exp(-damping * t) * math.cos(freq * 2 * math.pi * t)


def window(t: float, start: float, dur: float, attack: float = 0.0, release: float = 0.0) -> float:
    """1 inside [start, start+dur], ramping at edges."""
    if t < start or t > start + dur:
        return 0.0
    a = 1.0 if attack <= 0 else clamp((t - start) / attack)
    r = 1.0 if release <= 0 else clamp((start + dur - t) / release)
    return min(a, r)


def stagger(i: int, gap: float) -> float:
    return i * gap


def reveal(t: float, start: float, dur: float = 0.8, curve=out_expo) -> tuple[float, float]:
    """Return (progress, eased). progress is clamped 0..1."""
    p = clamp((t - start) / dur) if dur > 0 else 1.0
    return p, curve(p)


from contextlib import contextmanager


@contextmanager
def mask_up(r, x, y, w, h, t, start, dur=0.85, rise=48.0):
    """Clip a text block to a bottom-up mask and slide it up into place."""
    p = clamp((t - start) / dur) if dur > 0 else 1.0
    if p <= 0:
        yield
        return
    e = out_expo(p)
    r.canvas.save()
    r.canvas.clipRect(skia_rect(x - 6, y - 2, w + 12, h + 4))
    r.canvas.translate(0, (1 - e) * rise)
    try:
        yield
    finally:
        r.canvas.restore()


def skia_rect(x, y, w, h):
    import skia

    return skia.Rect.MakeXYWH(x, y, w, h)
