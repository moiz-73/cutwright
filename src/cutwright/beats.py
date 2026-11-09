"""Beat and onset detection without librosa/aubio.

Spectral-flux onsets + autocorrelation tempo + comb-filter phase. Pure numpy,
about 0.2 s for a 30 s track at 22 kHz, which is cheap enough to run inside an
edit command rather than as a separate service.
"""
from __future__ import annotations

import subprocess

import numpy as np

from .render import ffmpeg_bin

SR = 22050
HOP = 512
WIN = 1024


def decode(path: str, sr: int = SR) -> np.ndarray:
    out = subprocess.run(
        [ffmpeg_bin(), "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
        capture_output=True,
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr.decode("utf-8", "replace")[-500:])
    return np.frombuffer(out.stdout, np.float32).copy()


def onset_envelope(y: np.ndarray) -> np.ndarray:
    if len(y) < WIN * 2:
        return np.zeros(1, np.float32)
    frames = np.lib.stride_tricks.sliding_window_view(y, WIN)[::HOP]
    window = np.hanning(WIN).astype(np.float32)
    spec = np.abs(np.fft.rfft(frames * window, axis=1)).astype(np.float32)
    flux = np.maximum(0.0, np.diff(spec, axis=0)).sum(axis=1)
    flux = np.concatenate([[0.0], flux])
    # remove slow loudness drift, then normalise
    k = 32
    base = np.convolve(flux, np.ones(k, np.float32) / k, mode="same")
    flux = np.maximum(0.0, flux - base)
    m = flux.max()
    return flux / m if m > 0 else flux


def tempo(flux: np.ndarray, sr: int = SR, hop: int = HOP) -> tuple[float, int]:
    """Return (bpm, lag in frames)."""
    if len(flux) < 8:
        return 0.0, 0
    x = flux - flux.mean()
    ac = np.correlate(x, x, mode="full")[len(x) - 1 :]
    ac /= ac[0] + 1e-9
    lo = int(60.0 / 200.0 * sr / hop)  # 200 bpm
    hi = int(60.0 / 55.0 * sr / hop)   # 55 bpm
    hi = min(hi, len(ac) - 1)
    if hi <= lo:
        return 0.0, 0
    lag = lo + int(np.argmax(ac[lo:hi]))
    # octave correction: prefer the faster pulse when its correlation is close
    for div in (2, 3):
        cand = lag // div
        if cand >= lo and ac[cand] > 0.82 * ac[lag]:
            lag = cand
    bpm = 60.0 * sr / (hop * lag)
    return bpm, lag


def beat_times(y: np.ndarray, sr: int = SR) -> dict:
    flux = onset_envelope(y)
    bpm, lag = tempo(flux, sr)
    if lag <= 0:
        return {"bpm": 0.0, "beats": [], "flux": flux}
    # phase: offset that puts the most onset energy on the grid
    best, best_score = 0, -1.0
    for off in range(lag):
        score = float(flux[off::lag].sum())
        if score > best_score:
            best, best_score = off, score
    bpm, times = refine(flux, lag, best, sr)
    return {"bpm": round(float(bpm), 2), "beats": times, "flux": flux}


def refine(flux: np.ndarray, lag: int, offset: int, sr: int = SR, hop: int = HOP) -> tuple[float, list[float]]:
    """Least-squares fit of t_i = a + i*T over local onset peaks.

    A constant-lag grid drifts because tempo is rarely exactly lag*fps; fitting
    the whole beat array keeps 30 s of cuts within a frame.
    """
    idx = np.arange(offset, len(flux), lag)
    if len(idx) < 4:
        return sr / (hop * lag) * 60.0, [i * hop / sr for i in idx]
    window = max(2, int(0.06 * sr / hop))
    obs_i, obs_t = [], []
    for k, i in enumerate(idx):
        lo, hi = max(0, i - window), min(len(flux), i + window + 1)
        j = lo + int(np.argmax(flux[lo:hi]))
        obs_i.append(k)
        obs_t.append(j * hop / sr)
    obs_i = np.asarray(obs_i, np.float64)
    obs_t = np.asarray(obs_t, np.float64)
    A = np.stack([np.ones_like(obs_i), obs_i], 1)
    (a, T), *_ = np.linalg.lstsq(A, obs_t, rcond=None)
    if not (0.2 < T < 1.4):
        return sr / (hop * lag) * 60.0, [i * hop / sr for i in idx]
    residual = float(np.max(np.abs(obs_t - (a + T * obs_i))))
    if residual > 0.045:  # >45 ms: the grid does not really fit; keep the comb
        return sr / (hop * lag) * 60.0, [i * hop / sr for i in idx]
    beats = [float(a + T * i) for i in obs_i]
    beats = [b for b in beats if b >= 0]
    return 60.0 / T, beats


def analyze(path: str) -> dict:
    y = decode(path)
    r = beat_times(y)
    r.pop("flux", None)
    r["duration"] = round(len(y) / SR, 3)
    return r
