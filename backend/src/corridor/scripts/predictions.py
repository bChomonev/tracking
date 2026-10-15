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
from corridor.ingest.http import DATA_DIR, fetch_json
from corridor.scripts.build_season import _name_map

# Frozen after tuning on 2016-17 … 2019-20 (D-023). Re-tune only deliberately, never to
# chase the held-out seasons.
PARAMS = P.Params(half_life=24.0, carry=1.0, features="xg+goals+lines", C=0.05, adjust=True)
FIRST_TRAIN, FIRST_TEST = 2015, 2020
FEATURE_WORDS = {
    "xg_diff": "chance quality for and against",
    "xg_total": "how open their games are",
    "goal_diff": "goal difference",
    "elite_diff": "elite lines reached",
    "danger_diff": "worst lines hit",
}


def _pct(x: float) -> float:
    return round(100 * x, 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    args = ap.parse_args()
    season = args.season
    now = datetime.now(UTC).replace(tzinfo=None)

    hist = P.load_history(2014, season)
    scored, ratings = P.walk(hist, PARAMS)
    P.attach_odds(scored, range(FIRST_TRAIN, season + 1), current=season)

    # 1. Backtest: walk-forward on the held-out seasons (tuning used earlier seasons only).
    ev = P.evaluate(scored, PARAMS, range(FIRST_TEST, season + 1), FIRST_TRAIN)
    ev_goals = P.evaluate_goals(scored, range(FIRST_TEST, season + 1), FIRST_TRAIN)

    # 2. Final model: every played match up to now.
    train = [m for m in scored if m["played"] and m["season"] >= FIRST_TRAIN]
    model = P.Model(PARAMS).fit(train)
    goals = P.GoalsModel().fit(train)

    # Understat → FotMob names, so predictions link to the team pages.
    fm_fix = fotmob.league_matches(f"{season}/{season + 1}")
    us_dates = [
        {"datetime": m["kickoff"], "h": {"title": m["home"]}, "a": {"title": m["away"]}}
        for m in scored
        if m["season"] == season
    ]
    names = _name_map(fm_fix, us_dates)

    current = [m for m in scored if m["season"] == season]
    upcoming = [m for m in current if not m["played"]]
    probs = model.predict(upcoming) if upcoming else np.zeros((0, 3))
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

    nxt_ms = P.next_round(current, now)
    nxt = [fixture(m) for m in nxt_ms]
    # Scorelines and goal lines from the goals model (D-027). Win/draw/loss stays with the
    # logistic model, which won on the tuning seasons.
    if nxt_ms:
        lh, la = goals.rates(nxt_ms)
        for f, x, y in zip(nxt, lh, la, strict=True):
            mk = P.markets(goals.matrix(x, y))
            f["goals"] = {"exp_home": round(float(x), 2), "exp_away": round(float(y), 2)} | {
                k: (round(v, 4) if isinstance(v, float) else v) for k, v in mk.items() if k != "p"
            }

    # Team news (D-026): FotMob's unavailable lists for the next round, weighted by each
    # absent player's share of the team's minutes; a one-parameter shift of the odds.
    def _players(s: int) -> list[dict]:
        p = DATA_DIR / "processed" / str(s) / "player_matches.json"
        return json.loads(p.read_text()) if p.exists() else []

    contrib = AB.current_contributions(_players(season - 1), _players(season))
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
        f["p"] = [round(x, 4) for x in adj]
        pmap[f["id"]] = np.array(f["p"])
    if upcoming:
        probs = np.array([pmap[m["id"]] for m in upcoming])

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
    out_dir = DATA_DIR / "site" / str(season)
    log_path = out_dir / "predictions_log.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else {}
    made_at = datetime.now(UTC).isoformat()
    for f in nxt:
        if datetime.fromisoformat(f["kickoff"]) > now:
            log[f["id"]] = {k: f[k] for k in ("kickoff", "home", "away", "p", "p_base")} | {
                "made_at": made_at
            }
    by_id = {m["id"]: m for m in current}
    for fid, e in log.items():
        m = by_id.get(fid)
        if m and m["played"] and "result" not in e:
            e["result"] = m["result"]
            e["score"] = f"{m['hg']}-{m['ag']}"
            e["rps"] = P.rps(e["p"], m["result"])
            e["rps_base"] = P.rps(e.get("p_base", e["p"]), m["result"])
            for book in ("avg", "closing"):
                if book in m.get("odds", {}):
                    e[f"{book}_rps"] = P.rps(m["odds"][book], m["result"])
    log_path.write_text(json.dumps(log, indent=1))
    done = [e for e in log.values() if "result" in e]
    record = {
        "scored": len(done),
        "rps": float(np.mean([e["rps"] for e in done])) if done else None,
        "hits": sum(P.OUTCOMES[int(np.argmax(e["p"]))] == e["result"] for e in done),
        "rps_base": float(np.mean([e["rps_base"] for e in done])) if done else None,
        "avg_rps": float(np.mean([e["avg_rps"] for e in done if "avg_rps" in e]))
        if any("avg_rps" in e for e in done)
        else None,
        "matches": sorted(
            ({"id": k, **e} for k, e in log.items() if "result" in e),
            key=lambda e: e["kickoff"],
            reverse=True,
        )[:20],
    }

    out = {
        "generated_at": made_at,
        "params": vars(PARAMS),
        "next_round": nxt,
        "projection": projection,
        "backtest": ev,
        "backtest_goals": ev_goals,
        "record": record,
        "trained_on": len(train),
    }
    (out_dir / "predictions.json").write_text(json.dumps(out, indent=1))

    pooled = ev["pooled"]
    book = pooled.get("avg", {}).get("rps", float("nan"))
    print(
        f"backtest {FIRST_TEST}→{season}: model RPS {pooled['model']['rps']:.4f}, "
        f"base {pooled['base']['rps']:.4f}, bookmakers {book:.4f}"
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
