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


def test_form_is_recent_minus_level_and_never_sees_its_own_match():
    # S dominates for 10 matches, then has three poor ones: the short ratings fall faster
    # than the long ones, so form_diff turns negative before the 14th match. The 14th
    # match's own result must not be in its features.
    ms = [_match(i, 2020, "S", "W", 3, 0, 2.5, 0.4) for i in range(10)]
    ms += [_match(10 + i, 2020, "S", "W", 0, 1, 0.6, 1.4) for i in range(3)]
    ms.append(_match(13, 2020, "S", "W", 5, 0, 4.0, 0.1))
    p = P.Params(half_life=24, adjust=False, form_half_life=2, features="xg+goals+lines+form")
    scored, R = P.walk(ms, p)
    x = [m for m in scored if m["id"] == "13"][0]["x"]
    assert x["form_diff"] < -0.5 and x["xg_diff"] > 1.0  # still a strong side, off form
    assert x["h_form_npxg"] < x["h_npxg"]
    early = [m for m in scored if m["id"] == "5"][0]["x"]
    assert abs(early["form_diff"]) < 0.3  # steady run: recent ≈ level
    # Without form_half_life the form features are simply absent.
    plain, _ = P.walk(ms, P.Params(half_life=24, adjust=False))
    assert "form_diff" not in plain[-1]["x"]
    assert R.form is not None and R.form.alpha > R.alpha


def test_rps_and_score():
    assert P.rps([1, 0, 0], "H") == 0
    assert P.rps([0, 0, 1], "H") == 1
    assert abs(P.rps([0.5, 0.3, 0.2], "D") - (0.25 + 0.04) / 2) < 1e-12
    s = P.score(np.array([[0.6, 0.3, 0.1], [0.2, 0.3, 0.5]]), ["H", "A"])
    assert s["hit_rate"] == 1.0 and s["n"] == 2
    # Favourite lost = the other side won; a draw is not a loss (1X / X2).
    s = P.score(np.array([[0.6, 0.3, 0.1], [0.2, 0.3, 0.5], [0.45, 0.3, 0.25]]), ["D", "H", "A"])
    assert s["hit_rate"] == 0 and abs(s["fav_lost"] - 2 / 3) < 1e-12
    # All three underdogs were at 25% or less (0.1, 0.2, 0.25); two of them won.
    assert s["long_shots"] == 3 and s["surprises"] == 2
    assert abs(s["surprises_expected"] - 0.55) < 1e-12
    s = P.score(np.array([[0.4, 0.3, 0.3]]), ["A"])
    assert s["fav_lost"] == 1 and s["long_shots"] == 0 and s["surprises"] == 0


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
        {"id": "1", "played": True, "kickoff": "2026-10-10 14:00:00", "home": "A", "away": "B"},
        {"id": "2", "played": False, "kickoff": "2026-10-17 14:00:00", "home": "A", "away": "B"},
        {"id": "3", "played": False, "kickoff": "2026-10-19 19:00:00", "home": "C", "away": "D"},
        {"id": "4", "played": False, "kickoff": "2026-10-31 14:00:00", "home": "E", "away": "F"},
    ]
    got = P.next_round(fx, datetime(2026, 10, 15, 12))
    assert [m["id"] for m in got] == ["2", "3"]


def test_next_round_stops_when_a_team_plays_again():
    from datetime import datetime

    fx = [
        {"id": "1", "played": False, "kickoff": "2026-10-17 13:30:00", "home": "A", "away": "B"},
        {"id": "2", "played": False, "kickoff": "2026-10-18 13:30:00", "home": "C", "away": "D"},
        {"id": "3", "played": False, "kickoff": "2026-10-23 18:30:00", "home": "B", "away": "C"},
    ]
    assert [m["id"] for m in P.next_round(fx, datetime(2026, 10, 15))] == ["1", "2"]


def test_next_round_uses_matchdays_and_keeps_leftovers():
    from datetime import datetime

    # 8 teams → 4 games a matchday. Matchday 7 has one Monday leftover; matchday 8 is full
    # even though team A (Monday) plays again on Saturday; matchday 9 is left out.
    fx = [
        {"id": "m7", "played": False, "kickoff": "2026-10-19 19:00:00", "home": "A", "away": "B"},
        {"id": "a8", "played": False, "kickoff": "2026-10-23 19:00:00", "home": "C", "away": "D"},
        {"id": "b8", "played": False, "kickoff": "2026-10-24 14:00:00", "home": "A", "away": "E"},
        {"id": "c8", "played": False, "kickoff": "2026-10-25 14:00:00", "home": "B", "away": "F"},
        {"id": "d8", "played": False, "kickoff": "2026-10-25 16:30:00", "home": "G", "away": "H"},
        {"id": "a9", "played": False, "kickoff": "2026-10-31 12:30:00", "home": "C", "away": "A"},
    ]
    rounds = {
        ("A", "B"): 7,
        ("C", "D"): 8,
        ("A", "E"): 8,
        ("B", "F"): 8,
        ("G", "H"): 8,
        ("C", "A"): 9,
    }
    got = P.next_round(fx, datetime(2026, 10, 19, 10), rounds=rounds)
    assert [m["id"] for m in got] == ["m7", "a8", "b8", "c8", "d8"]


def test_temper_keeps_order_and_softens_above_one():
    p = np.array([[0.7, 0.2, 0.1], [0.2, 0.3, 0.5]])
    assert np.allclose(P.temper(p, 1.0), p)
    soft = P.temper(p, 1.3)
    assert np.allclose(soft.sum(1), 1)
    assert (soft.argsort(1) == p.argsort(1)).all()
    assert soft[0, 0] < p[0, 0] and soft[0, 2] > p[0, 2]


def test_fit_temperature_softens_over_confident_predictions():
    rng = np.random.default_rng(42)
    true = rng.dirichlet([4, 3, 3], size=3000)
    results = [P.OUTCOMES[rng.choice(3, p=t)] for t in true]
    assert P.fit_temperature(P.temper(true, 0.8), results) > 1.1  # undoes the sharpening
    assert abs(P.fit_temperature(true, results) - 1.0) < 0.1


def test_calibration_never_uses_its_own_season():
    def season(p, results):
        return ([{"result": r} for r in results], np.tile(p, (len(results), 1)))

    # 2017: confident favourites that won; 2018: the same predictions, favourites all lost.
    wf = {2017: season([0.8, 0.1, 0.1], ["H"] * 80 + ["D"] * 10 + ["A"] * 10)}
    wf[2018] = season([0.8, 0.1, 0.1], ["A"] * 100)
    cal = P.calibrate(wf, 2017)
    assert cal[2017][3] == 1.0  # nothing earlier to fit on
    assert cal[2018][3] == P.fit_temperature(wf[2017][1], ["H"] * 80 + ["D"] * 10 + ["A"] * 10)
    assert P.temperature_for(wf, 2019, 2017) > cal[2018][3]  # 2018's misses now count
