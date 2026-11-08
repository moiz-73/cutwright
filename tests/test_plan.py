from cutwright.edit import _merge


def test_merge_joins_close_spans():
    assert _merge([(0, 1), (1.02, 2)], gap=0.08) == [(0, 2)]


def test_merge_keeps_gaps():
    assert _merge([(0, 1), (2, 3)], gap=0.08) == [(0, 1), (2, 3)]


def test_merge_handles_empty_and_unsorted():
    assert _merge([]) == []
    assert _merge([(3, 4), (0, 1)]) == [(0, 1), (3, 4)]


def test_clamp_time_keeps_samples_inside_a_scene():
    from cutwright.comps import LaunchFilm, STARTS, DUR

    f = LaunchFilm()
    lo, hi = STARTS["hero"], STARTS["hero"] + DUR["hero"]
    assert lo < f.clamp_time(lo, lo) < hi
    # a sub-frame sample before the cut must not fall into the previous scene
    assert f.clamp_time(lo - 0.4, lo) >= lo
    assert f.clamp_time(hi + 0.4, hi - 0.001) <= hi
