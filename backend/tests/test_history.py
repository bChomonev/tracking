import json

from corridor import predict as P
from corridor import proof
from corridor.leagues import LEAGUES


def _fm(mid, team, opp, is_home, gf, ga, **extra):
    return {
        "match_id": mid,
        "team": team,
        "opponent": opp,
        "is_home": is_home,
        "kickoff_utc": f"2026-10-{mid:02d}T15:00:00.000Z",
        "goals_for": gf,
        "goals_against": ga,
        "xg": 1.2,
        "xg_conceded": 0.8,
        "npxg": 1.0,
        "npxg_conceded": 0.7,
        "passes_conceded": 400,
        "tackles": 10,
        "interceptions": 6,
        "fouls": 4,
        "box_touches": 24,
        "box_touches_conceded": 12,
    } | extra


def test_core_row_keys_a_fotmob_match_like_the_profile_metrics():
    r = proof.core_row(_fm(3, "A", "B", True, 2, 1))
    assert r["kickoff"] == "2026-10-03 15:00:00" and r["result"] == "W"
    assert r["ppda"] == 20.0  # 400 opponent passes / 20 defensive actions
    assert r["npxg_conceded"] == 0.7 and r["box_touches_conceded"] == 12
    assert set(proof.CORE_KEYS) <= set(r)


def test_season_matches_pairs_the_rows_and_adds_the_fixtures_still_to_play(tmp_path, monkeypatch):
    rows = [
        _fm(1, "A", "B", True, 2, 1),
        _fm(1, "B", "A", False, 1, 2),
        _fm(2, "C", "D", True, 0, 0, npxg=None),  # no xG yet: not a played match
        _fm(2, "D", "C", False, 0, 0),
    ]
    (tmp_path / "team_matches.json").write_text(json.dumps(rows))
    monkeypatch.setattr(P, "processed_dir", lambda s, lg: tmp_path)
    fixtures = [
        {
            "id": "1",
            "status": {"finished": True, "utcTime": "2026-10-01T15:00:00Z"},
            "home": {"name": "A"},
            "away": {"name": "B"},
        },
        {
            "id": 9,
            "status": {"finished": False, "utcTime": "2026-11-21T12:30:00Z"},
            "home": {"name": "A"},
            "away": {"name": "D"},
        },
        {
            "id": 10,
            "status": {"finished": False, "cancelled": True, "utcTime": "2026-11-22T12:30:00Z"},
            "home": {"name": "B"},
            "away": {"name": "C"},
        },
    ]
    ms = P.season_matches(2026, LEAGUES["pl"], fixtures=fixtures)
    assert [(m["id"], m["played"]) for m in ms] == [("1", True), ("9", False)]
    m = ms[0]
    assert m["home"] == "A" and m["result"] == "H" and (m["hg"], m["ag"]) == (2, 1)
    assert m["rows"]["away"]["team"] == "B" and m["rows"]["home"]["npxg"] == 1.0
    assert ms[1]["kickoff"] == "2026-11-21 12:30:00" and ms[1]["away"] == "D"


def test_migrate_log_moves_old_ids_onto_the_same_fixture():
    from corridor.scripts.predictions import migrate_log

    current = [
        {
            "id": "5795512",
            "home": "Manchester United",
            "away": "Aston Villa",
            "kickoff": "2026-11-08 16:30:00",
        },
        {
            "id": "5795600",
            "home": "Liverpool",
            "away": "Manchester United",
            "kickoff": "2026-11-22 16:30:00",
        },
    ]
    log = {
        "31280": {
            "home": "Manchester United",
            "away": "Aston Villa",
            "kickoff": "2026-11-08 16:30:00",
            "p": [0.4, 0.3, 0.3],
        },
        "5795600": {
            "home": "Liverpool",
            "away": "Manchester United",
            "kickoff": "2026-11-22 16:30:00",
            "p": [0.5, 0.2, 0.3],
        },
        "31999": {"home": "X", "away": "Y", "kickoff": "2026-11-08 16:30:00", "p": [0.4, 0.3, 0.3]},
    }
    assert migrate_log(log, current) == 1
    assert set(log) == {"5795512", "5795600", "31999"}
    assert log["5795512"]["p"] == [0.4, 0.3, 0.3]
