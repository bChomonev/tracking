import numpy as np
import pytest

from corridor.engine.calibration import solve_corridor_lines
from corridor.engine.metrics import METRIC_KEYS
from corridor.engine.vectorizer import fit_scales, vectorize


def test_cohorts_meet_targets(lines):
    assert lines.win_cohort_win_pct >= 90.0
    assert lines.loss_cohort_loss_pct >= 85.0
    assert lines.npxgd_loss_threshold < 0 < lines.npxgd_win_threshold
    assert lines.win_cohort_size >= 30 and lines.loss_cohort_size >= 30


def test_centroids_are_ordered(lines):
    # The win centroid should beat the loss centroid on the headline xG dimensions.
    i_created, i_conceded = METRIC_KEYS.index("npxg_created"), METRIC_KEYS.index("npxg_conceded")
    assert lines.v_best[i_created] > lines.v_worst[i_created]
    assert lines.v_best[i_conceded] > lines.v_worst[i_conceded]  # direction-flipped: higher=better
    assert lines.win_90_ceiling_raw["npxg_created"] > lines.loss_85_floor_raw["npxg_created"]


def test_deterministic(dataset, vectors, lines):
    again = solve_corridor_lines(vectors, dataset.raw_matrix(), dataset.npxgd(), dataset.results())
    np.testing.assert_array_equal(again.v_best, lines.v_best)


def test_threshold_matches_empirical_cohort(dataset, lines):
    """The fitted threshold should sit near where the empirical cohort crosses 90%."""
    x, r = dataset.npxgd(), dataset.results()
    empirical = (r[x >= lines.npxgd_win_threshold] == "W").mean()
    assert 0.85 <= empirical <= 0.97


def test_small_window_still_solves(dataset):
    sub = slice(0, 4000)
    raw = dataset.raw_matrix()[sub]
    small = solve_corridor_lines(
        vectorize(raw, fit_scales(raw)), raw, dataset.npxgd()[sub], dataset.results()[sub]
    )
    assert small.win_cohort_size >= 30 and small.loss_cohort_size >= 30


def test_rejects_tiny_and_unpredictive_samples(dataset, vectors):
    raw = dataset.raw_matrix()
    with pytest.raises(ValueError, match="need at least"):
        solve_corridor_lines(vectors[:50], raw[:50], dataset.npxgd()[:50], dataset.results()[:50])
    rng = np.random.default_rng(42)
    noise = rng.normal(0, 1, len(vectors))  # npxGD unrelated to results
    with pytest.raises(ValueError):
        solve_corridor_lines(vectors, raw, noise, rng.permutation(dataset.results()))
