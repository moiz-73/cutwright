"""HYPERCUT: a beat-locked 3D sting.

18 beats at 120 BPM. Everything is driven by the same 0.5 s grid: camera
kicks, card swaps, flashes, and the soundtrack's impacts land on the same
timestamp, so the cut reads as one gesture rather than six effects.
"""
from __future__ import annotations

import math

import numpy as np

from . import audio, motion
from .raster import Raster, fit_size
from .theme import Format, Theme
from . import threed as T

BPM = 120.0
BEAT = 60.0 / BPM
TOTAL = 9.5
SECTIONS = {"ignition": 0.0, "fly": 2.0, "cards": 4.25, "end": 6.25}


def beat(t: float) -> int:
    return int(t / BEAT)


def beat_phase(t: float) -> float:
    return (t % BEAT) / BEAT


def pulse(t: float, decay: float = 9.0) -> float:
    return math.exp(-beat_phase(t) * decay)


def shake(t: float, hits: list[float], amp: float = 1.0) -> tuple[float, float]:
    x = y = 0.0
    for h in hits:
        d = t - h
        if 0 <= d < 0.35:
            k = math.exp(-d * 11) * amp
            x += math.sin(d * 91 + h) * 0.06 * k
            y += math.cos(d * 77 + h) * 0.04 * k
    return x, y


