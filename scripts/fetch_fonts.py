#!/usr/bin/env python3
"""Fetch and pin the type stack cutwright expects.

Downloads the upstream variable fonts, instantiates the exact static weights we
use (so Skia does not have to interpret variable axes), and writes them to
$CUTWRIGHT_FONTS (default ~/.local/share/fonts/cutwright/static).

    python scripts/fetch_fonts.py
"""
from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/google/fonts/main/ofl"
DEST = Path(
    os.environ.get("CUTWRIGHT_FONTS", Path.home() / ".local/share/fonts/cutwright/static")
)

VARIABLE = {
    "Inter-var.ttf": "inter/Inter%5Bopsz,wght%5D.ttf",
    "InterTight-var.ttf": "intertight/InterTight%5Bwght%5D.ttf",
    "JetBrainsMono-var.ttf": "jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf",
    "SpaceGrotesk-var.ttf": "spacegrotesk/SpaceGrotesk%5Bwght%5D.ttf",
    "Sora-var.ttf": "sora/Sora%5Bwght%5D.ttf",
    "Bricolage-var.ttf": "bricolagegrotesque/BricolageGrotesque%5Bopsz,wdth,wght%5D.ttf",
}

STATIC = {
    "InstrumentSerif-Regular.ttf": "instrumentserif/InstrumentSerif-Regular.ttf",
    "InstrumentSerif-Italic.ttf": "instrumentserif/InstrumentSerif-Italic.ttf",
}

WEIGHTS = {
    "Inter": [400, 500, 600, 700, 800, 900],
    "InterTight": [500, 700, 800],
    "JetBrainsMono": [400, 600],
    "SpaceGrotesk": [500, 700],
    "Sora": [600, 800],
}


def fetch(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "cutwright/0.1"})
    with urllib.request.urlopen(req, timeout=90) as r:
        dest.write_bytes(r.read())


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    cache = DEST.parent / "var"
    cache.mkdir(exist_ok=True)

    for name, path in {**VARIABLE, **STATIC}.items():
        dest = cache / name
        if not dest.exists():
            print(f"  get {name}")
            fetch(f"{BASE}/{path}", dest)

    try:
        from fontTools.ttLib import TTFont
        from fontTools.varLib.instancer import instantiateVariableFont
    except ImportError:
        print("fonttools is required: pip install fonttools", file=sys.stderr)
        return 1

    for stem, weights in WEIGHTS.items():
        src = cache / f"{stem}-var.ttf"
        for w in weights:
            out = DEST / f"{stem}-{w}.ttf"
            if out.exists():
                continue
            inst = instantiateVariableFont(
                TTFont(src), {"wght": w}, inplace=False, updateFontNames=False
            )
            inst.save(out)
            print(f"  pin {out.name}")

    for w in (700, 800):
        out = DEST / f"Bricolage-{w}.ttf"
        if out.exists():
            continue
        inst = instantiateVariableFont(
            TTFont(cache / "Bricolage-var.ttf"),
            {"wght": w, "opsz": 48, "wdth": 100},
            inplace=False,
            updateFontNames=False,
        )
        inst.save(out)
        print(f"  pin {out.name}")

    for name in STATIC:
        out = DEST / name
        if not out.exists():
            out.write_bytes((cache / name).read_bytes())
            print(f"  pin {out.name}")

    print(f"fonts ready in {DEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
