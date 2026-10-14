"""Write-path persistence: loading performances, calibrating corridors, twin lookups."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import insert, select, text, update
from sqlalchemy.orm import Session

from corridor.db.models import BenchmarkCorridor, Match, Team, TeamMatchPerformance
from corridor.engine.calibration import CorridorLines, solve_corridor_lines
from corridor.engine.corridor import evaluate
from corridor.engine.metrics import METRIC_KEYS, STACKS, TEAM_METRICS
from corridor.engine.vectorizer import MetricScales, fit_scales, vectorize
from corridor.synthetic.generator import SyntheticDataset

_METRIC_COLS = [getattr(TeamMatchPerformance, k) for k in METRIC_KEYS]


def load_synthetic(session: Session, ds: SyntheticDataset) -> None:
    """Bulk-insert a synthetic dataset as HISTORICAL matches (no vectors yet)."""
    team_ids = session.scalars(
        insert(Team).returning(Team.id, sort_by_parameter_order=True),
        [
            {
                "external_id": t.external_id,
                "name": t.name,
                "short_code": t.short_code,
                "league_code": t.league_code,
                "is_benchmark_cohort": True,
            }
            for t in ds.teams
        ],
    ).all()
    match_ids = session.scalars(
        insert(Match).returning(Match.id, sort_by_parameter_order=True),
        [
            {
                "external_id": m.external_id,
                "competition_code": m.competition_code,
                "season": m.season,
                "kickoff_utc": m.kickoff_utc,
                "audit_status": "HISTORICAL",
                "home_team_id": team_ids[m.home],
                "away_team_id": team_ids[m.away],
                "home_goals": m.home_goals,
                "away_goals": m.away_goals,
            }
            for m in ds.matches
        ],
    ).all()
    session.execute(
        insert(TeamMatchPerformance),
        [
            {
                "match_id": match_ids[p.match],
                "team_id": team_ids[p.team],
                "opponent_id": team_ids[p.opponent],
                "kickoff_utc": ds.matches[p.match].kickoff_utc,
                "is_home": p.is_home,
                "result": p.result,
                "points": p.points,
                "goals_for": p.goals_for,
                "goals_against": p.goals_against,
                "possession_pct": p.possession_pct,
                **{k: None if np.isnan(v) else round(float(v), 3) for k, v in p.metrics.items()},
            }
            for p in ds.performances
        ],
    )


def _float_or_nan(rows: Sequence[Sequence]) -> np.ndarray:
    return np.array([[np.nan if v is None else float(v) for v in r] for r in rows])


@dataclass(frozen=True)
class CalibrationResult:
    corridor_id: int
    scales: MetricScales
    lines: CorridorLines
    sample_size: int
    rows_vectorized: int


def calibrate(
    session: Session, *, window_end: datetime, window_days: int = 365, label: str | None = None
) -> CalibrationResult:
    """Fit scales + corridor lines on the trailing window, activate them, and re-vectorize
    *every* stored performance so all vectors (and twin distances) share one scale."""
    window_start = window_end - timedelta(days=window_days)
    in_window = session.execute(
        select(*_METRIC_COLS, TeamMatchPerformance.result).where(
            TeamMatchPerformance.kickoff_utc >= window_start,
            TeamMatchPerformance.kickoff_utc < window_end,
        )
    ).all()
    raw = _float_or_nan([r[:-1] for r in in_window])
    results = np.array([r[-1] for r in in_window])
    scales = fit_scales(raw)
    vectors = vectorize(raw, scales)
    i_for, i_against = METRIC_KEYS.index("npxg_created"), METRIC_KEYS.index("npxg_conceded")
    lines = solve_corridor_lines(vectors, raw, raw[:, i_for] - raw[:, i_against], results)

    means, stds = scales.to_dicts()
    session.execute(update(BenchmarkCorridor).values(is_active=False))
    corridor = BenchmarkCorridor(
        window_label=label or f"{window_end:%Y-%m-%d}-ROLLING-{window_days}D",
        window_start_utc=window_start,
        window_end_utc=window_end,
        sample_matches_count=len(in_window) // 2,
        metric_means=means,
        metric_stds=stds,
        metric_weights={m.key: m.weight for m in TEAM_METRICS},
        calibration={
            "method": "logistic_cohort_mean",
            "npxgd_win_threshold": lines.npxgd_win_threshold,
            "npxgd_loss_threshold": lines.npxgd_loss_threshold,
            "win_cohort_size": lines.win_cohort_size,
            "loss_cohort_size": lines.loss_cohort_size,
            "win_cohort_win_pct": lines.win_cohort_win_pct,
            "loss_cohort_loss_pct": lines.loss_cohort_loss_pct,
        },
        win_90_ceiling_raw=lines.win_90_ceiling_raw,
        loss_85_floor_raw=lines.loss_85_floor_raw,
        v_best_centroid=lines.v_best.astype(np.float16),
        v_worst_centroid=lines.v_worst.astype(np.float16),
        is_active=True,
    )
    session.add(corridor)
    session.flush()

    n = revectorize_all(session, corridor.id, scales, lines)
    return CalibrationResult(corridor.id, scales, lines, len(in_window), n)


def revectorize_all(
    session: Session, corridor_id: int, scales: MetricScales, lines: CorridorLines
) -> int:
    rows = session.execute(select(TeamMatchPerformance.id, *_METRIC_COLS)).all()
    ids = [r[0] for r in rows]
    vectors = vectorize(_float_or_nan([r[1:] for r in rows]), scales)
    updates = []
    for pid, v in zip(ids, vectors, strict=True):
        e = evaluate(v.astype(np.float64), lines)
        updates.append(
            {
                "id": pid,
                "stats_vector": v,
                "corridor_version_id": corridor_id,
                "overall_corridor_score": e.overall,
                **{s.score_column: e.stack_scores[s.stack_id] for s in STACKS},
            }
        )
    session.execute(update(TeamMatchPerformance), updates)
    return len(updates)


@dataclass(frozen=True)
class Twin:
    performance_id: int
    match_id: int
    team_id: int
    result: str
    l2_distance: float


TWINS_SQL = text(
    """
    SELECT id, match_id, team_id, result, stats_vector <-> CAST(:v AS halfvec(12)) AS dist
    FROM team_match_performances
    WHERE stats_vector IS NOT NULL
      AND kickoff_utc < :before
      AND match_id <> :exclude_match_id
    ORDER BY stats_vector <-> CAST(:v AS halfvec(12))
    LIMIT :k
    """
)


def find_twins(
    session: Session,
    vector: np.ndarray,
    *,
    before: datetime,
    exclude_match_id: int,
    k: int = 50,
    ef_search: int = 200,
) -> list[Twin]:
    """k nearest historical performances, strictly before ``before`` and excluding both
    rows of the audited match. Uses HNSW with iterative scan so the filter can't starve k."""
    session.execute(text(f"SET LOCAL hnsw.ef_search = {int(ef_search)}"))
    session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
    vec = "[" + ",".join(f"{float(x):.4f}" for x in np.asarray(vector)) + "]"
    rows = session.execute(
        TWINS_SQL, {"v": vec, "before": before, "exclude_match_id": exclude_match_id, "k": k}
    ).all()
    return [Twin(r[0], r[1], r[2], r[3], float(r[4])) for r in rows]
