from corridor.scripts.united_profile import _expected_points, _understat_row


def _us(team, gf, ga, ppda, deep, deep_allowed):
    return {
        "team": team,
        "kickoff_utc": "2026-09-06 13:00:00",
        "goals_for": gf,
        "goals_against": ga,
        "ppda": ppda,
        "deep_completions": deep,
        "deep_allowed": deep_allowed,
    }


def test_understat_join_tells_apart_two_draws_with_the_same_score_and_deep_completions():
    rec = {
        "us_rows": [
            _us("Everton", 2, 2, 13.26, 7, 7),
            _us("Manchester United", 2, 2, 15.86, 7, 7),
        ]
    }
    fm_row = {
        "kickoff_utc": "2026-09-06T13:00:00Z",
        "goals_for": 2,
        "goals_against": 2,
        "ppda": 15.86,
        "deep_completions": 7,
        "deep_allowed": 7,
    }
    assert _understat_row(rec, fm_row)["team"] == "Manchester United"
    assert _understat_row(rec, fm_row | {"ppda": None}) is None


def test_expected_points_average_the_two_histories():
    x = {
        "best_weighted": {"history": {"n": 50, "W": 0.6, "D": 0.2}},
        "worst_weighted": {"history": {"n": 40, "W": 0.2, "D": 0.4}},
    }
    assert abs(_expected_points(x) - ((1.8 + 0.2) + (0.6 + 0.4)) / 2) < 1e-9
    empty = {"best_weighted": {"history": None}, "worst_weighted": {"history": {"n": 0}}}
    assert _expected_points(empty) is None


def test_odds_name_map_never_guesses_a_wrong_team():
    from corridor.ingest.odds import name_map

    ours = {
        "Wolverhampton Wanderers",
        "West Ham",
        "Leeds",
        "West Bromwich Albion",
        "Manchester United",
    }
    got = name_map({"Wolves", "West Ham", "Leeds", "West Brom", "Man United"}, ours)
    assert got["Wolves"] == "Wolverhampton Wanderers" and got["West Brom"] == "West Bromwich Albion"
    assert len(set(got.values())) == len(got)
