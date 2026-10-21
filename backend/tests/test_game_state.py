"""Game-state layer (D-051): shots split by the score at the time."""

import pytest

from corridor import proof
from corridor.analyst.facts import _game_state_facts
from corridor.ingest.fotmob import goal_times, state_minutes, state_profile
from corridor.profile import METRICS, STATE_KEYS, derive, team_profile


def _goal(time, is_home, overload=None):
    return {"type": "Goal", "time": time, "overloadTime": overload, "isHome": is_home}


def _match(events):
    return {"content": {"matchFacts": {"events": {"events": events}}}}


def _shot(team, minute, xg=0.1, x=95.0, y=34.0, inside=True, **kw):
    return {
        "teamId": team,
        "min": minute,
        "minAdded": kw.get("added"),
        "expectedGoals": xg,
        "x": x,
        "y": y,
        "isFromInsideBox": inside,
        "situation": kw.get("situation", "RegularPlay"),
        "isOwnGoal": kw.get("own_goal", False),
    }


def test_goal_times_credit_own_goals_to_the_benefiting_side_and_order_added_time():
    d = _match([_goal(60, False), _goal(45, True, overload=3), _goal(30, True)])
    assert goal_times(d) == [(30.0, True), (45.03, True), (60.0, False)]


def test_state_minutes_on_a_90_minute_clock():
    goals = [(30.0, True), (60.0, False), (90.05, True)]  # home lead, level, late winner
    home = state_minutes(goals, is_home=True)
    away = state_minutes(goals, is_home=False)
    assert home == pytest.approx({"level": 60.0, "ahead": 30.0, "behind": 0.0})
    assert away == pytest.approx({"level": 60.0, "ahead": 0.0, "behind": 30.0})
    assert state_minutes([], True) == {"level": 90.0, "ahead": 0.0, "behind": 0.0}


def test_state_profile_splits_shots_by_the_score_at_the_time():
    goals = [(30.0, True)]
    shots = [
        _shot(1, 10, xg=0.2),  # home, level
        _shot(1, 30, xg=0.3),  # the goal itself: still level when taken
        _shot(1, 50, xg=0.1, x=80.0, inside=False),  # home, ahead, from 25 m
        _shot(2, 70, xg=0.4),  # away, behind → conceded by home while ahead
        _shot(2, 20, xg=0.9, situation="Penalty"),  # excluded
        _shot(2, 80, xg=None, own_goal=True),  # excluded
    ]
    p = state_profile(shots, goals, team_id=1, is_home=True)
    assert p["level_minutes"] == 30 and p["ahead_minutes"] == 60 and p["behind_minutes"] == 0
    assert p["level_np_shots"] == 2 and p["level_npxg"] == pytest.approx(0.5)
    assert p["ahead_np_shots"] == 1 and p["ahead_shot_distance_sum_m"] == pytest.approx(25)
    assert p["ahead_np_shots_conceded"] == 1 and p["ahead_npxg_conceded"] == pytest.approx(0.4)
    assert p["level_np_shots_conceded"] == 0 and p["behind_np_shots"] == 0
    # Same shots from the away side's view.
    q = state_profile(shots, goals, team_id=2, is_home=False)
    assert q["behind_np_shots"] == 1 and q["behind_np_shots_conceded"] == 1


def test_derive_guards_short_states_and_few_shots():
    base = {"result": "W", "np_shots": 0, "shots_outside_box": 0, "shots_blocked": 0}
    base |= {"shot_distance_sum_m": 0.0, "np_shots_conceded": 0}
    base |= {"shot_distance_sum_m_conceded": 0.0}
    r = base | {
        "level_minutes": 45.0,
        "level_np_shots": 3,
        "level_npxg": 0.6,
        "level_shot_distance_sum_m": 60.0,
        "level_np_shots_conceded": 2,
        "level_npxg_conceded": 0.4,
        "ahead_minutes": 10.0,  # too short: everything None
        "ahead_np_shots": 5,
        "ahead_npxg": 1.0,
        "ahead_shot_distance_sum_m": 50.0,
        "ahead_np_shots_conceded": 0,
        "ahead_npxg_conceded": 0.0,
        "behind_minutes": 35.0,  # long enough but only 2 shots: rates yes, per-shot no
        "behind_np_shots": 2,
        "behind_npxg": 0.2,
        "behind_shot_distance_sum_m": 30.0,
        "behind_np_shots_conceded": 0,
        "behind_npxg_conceded": 0.0,
    }
    d = derive(r)
    assert d["level_npxg_p90"] == pytest.approx(1.2) and d["level_shots_p90"] == pytest.approx(6)
    assert d["level_npxg_per_shot"] == pytest.approx(0.2) and d["level_shot_distance_m"] == 20
    assert d["level_npxg_per_shot_conceded"] is None  # 2 shots faced < 3
    assert d["level_npxg_p90_conceded"] == pytest.approx(0.8)
    assert d["ahead_npxg_p90"] is None and d["ahead_npxg_per_shot"] is None
    assert d["behind_shots_p90"] == pytest.approx(90 * 2 / 35)
    assert d["behind_npxg_per_shot"] is None and d["behind_shot_distance_m"] is None


