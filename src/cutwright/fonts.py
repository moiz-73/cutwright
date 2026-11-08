"""Font registry: maps (family, weight) to cached Skia types."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import skia

FONT_DIR = Path(
    os.environ.get(
        "CUTWRIGHT_FONTS",
        Path.home() / ".local/share/fonts/cutwright/static",
    )
)

FAMILIES = {
    "sans": "Inter",
    "display": "InterTight",
    "serif": "InstrumentSerif",
    "serif-i": "InstrumentSerif",
    "mono": "JetBrainsMono",
    "grotesk": "SpaceGrotesk",
    "sora": "Sora",
    "bricolage": "Bricolage",
}

# Weights that actually exist on disk for each family.
_AVAILABLE = {
    "Inter": [400, 500, 600, 700, 800, 900],
    "InterTight": [500, 700, 800],
    "InstrumentSerif": [400],
    "JetBrainsMono": [400, 600],
    "SpaceGrotesk": [500, 700],
    "Sora": [600, 800],
    "Bricolage": [700, 800],
}


def _path(family: str, weight: int) -> Path:
    name = FAMILIES.get(family, family)
    weights = _AVAILABLE.get(name, [400])
    weight = min(weights, key=lambda w: abs(w - weight))
    fname = f"{name}-{weight}.ttf"
    if family == "serif-i":
        fname = "InstrumentSerif-Italic.ttf"
    p = FONT_DIR / fname
    if not p.exists():
        raise FileNotFoundError(f"font missing: {p} (run `cw fonts`)")
    return p


@lru_cache(maxsize=None)
def typeface(family: str, weight: int) -> skia.Typeface:
    tf = skia.Typeface.MakeFromFile(str(_path(family, weight)))
    if tf is None:  # pragma: no cover
        raise RuntimeError(f"could not load typeface {_path(family, weight)}")
    return tf


@lru_cache(maxsize=None)
def font(family: str, weight: int, size: float) -> skia.Font:
    f = skia.Font(typeface(family, weight), float(size))
    f.setSubpixel(True)
    f.setEdging(skia.Font.Edging.kAntiAlias)
    f.setHinting(skia.FontHinting.kNone)
    f.setLinearMetrics(True)
    return f
