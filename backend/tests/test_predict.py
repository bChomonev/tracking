import numpy as np

from corridor import predict as P


def _row(team, gf, ga, npxg, npxga):
    return {
        "team": team,
        "kickoff": "x",
        "goals_for": gf,
        "goals_against": ga,
        "us_npxg": npxg,
        "us_npxga": npxga,
        "ppda": 10.0,
        "deep_completions": 6,
        "deep_allowed": 6,
    }


def _match(i, season, home, away, hg, ag, hx, ax):
    return {
        "id": str(i),
        "season": season,
        "kickoff": f"{season}-09-{1 + i % 28:02d} 15:00:00",
        "home": home,
        "away": away,
        "played": True,
        "hg": hg,
        "ag": ag,
        "result": "H" if hg > ag else "D" if hg == ag else "A",
        "rows": {"home": _row(home, hg, ag, hx, ax), "away": _row(away, ag, hg, ax, hx)},
    }


def test_features_use_only_matches_before_kickoff():
    # Strong team S keeps beating W; one freak result must not leak into its own features.
    ms = [_match(i, 2020, "S", "W", 3, 0, 2.5, 0.4) for i in range(10)]
    ms.append(_match(10, 2020, "S", "W", 0, 5, 0.1, 4.0))
    scored, _ = P.walk(ms, P.Params(half_life=4, adjust=False))
    before = [m for m in scored if m["id"] == "10"][0]["x"]
    assert before["xg_diff"] > 1.5  # still the strong-team rating from earlier matches


def test_rps_and_score():
    assert P.rps([1, 0, 0], "H") == 0
    assert P.rps([0, 0, 1], "H") == 1
    assert abs(P.rps([0.5, 0.3, 0.2], "D") - (0.25 + 0.04) / 2) < 1e-12
    s = P.score(np.array([[0.6, 0.3, 0.1], [0.2, 0.3, 0.5]]), ["H", "A"])
    assert s["hit_rate"] == 1.0 and s["n"] == 2


def test_simulation_is_seeded_and_sane():
    table = {
        "A": {"points": 10, "gd": 5},
        "B": {"points": 0, "gd": -5},
        "C": {"points": 5, "gd": 0},
        "D": {"points": 4, "gd": 0},
    }
    fx = [{"home": "A", "away": "B"}, {"home": "C", "away": "D"}]
    probs = np.array([[1.0, 0.0, 0.0], [0.4, 0.3, 0.3]])
    s1 = P.simulate(table, fx, probs, n=2000)
    s2 = P.simulate(table, fx, probs, n=2000)
    assert s1 == s2
    assert s1["A"]["points"] == 13 and s1["A"]["title"] == 1.0
    assert abs(sum(r["title"] for r in s1.values()) - 1) < 1e-9


def test_next_round_is_one_window_from_the_next_kickoff():
    from datetime import datetime

    fx = [
        {"id": "1", "played": True, "kickoff": "2026-10-10 14:00:00"},
        {"id": "2", "played": False, "kickoff": "2026-10-17 14:00:00"},
        {"id": "3", "played": False, "kickoff": "2026-10-19 19:00:00"},
        {"id": "4", "played": False, "kickoff": "2026-10-31 14:00:00"},
    ]
    got = P.next_round(fx, datetime(2026, 10, 15, 12))
    assert [m["id"] for m in got] == ["2", "3"]
