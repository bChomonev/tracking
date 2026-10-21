from corridor.ingest.uefa import match_to_fotmob, physical
from corridor.profile import derive, team_profile


def _row(team, opp, mid, npxg, day):
    return {
        "match_id": mid,
        "kickoff_utc": f"2026-09-{day:02d}T15:00:00Z",
        "team": team,
        "opponent": opp,
        "is_home": True,
        "goals_for": 1,
        "goals_against": 1,
        "result": "D",
        "npxg": npxg,
        "possession_pct": 50.0,
    }


def _league():
    """United: one freak 5.0 npxG match, otherwise 0.5. Rivals: steady 1.0 and 0.9 ...
    so United top the league on average but are bottom on a typical match."""
    rows = [_row("United", "X", i, v, i + 1) for i, v in enumerate([5.0, 0.5, 0.5, 0.5, 0.5])]
    for t, base in (("A", 1.0), ("B", 0.9), ("C", 0.8), ("X", 0.7)):
        rows += [_row(t, "United", 100 + i, base, i + 1) for i in range(5)]
    return rows


def _npxg(profile):
    return next(m for m in profile["metrics"] if m["key"] == "npxg")


def test_rank_uses_median_and_flags_the_freak_match():
    m = _npxg(team_profile(_league(), "United"))
    assert m["value"] == 0.5 and m["rank"] == 5  # typical match: worst in the league
    assert m["season_average"] == 1.4 and m["rank_by_average"] == 1
    assert m["skew"]["flag"] and m["skew"]["match_id"] == 0
    assert m["skew"]["average_without"] == 0.5 and m["skew"]["rank_without"] == 5


def test_metrics_missing_in_a_competition_are_skipped():
    keys = {m["key"] for m in team_profile(_league(), "United")["metrics"]}
    assert "npxg" in keys and "distance_oop_adj_km" not in keys and "ppda" not in keys


def test_uefa_join_by_date_score_and_name():
    fm = {
        "status": {"utcTime": "2026-10-13T19:00:00Z", "scoreStr": "2 - 0"},
        "home": {"name": "Atlético Madrid"},
        "away": {"name": "Manchester United"},
    }

    def u(i, h, a, hg, ag):
        return {
            "id": i,
            "kickOffTime": {"date": "2026-10-13"},
            "score": {"regular": {"home": hg, "away": ag}},
            "homeTeam": {"internationalName": h},
            "awayTeam": {"internationalName": a},
        }

    cands = [
        u("1", "Inter", "Ajax", 2, 0),
        u("2", "Atleti", "Man Utd", 2, 0),
        u("3", "Atleti", "Man Utd", 1, 0),
    ]
    assert match_to_fotmob(fm, cands)["id"] == "2"
    assert match_to_fotmob(fm, cands[2:]) is None


def test_uefa_physical_units():
    p = physical(
        {
            "distance_covered": "112.210",
            "sprints": "129.0",
            "distance_covered_not_in_possession": "69.658",
        },
        {"distance_covered": "114.149", "sprints": "156.0", "ball_possession": "57"},
    )
    assert (
        p["distance_m"] == 112210 and p["opp_sprints"] == 156 and p["opp_possession_pct_uefa"] == 57
    )


def test_passing_metrics_use_completed_passes():
    # FotMob's own-half + opposition-half passes add up to the accurate (completed) passes.
    r = {
        "passes": 669.0,
        "accurate_passes": 588.0,
        "opp_half_passes": 391.0,
        "opp_half_passes_conceded": 200.0,
    }
    r |= {"accurate_long_balls": 25.0, "npxg": 1.0, "shots": 10, "xg": 1.0, "result": "D"}
    d = derive(r)
    assert round(d["pass_accuracy_pct"], 1) == 87.9
    assert round(d["opp_half_pass_pct"], 1) == 66.5
    assert round(d["long_ball_pct"], 2) == 4.25
    assert derive({"result": "W", "passes": 0})["pass_accuracy_pct"] is None
