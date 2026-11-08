"""Thin, fast drawing layer over Skia with typographic helpers."""
from __future__ import annotations

import math
from contextlib import contextmanager

import numpy as np
import skia

from . import fonts
from .theme import hex_rgba


def col(value, alpha: float = 1.0) -> skia.Color4f:
    if isinstance(value, skia.Color4f):
        return value
    if isinstance(value, str):
        return skia.Color4f(*hex_rgba(value, alpha))
    if len(value) == 3:
        return skia.Color4f(value[0], value[1], value[2], alpha)
    return skia.Color4f(value[0], value[1], value[2], value[3] * alpha)


class Raster:
    """A single canvas. One instance is reused across frames."""

    def __init__(self, width: int, height: int):
        self.W = int(width)
        self.H = int(height)
        self.surface = skia.Surface(self.W, self.H)
        self.canvas = self.surface.getCanvas()
        self._img_cache: dict[int, skia.Image] = {}

    # ---------------------------------------------------------------- state
    def clear(self, color="#000000", alpha: float = 1.0) -> None:
        self.canvas.clear(col(color, alpha))

    @contextmanager
    def alpha(self, value: float):
        a = max(0, min(255, int(round(value * 255))))
        self.canvas.saveLayerAlpha(None, a)
        try:
            yield
        finally:
            self.canvas.restore()

    @contextmanager
    def transform(self, scale: float = 1.0, tx: float = 0.0, ty: float = 0.0):
        self.canvas.save()
        self.canvas.translate(tx, ty)
        if scale != 1.0:
            self.canvas.scale(scale, scale)
        try:
            yield
        finally:
            self.canvas.restore()

    @contextmanager
    def clip(self, x, y, w, h):
        self.canvas.save()
        self.canvas.clipRect(skia.Rect.MakeXYWH(x, y, w, h))
        try:
            yield
        finally:
            self.canvas.restore()

    def _paint(self, color, alpha=1.0, blur=0.0, blend=None) -> skia.Paint:
        p = skia.Paint(AntiAlias=True)
        p.setColor4f(col(color, alpha))
        if blur > 0:
            p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, blur))
        if blend is not None:
            p.setBlendMode(blend)
        return p

    # --------------------------------------------------------------- shapes
    def rect(self, x, y, w, h, color, alpha=1.0, blur=0.0, blend=None) -> None:
        if w <= 0 or h <= 0:
            return
        self.canvas.drawRect(
            skia.Rect.MakeXYWH(x, y, w, h), self._paint(color, alpha, blur, blend)
        )

    def rrect(self, x, y, w, h, r, color, alpha=1.0, blur=0.0, blend=None) -> None:
        if w <= 0 or h <= 0:
            return
        rr = skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x, y, w, h), r, r)
        self.canvas.drawRRect(rr, self._paint(color, alpha, blur, blend))

    def line(self, x1, y1, x2, y2, color, width=1.0, alpha=1.0, blur=0.0) -> None:
        p = self._paint(color, alpha, blur)
        p.setStyle(skia.Paint.kStroke_Style)
        p.setStrokeWidth(width)
        p.setStrokeCap(skia.Paint.kRound_Cap)
        self.canvas.drawLine(x1, y1, x2, y2, p)

    def circle(self, cx, cy, r, color, alpha=1.0, blur=0.0, blend=None) -> None:
        if r <= 0:
            return
        self.canvas.drawCircle(cx, cy, r, self._paint(color, alpha, blur, blend))

    def linear_gradient(self, x, y, w, h, stops, vertical=True, alpha=1.0) -> None:
        """stops: list of (offset, colour)."""
        if vertical:
            pts = [skia.Point(x, y), skia.Point(x, y + h)]
        else:
            pts = [skia.Point(x, y), skia.Point(x + w, y)]
        colors = [col(c, alpha) for _, c in stops]
        positions = [max(0.0, min(1.0, p)) for p, _ in stops]
        shader = skia.GradientShader.MakeLinear(pts, colors, positions)
        p = skia.Paint(AntiAlias=True)
        p.setShader(shader)
        self.canvas.drawRect(skia.Rect.MakeXYWH(x, y, w, h), p)

    def radial_glow(self, cx, cy, r, color, alpha=1.0, blend=skia.BlendMode.kScreen) -> None:
        if r <= 0:
            return
        shader = skia.GradientShader.MakeRadial(
            skia.Point(cx, cy),
            r,
            [col(color, alpha), col(color, 0.0)],
            [0.0, 1.0],
        )
        p = skia.Paint(AntiAlias=True)
        p.setShader(shader)
        p.setBlendMode(blend)
        self.canvas.drawCircle(cx, cy, r, p)

    # ----------------------------------------------------------------- text
    def text_width(self, s: str, size: float, family="sans", weight=500, tracking=0.0) -> float:
        f = fonts.font(family, weight, size)
        if not s:
            return 0.0
        if tracking == 0:
            return f.measureText(s)
        return sum(f.measureText(ch) for ch in s) + tracking * size * (len(s) - 1)

    def text(
        self,
        s: str,
        x: float,
        y: float,
        size: float,
        family="sans",
        weight=500,
        color="#ffffff",
        alpha: float = 1.0,
        tracking: float = 0.0,
        align: str = "left",
        baseline: bool = True,
    ) -> float:
        if not s:
            return 0.0
        f = fonts.font(family, weight, size)
        w = self.text_width(s, size, family, weight, tracking)
        if align == "center":
            x -= w / 2
        elif align == "right":
            x -= w
        if not baseline:
            y += -f.getMetrics().fAscent
        p = self._paint(color, alpha)
        if tracking == 0:
            self.canvas.drawString(s, x, y, f, p)
        else:
            cx = x
            for ch in s:
                self.canvas.drawString(ch, cx, y, f, p)
                cx += f.measureText(ch) + tracking * size
        return w

    def paragraph(
        self,
        s: str,
        x: float,
        y: float,
        size: float,
        max_width: float,
        family="sans",
        weight=400,
        color="#ffffff",
        alpha: float = 1.0,
        leading: float = 1.42,
        align: str = "left",
    ) -> float:
        words = s.split()
        lines: list[str] = []
        cur = ""
        for word in words:
            trial = f"{cur} {word}".strip()
            if self.text_width(trial, size, family, weight) <= max_width or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        lh = size * leading
        for i, line in enumerate(lines):
            self.text(
                line,
                x,
                y + i * lh,
                size,
                family,
                weight,
                color,
                alpha,
                align=align,
                baseline=False,
            )
        return len(lines) * lh

    # ---------------------------------------------------------------- image
    def image(self, rgb: np.ndarray, x, y, w, h, alpha=1.0, radius=0.0) -> None:
        key = id(rgb)
        img = self._img_cache.get(key)
        if img is None:
            if rgb.ndim == 2:
                rgb = np.stack([rgb] * 3, -1)
            rgba = np.empty((rgb.shape[0], rgb.shape[1], 4), np.uint8)
            rgba[..., :3] = rgb[..., :3]
            rgba[..., 3] = 255
            img = skia.Image.fromarray(rgba)
            self._img_cache = {key: img}
        p = skia.Paint(AntiAlias=True)
        p.setAlphaf(alpha)
        dst = skia.Rect.MakeXYWH(x, y, w, h)
        src = skia.Rect.MakeXYWH(0, 0, img.width(), img.height())
        if radius > 0:
            self.canvas.save()
            self.canvas.clipRRect(
                skia.RRect.MakeRectXY(dst, radius, radius), skia.ClipOp.kIntersect, True
            )
        sample = skia.SamplingOptions(skia.FilterMode.kLinear, skia.MipmapMode.kLinear)
        self.canvas.drawImageRect(img, src, dst, sample, p)
        if radius > 0:
            self.canvas.restore()

    # -------------------------------------------------------------- capture
    def rgb(self) -> np.ndarray:
        arr = self.surface.makeImageSnapshot().toarray()
        return arr[..., [2, 1, 0]]


def fit_size(
    r: Raster, s: str, max_width: float, start: float, family="display",
    weight=800, tracking=0.0, floor: float = 8.0,
) -> float:
    size = start
    while size > floor and r.text_width(s, size, family, weight, tracking) > max_width:
        size *= 0.97
    return size


def text_lines_height(size: float, leading: float, n: int) -> float:
    return size * leading * n
