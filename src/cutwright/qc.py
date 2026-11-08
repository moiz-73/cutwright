"""Quality gates: specs, dead frames, loudness, stream sanity."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import analyze
from .media import probe, run, run_bytes
from .render import ffmpeg_bin

_BLACK = re.compile(r"black_start:([\d.]+)\s+black_end:([\d.]+)")
_FREEZE = re.compile(r"freeze_start:\s*([\d.]+)")
_NB = re.compile(r"nb_frames=(\d+)")


def content_profile(path: str, width: int = 3200) -> tuple:
    """Per-frame max luminance at thumbnail size.

    A near-black title card with 40 px of type is not dead air; a frame with no
    bright pixel at all is. blackdetect cannot tell those apart, so measure the
    peak instead of the mean.
    """
    import numpy as np
    from .media import probe as _probe

    fps = _probe(path)["fps"] or 30.0
    h = 180
    w = max(2, int(width / 10))
    res = run_bytes(
        [
            ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-i", path,
            "-vf", f"scale={w}:{h}", "-an", "-f", "rawvideo", "-pix_fmt", "gray", "-",
        ]
    )
    frames = np.frombuffer(res.stdout, np.uint8)
    if frames.size == 0:
        return [], fps
    frames = frames[: (frames.size // (w * h)) * w * h].reshape(-1, h, w)
    peak = frames.max(axis=(1, 2)).astype(np.float32)
    bright = (frames > 70).mean(axis=(1, 2)).astype(np.float32)
    return list(zip(peak.tolist(), bright.tolist())), fps


def dead_spans(path: str, min_dur: float = 0.4, peak_threshold: float = 60.0) -> list[tuple[float, float]]:
    prof, fps = content_profile(path)
    spans, start = [], None
    for i, (peak, _bright) in enumerate(prof):
        empty = peak < peak_threshold
        if empty and start is None:
            start = i
        elif not empty and start is not None:
            if (i - start) / fps >= min_dur:
                spans.append((start / fps, i / fps))
            start = None
    if start is not None and (len(prof) - start) / fps >= min_dur:
        spans.append((start / fps, len(prof) / fps))
    return spans


def black_spans(path: str, min_dur: float = 0.4, pic_th: float = 0.96, pix_th: float = 0.04):
    out = run(
        [
            ffmpeg_bin(), "-hide_banner", "-nostats", "-i", path,
            "-vf", f"blackdetect=d={min_dur}:pic_th={pic_th}:pix_th={pix_th}",
            "-an", "-f", "null", "-",
        ]
    )
    return [(float(a), float(b)) for a, b in _BLACK.findall(out.stderr)]


def freeze_starts(path: str, min_dur: float = 2.0, noise_db: float = -60.0):
    out = run(
        [
            ffmpeg_bin(), "-hide_banner", "-nostats", "-i", path,
            "-vf", f"freezedetect=n={noise_db}dB:d={min_dur}",
            "-an", "-f", "null", "-",
        ]
    )
    return [float(x) for x in _FREEZE.findall(out.stderr)]


def qc(path: str, expect: dict | None = None) -> dict:
    p = probe(path)
    expect = expect or {}
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    if "width" in expect:
        check("width", p["width"] == expect["width"], f"{p['width']} vs {expect['width']}")
    if "height" in expect:
        check("height", p["height"] == expect["height"], f"{p['height']} vs {expect['height']}")
    if "duration" in expect:
        d = float(expect["duration"])
        check("duration", abs(p["duration"] - d) <= 0.12, f"{p['duration']:.3f}s vs {d:.3f}s")

    blacks = dead_spans(path)
    # A deliberate fade at the head or tail is not a dead-air defect.
    def _fade(span) -> bool:
        a, b = span
        return (a <= 0.08 and b <= 1.2) or (b >= p["duration"] - 0.08)
    dead = [sp for sp in blacks if not _fade(sp)]
    check("no_dead_air", not dead, f"{len(dead)} mid-roll empty span(s); {len(blacks)} total")
    freezes = freeze_starts(path)
    check("no_freezes", not freezes, f"{len(freezes)} freeze(s) >=2s")

    if p["has_audio"]:
        l = analyze.loudness(path)
        i = l.get("integrated_lufs")
        target = float(expect.get("loudness", -14.0))
        check("loudness", i is not None and abs(i - target) <= 1.5, f"{i} LUFS vs {target}")
        check("true_peak", (l.get("true_peak_dbfs") or -99) <= -1.0, f"{l.get('true_peak_dbfs')} dBFS")
    else:
        check("has_audio", False, "no audio stream")

    mb = p["size_mb"]
    check("file_weight", mb < 400, f"{mb} MB")

    passed = all(c["ok"] for c in checks)
    return {"file": str(path), "passed": passed, "probe": p, "checks": checks, "loudness": l if p["has_audio"] else None}


def report(path: str, out_json: str | None = None, expect: dict | None = None) -> dict:
    r = qc(path, expect)
    if out_json:
        Path(out_json).write_text(json.dumps(r, indent=2))
    return r
