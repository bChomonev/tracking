from corridor.cup import next_cup_match


def _fx(home, away, t, finished=False):
    return {
        "home": {"name": home},
        "away": {"name": away},
        "status": {"utcTime": t, "finished": finished},
    }


LEAGUES = {
    "seriea": {
        "competition": "Serie A",
        "table": [
            {
                "team": "Como",
                "position": 5,
                "played": 2,
                "w": 1,
                "d": 1,
                "l": 0,
                "points": 4,
                "gf": 3,
                "ga": 1,
                "xg": 3.0,
                "xga": 2.0,
                "form": ["W", "D"],
            },
            {
                "team": "Inter",
                "position": 1,
                "played": 2,
                "w": 2,
                "d": 0,
                "l": 0,
                "points": 6,
                "gf": 4,
                "ga": 0,
                "xg": 4.0,
                "xga": 1.0,
                "form": ["W", "W"],
            },
        ],
        "teams": {"Como": {"matches": [{"possession_pct": 60.0}, {"possession_pct": 62.0}]}},
    }
}
ROWS = [
    {
        "team": "Como",
        "opponent": "Feyenoord",
        "kickoff_utc": "2026-10-14T19:00:00Z",
        "is_home": False,
        "goals_for": 2,
        "goals_against": 3,
        "xg": 1.28,
        "xg_conceded": 0.59,
    },
    {
        "team": "Manchester United",
        "opponent": "Sabah FK",
        "kickoff_utc": "2026-09-10T19:00:00Z",
        "is_home": True,
        "goals_for": 4,
        "goals_against": 0,
        "xg": 3.54,
        "xg_conceded": 0.84,
    },
]


def test_next_cup_match_takes_the_first_unplayed_game_and_has_no_prediction():
    fixtures = [
        _fx("Manchester United", "Sabah FK", "2026-09-10T19:00:00.000Z", finished=True),
        _fx("PSG", "Manchester United", "2026-11-04T20:00:00.000Z"),
        _fx("Como", "Manchester United", "2026-10-21T16:45:00.000Z"),
        _fx("Como", "Inter", "2026-10-20T16:45:00.000Z"),
    ]
    c = next_cup_match("Manchester United", fixtures, LEAGUES, ROWS, "2026-10-20T12:00:00+00:00")
    assert (c["home"], c["away"], c["kickoff"]) == (
        "Como",
        "Manchester United",
        "2026-10-21 16:45:00",
    )
    assert not any("p" in k or "pct" in k for k in c if k != "competition")
    como = c["sides"]["Como"]
    assert como["league"]["competition"] == "Serie A" and como["league"]["position"] == 5
    assert como["league"]["goals_for_pg"] == 1.5 and como["league"]["possession_pct"] == 61
    assert como["cup"][0]["opponent"] == "Feyenoord" and como["cup"][0]["venue"] == "away"
    # United's league isn't in the files passed: no league numbers, cup games still there
    utd = c["sides"]["Manchester United"]
    assert utd["league"] is None and utd["cup"][0]["goals_for"] == 4


def test_no_next_cup_match_when_none_left():
    fx = [_fx("Como", "Manchester United", "2026-10-21T16:45:00.000Z", finished=True)]
    assert next_cup_match("Manchester United", fx, LEAGUES, ROWS, "2026-10-22T00:00:00") is None
