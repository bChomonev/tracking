"""The round at a glance (corridor.picks): tiers with their own records."""

from corridor import picks


def _league(key, comp, fixtures, record=(), bands=(), over_bins=(), previews=None):
    return {
        "competition": comp,
        "predictions": {
            "next_round": fixtures,
            "record": {"matches": list(record)},
            "mistakes": {"bands": {"win_or_draw": list(bands)}},
            "backtest_goals": {"calibration_over": list(over_bins)},
        },
        "previews": previews or {"fixtures": {}, "backtest": {}},
    }


def _fx(i, home, away, p, over=0.5):
    return {
        "id": str(i),
        "kickoff": f"2026-11-0{i} 15:00:00",
        "home": home,
        "away": away,
        "p": p,
        "goals": {"over_2_5": over, "exp_home": 1.5, "exp_away": 1.2},
    }


def test_double_chance_tiers_pick_the_favourite_and_pool_the_records():
    pl = _league(
        "pl",
        "Premier League",
        [
            _fx(1, "A", "B", [0.70, 0.22, 0.08]),
            _fx(2, "C", "D", [0.10, 0.25, 0.65]),
            _fx(3, "E", "F", [0.40, 0.30, 0.30]),
        ],
        record=[
            {"result": "H", "p": [0.72, 0.20, 0.08]},  # 92%: came in
            {"result": "A", "p": [0.72, 0.20, 0.08]},  # 92%: did not
            {"result": "D", "p": [0.10, 0.25, 0.65]},  # 90% X2: came in
        ],
        bands=[{"from": 0.9, "to": 1.0, "n": 100, "said": 0.93, "happened": 0.91}],
    )
    de = _league(
        "bundesliga",
        "Bundesliga",
        [_fx(4, "G", "H", [0.55, 0.25, 0.20])],
        bands=[{"from": 0.9, "to": 1.0, "n": 100, "said": 0.95, "happened": 0.89}],
    )
    tiers = picks.double_chance({"pl": pl, "bundesliga": de})
    top = tiers[0]
    assert top["label"] == "90%+" and [x["call"] for x in top["picks"]] == ["1X", "X2"]
    assert top["picks"][0]["favourite"] == "A" and top["picks"][0]["p"] == 0.92
    assert top["backtest"] == {"n": 200, "said": 0.94, "happened": 0.9}
    assert top["season"] == {"n": 3, "hit": 2}
    assert tiers[2]["picks"][0]["home"] == "G" and tiers[2]["label"] == "80–85%"  # 0.55 + 0.25
    assert sum(len(t["picks"]) for t in tiers) == 4  # E v F at exactly 70% is in


def test_goals_shooters_and_cards_apply_their_floors():
    previews = {
        "fixtures": {
            "1": {
                "sides": {
                    "home": {
                        "team": "A",
                        "shooters": [
                            {
                                "name": "S1",
                                "role": "ST",
                                "p_shot2": 0.62,
                                "exp_shots": 2.1,
                                "p_goal": 0.3,
                            }
                        ],
                    },
                    "away": {
                        "team": "B",
                        "shooters": [
                            {
                                "name": "S2",
                                "role": "W",
                                "p_shot2": 0.31,
                                "exp_shots": 1.2,
                                "p_goal": 0.1,
                            }
                        ],
                    },
                },
                "cards": {
                    "p_home_more": 0.70,
                    "p_away_more": 0.15,
                    "exp_home": 2.6,
                    "exp_away": 1.4,
                },
            }
        },
        "backtest": {
            "shooters": {
                "2025": {
                    "calibration_shot2": [
                        {"from": 0.6, "n": 50, "predicted": 0.64, "observed": 0.6}
                    ]
                }
            },
            "cards": {"matches": 400, "more_cards_side": 0.61},
        },
    }
    lg = _league(
        "pl",
        "Premier League",
        [
            _fx(1, "A", "B", [0.5, 0.3, 0.2], over=0.74),
            _fx(2, "C", "D", [0.5, 0.3, 0.2], over=0.25),
        ],
        record=[{"result": "H", "p": [0.5, 0.3, 0.2], "score": "3-1", "over_2_5": 0.75}],
        over_bins=[
            {"from": 0.7, "n": 100, "predicted": 0.74, "observed": 0.70},
            {"from": 0.2, "n": 100, "predicted": 0.25, "observed": 0.28},
        ],
        previews=previews,
    )
    g = picks.goals({"pl": lg})
    assert [x["call"] for x in g["picks"]] == ["Under 2.5", "Over 2.5"] and g["picks"][0][
        "p"
    ] == 0.75
    assert g["backtest"]["over"] == {"n": 100, "said": 0.74, "happened": 0.7}
    assert g["backtest"]["under"]["happened"] == 0.72 and g["season"]["over"] == {"n": 1, "hit": 1}
    sh = picks.shooters({"pl": lg})
    assert [x["name"] for x in sh["top"]] == ["S1", "S2"] and sh["top"][0]["band"][
        "happened"
    ] == 0.6
    c = picks.cards({"pl": lg})
    assert c["picks"] == [
        {
            "league": "pl",
            "competition": "Premier League",
            "id": "1",
            "kickoff": "2026-11-01 15:00:00",
            "home": "A",
            "away": "B",
            "call": "A more yellows",
            "p": 0.7,
            "expected": [2.6, 1.4],
        }
    ]
    assert c["backtest"] == {"n": 400, "happened": 0.61}


def test_why_says_only_the_numbers_that_support_the_call():
    att = lambda v, r, of=20: {"value": v, "rank": r, "of": of}  # noqa: E731
    pairings = {
        "home_attack_v_away_defence": [{"attack": att(3.3, 1), "defence": att(0.8, 3)}],
        "away_attack_v_home_defence": [{"attack": att(0.9, 18), "defence": att(1.0, 5)}],
    }
    shape = {
        "A": {"recent_form": {"last_matches": 5, "xg_diff": {"call": "steady"}}},
        "B": {
            "recent_form": {
                "last_matches": 5,
                "xg_diff": {"call": "down", "recent": -0.3, "before": 0.5},
            }
        },
    }
    w = picks.why({"pairings": pairings, "shape": shape}, True, "A", "B")
    # A's attack is 1st (said), B's defence is 3rd (good: not said); B's attack is 18th (said),
    # A's defence 5th (top third: said); B trending down (said).
    assert w == (
        "A create 3.3 npxG a match (1st of 20); B create 0.9 (18th of 20); A concede 1.0 (5th); "
        "B trending down: -0.30 a match over the last 5 against +0.50 before."
    )
    # A fourth clause (the favourite also trending up) is dropped: three read, five don't.
    shape["A"]["recent_form"]["xg_diff"] = {"call": "up", "recent": 1.0, "before": 0.2}
    w = picks.why({"pairings": pairings, "shape": shape}, True, "A", "B")
    assert w.endswith("A trending up: +1.00 a match over the last 5 against +0.20 before.")
    assert "B trending" not in w
    # Nothing supports the call → nothing said.
    mid = {
        "home_attack_v_away_defence": [{"attack": att(1.2, 10), "defence": att(1.2, 9)}],
        "away_attack_v_home_defence": [{"attack": att(1.2, 11), "defence": att(1.2, 10)}],
    }
    assert picks.why({"pairings": mid, "shape": {}}, True, "A", "B") is None
    assert picks.why(None, True, "A", "B") is None
