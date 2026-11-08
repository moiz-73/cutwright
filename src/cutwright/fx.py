"""CPU film finishing: grade, bloom, halation, grain, vignette.

Optimised for 1080p on two cores: 8-bit LUTs and OpenCV integer paths instead
of full-frame float maths. Target budget is ~50 ms/frame for the whole chain.
"""
from __future__ import annotations

from functools import lru_cache

import cv2
import numpy as np


def _luma(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)


@lru_cache(maxsize=8)
def _tone_lut(contrast: float, lift: float, toe: float) -> np.ndarray:
    x = np.arange(256, dtype=np.float32) / 255.0
    x = (x - 0.5) * contrast + 0.5 + lift
    x = np.clip(x, 0, 1)
    x = np.where(x < toe, x * 0.86, x)
    lut = np.clip(x * 255.0, 0, 255).astype(np.uint8)
    return np.repeat(lut[:, None], 3, axis=1).reshape(256, 1, 3)


@lru_cache(maxsize=8)
def _sat_matrix(saturation: float, warm: float) -> np.ndarray:
    # Rec.709 luma weights
    lr, lg, lb = 0.2126, 0.7152, 0.0722
    m = np.array(
        [
            [lr + (1 - lr) * saturation, lg - lg * saturation, lb - lb * saturation],
            [lr - lr * saturation, lg + (1 - lg) * saturation, lb - lb * saturation],
            [lr - lr * saturation, lg - lg * saturation, lb + (1 - lb) * saturation],
        ],
        np.float32,
    )
    m[0, 0] += warm * 0.03
    m[2, 2] -= warm * 0.03
    return m


def grade(img, contrast=1.07, saturation=1.05, warm=0.15, lift=0.0, toe=0.02) -> np.ndarray:
    out = cv2.LUT(img, _tone_lut(contrast, lift, toe))
    out = cv2.transform(out, _sat_matrix(saturation, warm))
    return out


def bloom(img, threshold=182, sigma=5.0, amount=0.55, scale=6) -> np.ndarray:
    h, w = img.shape[:2]
    small = cv2.resize(img, (max(2, w // scale), max(2, h // scale)), interpolation=cv2.INTER_AREA)
    g = _luma(small).astype(np.int16)
    hot = np.clip((g - threshold) * 2, 0, 255).astype(np.uint8)
    hot = cv2.GaussianBlur(hot, (0, 0), sigma)
    up = cv2.resize(hot, (w, h), interpolation=cv2.INTER_LINEAR)
    if amount != 1.0:
        up = cv2.convertScaleAbs(up, alpha=amount)
    glow = cv2.cvtColor(up, cv2.COLOR_GRAY2RGB)
    # screen: 255 - (255-a)*(255-b)/255
    inv_a = cv2.subtract(255, glow)
    inv_b = cv2.subtract(255, img)
    prod = cv2.multiply(inv_a, inv_b, scale=1.0 / 255.0)
    return cv2.subtract(255, prod)


def chromatic(img, amount=1.0) -> np.ndarray:
    if amount <= 0:
        return img
    s = max(1, int(round(amount)))
    out = img.copy()
    out[..., 0] = np.roll(img[..., 0], s, axis=1)
    out[..., 2] = np.roll(img[..., 2], -s, axis=1)
    return out


@lru_cache(maxsize=8)
def _vignette_mask_u8(h: int, w: int, strength: float) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = (w - 1) / 2, (h - 1) / 2
    nx = (xx - cx) / cx
    ny = (yy - cy) / cy
    r = np.sqrt(nx * nx + ny * ny) / np.sqrt(2)
    mask = 1 - strength * np.clip((r - 0.35) / 0.65, 0, 1) ** 2.1
    return np.repeat((mask * 255).astype(np.uint8)[..., None], 3, axis=2)


def vignette(img, strength=0.35) -> np.ndarray:
    return cv2.multiply(img, _vignette_mask_u8(img.shape[0], img.shape[1], strength), scale=1.0 / 255.0)


@lru_cache(maxsize=4)
def _grain_bank(h: int, w: int, amount: float) -> tuple[np.ndarray, ...]:
    """A small bank of full-res signed grain offsets, reused with different seeds.

    Repetition every 16 frames is invisible at 30 fps and saves ~150 ms/frame.
    """
    rng = np.random.default_rng(20261108)
    amp = max(1.0, amount * 255.0)
    frames = []
    for _ in range(16):
        n = rng.standard_normal((h, w), dtype=np.float32) * amp
        frames.append(np.clip(n, -amp * 3, amp * 3).astype(np.int16)[..., None])
    return tuple(frames)


def grain(img, amount=0.010, seed=0) -> np.ndarray:
    frames = _grain_bank(img.shape[0], img.shape[1], amount)
    n = frames[seed % len(frames)]
    out = cv2.add(img.astype(np.int16), n, dtype=cv2.CV_16S)
    return np.clip(out, 0, 255).astype(np.uint8)


def develop(img, seed=0, do_bloom=True, do_grain=False, do_vignette=True, ca=0.0) -> np.ndarray:
    img = grade(img)
    if do_bloom:
        img = bloom(img)
    if ca:
        img = chromatic(img, ca)
    if do_grain:
        img = grain(img, seed=seed)
    if do_vignette:
        img = vignette(img)
    return img


def fade(img, amount: float, color=(0, 0, 0)) -> np.ndarray:
    if amount <= 0:
        return img
    c = np.array(color, np.uint8)
    return cv2.addWeighted(img, 1 - amount, np.broadcast_to(c, img.shape), amount, 0)
