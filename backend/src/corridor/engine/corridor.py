"""Corridor scores, stack vetoes, verdict badges and historical-twin aggregation."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np

from corridor.engine.calibration import CorridorLines
from corridor.engine.metrics import STACK_DIMS, STACKS

VETO_THRESHOLD = 20.0  # stack score at/below which the stack crossed the 85% Loss Floor


class Badge(StrEnum):
    ELITE_90_STANDARD = "ELITE_90_STANDARD"
    MIRAGE_WIN = "MIRAGE_WIN"
    UNLUCKY_LOSS = "UNLUCKY_LOSS"
    SYSTEMIC_COLLAPSE = "SYSTEMIC_COLLAPSE"
    MID_TABLE_STANDARD = "MID_TABLE_STANDARD"


def corridor_score(
    v: np.ndarray, v_best: np.ndarray, v_worst: np.ndarray, dims: Sequence[int] | None = None
) -> float:
    """C(v) = D_worst / (D_best + D_worst) × 100, over all dims or a stack's subset."""
    v, v_best, v_worst = (np.asarray(a, dtype=np.float64) for a in (v, v_best, v_worst))
    if dims is not None:
        idx = list(dims)
        v, v_best, v_worst = v[idx], v_best[idx], v_worst[idx]
    d_best = float(np.linalg.norm(v - v_best))
    d_worst = float(np.linalg.norm(v - v_worst))
    total = d_best + d_worst
    if total == 0.0:
        return 50.0
    return round(d_worst / total * 100.0, 1)


def veto_flag(stack_id: str) -> str:
    """'STACK_01' → 'STACK_01_WORK_RATE_VETO' (derived from the stack's score column)."""
    col = next(s.score_column for s in STACKS if s.stack_id == stack_id)
    return col.upper().removesuffix("_SCORE") + "_VETO"


@dataclass(frozen=True)
class CorridorEvaluation:
    overall: float
    stack_scores: dict[str, float]  # stack_id → score
    veto_flags: list[str] = field(default_factory=list)


def evaluate(v: np.ndarray, lines: CorridorLines) -> CorridorEvaluation:
    stack_scores = {
        sid: corridor_score(v, lines.v_best, lines.v_worst, dims)
        for sid, dims in STACK_DIMS.items()
    }
    return CorridorEvaluation(
        overall=corridor_score(v, lines.v_best, lines.v_worst),
        stack_scores=stack_scores,
        veto_flags=[veto_flag(sid) for sid, s in stack_scores.items() if s <= VETO_THRESHOLD],
    )


@dataclass(frozen=True)
class TwinsSummary:
    cohort_size: int
    empirical_win_pct: float
    empirical_draw_pct: float
    empirical_loss_pct: float
    expected_points: float


def summarize_twins(results: Sequence[str]) -> TwinsSummary:
    r = np.asarray(results)
    n = len(r)
    if n == 0:
        raise ValueError("no twins to summarize")
    w, d, lo = (float((r == x).mean()) for x in ("W", "D", "L"))
    return TwinsSummary(
        cohort_size=n,
        empirical_win_pct=round(w * 100, 1),
        empirical_draw_pct=round(d * 100, 1),
        empirical_loss_pct=round(lo * 100, 1),
        expected_points=round(3 * w + d, 2),
    )


def similarity_pct(l2_distance: float, lines: CorridorLines) -> float:
    """Distance as a share of the corridor width ‖v_best − v_worst‖: 0 → 100%, ≥ width → 0%."""
    width = float(np.linalg.norm(np.asarray(lines.v_best) - np.asarray(lines.v_worst)))
    return round(max(0.0, 1.0 - l2_distance / width) * 100.0, 1)


def classify(points: int, overall: float, n_vetoes: int, twin_win_pct: float) -> Badge:
    """Verdict badge. Order matters: scoreline-deception badges outrank profile badges."""
    if points == 3 and (twin_win_pct <= 22.0 or n_vetoes >= 2):
        return Badge.MIRAGE_WIN
    if points == 0 and twin_win_pct >= 75.0:
        return Badge.UNLUCKY_LOSS
    if overall >= 82.0 and twin_win_pct >= 88.0 and n_vetoes == 0:
        return Badge.ELITE_90_STANDARD
    if overall <= VETO_THRESHOLD or n_vetoes >= 2:
        return Badge.SYSTEMIC_COLLAPSE
    return Badge.MID_TABLE_STANDARD
