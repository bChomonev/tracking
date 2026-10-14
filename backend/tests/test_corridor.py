import numpy as np
import pytest

from corridor.engine.corridor import (
    Badge,
    classify,
    corridor_score,
    evaluate,
    similarity_pct,
    summarize_twins,
    veto_flag,
)


def test_score_endpoints(lines):
    assert corridor_score(lines.v_best, lines.v_best, lines.v_worst) == 100.0
    assert corridor_score(lines.v_worst, lines.v_best, lines.v_worst) == 0.0
    mid = (lines.v_best + lines.v_worst) / 2
    assert corridor_score(mid, lines.v_best, lines.v_worst) == pytest.approx(50.0)


def test_stack_scores_and_vetoes(lines):
    v = np.array(lines.v_best, dtype=float)
    v[0:3] = lines.v_worst[0:3]  # collapse the Work Rate stack only
    e = evaluate(v, lines)
    assert e.stack_scores["STACK_01"] == 0.0
    assert e.stack_scores["STACK_03"] == 100.0
    assert e.veto_flags == ["STACK_01_WORK_RATE_VETO"]


def test_veto_flag_names():
    assert veto_flag("STACK_02") == "STACK_02_PROGRESSION_VETO"
    assert veto_flag("STACK_04") == "STACK_04_DEFENSIVE_VETO"


@pytest.mark.parametrize(
    ("points", "overall", "vetoes", "twin_win", "expected"),
    [
        (3, 45.0, 0, 20.0, Badge.MIRAGE_WIN),  # won, but twins win 20%
        (3, 45.0, 2, 50.0, Badge.MIRAGE_WIN),  # won through two collapsed stacks
        (0, 70.0, 0, 80.0, Badge.UNLUCKY_LOSS),
        (3, 85.0, 0, 90.0, Badge.ELITE_90_STANDARD),
        (3, 85.0, 1, 90.0, Badge.MID_TABLE_STANDARD),  # one veto blocks elite
        (0, 15.0, 1, 5.0, Badge.SYSTEMIC_COLLAPSE),
        (1, 40.0, 2, 30.0, Badge.SYSTEMIC_COLLAPSE),
        (1, 50.0, 0, 40.0, Badge.MID_TABLE_STANDARD),
    ],
)
def test_classify(points, overall, vetoes, twin_win, expected):
    assert classify(points, overall, vetoes, twin_win) is expected


def test_summarize_twins():
    s = summarize_twins(["W"] * 2 + ["D"] * 6 + ["L"] * 42)
    assert (s.empirical_win_pct, s.empirical_draw_pct, s.empirical_loss_pct) == (4.0, 12.0, 84.0)
    assert s.expected_points == 0.24
    with pytest.raises(ValueError):
        summarize_twins([])


def test_similarity_pct(lines):
    width = float(np.linalg.norm(lines.v_best - lines.v_worst))
    assert similarity_pct(0.0, lines) == 100.0
    assert similarity_pct(width / 2, lines) == 50.0
    assert similarity_pct(width * 2, lines) == 0.0


def test_score_predicts_outcomes(dataset, vectors, lines):
    """End-to-end sanity on synthetic data: higher corridor score → more wins."""
    scores = np.array([evaluate(v.astype(float), lines).overall for v in vectors])
    res = dataset.results()
    low, high = scores < 30, scores >= 70
    assert (res[low] == "L").mean() > 0.6
    assert (res[high] == "W").mean() > 0.6
