import numpy as np
from cutwright import fx


def _img():
    rng = np.random.default_rng(0)
    return rng.integers(0, 256, (96, 128, 3), dtype=np.uint8)


def test_grade_preserves_shape_and_dtype():
    out = fx.grade(_img())
    assert out.shape == (96, 128, 3) and out.dtype == np.uint8


def test_vignette_darkens_corners_more_than_centre():
    img = np.full((96, 128, 3), 200, np.uint8)
    out = fx.vignette(img, 0.4)
    assert out[0, 0, 0] < out[48, 64, 0]


def test_bloom_returns_valid_image():
    out = fx.bloom(_img())
    assert out.dtype == np.uint8 and out.shape == (96, 128, 3)


def test_develop_runs():
    out = fx.develop(_img(), seed=3)
    assert out.shape == (96, 128, 3)
