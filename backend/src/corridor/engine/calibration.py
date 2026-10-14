"""Solve the 90% Win Ceiling and 85% Loss Floor cohorts and their centroids.

Cohorts are defined on non-penalty xG difference (npxGD = npxg_created − npxg_conceded).
We fit P(win | npxGD) and P(loss | npxGD) with 1-D logistic regressions, then pick the
widest tail cohort whose *fitted* average outcome rate still meets the target:

* Win cohort  = npxGD ≥ t_win,  lowest t_win  with mean P(win)  over the cohort ≥ ``win_target``
* Loss cohort = npxGD ≤ t_loss, highest t_loss with mean P(loss) over the cohort ≥ ``loss_target``

Averaging fitted probabilities (rather than raw results) makes the cumulative rate monotone,
so the thresholds stay stable on small windows where a handful of results in the extreme
tail would otherwise swing them.
If fewer than ``min_cohort`` rows clear a threshold, the most extreme ``min_cohort`` rows
are used so the centroid is never averaged over a tiny sample.
"""

import warnings
from dataclasses import dataclass

import numpy as np

from corridor.engine.metrics import METRIC_KEYS, N_DIMS


@dataclass(frozen=True)
class CorridorLines:
    v_best: np.ndarray  # (12,) centroid of the win cohort (weighted-z space)
    v_worst: np.ndarray  # (12,) centroid of the loss cohort
    npxgd_win_threshold: float
    npxgd_loss_threshold: float
    win_cohort_size: int
    loss_cohort_size: int
    win_cohort_win_pct: float
    loss_cohort_loss_pct: float
    win_90_ceiling_raw: dict[str, float | None]  # per-metric medians of win cohort, for UI
    loss_85_floor_raw: dict[str, float | None]  # per-metric medians of loss cohort, for UI


def fit_logistic(x: np.ndarray, y: np.ndarray, iters: int = 50) -> tuple[float, float]:
    """Fit P(y=1|x) = σ(a + b·x) by Newton–Raphson. Returns (a, b)."""
    X = np.column_stack([np.ones_like(x), x])
    beta = np.zeros(2)
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-(X @ beta)))
        grad = X.T @ (y - p)
        hess = X.T @ (X * (p * (1 - p))[:, None]) + 1e-9 * np.eye(2)
        step = np.linalg.solve(hess, grad)
        beta += step
        if np.max(np.abs(step)) < 1e-10:
            break
    return float(beta[0]), float(beta[1])


def _solve_threshold(x: np.ndarray, hit: np.ndarray, target: float, upper: bool) -> float:
    a, b = fit_logistic(x, hit.astype(np.float64))
    if (b <= 0) if upper else (b >= 0):
        raise ValueError("npxGD is not predictive of the outcome; cannot solve corridor")
    order = np.argsort(-x if upper else x, kind="stable")  # most extreme first
    p = 1.0 / (1.0 + np.exp(-(a + b * x[order])))
    cum_rate = np.cumsum(p) / np.arange(1, len(p) + 1)  # monotone non-increasing
    meets = np.flatnonzero(cum_rate >= target)
    if meets.size == 0:
        raise ValueError(f"no tail cohort reaches the {target:.0%} target")
    return float(x[order][meets[-1]])


def _cohort(npxgd: np.ndarray, t: float, min_cohort: int, upper: bool) -> np.ndarray:
    mask = npxgd >= t if upper else npxgd <= t
    if mask.sum() >= min_cohort:
        return mask
    order = np.argsort(-npxgd if upper else npxgd, kind="stable")
    mask = np.zeros_like(mask)
    mask[order[:min_cohort]] = True
    return mask


def solve_corridor_lines(
    vectors: np.ndarray,
    raw: np.ndarray,
    npxgd: np.ndarray,
    results: np.ndarray,
    *,
    win_target: float = 0.90,
    loss_target: float = 0.85,
    min_cohort: int = 30,
) -> CorridorLines:
    vectors = np.asarray(vectors, dtype=np.float64)
    raw = np.asarray(raw, dtype=np.float64)
    npxgd = np.asarray(npxgd, dtype=np.float64)
    results = np.asarray(results)
    if vectors.ndim != 2 or vectors.shape[1] != N_DIMS or raw.shape != vectors.shape:
        raise ValueError("vectors and raw must both be (n, 12)")
    if len(npxgd) < 4 * min_cohort:
        raise ValueError(f"need at least {4 * min_cohort} performances, got {len(npxgd)}")

    t_win = _solve_threshold(npxgd, results == "W", win_target, upper=True)
    t_loss = _solve_threshold(npxgd, results == "L", loss_target, upper=False)
    if not t_loss < 0 < t_win:
        raise ValueError(f"degenerate corridor thresholds (t_loss={t_loss}, t_win={t_win})")

    win_mask = _cohort(npxgd, t_win, min_cohort, upper=True)
    loss_mask = _cohort(npxgd, t_loss, min_cohort, upper=False)
    return CorridorLines(
        v_best=vectors[win_mask].mean(axis=0),
        v_worst=vectors[loss_mask].mean(axis=0),
        npxgd_win_threshold=round(float(t_win), 2),
        npxgd_loss_threshold=round(float(t_loss), 2),
        win_cohort_size=int(win_mask.sum()),
        loss_cohort_size=int(loss_mask.sum()),
        win_cohort_win_pct=round(float((results[win_mask] == "W").mean()) * 100, 1),
        loss_cohort_loss_pct=round(float((results[loss_mask] == "L").mean()) * 100, 1),
        win_90_ceiling_raw=_medians(raw[win_mask]),
        loss_85_floor_raw=_medians(raw[loss_mask]),
    )


def _medians(raw: np.ndarray) -> dict[str, float | None]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN column = metric unavailable
        med = np.nanmedian(raw, axis=0)
    return {
        k: None if np.isnan(v) else round(float(v), 3)
        for k, v in zip(METRIC_KEYS, med, strict=True)
    }