class HyperFilm:
    def __init__(self, fmt: Format | None = None):
        self.fmt = fmt or Format()
        self.th = Theme(bg="#050507", ink="#F4F1E9", accent="#FFB26B", accent2="#6C7BFF")
        self.W, self.H = self.fmt.width, self.fmt.height
        self.duration = TOTAL
        self.hits = [2.0, 4.25, 6.25, 7.6, 8.6]

    # ------------------------------------------------------------------ util
    def _cam(self, t: float) -> T.Camera:
        W, H = self.W, self.H
        sx, sy = shake(t, self.hits, 1.0)
        z = 4.6
        ty = 0.9
        target = (0.0, 0.35, -2.0)
        if t < SECTIONS["fly"]:
            u = motion.in_out_cubic(t / SECTIONS["fly"])
            z = 4.6 - 2.2 * u
            ty = 1.3 - 0.4 * u
            target = (0.0, 0.30 - 0.15 * u, -3.0)
        elif t < SECTIONS["cards"]:
            u = motion.in_out_cubic((t - SECTIONS["fly"]) / (SECTIONS["cards"] - SECTIONS["fly"]))
            z = 2.4 - 4.8 * u
            ty = 0.9 - 0.35 * u
            target = (0.0, 0.20, z - 8.0)
        elif t < SECTIONS["end"]:
            z = 3.4
            ty = 0.45
            target = (0.0, 0.15, 0.0)
        else:
            u = motion.out_cubic(motion.clamp((t - SECTIONS["end"]) / (TOTAL - SECTIONS["end"])))
            a = math.radians(26 * (1 - u))
            z = 5.6
            ty = 0.55
            target = (0.0, 0.35, -0.4)
        fov = 40.0 + 1.6 * pulse(t) - 1.2 * (0.5 if t > SECTIONS["fly"] else 0.0)
        return T.Camera(W, H, pos=(sx, ty + sy, z), target=target, fov=fov)

    def _floor(self, r: Raster, cam: T.Camera, t: float, y: float = -1.25) -> None:
        segs = T.grid_lines(cam, z0=6.0, z1=-34.0, step=1.15, half_width=7.0, y=y)
        for a, b, fade in segs:
            r.line(float(a[0]), float(a[1]), float(b[0]), float(b[1]),
                   self.th.ink, 1.0, 0.11 * fade)
        # horizon glow at the vanishing point
        r.radial_glow(cam.width * 0.5, cam.height * 0.47, cam.width * 0.42, self.th.accent, 0.10)

    def _word_plane(self, text: str, size: float, w: float, h: float, color=None, tracking=0.02, family="display", weight=800):
        color = color or self.th.ink

        def draw(rr):
            tw = rr.text_width(text, size, family, weight, tracking)
            x = (w * 200 - tw) / 2
            hh = h * 200
            f = size
            rr.text(text, x, hh * 0.5 + f * 0.35, f, family, weight, color, tracking=tracking)

        return draw

    # ---------------------------------------------------------------- scenes
    def _ignition(self, r: Raster, t: float, cam: T.Camera) -> None:
        self._floor(r, cam, t)
        # centre reticle that snaps on every beat
        p = pulse(t, 7.0)
        cx, cy = self.W * 0.5, self.H * 0.52
        r.circle(cx, cy, 3 + 2 * p, self.th.accent, 0.9)
        for k in range(4):
            a = math.radians(45 + k * 90)
            r.line(cx + math.cos(a) * 26, cy + math.sin(a) * 26,
                   cx + math.cos(a) * (40 + 16 * p), cy + math.sin(a) * (40 + 16 * p),
                   self.th.accent, 1.4, 0.55)
        r.text("REC", self.W * 0.5, self.H * 0.70, self.H * 0.014, "mono", 600,
               self.th.ink, 0.55, tracking=0.32, align="center")
        # boot column, as if the camera is reporting
        rows = ["SHUTTER 1/48", "ISO 6400", "WB 3200K", "0.02 LUX"]
        for i, row in enumerate(rows):
            a = 0.42 + 0.25 * pulse(t, 5.0) if i == 3 else 0.42
            r.text(row, 120, self.H * (0.30 + i * 0.055), self.H * 0.0135, "mono", 400,
                   self.th.muted, a, tracking=0.16)
        # big beat counter
        b = beat(t)
        r.text(f"0{b}", 120, self.H * 0.86, self.H * 0.20, "display", 800, self.th.ink,
               0.55, tracking=-0.04)
        # concentric rings snapping on the beat
        p = pulse(t, 6.0)
        for k in range(3):
            rad = (70 + k * 58) * (1 + 0.12 * p)
            r.circle(cx, cy, rad, self.th.ink, 0.12 - k * 0.03)

    def _fly(self, r: Raster, t: float, cam: T.Camera) -> None:
        self._floor(r, cam, t)
        # wordmark ahead, camera passes through it
        z = -6.0
        yaw = 0.10 * math.sin(t * 2.0)
        m = T.mat_translate(0, 0.35, z) @ T.mat_rot_y(yaw)
        pl = T.Plane(7.0, 1.7, model=m, draw=self._word_plane("LUMEN", 230, 7.0, 1.7, tracking=0.10))
        T.draw_scene(r, cam, [pl])
        # warp streaks: radial, beat-reactive, keeps the frame full at the pass
        p = pulse(t, 5.0)
        cx, cy = self.W * 0.5, self.H * 0.5
        for i in range(56):
            a = (i / 56.0) * math.tau + 0.15 * math.sin(t * 1.7 + i)
            r0 = 110 + 70 * ((i * 37) % 100) / 100.0
            r1 = r0 + (260 + 520 * p) * (0.45 + 0.55 * ((i * 53) % 100) / 100.0)
            r.line(cx + math.cos(a) * r0, cy + math.sin(a) * r0,
                   cx + math.cos(a) * r1, cy + math.sin(a) * r1,
                   self.th.ink, 1.2, 0.20)
        # edge ticker
        r.text("48.8566 N", self.W - 90, self.H * 0.5, self.H * 0.013, "mono", 400,
               self.th.muted, 0.5, tracking=0.18, align="right")

    def _cards(self, r: Raster, t: float, cam: T.Camera) -> None:
        self._floor(r, cam, t)
        idx = min(3, int((t - SECTIONS["cards"]) / BEAT))
        word = ["NIGHT", "FOCUS", "CINEMA", "0.02 lx"][idx]
        local = (t - SECTIONS["cards"]) % BEAT
        punch = 1.0 + 0.22 * math.exp(-local * 16)
        yaw = 0.55 * math.exp(-local * 7) * (1 if idx % 2 == 0 else -1)
        m = (T.mat_translate(0, 0.25, -1.4) @ T.mat_rot_y(yaw) @ T.mat_scale(punch))
        size = 190 if idx < 3 else 210
        pl = T.Plane(4.7, 1.25, model=m,
                     draw=self._word_plane(word, size, 4.7, 1.25, tracking=0.04))
        T.draw_scene(r, cam, [pl])
        r.text(f"{idx+1:02d} / 04", 120, self.H * 0.905, self.H * 0.013, "mono", 400,
               self.th.muted, 0.6, tracking=0.2)

    def _end(self, r: Raster, t: float, cam: T.Camera) -> None:
        self._floor(r, cam, t)
        u = motion.out_cubic(motion.clamp((t - SECTIONS["end"]) / 1.1))
        yaw = -0.25 + 0.25 * u
        m = T.mat_translate(0, 0.45, 0) @ T.mat_rot_y(yaw)
        pl = T.Plane(6.4, 1.5, model=m, draw=self._word_plane("LUMEN", 250, 6.4, 1.5, tracking=0.12))
        tag = T.Plane(3.4, 0.22, model=T.mat_translate(0, -0.55, 0.02),
                      draw=self._word_plane("see in the dark", 30, 3.4, 0.22, color=self.th.muted, family="serif-i", weight=400, tracking=0.01))
        T.draw_scene(r, cam, [tag, pl])

    # --------------------------------------------------------------- driver
    def draw(self, r: Raster, t: float) -> None:
        r.clear(self.th.bg)
        cam = self._cam(t)
        r.radial_glow(self.W * 0.5, self.H * 0.45, self.W * 0.55, self.th.accent2, 0.05)
        if t < SECTIONS["fly"]:
            self._ignition(r, t, cam)
        elif t < SECTIONS["cards"]:
            self._fly(r, t, cam)
        elif t < SECTIONS["end"]:
            self._cards(r, t, cam)
        else:
            self._end(r, t, cam)

        # beat flash + vignette-ish edge darkening stays in the finish chain
        f = pulse(t, 16.0) * 0.10
        if f > 0.002:
            r.rect(0, 0, self.W, self.H, "#FFFFFF", f)
        # final fade
        if t > TOTAL - 0.45:
            a = (t - (TOTAL - 0.45)) / 0.45
            r.rect(0, 0, self.W, self.H, "#000000", min(1.0, a))

    # ---------------------------------------------------------------- sound
    def soundtrack(self) -> audio.Soundtrack:
        st = audio.Soundtrack(self.duration)
        st.add(audio.drone(self.duration, root=55.0, gain=0.30, bpm=120.0), 0.0)
        for at in (SECTIONS["fly"], SECTIONS["cards"], SECTIONS["end"]):
            st.add(audio.whoosh(0.85), at - 0.30, 0.42)
        st.add(audio.riser(1.1), SECTIONS["end"] - 1.15, 0.34)
        n = int(self.duration / BEAT)
        for i in range(n):
            at = i * BEAT
            st.add(audio.impact(0.42), at, 0.16 if i % 2 else 0.24)
        for at in (SECTIONS["fly"], SECTIONS["cards"], SECTIONS["end"], 7.6):
            st.add(audio.impact(1.1), at, 0.42)
            st.duck(at, 0.30, 0.4)
        for i in range(4):
            st.add(audio.tick(), SECTIONS["cards"] + i * BEAT, 0.28)
        return st
