import numpy as np

from corridor import proof


def _season(seed, n_teams=8, rounds=10):
    """Synthetic league where a higher npxG genuinely makes winning more likely."""
    rng = np.random.default_rng(seed)
    rows = []
    teams = [f"T{i}" for i in range(n_teams)]
    for _ in range(rounds):
        order = rng.permutation(teams)
        for h, a in zip(order[::2], order[1::2], strict=True):
            xh, xa = rng.gamma(2, 0.6), rng.gamma(2, 0.6)
            gh, ga = rng.poisson(xh), rng.poisson(xa)
            for t, o, gf, gc, x, xc in ((h, a, gh, ga, xh, xa), (a, h, ga, gh, xa, xh)):
                rows.append(
                    {
                        "team": t,
                        "opponent": o,
                        "goals_for": int(gf),
                        "goals_against": int(gc),
                        "result": "W" if gf > gc else "D" if gf == gc else "L",
                        "npxg": x,
                        "npxg_conceded": xc,
                        "ppda": rng.normal(11, 3),
                        "deep_completions": rng.poisson(6),
                        "deep_allowed": rng.poisson(6),
                    }
                )
    return rows


def test_lines_come_from_the_previous_season_only():
    seasons = [("A", _season(1)), ("B", _season(2)), ("C", _season(3))]
    out = proof.evaluate(seasons, proof.UNDERSTAT_METRICS, proof.UNDERSTAT_BINS)
    assert [(p["lines_from"], p["tested_on"]) for p in out["pairs"]] == [("A", "B"), ("B", "C")]
    assert out["team_matches"] == len(seasons[1][1]) + len(seasons[2][1])


def test_win_rate_rises_with_lines_reached_and_npxg_has_lift():
    seasons = [(str(y), _season(y, n_teams=12, rounds=30)) for y in range(4)]
    out = proof.evaluate(seasons, proof.UNDERSTAT_METRICS, proof.UNDERSTAT_BINS)
    lift = {m["key"]: m["lift"] for m in out["best"]["by_metric"]}
    assert lift["npxg"] > 0.15 and abs(lift["ppda"]) < 0.1  # ppda is pure noise here
    rates = [b["W"] for b in out["best"]["bins"] if b["n"] >= 30]
    assert rates[-1] > rates[0]


def test_outcome_linked_metrics_are_not_tested():
    keys = {m.key for m in proof.FOTMOB_METRICS}
    assert not keys & proof.OUTCOME_LINKED and "npxg" in keys


def test_place_finds_the_bin():
    summary = {"bins": [{"from": 0.0, "to": 0.5, "W": 0.2}, {"from": 0.5, "to": 1.0, "W": 0.8}]}
    assert proof.place(0.7, summary)["W"] == 0.8 and proof.place(1.0, summary)["W"] == 0.8
    assert proof.place(None, summary) is None
