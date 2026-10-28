"""Player form (corridor.engine.player_trend): role percentile per match, adjusted for the opponent,
then the last matches against the earlier ones."""

import numpy as np

from corridor.engine import player_trend, trend

TEAMS = [f"T{i}" for i in range(6)]


def _season(rng, n_rounds=10, strength=None):
    """A round-robin-ish season: every round each team plays one match. Team rows carry
    npxG for / against; player rows one striker and one centre-back per team."""
    strength = strength or dict.fromkeys(TEAMS, 0.0)
    team_rows, players = [], []
    mid = 1000
    for rd in range(n_rounds):
        order = list(TEAMS)
        rng.shuffle(order)
        for h, a in zip(order[::2], order[1::2], strict=True):
            mid += 1
            ko = f"2026-08-{rd + 1:02d}T15:00:00Z"
            for me, them in ((h, a), (a, h)):
                npxg = max(0.1, 1.3 + strength[me] - strength[them] + rng.normal(0, 0.3))
                npxga = max(0.1, 1.3 + strength[them] - strength[me] + rng.normal(0, 0.3))
                team_rows.append(
                    {
                        "match_id": mid,
                        "team": me,
                        "opponent": them,
                        "kickoff_utc": ko,
                        "npxg": npxg,
                        "npxg_conceded": npxga,
                    }
                )
                for role, pid_off in (("ST", 0), ("CB", 100)):
                    pid = pid_off + TEAMS.index(me)
                    # Output scales with the match's npxG for strikers, against for CBs.
                    base = npxg if role == "ST" else 2.5 - npxga
                    players.append(
                        {
                            "player_id": pid,
                            "name": f"P{pid}",
                            "team": me,
                            "match_id": mid,
                            "role": role,
                            "minutes": 90.0,
                            "npxg_shots": max(0, base * 0.4 + rng.normal(0, 0.1)),
                            "xa": max(0, rng.normal(0.1, 0.05)),
                            "np_shots": rng.poisson(1 + 2 * base),
                            "box_touches": rng.poisson(2 + 3 * base),
                            "duels_won": rng.poisson(3 + 2 * base),
                            "duels_lost": rng.poisson(5 - base),
                            "recoveries": rng.poisson(2 + 2 * base),
                            "line_breaking_passes": rng.poisson(1 + base),
                        }
                    )
    return team_rows, players


def test_percentiles_are_role_shares_with_ties_half_and_lower_is_better_flipped():
    rng = np.random.default_rng(42)
    team_rows, players = _season(rng, n_rounds=8)
    rows = player_trend.match_scores(players, team_rows)
    assert rows and all(0 <= r["score"] <= 100 for r in rows)
    # Striker rows are scored on the striker metrics only, and in kickoff order.
    st = [r for r in rows if r["role"] == "ST"]
    assert set(st[0]["percentiles"]) == {"xg_xa", "np_shots", "box_touches", "duels_won"}
    assert [r["kickoff_utc"] for r in rows] == sorted(r["kickoff_utc"] for r in rows)
    # The best striker match on a metric beats every other one: percentile 100.
    best = max(st, key=lambda r: r["percentiles"]["box_touches"])
    assert best["percentiles"]["box_touches"] == 100
    # Duels lost: the centre-back with the most lost duels gets the lowest percentile.
    cb = [p for p in players if p["role"] == "CB"]
    worst = max(cb, key=lambda p: p["duels_lost"])
    r = next(
        x
        for x in rows
        if x["match_id"] == worst["match_id"] and x["team"] == worst["team"] and x["role"] == "CB"
    )
    assert r["percentiles"]["duels_lost"] == min(
        x["percentiles"]["duels_lost"] for x in rows if x["role"] == "CB"
    )


def test_substitutes_and_goalkeepers_do_not_count():
    rng = np.random.default_rng(42)
    team_rows, players = _season(rng, n_rounds=8)
    players[0]["minutes"] = 59.0
    players[1]["role"] = "GK"
    players[2]["role"] = None
    rows = player_trend.match_scores(players, team_rows)
    ids = {(r["player_id"], r["match_id"]) for r in rows}
    for p in players[:3]:
        assert (p["player_id"], p["match_id"]) not in ids
    assert len(rows) == len(players) - 3


def test_opponent_adjustment_credits_matches_against_strong_sides():
    rng = np.random.default_rng(42)
    strength = {"T0": 0.6, "T1": 0.3, "T2": 0.0, "T3": 0.0, "T4": -0.3, "T5": -0.6}
    team_rows, players = _season(rng, n_rounds=12, strength=strength)
    s = player_trend.opponent_strength(team_rows)
    assert s["T0"] > s["T2"] > s["T5"]
    rows = player_trend.match_scores(players, team_rows)
    st = [r for r in rows if r["role"] == "ST"]
    # Strikers score lower against strong sides; after the adjustment that gap is gone.
    raw_gap = np.mean([r["score"] for r in st if r["opponent"] == "T0"]) - np.mean(
        [r["score"] for r in st if r["opponent"] == "T5"]
    )
    adj_gap = np.mean([r["adjusted"] for r in st if r["opponent"] == "T0"]) - np.mean(
        [r["adjusted"] for r in st if r["opponent"] == "T5"]
    )
    assert raw_gap < -10 and abs(adj_gap) < abs(raw_gap) / 2
    # Strength is relative to the league: the adjustments net out to about nothing.
    assert abs(np.mean([r["adjusted"] - r["score"] for r in st])) < 1.0


def test_build_windows_count_the_players_matches_not_the_teams():
    rng = np.random.default_rng(42)
    team_rows, players = _season(rng, n_rounds=10)
    # Player 0 comes off the bench in half his matches: 5 counted, under the 7 minimum.
    for p in players:
        if p["player_id"] == 0 and p["match_id"] % 2 == 0:
            p["minutes"] = 20.0
    out = player_trend.build(players, team_rows)
    p0 = out[0]
    assert p0["n_counted"] == sum(1 for p in players if p["player_id"] == 0 and p["minutes"] >= 60)
    assert p0["n_counted"] < player_trend.MIN_MATCHES
    assert p0["composite"]["call"] is None and p0["composite"]["n"] == p0["n_counted"]
    assert p0["window"] == player_trend.WINDOW == 4
    assert p0["min_matches"] == 4 + trend.MIN_BEFORE
    # A full-season regular gets a call and a per-metric trend for each of his metrics.
    p1 = out[1]
    assert p1["n_counted"] == 10 and p1["composite"]["call"] in ("up", "down", "steady")
    assert p1["composite"]["n_recent"] == 4
    assert set(p1["metrics"]) == {"xg_xa", "np_shots", "box_touches", "duels_won"}
    assert len(p1["matches"]) == 10 and p1["matches"][0]["opponent"] in TEAMS


def test_words_say_both_numbers_and_the_count():
    rng = np.random.default_rng(42)
    team_rows, players = _season(rng, n_rounds=10)
    out = player_trend.build(players, team_rows)
    t = out[1]
    s = player_trend.words(t, "P1")
    assert s.startswith("P1: ") and "his last 4 matches rate" in s and "in the 6 before" in s
    assert player_trend.words({"composite": None}, "x") is None
