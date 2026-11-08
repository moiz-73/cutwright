"""ffprobe/ffmpeg plumbing."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .render import ffmpeg_bin, ffprobe_bin


class MediaError(RuntimeError):
    pass


def run(cmd: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:  # pragma: no cover
        raise MediaError(f"timeout after {timeout}s: {' '.join(cmd[:4])}") from e


def run_bytes(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True)


def probe(path: str | Path) -> dict:
    p = str(path)
    if not Path(p).exists():
        raise MediaError(f"no such file: {p}")
    out = run(
        [
            ffprobe_bin(), "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", p,
        ]
    )
    if out.returncode != 0:
        raise MediaError(out.stderr.strip()[-800:] or f"ffprobe failed: {p}")
    data = json.loads(out.stdout)
    v = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
    a = next((s for s in data["streams"] if s.get("codec_type") == "audio"), None)
    if v is None:
        raise MediaError(f"no video stream: {p}")

    def _fraction(s: str) -> float:
        try:
            n, d = s.split("/")
            return float(n) / float(d) if float(d) else 0.0
        except Exception:
            return 0.0

    fps = _fraction(v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1")
    rotation = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rotation = int(float(sd["rotation"]))
    w, h = int(v["width"]), int(v["height"])
    if abs(rotation) in (90, 270):
        w, h = h, w
    duration = float(data["format"].get("duration") or v.get("duration") or 0.0)
    return {
        "path": p,
        "width": w,
        "height": h,
        "fps": round(fps, 4),
        "duration": duration,
        "rotation": rotation,
        "vcodec": v.get("codec_name"),
        "pix_fmt": v.get("pix_fmt"),
        "bit_rate": int(data["format"].get("bit_rate") or 0),
        "has_audio": a is not None,
        "acodec": a.get("codec_name") if a else None,
        "sample_rate": int(a.get("sample_rate", 0)) if a else 0,
        "channels": int(a.get("channels", 0)) if a else 0,
        "size_mb": round(Path(p).stat().st_size / 1e6, 2),
    }


def doctor() -> dict:
    out = {"ffmpeg": ffmpeg_bin(), "ffprobe": ffprobe_bin(), "ok": False}
    try:
        v = run([ffmpeg_bin(), "-version"]).stdout.splitlines()[0]
        out["version"] = v
        enc = run([ffmpeg_bin(), "-hide_banner", "-encoders"]).stdout
        out["libx264"] = "libx264" in enc
        out["aac"] = " aac " in enc
        out["ok"] = out["libx264"]
    except Exception as e:  # pragma: no cover
        out["error"] = str(e)
    return out
