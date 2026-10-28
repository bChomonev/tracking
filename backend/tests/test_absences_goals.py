import numpy as np

from corridor import absences as AB
from corridor import predict as P
from corridor.profile import shooting


def test_absence_adjustment_moves_towards_the_fuller_side():
    p = [0.4, 0.3, 0.3]
    assert AB.adjust(p, 0.1, 0.1) == p or np.allclose(AB.adjust(p, 0.1, 0.1), p)
    q = AB.adjust(p, 0.25, 0.05)  # home missing far more
    assert q[0] < p[0] and q[2] > p[2] and abs(sum(q) - 1) < 1e-12


def test_contributions_weight_players_by_their_share():
    C = AB.Contributions()
    C.add({"team": "T", "player_id": 1, "minutes": 90, "npxg_shots": 0.6, "xa": 0.2})
    C.add({"team": "T", "player_id": 2, "minutes": 90, "npxg_shots": 0.1, "xa": 0.1})
    m = C.missing("T", [1])
    assert abs(m["output"] - 0.8) < 1e-12 and abs(m["minutes"] - 0.5) < 1e-12
    assert C.missing("Other", [1]) == {"output": 0.0, "minutes": 0.0}


def test_unavailable_parses_the_team_news():
    d = {
        "content": {
            "lineup": {
                "homeTeam": {
                    "unavailable": [{"id": 7, "name": "X", "unavailability": {"type": "injury"}}]
                },
                "awayTeam": {},
            }
        }
    }
    assert AB.unavailable(d) == {"home": [{"id": 7, "name": "X", "type": "injury"}], "away": []}


def test_goal_markets_from_a_scoreline_matrix():
    g = P.GoalsModel(shrink=1.0)
    g.rho = 0.0
    mx = g.matrix(1.5, 1.0)
    mk = P.markets(mx)
    assert abs(sum(mk["p"]) - 1) < 1e-9 and mk["p"][0] > mk["p"][2]
    assert abs(mk["btts"] - (1 - np.exp(-1.5)) * (1 - np.exp(-1.0))) < 1e-6
    assert mk["scores"][0]["p"] == max(s["p"] for s in mk["scores"])


def _p(team, pid, role, shots, npxg, minutes=90):
    return {
        "team": team,
        "player_id": pid,
        "name": f"P{pid}",
        "role": role,
        "position": "FWD",
        "match_id": 1,
        "minutes": minutes,
        "np_shots": shots,
        "npxg_shots": npxg,
    }


def test_shooting_quality_gap_sums_to_the_team_gap():
    rows = [_p("A", 1, "ST", 10, 0.5), _p("A", 2, "ST", 10, 2.5), _p("B", 3, "ST", 20, 3.0)]
    sh = shooting(rows, "A")
    role_q = 6.0 / 40  # ST league average npxG per shot
    gaps = {r["name"]: r["quality_gap"] for r in sh["players"]}
    assert abs(gaps["P1"] - (10 * role_q - 0.5)) < 1e-12 and gaps["P2"] < 0
    assert abs(sh["quality_gap"] - sum(gaps.values())) < 1e-12


def test_aligned_scorelines_add_up_to_the_published_prediction():
    g = P.GoalsModel(shrink=1.0)
    g.rho = -0.05
    p = [0.45, 0.25, 0.30]
    lh, la = P.align(g, 1.43, 1.49, p)  # goals model alone had the away side ahead
    mk = P.markets(g.matrix(lh, la))
    assert abs((mk["p"][0] - mk["p"][2]) - (p[0] - p[2])) < 1e-6
    assert abs(lh + la - (1.43 + 1.49)) < 1e-9 and lh > la


def test_reconciled_scorelines_sum_exactly_to_the_prediction():
    g = P.GoalsModel(shrink=1.0)
    g.rho = -0.05
    p = [0.4668, 0.2647, 0.2685]
    mk = P.markets(P.reconcile(g.matrix(*P.align(g, 1.7, 1.3, p)), p))
    assert np.allclose(mk["p"], p, atol=1e-9)


def test_usual_xi_excludes_players_who_left_and_waits_for_three_matches():
    # D-065: last season's regulars count at half weight, but only players seen in a squad
    # this season can be in the usual XI, and the measure waits for three team matches.
    C = AB.Contributions()
    for pid in range(1, 15):  # last season: 1-11 played a lot, 12-14 a little
        C.add(
            {"team": "T", "player_id": pid, "minutes": 2000 if pid <= 11 else 300, "match_id": 0},
            0.5,
        )
    assert C.regulars("T") == [] and C.regulars_missing("T", set(range(1, 12))) is None
    # This season: player 1 has left; 12 plays every match; three matches.
    for mid in (101, 102, 103):
        for pid in range(2, 15):
            C.add(
                {"team": "T", "player_id": pid, "minutes": 90 if pid != 14 else 0, "match_id": mid}
            )
    reg = C.regulars("T")
    assert 1 not in reg and len(reg) == 11 and set(reg) == set(range(2, 13))
    # The whole usual XI starts → 0; three of them on the bench → 3/11.
    assert C.regulars_missing("T", set(range(2, 13))) == 0.0
    assert abs(C.regulars_missing("T", set(range(5, 13)) | {13, 14, 1}) - 3 / 11) < 1e-9


def test_lineups_only_when_official_and_complete():
    starters = [{"id": i} for i in range(11)]
    d = {
        "content": {
            "lineup": {
                "lineupType": "standard",
                "homeTeam": {"starters": starters},
                "awayTeam": {"starters": [{"id": 100 + i} for i in range(11)]},
            }
        }
    }
    xi = AB.lineups(d)
    assert xi["home"] == set(range(11)) and xi["away"] == set(range(100, 111))
    d["content"]["lineup"]["lineupType"] = "predicted"
    assert AB.lineups(d) is None
    d["content"]["lineup"]["lineupType"] = "standard"
    d["content"]["lineup"]["awayTeam"]["starters"] = starters[:10]
    assert AB.lineups(d) is None


def test_regulars_split_separates_injured_from_rested():
    C = AB.Contributions()
    for mid in (1, 2, 3):
        for pid in range(1, 15):
            C.add(
                {"team": "T", "player_id": pid, "minutes": 90 if pid <= 11 else 10, "match_id": mid}
            )
    xi = set(range(4, 12)) | {12, 13, 14}  # regulars 1, 2, 3 out
    assert C.regulars_split("T", xi, unavailable={1}) == (1 / 11, 2 / 11)
    assert C.regulars_split("Other", xi, set()) is None
