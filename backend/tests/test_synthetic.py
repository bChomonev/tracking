from collections import Counter

import numpy as np

from corridor.synthetic.generator import generate


def test_shape_and_determinism(dataset):
    assert len(dataset.matches) == 5 * 5 * 380
    assert len(dataset.performances) == 2 * len(dataset.matches)
    again = generate(seed=42)
    np.testing.assert_array_equal(again.raw_matrix(), dataset.raw_matrix())


def test_paired_metrics_mirror(dataset):
    for k in range(0, 200, 2):
        home, away = dataset.performances[k], dataset.performances[k + 1]
        assert home.match == away.match and home.is_home and not away.is_home
        assert home.metrics["npxg_conceded"] == away.metrics["npxg_created"]
        assert home.metrics["field_tilt_pct"] + away.metrics["field_tilt_pct"] == 100.0
        assert home.goals_for == away.goals_against


def test_results_are_plausible(dataset):
    c = Counter(dataset.results())
    draw_rate = c["D"] / sum(c.values())
    assert 0.18 < draw_rate < 0.30
    home = [p for p in dataset.performances if p.is_home]
    assert sum(p.result == "W" for p in home) > sum(p.result == "L" for p in home)
