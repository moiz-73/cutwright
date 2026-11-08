"""Procedural sound design: whooshes, impacts, risers, ticks, drone bed.

No samples, no licensing, no network. Everything is synthesised with numpy so
the soundtrack costs nothing and lands on exact frames.
"""
from __future__ import annotations

import wave

import numpy as np

SR = 48000
RNG = np.random.default_rng(7)


def _t(dur: float) -> np.ndarray:
    return np.arange(int(dur * SR), dtype=np.float32) / SR


def _exp_env(t: np.ndarray, decay: float, attack: float = 0.005) -> np.ndarray:
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return (a * np.exp(-t * decay)).astype(np.float32)


def _lp(x: np.ndarray, alpha: float) -> np.ndarray:
    """One-pole low pass, vectorised via lfilter-like recursion using cumsum.

    y[n] = y[n-1] + alpha * (x[n] - y[n-1]); implemented with scipy-free
    exponential weighting through np.convolve for short kernels.
    """
    k = max(1, int(3 / max(alpha, 1e-3)))
    kernel = (1 - alpha) ** np.arange(k, dtype=np.float32)
    kernel /= kernel.sum()
    return np.convolve(x, kernel, mode="same").astype(np.float32)


def _stereo(mono: np.ndarray, width: float = 1.0) -> np.ndarray:
    if width <= 0:
        return np.stack([mono, mono], 1)
    d = max(1, int(0.004 * SR * width))
    left = mono
    right = np.concatenate([np.zeros(d, np.float32), mono[:-d]])
    return np.stack([left, right], 1)


def whoosh(dur=0.9, f0=180.0, f1=2600.0, gain=1.0, pan=0.0) -> np.ndarray:
    t = _t(dur)
    n = len(t)
    noise = RNG.standard_normal(n).astype(np.float32)
    cutoff = np.linspace(0.02, 0.5, n, dtype=np.float32)
    # crude time-varying brightness via three fixed filters crossfaded
    bands = [_lp(noise, 0.02), _lp(noise, 0.12), _lp(noise, 0.45)]
    w = np.stack([1 - np.clip(cutoff / 0.2, 0, 1), np.clip(cutoff / 0.2, 0, 1) * (1 - np.clip((cutoff - 0.2) / 0.3, 0, 1)), np.clip((cutoff - 0.2) / 0.3, 0, 1)], 1)
    air = (bands[0] * w[:, 0] + bands[1] * w[:, 1] + bands[2] * w[:, 2])
    sweep = np.sin(2 * np.pi * (f0 * t + 0.5 * (f1 - f0) / dur * t * t)).astype(np.float32)
    env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 2.2
    mono = (air * 0.75 + sweep * 0.18) * env
    mono *= gain / (np.max(np.abs(mono)) + 1e-6)
    out = _stereo(mono, 0.6)
    if pan:
        out[:, 0] *= 1 - max(0, pan) * 0.7
        out[:, 1] *= 1 + min(0, pan) * 0.7
    return out


def impact(dur=1.6, gain=1.0) -> np.ndarray:
    t = _t(dur)
    body = np.sin(2 * np.pi * (52 - 12 * t) * t) * _exp_env(t, 3.4, 0.002)
    sub = np.sin(2 * np.pi * 31 * t) * _exp_env(t, 1.9, 0.01)
    click = _lp(RNG.standard_normal(len(t)).astype(np.float32), 0.6) * _exp_env(t, 55, 0.001)
    mono = body * 0.9 + sub * 0.55 + click * 0.35
    mono *= gain / (np.max(np.abs(mono)) + 1e-6)
    return _stereo(mono, 0.25)


