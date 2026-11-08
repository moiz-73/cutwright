from cutwright import motion


def test_easing_is_clamped_and_monotonic():
    for fn in (motion.out_expo, motion.out_cubic, motion.out_quint, motion.in_out_cubic):
        vals = [fn(i / 20) for i in range(21)]
        assert all(0.0 <= v <= 1.0 for v in vals)
        assert all(b >= a - 1e-9 for a, b in zip(vals, vals[1:]))
        assert abs(fn(1.0) - 1.0) < 1e-6


def test_late_times_do_not_explode():
    assert motion.out_expo(99) == 1.0
    assert motion.clamp(-3) == 0.0
    assert 0.0 <= motion.spring(10.0) <= 1.01


def test_window_fades():
    assert motion.window(0.5, 0.0, 1.0) == 1.0
    assert motion.window(1.5, 0.0, 1.0) == 0.0
    assert 0.0 < motion.window(0.05, 0.0, 1.0, attack=0.1) < 1.0
