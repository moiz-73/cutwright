"""Design tokens: colour, type scale, spacing grid, safe areas."""
from __future__ import annotations

from dataclasses import dataclass, field


def hex_rgba(value: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    v = value.strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) == 6:
        v += "ff"
    r, g, b, a = (int(v[i : i + 2], 16) / 255.0 for i in (0, 2, 4, 6))
    return (r, g, b, a * alpha)


@dataclass
class Theme:
    """A small, opinionated design system.

    Everything is expressed relative to frame width so a 1080x1920 cut of the
    same film stays optically consistent.
    """

    bg: str = "#07070A"
    ink: str = "#F4F1E9"
    muted: str = "#9A9AA4"
    accent: str = "#C8FF4D"
    accent2: str = "#7B8CFF"
    grid_cols: int = 12
    margin: float = 0.0625  # fraction of width
    headline: float = 0.092  # fraction of width
    subhead: float = 0.052
    body: float = 0.0165
    label: float = 0.0104

    def c(self, name: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
        return hex_rgba(getattr(self, name), alpha)


@dataclass
class Format:
    width: int = 1920
    height: int = 1080
    fps: int = 30

    @property
    def vertical(self) -> bool:
        return self.height > self.width

    def px(self, frac: float) -> float:
        """Fraction of the short edge, so type scales with the frame."""
        return frac * min(self.width, self.height)


@dataclass
class Layer:
    """Convenience container for a timed element."""

    start: float
    duration: float
    data: dict = field(default_factory=dict)