def test_state_metrics_are_registered_but_out_of_the_share_and_tiers():
    assert len(STATE_KEYS) == 21 and "level_npxg_per_shot" in STATE_KEYS
    assert all(m.stack == "state" for m in METRICS if m.key in STATE_KEYS)
    assert proof.STATE <= proof.SHARE_EXCLUDED
    assert {m.key for m in proof.FOTMOB_METRICS} >= STATE_KEYS  # still tested for impact


def _row(team, opp, mid, gf, ga, level_xg):
    return {
        "match_id": mid,
        "kickoff_utc": f"2026-09-{mid % 28 + 1:02d}T15:00:00Z",
        "team": team,
        "opponent": opp,
        "is_home": True,
        "goals_for": gf,
        "goals_against": ga,
        "result": "W" if gf > ga else "D" if gf == ga else "L",
        "np_shots": 0,
        "shots_outside_box": 0,
        "shots_blocked": 0,
        "shot_distance_sum_m": 0.0,
        "np_shots_conceded": 0,
        "shot_distance_sum_m_conceded": 0.0,
        "possession_pct": 50.0,
        "level_minutes": 60.0,
        "level_np_shots": 6,
        "level_npxg": level_xg,
        "level_shot_distance_sum_m": 100.0,
        "level_np_shots_conceded": 4,
        "level_npxg_conceded": 0.5,
        "ahead_minutes": 30.0 if gf > ga else 0.0,
        "ahead_np_shots": 1,
        "ahead_npxg": 0.1,
        "ahead_shot_distance_sum_m": 15.0,
        "ahead_np_shots_conceded": 1,
        "ahead_npxg_conceded": 0.1,
        "behind_minutes": 0.0 if gf > ga else 30.0,
        "behind_np_shots": 1,
        "behind_npxg": 0.1,
        "behind_shot_distance_sum_m": 15.0,
        "behind_np_shots_conceded": 1,
        "behind_npxg_conceded": 0.1,
    }


def test_profile_ranks_state_metrics_and_reports_minutes_context():
    rows = []
    for k in range(4):
        rows += [_row("A", "B", k, 2, 0, 1.2), _row("B", "A", k, 0, 2, 0.4)]
    prof = team_profile(rows, "A")
    m = {x["key"]: x for x in prof["metrics"]}
    assert m["level_npxg_p90"]["value"] == pytest.approx(1.8) and m["level_npxg_p90"]["rank"] == 1
    assert "behind_npxg_p90" not in m  # A was never behind for 20+ minutes
    assert any(s["id"] == "state" and s["score"] is not None for s in prof["stacks"])
    ctx = prof["context"]["game_state_minutes"]
    assert ctx["ahead"]["team_pct"] == pytest.approx(100 * 30 / 90, abs=0.1)
    assert ctx["ahead"]["rank_most_time"] == 1 and ctx["behind"]["team_pct"] == 0
    assert prof["matches"][0]["level_minutes"] == 60.0
    from corridor.best_line import build_line, compare

    line = build_line(rows, "prev", rows, side="best")
    compare(prof, line, uncounted=STATE_KEYS)
    assert prof["best_line"]["metrics_compared"] == sum(
        1 for x in prof["metrics"] if "best_line" in x and x["key"] not in STATE_KEYS
    )
    facts = _game_state_facts(prof)
    assert facts["when level"]["chance_quality_created_npxg_per_90"]["typical_match"] == 1.8
    assert facts["when behind"]["chance_quality_created_npxg_per_90"] is None
