"""Stage 4: predict the next Premier League round, simulate the rest of the season, and keep
an honest running record of every prediction made before kickoff (D-023).

    uv run python -m corridor.scripts.predictions [--season 2026]

Reads the cached Understat seasons (build_season refreshes the current one) and the
football-data odds files; writes data/site/{season}/predictions.json and appends to
predictions_log.json. Both gitignored.
"""

import argparse
import json
from datetime import UTC, datetime

import numpy as np

from corridor import absences as AB
from corridor import predict as P
from corridor.ingest import fotmob
from corridor.ingest.fotmob import BASE
from corridor.ingest.http import fetch_json
from corridor.leagues import LEAGUES, processed_dir, site_dir
from corridor.scripts.build_season import _name_map

# Frozen after tuning on 2016-17 … 2019-20 (D-023). Re-tune only deliberately, never to
# chase the held-out seasons.
PARAMS = P.Params(half_life=24.0, carry=1.0, features="xg+goals+lines", C=0.05, adjust=True)
FIRST_TRAIN, FIRST_TEST = 2015, 2020
# Rolling calibration (D-036) is fitted on walk-forward predictions from this season on.
CAL_FIRST = FIRST_TRAIN + 1
FEATURE_WORDS = {
    "xg_diff": "chance quality for and against",
    "xg_total": "how open their games are",
    "goal_diff": "goal difference",
    "elite_diff": "elite lines reached",
    "danger_diff": "worst lines hit",
}


def _label(y: int) -> str:
    return f"{y}-{(y + 1) % 100:02d}"


def team_news_test(
    league, scored: list[dict], season: int, published: dict[str, np.ndarray]
) -> dict | None:
    """Out-of-sample test of the frozen team-news weight (fitted on the Premier League,
    D-026) on another league's own matches: RPS with and without the adjustment, applied
    to the walk-forward predictions as published (``published``: match id → chances)."""
    seasons = []
    for s in range(season - 2, season + 1):
        d = processed_dir(s, league)
        if (d / "team_matches.json").exists():
            seasons.append(
                (
                    s,
                    json.loads((d / "team_matches.json").read_text()),
                    json.loads((d / "player_matches.json").read_text()),
                )
            )
    if len(seasons) < 2:
        return None
    absn = AB.history(seasons)
    base_p = published
    rows = []
    for s, *_ in seasons:
        fm = fotmob.league_matches(f"{s}/{s + 1}", league.fotmob_id)
        us = [m for m in scored if m["season"] == s and m["played"]]
        nm = _name_map(
            fm,
            [
                {"datetime": m["kickoff"], "h": {"title": m["home"]}, "a": {"title": m["away"]}}
                for m in us
            ],
        )
        idx = {(a["home_team"], a["away_team"], a["kickoff"][:10]): a for a in absn.values()}
        for m in us:
            a = idx.get((nm.get(m["home"]), nm.get(m["away"]), m["kickoff"][:10]))
            if a and m["id"] in base_p:
                rows.append((m, a))
    if not rows:
        return None
    base = [P.rps(base_p[m["id"]], m["result"]) for m, _ in rows]
    adj_p = [
        AB.adjust(base_p[m["id"]], a["home"]["minutes"], a["away"]["minutes"]) for m, a in rows
    ]
    adj = [P.rps(p, m["result"]) for p, (m, _) in zip(adj_p, rows, strict=True)]
    big = [
        (m, a, p)
        for (m, a), p in zip(rows, adj_p, strict=True)
        if a["home"]["minutes"] - a["away"]["minutes"] >= 0.12
    ]
    label = f"{_label(seasons[0][0])} to {_label(seasons[-1][0])}"
    return {
        "matches": len(rows),
        "fits": [
            {
                "fit_on": "Premier League (frozen, not refitted)",
                "tested_on": f"{league.name} {label}",
                "n": len(rows),
                "k": AB.K_MINUTES,
                "rps_base": float(np.mean(base)),
                "rps_adjusted": float(np.mean(adj)),
            }
        ],
        "big_gap": {
            "n": len(big),
            "base_home_win": float(np.mean([base_p[m["id"]][0] for m, _, _ in big]))
            if big
            else None,
            "adjusted_home_win": float(np.mean([p[0] for _, _, p in big])) if big else None,
            "actual_home_win": float(np.mean([m["result"] == "H" for m, _, _ in big]))
            if big
            else None,
        },
    }


