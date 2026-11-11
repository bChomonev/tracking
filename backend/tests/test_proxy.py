from corridor import proxy
from corridor.scripts.predictions import fill_from_fotmob


def _fm(mid, team, opp, is_home, gf, ga, xg, xga, passes, actions, box, box_c):
    return {
        "match_id": mid,
        "team": team,
        "opponent": opp,
        "is_home": is_home,
        "kickoff_utc": f"2026-11-{mid:02d}T15:00:00.000Z",
        "goals_for": gf,
        "goals_against": ga,
        "xg": xg,
        "xg_conceded": xga,
        "npxg": xg,
        "npxg_conceded": xga,
        "passes": passes,
        "tackles": actions,
        "interceptions": 0,
        "fouls": 0,
        "box_touches": box,
        "box_touches_conceded": box_c,
    }


def _pairs(n):
    """n matches where Understat is exactly 1.1 × FotMob xG, PPDA equals the proxy, and a
    deep completion is 4 box touches."""
    rows, pairs = [], []
    for i in range(1, n + 1):
        xg_h, xg_a = 0.5 + i * 0.05, 1.5 - i * 0.03
        h = _fm(i, "H", "A", True, 2, 1, xg_h, xg_a, 400 + i, 20, 20 + i, 10 + i)
        a = _fm(i, "A", "H", False, 1, 2, xg_a, xg_h, 300 + i, 25, 10 + i, 20 + i)
        rows += [h, a]
        for m, o in ((h, a), (a, h)):
            pairs.append(
                (
                    {
                        "us_xg": 1.1 * m["xg"],
                        "us_xga": 1.1 * m["xg_conceded"],
                        "us_npxg": 1.1 * m["xg"],
                        "us_npxga": 1.1 * m["xg_conceded"],
                        "ppda": o["passes"] / m["tackles"],
                        "ppda_allowed": m["passes"] / o["tackles"],
                        "deep_completions": m["box_touches"] / 4,
                        "deep_allowed": m["box_touches_conceded"] / 4,
                    },
                    m,
                    o,
                )
            )
    return rows, pairs


def test_fit_recovers_the_lines_and_apply_tags_the_row():
    rows, pairs = _pairs(20)
    fits = proxy.fit(pairs)
    assert set(fits) == set(proxy.PROXIES)
    assert abs(fits["us_npxg"]["b"] - 1.1) < 1e-6 and abs(fits["us_npxg"]["a"]) < 1e-6
    assert abs(fits["ppda"]["b"] - 1.0) < 1e-6
    opp = proxy.opponents(rows)
    new = _fm(99, "H", "A", True, 0, 0, 1.0, 2.0, 500, 10, 40, 8)
    new_o = _fm(99, "A", "H", False, 0, 0, 2.0, 1.0, 250, 50, 8, 40)
    got = proxy.apply(new, new_o, fits)
    assert got["understat_proxy"] is True
    assert got["us_npxg"] == 1.1 and got["ppda"] == 25.0 and got["deep_completions"] == 10
    assert got["ppda_allowed"] == 10.0  # own passes / opponent's actions
    assert opp[(1, "H")]["team"] == "A"


def test_fit_leaves_a_field_out_when_too_few_pairs():
    _, pairs = _pairs(5)
    assert proxy.fit(pairs) == {}


def test_fill_from_fotmob_turns_an_unplayed_fixture_into_a_played_one(tmp_path, monkeypatch):
    import json

    from corridor import leagues

    rows, pairs = _pairs(20)
    fits = proxy.fit(pairs)
    opp = proxy.opponents(rows)
    for r in rows:
        r.update(proxy.apply(r, opp[(r["match_id"], r["team"])], fits))
    (tmp_path / "team_matches.json").write_text(json.dumps(rows))
    monkeypatch.setattr(leagues, "DATA_DIR", tmp_path)
    monkeypatch.setattr("corridor.scripts.predictions.processed_dir", lambda s, lg: tmp_path)
    hist = [
        {
            "id": "u1",
            "season": 2026,
            "kickoff": "2026-11-03 15:00:00",
            "home": "Home FC",
            "away": "Away FC",
            "played": False,
        },
        {
            "id": "u2",
            "season": 2026,
            "kickoff": "2026-12-01 15:00:00",
            "home": "Home FC",
            "away": "Away FC",
            "played": False,
        },
    ]
    n = fill_from_fotmob(hist, 2026, leagues.LEAGUES["pl"], {"Home FC": "H", "Away FC": "A"})
    assert n == 1
    m = hist[0]
    assert m["played"] and m["result"] == "H" and (m["hg"], m["ag"]) == (2, 1)
    assert m["rows"]["home"]["team"] == "Home FC" and m["rows"]["home"]["source"] == "fotmob_proxy"
    assert m["rows"]["away"]["goals_for"] == 1 and m["rows"]["away"]["us_npxg"] > 0
    assert not hist[1]["played"]
