"""D-054: the two sides played against each other."""

from corridor import matchup


def _metric(key, value, rank, of=20, pct=None, avg=1.0, tier="decisive", elite=False, worst=False):
    return {
        "key": key,
        "value": value,
        "rank": rank,
        "of": of,
        "percentile": pct if pct is not None else round(100 * (of - rank) / (of - 1)),
        "league_avg": avg,
        "decimals": 2,
        "impact": {"tier": tier},
        "best_line": {"typical_hits": elite},
        "worst_line": {"typical_hits": worst},
    }


def _player(name, **pcts):
    return {
        "name": name,
        "minutes": 500,
        "effort_percentile": pcts.get("effort", 50),
        "metrics": {
            k: {"value": 0.3, "percentile": v}
            for k, v in pcts.items()
            if k in ("xg_xa", "box_touches", "duels_won", "recoveries")
        },
    }


def _league():
    H = {
        "metrics": [
            _metric("npxg", 1.0, 17, avg=1.3, worst=True),
            _metric("npxg_conceded", 1.4, 12, avg=1.3),
            _metric("shots", 14.0, 3, avg=12.0, tier="helps"),
            _metric("shots_conceded", 12.0, 5, avg=12.0, tier="helps"),
            _metric("distance_gap_km", -2.5, 18, avg=0.0),
        ],
        "players": [
            _player("Winger H", xg_xa=90, box_touches=80),
            _player("FB H", duels_won=20, recoveries=30),
        ],
        "shooting": {
            "players": [
                {"name": "Winger H", "shots": 20, "npxg_per_shot": 0.15, "role_npxg_per_shot": 0.11}
            ]
        },
        "context": {
            "game_state_minutes": {
                s: {"team_pct": v} for s, v in (("level", 60.0), ("ahead", 20.0), ("behind", 20.0))
            }
        },
    }
    A = {
        "metrics": [
            _metric("npxg", 1.4, 6, avg=1.3, elite=True),
            _metric("npxg_conceded", 1.1, 8, avg=1.3),
            _metric("shots", 10.0, 15, avg=12.0, tier="helps"),
            _metric("shots_conceded", 10.0, 1, avg=12.0, tier="helps"),
            _metric("distance_gap_km", 2.9, 3, avg=0.0),
        ],
        "players": [
            _player("Winger A", xg_xa=40, box_touches=50),
            _player("FB A", duels_won=85, recoveries=90),
        ],
        "shooting": {"players": []},
        "context": {
            "game_state_minutes": {
                s: {"team_pct": v} for s, v in (("level", 40.0), ("ahead", 40.0), ("behind", 20.0))
            }
        },
    }
    return {
        "table": [
            {
                "team": "Home",
                "position": 13,
                "played": 7,
                "points": 7,
                "deserved_points": 7.2,
                "elite_score": 0.18,
                "danger_score": 0.44,
                "form": ["D"],
            },
            {
                "team": "Away",
                "position": 16,
                "played": 7,
                "points": 6,
                "deserved_points": 11.3,
                "elite_score": 0.46,
                "danger_score": 0.08,
                "form": ["W"],
            },
        ],
        "teams": {"Home": H, "Away": A},
    }


def test_rank_words():
    assert matchup.rank_words(1, 20, ("most", "fewest")) == "most"
    assert matchup.rank_words(2, 20, ("most", "fewest")) == "2nd-most"
    assert matchup.rank_words(20, 20, ("most", "fewest")) == "fewest"
    assert matchup.rank_words(19, 20, ("best", "worst")) == "2nd-worst"
    assert matchup.rank_words(12, 20, ("most", "fewest")) == "12th-most"


def test_pairings_combine_attack_and_defence_through_the_league_average():
    L = _league()
    M = matchup.build(L, "Home", "Away")
    p = {x["key"]: x for x in M["pairings"]["home_attack_v_away_defence"]}
    assert p["npxg"]["attack"]["value"] == 1.0 and p["npxg"]["defence"]["value"] == 1.1
    assert p["npxg"]["if_both_play_as_usual"] == round(1.0 * 1.1 / 1.3, 2)
    assert p["npxg"]["attack"]["at_worst_line"] and p["npxg"]["decides_matches"] == "decisive"
    q = {x["key"]: x for x in M["pairings"]["away_attack_v_home_defence"]}
    assert q["npxg"]["attack"]["at_elite_line"] and q["npxg"]["if_both_play_as_usual"] == round(
        1.4 * 1.4 / 1.3, 2
    )
    assert "words" not in p["npxg"]
    assert M["both_ways"][0]["home"]["value"] == -2.5 and M["both_ways"][0]["away"]["rank"] == 3
    assert M["shape"]["Away"]["points_the_performances_deserved"] == 11.3
    assert M["shape"]["Home"]["minutes_pct"]["level"] == 60.0


def test_battles_and_read_name_the_mismatch():
    L = _league()
    hx = [
        {"name": "Winger H", "role": "W"},
        {"name": "FB H", "role": "FB"},
        {"name": "Nobody", "role": "W"},
    ]
    ax = [{"name": "Winger A", "role": "W", "out": True}, {"name": "FB A", "role": "FB"}]
    M = matchup.build(L, "Home", "Away", hx, ax, (1.5, 1.56))
    b = M["battles"]["home_attack"][0]  # Home wingers v Away full-backs
    assert [x["name"] for x in b["attackers"]] == ["Winger H"]  # unknown players skipped
    assert b["attackers"][0]["shots"] == 20 and b["attackers_percentile"] == 85
    assert b["defenders_percentile"] == 88 and b["verdict"] == "even"
    back = M["battles"]["away_attack"][0]
    assert back["attackers"] == []  # Winger A is out
    assert M["model_expectation"] == {"home_npxg": 1.5, "away_npxg": 1.56}
    read = " ".join(M["read"])
    assert "Away's performances have been worth 11.3 points and they have 6." in read
    # The bigger mismatch is Home's weak attack against Away's sound defence.
    assert (
        "Home create the 17th-most chance quality in the league and Away concede the 8th-least"
        in read
    )
    assert "Away create the 6th-most" not in read


def test_build_returns_none_for_unknown_teams():
    assert matchup.build(_league(), "Home", "Elsewhere") is None
