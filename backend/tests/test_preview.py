import math

from corridor import preview as V


def test_negative_binomial_helpers_are_proper_distributions():
    pmf = V.nb_pmf(5.0, 12.0, kmax=60)
    assert abs(pmf.sum() - 1) < 1e-9
    assert abs(sum(k * p for k, p in enumerate(pmf)) - 5.0) < 1e-6
    a, eq, b = V.p_more(6.0, 4.0, 12.0)
    assert abs(a + eq + b - 1) < 1e-6 and a > b
    assert (
        abs(
            V.p_over(9.5, 10.0)
            - (1 - sum(math.exp(-10) * 10**k / math.factorial(k) for k in range(10)))
        )
        < 1e-12
    )


def _row(mid, ko, team, opp, home, corners):
    return {
        "match_id": mid,
        "kickoff_utc": ko,
        "team": team,
        "opponent": opp,
        "is_home": home,
        "corners": corners,
    }


def test_corner_predictions_use_only_earlier_matches():
    rows = []
    for i in range(12):
        ko = f"2025-09-{i + 1:02d}T15:00:00Z"
        rows += [_row(i, ko, "Big", "Small", True, 9), _row(i, ko, "Small", "Big", False, 2)]
    preds, R = V.corner_walk([(2025, rows)])
    assert preds[0]["exp_home"] == preds[0]["exp_away"] * 5.4 / 4.6  # nothing known yet
    assert preds[-1]["exp_home"] > preds[-1]["exp_away"] + 2  # learned from earlier ones
    h, a = R.expect("Big", "Small")
    assert h > a


def test_player_rates_shrink_towards_the_role_average():
    roles = {"ST": {"shots90": 2.0, "npxg90": 0.3}}
    R = V.PlayerRates(roles)
    assert R.rate(1, "ST") == (2.0, 0.3)  # no data → role average
    R.add({"player_id": 1, "np_shots": 10, "npxg_shots": 2.0, "minutes": 90, "started": True})
    s90, _ = R.rate(1, "ST")
    assert 2.0 < s90 < 10.0  # one big game moves him, but not all the way
    e = V.expect_player(R, 1, "ST", 90, 1.0, 1.0)
    assert abs(e["p_shot"] - (1 - math.exp(-e["exp_shots"]))) < 1e-12


def test_card_predictions_use_only_earlier_matches():
    rows = []
    for i in range(12):
        ko = f"2025-09-{i + 1:02d}T15:00:00Z"
        rows += [
            {
                "match_id": i,
                "kickoff_utc": ko,
                "team": "Dirty",
                "opponent": "Clean",
                "is_home": True,
                "yellow_cards": 5,
                "red_cards": 0,
                "referee": "R",
            },
            {
                "match_id": i,
                "kickoff_utc": ko,
                "team": "Clean",
                "opponent": "Dirty",
                "is_home": False,
                "yellow_cards": 0,
                "red_cards": 0,
                "referee": "R",
            },
        ]
    preds, R = V.card_walk([(2025, rows)])
    assert (
        preds[0]["exp_home"] < preds[-1]["exp_home"]
        and preds[-1]["exp_home"] > preds[-1]["exp_away"]
    )
    h, a = R.expect("Dirty", "Clean", "R")
    assert h > a and R.ref_factor("unknown") == 1.0


def test_player_extra_rates_assists_and_bookings():
    R = V.PlayerRates({"CM": {"shots90": 1.0, "npxg90": 0.08, "xa90": 0.1, "yellow90": 0.2}})
    R.add(
        {
            "player_id": 9,
            "np_shots": 0,
            "npxg_shots": 0.0,
            "minutes": 900,
            "started": True,
            "xa": 3.0,
            "yellow": 5,
        }
    )
    xa90, y90 = R.extra(9, "CM")
    assert 0.1 < xa90 < 0.3 and 0.2 < y90 < 0.5
    e = V.expect_player(R, 9, "CM", 90, 1.0, 1.0)
    assert e["p_involved"] >= max(e["p_goal"], e["p_assist"])


def test_opponent_factor_remembers_last_season_at_half_weight():
    from corridor.preview import opponent_factors

    def rows(team_vals, ko):
        return [
            {"team": t, "kickoff_utc": ko, "np_shots_conceded": v, "npxg_conceded": v / 10}
            for t, v in team_vals
        ]

    # This season: A and B both concede 10 (average). Last season A conceded 5, B 15.
    now = rows([("A", 10), ("B", 10)], "2026-09-01")
    last = rows([("A", 5), ("B", 15)] * 10, "2025-09-01")
    f_now = opponent_factors(now)
    assert f_now["A"][0] == f_now["B"][0] == 1.0
    f = opponent_factors(now, prev_rows=last)
    assert f["A"][0] < 1.0 < f["B"][0]  # last season's mean defence still counts
    # 1 match now + 10 last season at half weight (5) + 3 average: (1*1 + 5*0.5 + 3)/9
    assert abs(f["A"][0] - (1 + 5 * 0.5 + 3) / 9) < 1e-9
    assert opponent_factors(now, prev_rows=last, prev_weight=0)["A"][0] == 1.0
