"""Position-adjusted Player Effort & Passenger Index.

Each player's per-90 rates are ranked against their positional cohort. The composite is
50% physical (distance, sprints) + 50% event work rate (recoveries, duels, line-breaking
actions), and the composite itself is then re-ranked within the cohort — averaging
percentiles compresses toward 50, so classifying the raw average would almost never
reach the 85th-percentile Workhorse bar.

Players without physical tracking are scored on event work rate alone.
"""

import warnings
from enum import StrEnum

import numpy as np

PHYSICAL_KEYS = ("distance_per_90_km", "sprints_per_90")
EVENT_KEYS = ("ball_recoveries_per_90", "duels_contested_per_90", "line_breaking_actions_per_90")
EFFORT_KEYS = PHYSICAL_KEYS + EVENT_KEYS
POSITION_GROUPS = ("FWD", "MID", "FB", "CB")  # GK is not effort-audited
MIN_MINUTES = 20


class EffortStatus(StrEnum):
    WORKHORSE_ELITE = "WORKHORSE_ELITE"
    STANDARD_SHIFT = "STANDARD_SHIFT"
    PASSENGER_ALERT = "PASSENGER_ALERT"


def percentile_ranks(values: np.ndarray, cohort: np.ndarray) -> np.ndarray:
    """Mid-rank percentile (share below + half of ties) of each value within ``cohort``.

    NaNs in the cohort are ignored; NaN values map to NaN.
    """
    values = np.asarray(values, dtype=np.float64)
    c = np.sort(cohort[~np.isnan(cohort)])
    if c.size == 0:
        return np.full(values.shape, np.nan)
    below = np.searchsorted(c, values, side="left")
    at_or_below = np.searchsorted(c, values, side="right")
    pct = (below + 0.5 * (at_or_below - below)) / c.size * 100.0
    return np.where(np.isnan(values), np.nan, pct)


def _composites(rows: np.ndarray, cohort: np.ndarray) -> np.ndarray:
    pct = np.column_stack(
        [percentile_ranks(rows[:, j], cohort[:, j]) for j in range(len(EFFORT_KEYS))]
    )
    n_phys = len(PHYSICAL_KEYS)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN physical row
        phys = np.nanmean(pct[:, :n_phys], axis=1)
        event = np.nanmean(pct[:, n_phys:], axis=1)
    return np.where(np.isnan(phys), event, 0.5 * phys + 0.5 * event)


def effort_scores(players: np.ndarray, cohort: np.ndarray) -> np.ndarray:
    """Effort Corridor Scores (0–100) for ``players`` (n, 5) against a positional ``cohort``."""
    players = np.atleast_2d(np.asarray(players, dtype=np.float64))
    cohort = np.atleast_2d(np.asarray(cohort, dtype=np.float64))
    cohort_comp = _composites(cohort, cohort)
    return np.round(percentile_ranks(_composites(players, cohort), cohort_comp), 1)


def classify_effort(score: float) -> EffortStatus:
    if score >= 85.0:
        return EffortStatus.WORKHORSE_ELITE
    if score < 15.0:
        return EffortStatus.PASSENGER_ALERT
    return EffortStatus.STANDARD_SHIFT
