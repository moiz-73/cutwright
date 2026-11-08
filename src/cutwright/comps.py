"""Launch-film compositions.

Six scenes, one continuous film: cold open -> hero -> capabilities ->
product -> proof -> end card. Every element is a function of time, so any
frame can be rendered in isolation and the whole film is reproducible.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import skia

from . import audio, motion
from .raster import Raster, fit_size
from .theme import Format, Theme, hex_rgba


@dataclass
class LaunchSpec:
    name: str = "LUMEN"
    kicker: str = "INTRODUCING"
    hero_a: str = "See in the"
    hero_b: str = "dark."
    body: str = "A camera that finds light where there is none. No flash. No compromise."
    features: list = field(
        default_factory=lambda: [
            ("Night engine", "Computational capture down to 0.02 lux. No flash, no noise, no excuses."),
            ("Zero-lag focus", "Locks in twelve milliseconds and tracks faces through total darkness."),
            ("One-tap cinema", "Nine looks calibrated by colourists. Not filters, not luck."),
        ]
    )
    product_label: str = "THE CAMERA"
    product_a: str = "It sees what"
    product_b: str = "you can't."
    product_body: str = "A full-frame sensor, a new image pipeline, and an interface that gets out of the way."
    stat_value: float = 0.02
    stat_unit: str = "lux"
    stat_label: str = "MINIMUM ILLUMINATION"
    stat_note: str = "Streetlight off. Still recording."
    tagline: str = "See in the dark."
    url: str = "lumen.app"
    cta: str = "AVAILABLE 2026"
    accent: str = "#FFB26B"
    accent2: str = "#6C7BFF"
    bg: str = "#07070A"
    ink: str = "#F4F1E9"

    @classmethod
    def load(cls, path: str | Path) -> "LaunchSpec":
        data = json.loads(Path(path).read_text())
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


DUR = {
    "open": 2.0,
    "hero": 4.2,
    "features": 4.4,
    "product": 4.0,
    "stat": 2.8,
    "end": 3.6,
}
ORDER = list(DUR)
STARTS: dict[str, float] = {}
_acc = 0.0
for _k in ORDER:
    STARTS[_k] = _acc
    _acc += DUR[_k]
TOTAL = _acc


class LaunchFilm:
    def __init__(self, spec: LaunchSpec | None = None, fmt: Format | None = None):
        self.sp = spec or LaunchSpec()
        self.fmt = fmt or Format()
        self.th = Theme(bg=self.sp.bg, ink=self.sp.ink, accent=self.sp.accent, accent2=self.sp.accent2)
        self.W = self.fmt.width
        self.H = self.fmt.height
        self.m = self.W * 0.0625
        self.content = self.W - 2 * self.m
        self.duration = TOTAL

    # ------------------------------------------------------------------ util
    def _scene_at(self, t: float) -> tuple[str, float, float]:
        for i, k in enumerate(ORDER):
            s = STARTS[k]
            if t < s + DUR[k] or i == len(ORDER) - 1:
                return k, t - s, DUR[k]
        return "end", t - STARTS["end"], DUR["end"]

    def _head(self, r: Raster, t: float, idx: int) -> None:
        m, H = self.m, self.H
        r.circle(m + 4, H * 0.072, 4.5, self.th.accent, 0.95)
        r.text(self.sp.name, m + 20, H * 0.077, H * 0.0155, "mono", 600, self.th.ink, 0.9, tracking=0.22)
        r.text(f"{idx:02d} / 0{len(ORDER)-1}", r.W - m, H * 0.077, H * 0.0155, "mono", 400, self.th.muted, 0.85, tracking=0.14, align="right")

    def _rule(self, r: Raster, x: float, y: float, w: float, color, alpha=0.16, width=1.0) -> None:
        r.line(x, y, x + max(0.0, w), y, color, width, alpha)

    # ------------------------------------------------------------- backdrop
    def _bg(self, r: Raster, t: float) -> None:
        W, H = r.W, r.H
        r.clear(self.th.bg)
        r.radial_glow(
            W * 0.70 + math.sin(t * 0.11) * 46,
            H * 0.26 + math.cos(t * 0.09) * 26,
            W * 0.46,
            self.th.accent,
            0.055,
        )
        r.radial_glow(W * 0.16, H * 1.02, W * 0.40, self.th.accent2, 0.042)

    # ------------------------------------------------------------- scenes
    def _open(self, r: Raster, u: float, d: float) -> None:
        W, H, m = r.W, r.H, self.m
        fade = motion.smoothstep(u / 0.32)
        with r.alpha(fade):
            size = min(W, H) * 0.60
            r.text("01", m - 8, H * 0.94, size, "display", 800, self.th.ink, 0.035, tracking=-0.05)
            r.circle(m + 4, H * 0.072, 4.5, self.th.accent, 0.95)
            r.text(self.sp.name, m + 20, H * 0.077, H * 0.0155, "mono", 600, self.th.ink, 0.9, tracking=0.22)
            r.text("A FILM IN SIX PARTS", W - m, H * 0.077, H * 0.0145, "mono", 400, self.th.muted, 0.8, tracking=0.16, align="right")

            y = H * 0.735
            e = motion.out_expo(motion.clamp((u - 0.28) / 1.05))
            self._rule(r, m, y, self.content * e, self.th.ink, 0.20, 1.0)

            if u > 0.55:
                a = motion.clamp((u - 0.55) / 0.5)
                r.text("CINEMA, RE-DESIGNED FOR THE DARK", m, y + H * 0.042, H * 0.0148, "mono", 400, self.th.muted, 0.85 * a, tracking=0.22)
                n = int(round(100 * motion.out_cubic(motion.clamp((u - 0.35) / 1.3))))
                r.text(f"{n:03d}", W - m, y - H * 0.028, H * 0.017, "mono", 600, self.th.accent, a, tracking=0.10, align="right")

    def _hero(self, r: Raster, u: float, d: float) -> None:
        W, H, m = r.W, r.H, self.m
        push = 1 + 0.022 * motion.out_cubic(u / d)
        r.canvas.save()
        r.canvas.translate(W / 2, H / 2)
        r.canvas.scale(push, push)
        r.canvas.translate(-W / 2, -H / 2)

        self._head(r, u, 1)

        kx, ky = m, H * 0.30
        if u >= 0:
            r.text(self.sp.kicker, kx, ky, H * 0.0165, "mono", 600, self.th.accent, 0.95, tracking=0.30)
            e = motion.out_expo(motion.clamp(u / 0.55))
            self._rule(r, kx, ky + H * 0.028, 132 * e, self.th.accent, 0.55, 2.0)

        # line 1
        s1 = fit_size(r, self.sp.hero_a, self.content * 0.70, W * 0.104, "display", 800, -0.028)
        b1 = H * 0.535
        if u >= 0:
            with motion.mask_up(r, kx - 4, b1 - s1 * 0.86, r.text_width(self.sp.hero_a, s1, "display", 800, -0.028) + 8, s1 * 1.0, u, 0.02, 0.9, rise=s1 * 0.42):
                r.text(self.sp.hero_a, kx, b1, s1, "display", 800, self.th.ink, 1.0, tracking=-0.028)

        # line 2, serif italic
        s2 = W * 0.113
        b2 = H * 0.705
        if u > 0.10:
            with motion.mask_up(r, kx - 6, b2 - s2 * 0.90, r.text_width(self.sp.hero_b, s2, "serif-i", 400) + 12, s2 * 1.02, u, 0.10, 0.9, rise=s2 * 0.40):
                r.text(self.sp.hero_b, kx, b2, s2, "serif-i", 400, self.th.ink, 1.0)

        # right column
        if u > 0.45:
            a = motion.clamp((u - 0.45) / 0.6)
            bx = W * 0.655
            self._rule(r, bx, H * 0.395, 46 * a, self.th.ink, 0.30, 1.0)
            r.paragraph(self.sp.body, bx, H * 0.435, W * 0.0158, W * 0.275, "sans", 400, self.th.muted, 0.95 * a, 1.55)

        if u > 0.85:
            a = motion.clamp((u - 0.85) / 0.6)
            r.line(m, H * 0.885, W - m, H * 0.885, self.th.ink, 1.0, 0.12 * a)
            r.text("LUMEN ONE — 2026", m, H * 0.925, H * 0.0138, "mono", 400, self.th.muted, 0.8 * a, tracking=0.16)
            r.text("0.02 LUX  /  4K 60", W - m, H * 0.925, H * 0.0138, "mono", 400, self.th.muted, 0.8 * a, tracking=0.16, align="right")

        r.canvas.restore()

    def _features(self, r: Raster, u: float, d: float) -> None:
        W, H, m = r.W, r.H, self.m
        self._head(r, u, 2)
        if u >= 0:
            r.text("WHAT IT DOES", m, H * 0.205, H * 0.0145, "mono", 600, self.th.muted, 0.9, tracking=0.28)
        y0, gap = H * 0.315, H * 0.205
        for i, (title, desc) in enumerate(self.sp.features[:3]):
            start = 0.02 + i * 0.10
            if u < start:
                continue
            p = motion.clamp((u - start) / 0.7)
            e = motion.out_cubic(p)
            y = y0 + i * gap
            a = 0.9 * e
            r.line(m, y - gap * 0.30, m + self.content * e, y - gap * 0.30, self.th.ink, 1.0, 0.14)
            r.text(f"0{i+1}", m, y + H * 0.030, H * 0.0155, "mono", 600, self.th.accent, a, tracking=0.12)
            tx = m + W * 0.055 + (1 - e) * 26
            r.text(title, tx, y + H * 0.040, H * 0.052, "display", 800, self.th.ink, a, tracking=-0.018)
            r.paragraph(desc, W * 0.505 + (1 - e) * 18, y - H * 0.020, W * 0.0142, W * 0.34, "sans", 400, self.th.muted, 0.85 * a, 1.55)
            r.text("→", W - m - W * 0.012, y + H * 0.040, H * 0.030, "mono", 400, self.th.ink, 0.35 * a, align="right")
            if i == 0:
                uw = 120 * motion.out_expo(motion.clamp((u - start - 0.25) / 0.8))
                r.line(tx, y + H * 0.058, tx + uw, y + H * 0.058, self.th.accent, 3.0, 0.85)

    def _product(self, r: Raster, u: float, d: float) -> None:
        W, H, m = r.W, r.H, self.m
        self._head(r, u, 3)

        # left copy
        r.text(self.sp.product_label, m, H * 0.275, H * 0.0145, "mono", 600, self.th.accent, 0.9, tracking=0.28)
        s = H * 0.088
        for i, line in enumerate((self.sp.product_a, self.sp.product_b)):
            if u > 0.12 + i * 0.09:
                with motion.mask_up(r, m - 4, H * (0.365 + i * 0.115) - s * 0.84, r.text_width(line, s, "display", 800, -0.022) + 8, s, u, 0.12 + i * 0.09, 0.8, rise=s * 0.4):
                    r.text(line, m, H * (0.365 + i * 0.115), s, "display", 800, self.th.ink, 1.0, tracking=-0.022)
        if u > 0.55:
            a = motion.clamp((u - 0.55) / 0.6)
            r.paragraph(self.sp.product_body, m, H * 0.655, W * 0.0142, W * 0.30, "sans", 400, self.th.muted, 0.9 * a, 1.55)
            r.text("EXPLORE  →", m, H * 0.815, H * 0.015, "mono", 600, self.th.ink, 0.75 * a, tracking=0.18)

        # device card
        if u > 0.02:
            sp = motion.spring(motion.clamp((u - 0.02) / 1.0), 1.25, 5.5)
            cw, ch = W * 0.395, H * 0.625
            cx = W * 0.545
            cy = H * 0.185 + (1 - sp) * H * 0.16
            scale = 0.94 + 0.06 * sp
            r.canvas.save()
            r.canvas.translate(cx + cw / 2, cy + ch / 2)
            r.canvas.scale(scale, scale)
            r.canvas.translate(-(cx + cw / 2), -(cy + ch / 2))
            self._device(r, cx, cy, cw, ch, u - 0.02)
            r.canvas.restore()

    def _device(self, r: Raster, x: float, y: float, w: float, h: float, u: float) -> None:
        a = motion.clamp(u / 0.5)
        r.rrect(x, y, w, h, 26, "#0E0E13", 0.98 * a)
        # outer hairline
        p = skia.Paint(AntiAlias=True)
        p.setStyle(skia.Paint.kStroke_Style)
        p.setStrokeWidth(1.0)
        p.setColor4f(skia.Color4f(*hex_rgba(self.th.ink, 0.13 * a)))
        r.canvas.drawRRect(skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x, y, w, h), 26, 26), p)
        # glow behind
        r.radial_glow(x + w * 0.5, y + h * 0.45, w * 0.75, self.th.accent, 0.10 * a)

        pad = w * 0.045
        # top bar dots
        for i, c in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
            r.circle(x + pad + i * 18, y + pad, 4.0, c, 0.55 * a)
        r.text("LUMEN  /  CINEMA", x + w - pad, y + pad + 4, h * 0.020, "mono", 400, self.th.muted, 0.7 * a, tracking=0.16, align="right")

        # viewfinder
        vy = y + pad * 2.2
        vh = h * 0.52
        vx, vw = x + pad, w - 2 * pad
        r.rrect(vx, vy, vw, vh, 14, "#05060A", 1.0 * a)
        # night scene inside: gradient + moon + horizon
        r.canvas.save()
        r.canvas.clipRRect(skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(vx, vy, vw, vh), 14, 14), skia.ClipOp.kIntersect, True)
        r.linear_gradient(vx, vy, vw, vh, [(0.0, "#0A1424"), (0.55, "#070B14"), (1.0, "#04050A")])
        moon_x, moon_y, moon_r = vx + vw * 0.72, vy + vh * 0.30, vh * 0.13
        r.radial_glow(moon_x, moon_y, moon_r * 5.0, self.th.accent2, 0.18 * a)
        r.circle(moon_x, moon_y, moon_r, "#DFE6FF", 0.92 * a)
        # stars
        rng = [(0.12, 0.18), (0.24, 0.10), (0.36, 0.26), (0.55, 0.12), (0.88, 0.42), (0.08, 0.44)]
        for sx, sy in rng:
            r.circle(vx + vw * sx, vy + vh * sy, 1.2, "#FFFFFF", 0.35 * a)
        # horizon
        r.line(vx, vy + vh * 0.70, vx + vw, vy + vh * 0.70, self.th.ink, 1.0, 0.10)
        # focus brackets
        bw = vw * 0.10
        bx, by = vx + vw * 0.5 - bw / 2, vy + vh * 0.5 - bw / 2
        for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            px, py = bx + (bw if dx > 0 else 0), by + (bw if dy > 0 else 0)
            r.line(px, py, px + dx * bw * 0.22, py, self.th.accent, 1.6, 0.8 * a)
            r.line(px, py, px, py + dy * bw * 0.22, self.th.accent, 1.6, 0.8 * a)
        # scanline drift
        sy = (u * 0.12) % 1.0
        r.line(vx, vy + vh * sy, vx + vw, vy + vh * sy, self.th.ink, 1.0, 0.05)
        r.canvas.restore()

        # viewfinder HUD
        r.text("0.02 lx", vx + 12, vy + vh - 12, h * 0.018, "mono", 400, self.th.ink, 0.72 * a, tracking=0.08)
        r.text("4K 60", vx + vw - 12, vy + vh - 12, h * 0.018, "mono", 400, self.th.ink, 0.72 * a, tracking=0.08, align="right")

        # controls
        cy = y + h - pad * 1.6
        r.circle(x + w * 0.5, cy, h * 0.045, self.th.ink, 0.06 * a)
        r.circle(x + w * 0.5, cy, h * 0.032, "#F4F1E9", 0.92 * a)
        r.text("CINEMA", x + pad, cy + h * 0.008, h * 0.0165, "mono", 600, self.th.accent, 0.85 * a, tracking=0.14)
        r.text("f/1.2", x + w - pad, cy + h * 0.008, h * 0.0165, "mono", 400, self.th.muted, 0.8 * a, tracking=0.10, align="right")

    def _stat(self, r: Raster, u: float, d: float) -> None:
        W, H, m = r.W, r.H, self.m
        self._head(r, u, 4)
        r.text(self.sp.stat_label, m, H * 0.285, H * 0.0145, "mono", 600, self.th.muted, 0.9, tracking=0.28)
        e = motion.out_quint(motion.clamp(u / 1.25))
        val = self.sp.stat_value + (0.98 - self.sp.stat_value) * (1 - e)
        s = W * 0.132
        r.text(f"{val:.2f}", m - 6, H * 0.56, s, "display", 800, self.th.ink, 1.0, tracking=-0.045)
        vw = r.text_width(f"{val:.2f}", s, "display", 800, -0.045)
        r.text(self.sp.stat_unit, m + vw + 18, H * 0.56, H * 0.045, "serif-i", 400, self.th.accent, 0.95)
        r.line(m, H * 0.625, m + self.content * 0.92, H * 0.625, self.th.ink, 1.0, 0.14)
        r.paragraph(self.sp.stat_note, m, H * 0.675, W * 0.0165, W * 0.32, "serif-i", 400, self.th.muted, 0.9, 1.35)
        if u > 0.35:
            a = motion.clamp((u - 0.35) / 0.7)
            rx = W * 0.735
            r.line(rx, H * 0.285, rx, H * 0.60, self.th.ink, 1.0, 0.14 * a)
            r.text("MEASURED", rx + 34, H * 0.315, H * 0.0138, "mono", 600, self.th.accent, 0.85 * a, tracking=0.24)
            r.text("ISO 6400", rx + 34, H * 0.375, H * 0.020, "mono", 400, self.th.ink, 0.85 * a, tracking=0.08)
            r.text("1/8 s  ·  f/1.2", rx + 34, H * 0.425, H * 0.020, "mono", 400, self.th.ink, 0.85 * a, tracking=0.08)
            r.text("RAW + LOG", rx + 34, H * 0.475, H * 0.020, "mono", 400, self.th.ink, 0.85 * a, tracking=0.08)

    def _end(self, r: Raster, u: float, d: float) -> None:
        W, H = r.W, r.H
        e = motion.out_expo(motion.clamp((u - 0.1) / 1.0))
        with r.alpha(e):
            cy = H * 0.47
            r.radial_glow(W * 0.5, cy - H * 0.06, W * 0.30, self.th.accent, 0.06)
            size = W * 0.086
            tw = r.text_width(self.sp.name, size, "display", 800, 0.26)
            x = W / 2 - tw / 2
            r.text(self.sp.name, x, cy, size, "display", 800, self.th.ink, 1.0, tracking=0.26)
            pulse = 0.6 + 0.4 * math.sin(u * 3.2)
            r.circle(x + tw + 20, cy - size * 0.62, 5.0, self.th.accent, 0.9 * pulse)
            r.text(self.sp.tagline, W / 2, cy + H * 0.105, W * 0.030, "serif-i", 400, self.th.muted, 0.95, align="center")
            rw = 520 * motion.out_expo(motion.clamp((u - 0.5) / 0.9))
            r.line(W / 2 - rw / 2, cy + H * 0.175, W / 2 + rw / 2, cy + H * 0.175, self.th.ink, 1.0, 0.16)
            r.text(self.sp.url, W / 2, cy + H * 0.235, H * 0.018, "mono", 600, self.th.ink, 0.85, tracking=0.18, align="center")
            r.text(self.sp.cta, W / 2, cy + H * 0.285, H * 0.0145, "mono", 400, self.th.muted, 0.7, tracking=0.22, align="center")

    def clamp_time(self, ts: float, t: float | None = None) -> float:
        """Clamp a shutter sample to the scene of the frame it belongs to.

        `t` is the frame time, `ts` the offset sample. Using `ts` to pick the
        scene would let a sample 16 ms before a cut render the previous shot.
        """
        base = ts if t is None else t
        for k in ORDER:
            a, b = STARTS[k], STARTS[k] + DUR[k]
            if a <= base < b:
                return min(max(ts, a + 0.0005), b - 0.0005)
        return ts

    # --------------------------------------------------------------- driver
    def draw(self, r: Raster, t: float) -> None:
        self._bg(r, t)
        scene, u, d = self._scene_at(t)
        getattr(self, f"_{scene}")(r, u, d)

    # -------------------------------------------------------------- sound
    def soundtrack(self) -> audio.Soundtrack:
        st = audio.Soundtrack(self.duration)
        st.add(audio.drone(self.duration, gain=0.36), 0.0, 1.0)
        for at in (STARTS["hero"], STARTS["features"], STARTS["product"], STARTS["stat"], STARTS["end"]):
            st.add(audio.whoosh(0.95), at - 0.38, 0.32)
        st.add(audio.impact(1.3), STARTS["hero"], 0.30)
        st.add(audio.impact(1.7), STARTS["product"], 0.55)
        st.add(audio.impact(1.9), STARTS["end"], 0.45)
        for i in range(3):
            st.add(audio.tick(), STARTS["features"] + 0.55 + i * 0.11 * 1.0 + i * 0.42, 0.30)
        st.add(audio.riser(1.9), STARTS["end"] - 1.85, 0.30)
        for at in (STARTS["hero"], STARTS["product"], STARTS["end"]):
            st.duck(at, 0.35, 0.5)
        return st
