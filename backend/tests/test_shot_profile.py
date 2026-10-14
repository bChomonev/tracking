import pytest

from corridor.analyst.writer import _drop_flagged
from corridor.ingest.fotmob import shot_profile
from corridor.profile import derive


def _shot(team=1, x=95.0, y=34.0, situation="RegularPlay", event="Miss", **kw):
    return {
        "teamId": team,
        "x": x,
        "y": y,
        "situation": situation,
        "eventType": event,
        "expectedGoals": kw.pop("xg", 0.1),
        "isFromInsideBox": kw.pop("inside", True),
        "isBlocked": kw.pop("blocked", False),
        "isOwnGoal": kw.pop("own_goal", False),
        "shotType": kw.pop("shot_type", "RightFoot"),
    }


def test_shot_profile_excludes_penalties_and_own_goals():
    shots = [
        _shot(x=95, y=34, xg=0.2, event="Goal"),
        _shot(x=80, y=34, inside=False, blocked=True, xg=0.03),
        _shot(situation="FromCorner", shot_type="Header", xg=0.15, event="Goal"),
        _shot(situation="FastBreak", xg=0.4),
        _shot(situation="Penalty", xg=0.79, event="Goal"),
        _shot(x=5, own_goal=True, event="Goal", xg=None),  # credited to team 1's opponent
        _shot(team=2, xg=0.5),
    ]
    p = shot_profile(shots, 1)
    assert p["np_shots"] == 4
    assert p["shots_outside_box"] == 1 and p["shots_blocked"] == 1 and p["shots_headed"] == 1
    assert p["shot_distance_sum_m"] == pytest.approx(10 + 25 + 10 + 10)
    assert p["npxg_set_piece"] == pytest.approx(0.15)
    assert p["npxg_fast_break"] == pytest.approx(0.4)
    assert (p["goals_open_play"], p["goals_set_piece"], p["goals_penalty"]) == (1, 1, 1)


def test_derive_shot_rates_and_empty_shot_map():
    base = {"result": "D", "np_shots": 4, "shots_outside_box": 1, "shots_blocked": 2}
    d = derive(
        base
        | {"shot_distance_sum_m": 60.0, "np_shots_conceded": 0, "shot_distance_sum_m_conceded": 0.0}
    )
    assert d["shot_distance_m"] == 15 and d["outside_box_shot_pct"] == 25
    assert d["blocked_shot_pct"] == 50 and d["shot_distance_conceded_m"] is None


def test_critic_fallback_drops_only_interpretations_and_player_notes():
    analysis = {
        "findings": [{"interpretation": "a"}, {"interpretation": "b"}],
        "players": [{"name": "Kobbie Mainoo"}, {"name": "Bruno Fernandes"}],
    }
    assert _drop_flagged(analysis, [{"location": "Finding 2 interpretation"}])
    assert analysis["findings"][1]["interpretation"] is None
    assert analysis["findings"][0]["interpretation"] == "a"
    assert _drop_flagged(analysis, [{"location": "player Kobbie Mainoo"}])
    assert [p["name"] for p in analysis["players"]] == ["Bruno Fernandes"]
    assert not _drop_flagged(analysis, [{"location": "headline"}])
    assert not _drop_flagged(analysis, [{"location": "finding 1 text"}])
    assert not _drop_flagged(analysis, [{"location": "finding 9 interpretation"}])
