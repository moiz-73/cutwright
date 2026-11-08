"""Cheap analysis passes: silence, scene cuts, loudness, face position."""
from __future__ import annotations

import re
from pathlib import Path

import cv2
import numpy as np

from .media import MediaError, probe, run
from .render import ffmpeg_bin

_SIL_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SIL_END = re.compile(r"silence_end:\s*(-?[\d.]+)")
_PTS = re.compile(r"pts_time:([\d.]+)")
_I = re.compile(r"I:\s*(-?[\d.]+)\s*LUFS")
_LRA = re.compile(r"LRA:\s*(-?[\d.]+)\s*LU")
_TP = re.compile(r"Peak:\s*(-?[\d.]+)\s*dBFS")


def silences(path: str, noise_db: float = -32.0, min_dur: float = 0.35) -> list[tuple[float, float]]:
    out = run(
        [
            ffmpeg_bin(), "-hide_banner", "-nostats", "-i", path,
            "-af", f"silencedetect=noise={noise_db}dB:d={min_dur}",
            "-f", "null", "-",
        ]
    )
    starts = [float(m) for m in _SIL_START.findall(out.stderr)]
    ends = [float(m) for m in _SIL_END.findall(out.stderr)]
    spans = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else probe(path)["duration"]
        spans.append((max(0.0, s), e))
    return spans


def scene_cuts(path: str, threshold: float = 0.30) -> list[float]:
    out = run(
        [
            ffmpeg_bin(), "-hide_banner", "-nostats", "-i", path,
            "-vf", f"select='gt(scene,{threshold})',showinfo",
            "-an", "-f", "null", "-",
        ]
    )
    return sorted(float(x) for x in _PTS.findall(out.stderr))


def loudness(path: str) -> dict:
    out = run(
        [
            ffmpeg_bin(), "-hide_banner", "-nostats", "-i", path,
            "-af", "ebur128=peak=true", "-f", "null", "-",
        ]
    )
    tail = out.stderr[-4000:]
    i = _I.findall(tail)
    lra = _LRA.findall(tail)
    tp = _TP.findall(tail)
    return {
        "integrated_lufs": float(i[-1]) if i else None,
        "lra": float(lra[-1]) if lra else None,
        "true_peak_dbfs": float(tp[-1]) if tp else None,
    }


def face_x(path: str, samples: int = 24) -> tuple[float, float]:
    """Median horizontal face centre as a 0..1 fraction, plus hit rate."""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise MediaError(f"cannot open {path}")
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    xs: list[float] = []
    tries = 0
    for i in range(samples):
        idx = int(n * (i + 0.5) / samples) if n else 0
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            continue
        tries += 1
        small = cv2.resize(frame, (0, 0), fx=0.35, fy=0.35)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, 1.12, 5, minSize=(28, 28))
        if len(faces):
            fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])
            xs.append((fx + fw / 2) / small.shape[1])
    cap.release()
    if not xs:
        return 0.5, 0.0
    return float(np.median(xs)), len(xs) / max(1, tries)


def audio_energy_spans(path: str, window: float = 0.25) -> list[tuple[float, float, float]]:
    """(start, end, rms) on a coarse grid; used to rank candidate cuts."""
    p = probe(path)
    if not p["has_audio"]:
        return []
    out = run(
        [
            ffmpeg_bin(), "-hide_banner", "-nostats", "-i", path,
            "-af", f"asetnsamples={int(48000 * window)},astats=metadata=1:reset=1",
            "-f", "null", "-",
        ]
    )
    vals = [float(x) for x in re.findall(r"RMS level dB:\s*(-?[\d.]+)", out.stderr)]
    spans = []
    for i, v in enumerate(vals):
        spans.append((i * window, (i + 1) * window, v))
    return spans
