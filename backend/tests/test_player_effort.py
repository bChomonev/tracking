import numpy as np
import pytest

from corridor.engine.player_effort import (
    EffortStatus,
    classify_effort,
    effort_scores,
    percentile_ranks,
)
from corridor.synthetic.generator import generate_player_cohort


def test_percentile_ranks_midrank_and_nan():
    cohort = np.array([1.0, 2.0, 3.0, 4.0, np.nan])
    np.testing.assert_allclose(percentile_ranks(np.array([0.0, 2.0, 5.0]), cohort), [0, 37.5, 100])
    assert np.isnan(percentile_ranks(np.array([np.nan]), cohort)[0])


def test_effort_ordering_and_spread():
    cohort = generate_player_cohort(2000, seed=42)
    scores = effort_scores(cohort, cohort)
    assert scores.min() < 15 and scores.max() > 85  # re-ranking keeps the full 0-100 spread
    tireless = np.percentile(cohort, 99, axis=0)
    idle = np.percentile(cohort, 1, axis=0)
    assert classify_effort(effort_scores(tireless, cohort)[0]) is EffortStatus.WORKHORSE_ELITE
    assert classify_effort(effort_scores(idle, cohort)[0]) is EffortStatus.PASSENGER_ALERT


def test_missing_physical_falls_back_to_events():
    cohort = generate_player_cohort(1000, seed=7, physical_missing_rate=0.3)
    player = np.array([np.nan, np.nan, *np.percentile(cohort[:, 2:], 99, axis=0)])
    assert effort_scores(player, cohort)[0] > 85


@pytest.mark.parametrize(
    ("score", "status"),
    [
        (85.0, EffortStatus.WORKHORSE_ELITE),
        (84.9, EffortStatus.STANDARD_SHIFT),
        (15.0, EffortStatus.STANDARD_SHIFT),
        (14.9, EffortStatus.PASSENGER_ALERT),
    ],
)
def test_classify_boundaries(score, status):
    assert classify_effort(score) is status
