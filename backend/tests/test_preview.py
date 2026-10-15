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