def _pct(x: float) -> float:
    return round(100 * x, 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--league", choices=tuple(LEAGUES), default="pl")
    args = ap.parse_args()
    league = LEAGUES[args.league]
    season = args.season
    now = datetime.now(UTC).replace(tzinfo=None)

    hist = P.load_history(2014, season, league=league.understat)
    scored, ratings = P.walk(hist, PARAMS)
    P.attach_odds(scored, range(FIRST_TRAIN, season + 1), current=season, code=league.odds_code)

    # 1. Backtest: walk-forward on the held-out seasons (tuning used earlier seasons only).
    #    Every season's predictions are calibrated with a temperature fitted on the earlier
    #    seasons' walk-forward predictions (D-036); this season's comes from all before it.
    #    Like team news (D-031), it is applied only where its held-out test shows a gain.
    wf = P.walk_forward(scored, PARAMS, range(CAL_FIRST, season + 1), FIRST_TRAIN)
    cal = P.calibrate(wf, CAL_FIRST)
    tests = range(FIRST_TEST, season + 1)
    ev = P.evaluate(scored, PARAMS, tests, FIRST_TRAIN, cal=cal)
    cal_test = {
        "rps_raw": ev["pooled"]["model_raw"]["rps"],
        "rps_calibrated": ev["pooled"]["model"]["rps"],
        "temperatures": {r["season"]: r["temperature"] for r in ev["seasons"]},
    }
    cal_on = cal_test["rps_calibrated"] < cal_test["rps_raw"]
    if not cal_on:
        cal = {s: (test, raw, raw, 1.0) for s, (test, raw, _, _) in cal.items()}
        ev = P.evaluate(scored, PARAMS, tests, FIRST_TRAIN, cal=cal)
    published = {
        m["id"]: p for test, _, pc, _ in cal.values() for m, p in zip(test, pc, strict=True)
    }
    ev_goals = P.evaluate_goals(scored, tests, FIRST_TRAIN, published)
    temperature = P.temperature_for(wf, season, CAL_FIRST) if cal_on else 1.0

    # 2. Final model: every played match up to now.
    train = [m for m in scored if m["played"] and m["season"] >= FIRST_TRAIN]
    model = P.Model(PARAMS).fit(train)
    goals = P.GoalsModel().fit(train)

    # Understat → FotMob names, so predictions link to the team pages.
    fm_fix = fotmob.league_matches(f"{season}/{season + 1}", league.fotmob_id)
    us_dates = [
        {"datetime": m["kickoff"], "h": {"title": m["home"]}, "a": {"title": m["away"]}}
        for m in scored
        if m["season"] == season
    ]
    names = _name_map(fm_fix, us_dates)

    current = [m for m in scored if m["season"] == season]
    upcoming = [m for m in current if not m["played"]]
    probs = P.temper(model.predict(upcoming), temperature) if upcoming else np.zeros((0, 3))
    pmap = {m["id"]: p for m, p in zip(upcoming, probs, strict=True)}

    def fixture(m: dict) -> dict:
        p = pmap[m["id"]]
        contrib = model.contributions(m)
        top = sorted(contrib.items(), key=lambda kv: -abs(kv[1]))[:2]
        return {
            "id": m["id"],
            "kickoff": m["kickoff"],
            "home": names.get(m["home"], m["home"]),
            "away": names.get(m["away"], m["away"]),
            "p": [round(float(x), 4) for x in p],
            "exp_home": round(m["x"]["exp_home"], 2),
            "exp_away": round(m["x"]["exp_away"], 2),
            "drivers": [
                {
                    "feature": FEATURE_WORDS[f],
                    "favours": "home" if v > 0 else "away",
                    "size": round(abs(v), 3),
                }
                for f, v in top
            ],
        }

    # FotMob's matchday numbers decide what "the next round" is (leftover Monday games and
    # rearranged midweek ones must not cut the following matchday short).
    fm_round = {(m["home"]["name"], m["away"]["name"]): m.get("round") for m in fm_fix}
    rounds = {
        (m["home"], m["away"]): fm_round.get(
            (names.get(m["home"], m["home"]), names.get(m["away"], m["away"]))
        )
        for m in current
    }
    rounds = {k: int(v) for k, v in rounds.items() if str(v or "").isdigit()}
    nxt_ms = P.next_round(current, now, rounds=rounds)
    nxt = [fixture(m) for m in nxt_ms]

    # Team news (D-026): FotMob's unavailable lists for the next round, weighted by each
    # absent player's share of the team's minutes; a one-parameter shift of the odds.
    def _players(s: int) -> list[dict]:
        p = processed_dir(s, league) / "player_matches.json"
        return json.loads(p.read_text()) if p.exists() else []

    contrib = AB.current_contributions(_players(season - 1), _players(season))
    # The adjustment is applied only where its own out-of-sample test shows a gain (D-031):
    # England's two cross-season tests did; Spain's clean test with the frozen weight didn't.
    tn_test = AB.TEST if league.key == "pl" else team_news_test(league, scored, season, published)
    tn_on = bool(tn_test) and all(f["rps_adjusted"] < f["rps_base"] for f in tn_test["fits"])
    fm_open = {
        (m["home"]["name"], m["away"]["name"]): m for m in fm_fix if not m["status"].get("finished")
    }
    for f in nxt:
        fm = fm_open.get((f["home"], f["away"]))
        f["p_base"] = f["p"]
        if not fm:
            continue
        try:
            url = f"{BASE}/matchDetails?matchId={fm['id']}"
            details = fetch_json("fotmob_upcoming", url, refresh=True)
        except Exception:  # noqa: BLE001 — no team news → keep the base prediction
            continue
        un = AB.unavailable(details)
        miss = {
            side: contrib.missing(f[side], [u["id"] for u in un[side]]) | {"n": len(un[side])}
            for side in ("home", "away")
        }
        f["absence"] = {k: {kk: round(vv, 3) for kk, vv in v.items()} for k, v in miss.items()}
        adj = AB.adjust(f["p_base"], miss["home"]["minutes"], miss["away"]["minutes"])
        f["absence"]["p_with"] = [round(x, 4) for x in adj]
        f["absence"]["applied"] = tn_on
        if tn_on:
            f["p"] = [round(x, 4) for x in adj]
            pmap[f["id"]] = np.array(f["p"])
    if upcoming:
        probs = np.array([pmap[m["id"]] for m in upcoming])

    # Scorelines and goal lines (D-027): the goals model sets how many goals to expect;
    # the split between the sides is set so the scorelines add up to the published
    # win/draw/loss chances (team news included).
    if nxt_ms:
        lh, la = goals.rates(nxt_ms)
        for f, x, y in zip(nxt, lh, la, strict=True):
            ah, aa = P.align(goals, float(x), float(y), f["p"])
            mk = P.markets(P.reconcile(goals.matrix(ah, aa), f["p"]))
            f["goals"] = {"exp_home": round(ah, 2), "exp_away": round(aa, 2)} | {
                k: (round(v, 4) if isinstance(v, float) else v) for k, v in mk.items() if k != "p"
            }
            f["goals"]["p_check"] = [round(v, 4) for v in mk["p"]]

    # 3. Season simulation from the current table and fixed ratings.
    table: dict[str, dict] = {}
    for m in current:
        for side in ("home", "away"):
            table.setdefault(m[side], {"points": 0, "gd": 0, "played": 0})
        if m["played"]:
            h, a = table[m["home"]], table[m["away"]]
            h["played"] += 1
            a["played"] += 1
            h["gd"] += m["hg"] - m["ag"]
            a["gd"] += m["ag"] - m["hg"]
            h["points"] += {"H": 3, "D": 1, "A": 0}[m["result"]]
            a["points"] += {"H": 0, "D": 1, "A": 3}[m["result"]]
    sim = P.simulate(table, upcoming, probs)
    projection = sorted(
        (
            {
                "team": names.get(t, t),
                "points_now": table[t]["points"],
                "played": table[t]["played"],
                **{k: round(v, 3) for k, v in s.items()},
            }
            for t, s in sim.items()
        ),
        key=lambda r: -r["points"],
    )

    # 4. Running record: freeze the latest pre-kickoff prediction of every fixture, then
    #    score it once the result is in.
    out_dir = site_dir(season, league)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "predictions_log.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else {}
    made_at = datetime.now(UTC).isoformat()
    for f in nxt:
        if datetime.fromisoformat(f["kickoff"]) > now:
            log[f["id"]] = {k: f[k] for k in ("kickoff", "home", "away", "p", "p_base")} | {
                "p_with_news": (f.get("absence") or {}).get("p_with"),
                "made_at": made_at,
            }
    by_id = {m["id"]: m for m in current}
    for fid, e in log.items():
        m = by_id.get(fid)
        if m and m["played"] and "result" not in e:
            e["result"] = m["result"]
            e["score"] = f"{m['hg']}-{m['ag']}"
            e["rps"] = P.rps(e["p"], m["result"])
            e["rps_base"] = P.rps(e.get("p_base", e["p"]), m["result"])
            if e.get("p_with_news"):
                e["rps_with_news"] = P.rps(e["p_with_news"], m["result"])
            for book in ("avg", "closing"):
                if book in m.get("odds", {}):
                    e[f"{book}_rps"] = P.rps(m["odds"][book], m["result"])
    log_path.write_text(json.dumps(log, indent=1))
    done = [e for e in log.values() if "result" in e]
    round_of = {m["id"]: rounds.get((m["home"], m["away"])) for m in current}
    record = {
        "scored": len(done),
        "rps": float(np.mean([e["rps"] for e in done])) if done else None,
        "hits": sum(P.OUTCOMES[int(np.argmax(e["p"]))] == e["result"] for e in done),
        "rps_base": float(np.mean([e["rps_base"] for e in done])) if done else None,
        "avg_rps": float(np.mean([e["avg_rps"] for e in done if "avg_rps" in e]))
        if any("avg_rps" in e for e in done)
        else None,
        # The whole season, each tagged with its FotMob matchday so the site can show it
        # round by round.
        "matches": sorted(
            ({"id": k, **e, "round": round_of.get(k)} for k, e in log.items() if "result" in e),
            key=lambda e: e["kickoff"],
            reverse=True,
        ),
    }

    out = {
        "generated_at": made_at,
        "params": vars(PARAMS),
        "temperature": temperature,
        "calibration_test": cal_test,
        "calibration_applied": cal_on,
        "next_round": nxt,
        "projection": projection,
        "backtest": ev,
        "backtest_goals": ev_goals,
        "team_news_test": tn_test,
        "team_news_applied": tn_on,
        "record": record,
        "trained_on": len(train),
    }
    (out_dir / "predictions.json").write_text(json.dumps(out, indent=1))

    pooled = ev["pooled"]
    book = pooled.get("avg", {}).get("rps", float("nan"))
    print(
        f"backtest {FIRST_TEST}→{season}: model RPS {pooled['model']['rps']:.4f} "
        f"(uncalibrated {pooled['model_raw']['rps']:.4f}), base {pooled['base']['rps']:.4f}, "
        f"bookmakers {book:.4f}; temperature now {temperature:.2f}"
    )
    for f in nxt:
        pr = " / ".join(f"{_pct(x):4.1f}" for x in f["p"])
        print(f"  {f['kickoff'][:16]} {f['home']:>24} – {f['away']:<24} {pr}")
    for r in projection[:4] + projection[-3:]:
        print(
            f"  {r['team']:<24} {r['points']:5.1f} pts  title {_pct(r['title']):5.1f}%  "
            f"top4 {_pct(r['top4']):5.1f}%  rel {_pct(r['relegation']):5.1f}%"
        )
    print(f"record: {record['scored']} scored; wrote {out_dir / 'predictions.json'}")


if __name__ == "__main__":
    main()
