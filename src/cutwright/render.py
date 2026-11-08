"""Frame loop, motion blur, H.264 encode and audio mux."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from . import fx
from .raster import Raster


def ffmpeg_bin() -> str:
    return (
        os.environ.get("CUTWRIGHT_FFMPEG")
        or shutil.which("ffmpeg")
        or str(Path.home() / ".local/bin/ffmpeg")
    )


def ffprobe_bin() -> str:
    return (
        os.environ.get("CUTWRIGHT_FFPROBE")
        or shutil.which("ffprobe")
        or str(Path.home() / ".local/bin/ffprobe")
    )


@dataclass
class RenderSettings:
    fps: int = 30
    motion_blur: int = 3  # subframes; 1 disables
    shutter: float = 0.5  # fraction of a frame
    crf: int = 18
    preset: str = "medium"
    develop: bool = True
    grain: float = 4.0  # ffmpeg noise strength; 0 disables
    maxrate: str = "20M"
    audio_bitrate: str = "256k"
    loudness_target: float = -14.0


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, **kw)


def render_frames(
    draw: Callable[[Raster, float], None],
    out_path: str,
    duration: float,
    width: int,
    height: int,
    settings: RenderSettings | None = None,
    audio_path: str | None = None,
    verbose: bool = True,
    t_clamp=None,
) -> str:
    """Render `draw(raster, t)` for `duration` seconds into an MP4."""
    st = settings or RenderSettings()
    if width % 2:
        width += 1
    if height % 2:
        height += 1
    nframes = max(1, int(round(duration * st.fps)))
    out_path = str(out_path)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    tmp_video = out_path if not audio_path else tempfile.mktemp(suffix=".mp4")
    cmd = [
        ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{width}x{height}", "-framerate", str(st.fps), "-i", "-",
        "-an",
        *(["-vf", f"noise=alls={st.grain:g}:allf=t+u"] if st.grain > 0 else []),
        "-c:v", "libx264", "-preset", st.preset, "-crf", str(st.crf),
        "-maxrate", st.maxrate, "-bufsize", "40M",
        "-x264-params", "aq-mode=3:aq-strength=1.05",
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.2",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
        "-movflags", "+faststart",
        tmp_video,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    r = Raster(width, height)
    t0 = time.time()
    try:
        for i in range(nframes):
            t = i / st.fps
            if st.motion_blur > 1:
                acc = np.zeros((height, width, 3), np.float32)
                mb = st.motion_blur
                for k in range(mb):
                    off = ((k + 0.5) / mb - 0.5) * st.shutter / st.fps
                    ts = t + off
                    if t_clamp is not None:
                        ts = t_clamp(ts, t)
                    r.clear("#000000")
                    draw(r, ts)
                    acc += r.rgb()
                frame = (acc / mb).astype(np.uint8)
            else:
                r.clear("#000000")
                draw(r, t)
                frame = r.rgb()
            if st.develop:
                frame = fx.develop(frame, seed=i * 7919)
            proc.stdin.write(frame.tobytes())
            if verbose and (i % max(1, nframes // 10) == 0 or i == nframes - 1):
                pct = 100 * (i + 1) / nframes
                el = time.time() - t0
                eta = el / (i + 1) * (nframes - i - 1)
                print(
                    f"  frame {i+1}/{nframes}  {pct:5.1f}%  {el:5.1f}s elapsed  ~{eta:4.0f}s left",
                    file=sys.stderr,
                    flush=True,
                )
    finally:
        if proc.stdin:
            proc.stdin.close()
        err = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
        code = proc.wait()
        if code != 0:
            raise RuntimeError(f"ffmpeg video encode failed ({code}):\n{err[-2000:]}")

    if audio_path:
        _mux(tmp_video, audio_path, out_path, st)
        os.unlink(tmp_video)
    elapsed = time.time() - t0
    if verbose:
        print(f"  done in {elapsed:.1f}s -> {out_path}", file=sys.stderr)
    return out_path


def _mux(video: str, audio: str, out: str, st: RenderSettings) -> None:
    cmd = [
        ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
        "-i", video, "-i", audio,
        "-c:v", "copy",
        "-af", f"highpass=f=28,loudnorm=I={st.loudness_target}:TP=-1.5:LRA=11",
        "-c:a", "aac", "-b:a", st.audio_bitrate, "-ar", "48000",
        "-shortest", "-movflags", "+faststart", out,
    ]
    _run(cmd)


def render_still(draw: Callable[[Raster, float], None], out_png: str, t: float, width: int, height: int) -> str:
    r = Raster(width, height)
    r.clear("#000000")
    draw(r, t)
    frame = r.rgb()
    import cv2

    cv2.imwrite(out_png, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
    return out_png
