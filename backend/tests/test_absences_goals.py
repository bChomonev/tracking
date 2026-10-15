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