def riser(dur=2.0, gain=1.0) -> np.ndarray:
    t = _t(dur)
    n = len(t)
    noise = _lp(RNG.standard_normal(n).astype(np.float32), 0.35)
    sweep = np.sin(2 * np.pi * (140 * t + 0.5 * (900 / dur) * t * t)).astype(np.float32)
    env = np.clip(t / dur, 0, 1) ** 2.4
    mono = (noise * 0.55 + sweep * 0.25) * env
    mono *= gain / (np.max(np.abs(mono)) + 1e-6)
    return _stereo(mono, 0.8)


def tick(dur=0.09, gain=0.55) -> np.ndarray:
    t = _t(dur)
    mono = np.sin(2 * np.pi * 2400 * t) * _exp_env(t, 90, 0.001)
    mono += _lp(RNG.standard_normal(len(t)).astype(np.float32), 0.8) * _exp_env(t, 120, 0.001) * 0.4
    mono *= gain / (np.max(np.abs(mono)) + 1e-6)
    return _stereo(mono, 0.15)


def drone(dur: float, root: float = 55.0, gain: float = 0.32, bpm: float = 100.0) -> np.ndarray:
    """Slow, dark ambient bed: root+fifth+octave, breathing filter, soft pulse."""
    t = _t(dur)
    lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 0.055 * t)
    pad = np.zeros(len(t), np.float32)
    for mult, amp in ((1.0, 0.5), (1.5, 0.28), (2.0, 0.18), (3.0, 0.06)):
        pad += amp * np.sin(2 * np.pi * root * mult * t + mult)
    pad *= 0.55 + 0.45 * lfo
    pad = _lp(pad, 0.012)

    beat = 60.0 / bpm
    pulse = np.zeros(len(t), np.float32)
    step = int(beat * SR)
    for i in range(0, len(t), step * 2):
        seg = min(step, len(t) - i)
        tt = np.arange(seg, dtype=np.float32) / SR
        pulse[i : i + seg] += np.sin(2 * np.pi * 46 * tt) * np.exp(-tt * 14) * 0.5

    air = _lp(RNG.standard_normal(len(t)).astype(np.float32), 0.004) * 0.05
    mono = pad + pulse * 0.5 + air
    mono *= gain / (np.max(np.abs(mono)) + 1e-6)
    return _stereo(mono, 0.35)


class Soundtrack:
    """Place clips on a timeline and mix down."""

    def __init__(self, duration: float, sr: int = SR):
        self.duration = duration
        self.sr = sr
        self.buf = np.zeros((int(duration * sr) + sr, 2), np.float32)

    def add(self, clip: np.ndarray, at: float, gain: float = 1.0) -> None:
        i = int(at * self.sr)
        if i >= len(self.buf):
            return
        n = min(len(clip), len(self.buf) - i)
        self.buf[i : i + n] += clip[:n] * gain

    def duck(self, at: float, depth: float = 0.55, hold: float = 0.45) -> None:
        i = int(at * self.sr)
        n = min(int(hold * self.sr), len(self.buf) - i)
        if n <= 0:
            return
        env = np.linspace(1.0, 1.0 - depth, 10).tolist() + [1.0 - depth] * 8 + np.linspace(1.0 - depth, 1.0, 30).tolist()
        env = np.interp(np.linspace(0, 1, n), np.linspace(0, 1, len(env)), env).astype(np.float32)
        self.buf[i : i + n] *= env[:, None]

    def master(self, peak: float = 0.89) -> np.ndarray:
        out = self.buf[: int(self.duration * self.sr)]
        # gentle bus glue
        out = np.tanh(out * 1.15) * 0.97
        m = np.max(np.abs(out)) + 1e-9
        return (out * (peak / m)).astype(np.float32)

    def write(self, path: str) -> None:
        data = self.master()
        pcm = np.clip(data, -1, 1)
        pcm = (pcm * 32767).astype(np.int16)
        with wave.open(path, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(self.sr)
            w.writeframes(pcm.tobytes())


def rms_db(x: np.ndarray) -> float:
    r = float(np.sqrt(np.mean(np.square(x)) + 1e-12))
    return 20 * np.log10(r + 1e-12)
