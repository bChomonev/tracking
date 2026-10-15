import pytest

from corridor.best_line import build_line, compare, final_table


def _r(team, opp, gf, ga, npxg, mid, red=None):
    res = "W" if gf > ga else "D" if gf == ga else "L"
    return {
        "match_id": mid,
        "kickoff_utc": f"2025-09-{mid % 28 + 1:02d}T15:00:00Z",
        "team": team,
        "opponent": opp,
        "is_home": True,
        "goals_for": gf,
        "goals_against": ga,
        "result": res,
        "npxg": npxg,
        "opp_red_card_min": red,
    }


def _season():
    rows = []
    # Five strong teams beat the minnow 12 times each with npxG 1.0..2.1; the minnow loses.
    for t_i, t in enumerate(["A", "B", "C", "D", "E"]):
        for k in range(12):
            mid = t_i * 100 + k
            rows.append(_r(t, "Z", 2, 0, 1.0 + k / 10 + (0.5 if t == "E" else 0), mid))
            rows.append(_r("Z", t, 0, 2, 0.3, mid))
    rows[0]["goals_against"] = 1  # A's first win 2-1: GD tie-break puts A below B..D
    # One of B's wins came against 10 men from the 30th minute, with a huge npxG.
    rows.append(_r("B", "Z", 6, 0, 5.0, 999, red=30))
    return rows


def test_table_and_elite_exclude_red_card_wins():
    rows = _season()
    table = final_table(rows)
    assert table[0] == "B" and set(table[:4]) == {"B", "C", "D", "E"}  # A loses on GD
    line = build_line(rows, "2025-26")
    assert set(line["elite"]) == {"B", "C", "D", "E"}
    assert line["excluded"] and "10 men from 30'" in line["excluded"][0]["why"]
    assert line["metrics"]["npxg"]["n"] == 48  # 4 teams x 12 wins, red-card win excluded


def test_compare_counts_matches_at_the_line():
    line = {
        "season": "2025-26",
        "elite": ["A"],
        "wins": 20,
        "wins_by_team": {"A": 20},
        "excluded": [],
        "metrics": {
            "npxg": {"value": 1.5, "p25": 1.2, "p75": 2.0, "n": 20},
            "npxg_conceded": {"value": 0.8, "p25": 0.5, "p75": 1.1, "n": 20},
        },
    }
    profile = {
        "matches": [{"match_id": 1}, {"match_id": 2}, {"match_id": 3}],
        "metrics": [
            {
                "key": "npxg",
                "direction": 1,
                "value": 1.3,
                "matches": [{"value": 1.6}, {"value": 1.3}, {"value": None}],
            },
            {
                "key": "npxg_conceded",
                "direction": -1,
                "value": 1.0,
                "matches": [{"value": 0.7}, {"value": 1.2}, {"value": 0.8}],
            },
        ],
    }
    s = compare(profile, line)
    npxg, conc = (m["best_line"] for m in profile["metrics"])
    assert npxg["matches_reached"] == 1 and npxg["matches_counted"] == 2
    assert not npxg["typical_reaches"] and npxg["typical_in_range"]  # 1.3 >= p25 1.2
    assert npxg["gap"] == pytest.approx(-0.2)
    assert conc["weak_end"] == 1.1 and conc["typical_in_range"]  # lower is better
    assert conc["matches_reached"] == 2  # 0.7 and 0.8 are at or under 0.8
    assert [p["reached"] for p in s["per_match"]] == [2, 0, 1]


def test_metric_whose_definition_changed_gets_no_line():
    prev = _season()
    cur = [dict(r, npxg=r["npxg"] * 3) for r in prev]  # provider "redefined" npxG
    line = build_line(prev, "2025-26", cur)
    assert "npxg" in line["not_comparable"] and "npxg" not in line["metrics"]
    assert "npxg" in build_line(prev, "2025-26", prev)["metrics"]
