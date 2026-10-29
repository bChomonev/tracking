"""The round at a glance, every league together (D-073): the calls the models are surest
of, each tier next to its own track record, so the page audits itself.

Four lists, from what the league files already hold (nothing is recomputed):

* **Favourite to win or draw** (1X / X2) in tiers from 90%+ down to 70%, each with the
  held-out band record (D-060's "when we say it, does it happen?", pooled across leagues)
  and this season's running count from the prediction record.
* **Goals**: over or under 2.5 only when the scoreline model is at 70%+, with the pooled
  held-out calibration for that band and this season's running count.
* **Shooters**: the starters most likely to have two or more shots, with the held-out rate
  for players given that chance.
* **Cards**: the side likelier to draw more yellows when the cards model is at 60%+; the
  only cards call the backtest supports (D-030).

No "value against the bookmakers": the record shows the model a few thousandths of RPS
behind them, so a disagreement is not an edge.
"""

from typing import Any

TIERS = ((0.90, 1.01), (0.85, 0.90), (0.80, 0.85), (0.75, 0.80), (0.70, 0.75))
GOALS_MIN = 0.70
CARDS_MIN = 0.60
SHOOTERS_TOP = 12
OUTCOMES = ("H", "D", "A")


def _r(v: float | None, d: int = 3) -> float | None:
    return None if v is None else round(float(v), d)


def _dc(p: list[float]) -> tuple[int, float]:
    """(favourite index 0/2, chance to win or draw)."""
    fav = 0 if p[0] >= p[2] else 2
    return fav, p[fav] + p[1]


def _tier(x: float) -> int | None:
    for i, (lo, hi) in enumerate(TIERS):
        if lo <= x < hi:
            return i
    return None


def _pool(bins: list[dict], lo: float, hi: float, k_from: str, k_said: str, k_hit: str):
    """Pool calibration bins that start inside [lo, hi): n, mean said, mean happened."""
    sel = [b for b in bins if lo - 1e-9 <= b[k_from] < hi - 1e-9 and b.get("n")]
    n = sum(b["n"] for b in sel)
    if not n:
        return {"n": 0, "said": None, "happened": None}
    return {
        "n": n,
        "said": _r(sum(b[k_said] * b["n"] for b in sel) / n),
        "happened": _r(sum(b[k_hit] * b["n"] for b in sel) / n),
    }


def double_chance(leagues: dict[str, dict]) -> list[dict]:
    tiers: list[dict] = []
    for lo, hi in TIERS:
        tiers.append(
            {
                "from": lo,
                "to": min(hi, 1.0),
                "label": "90%+" if lo >= 0.9 else f"{round(lo * 100)}–{round(hi * 100)}%",
                "picks": [],
                "backtest": {"n": 0, "said": None, "happened": None},
                "season": {"n": 0, "hit": 0},
            }
        )
    bt_bins: list[dict] = []
    for key, lg in leagues.items():
        P = lg.get("predictions") or {}
        for f in P.get("next_round") or []:
            fav, p = _dc(f["p"])
            t = _tier(p)
            if t is None:
                continue
            tiers[t]["picks"].append(
                {
                    "league": key,
                    "competition": lg.get("competition"),
                    "id": f["id"],
                    "kickoff": f["kickoff"],
                    "home": f["home"],
                    "away": f["away"],
                    "favourite": f["home"] if fav == 0 else f["away"],
                    "call": "1X" if fav == 0 else "X2",
                    "p": _r(p),
                    "chances": [_r(x, 4) for x in f["p"]],
                    "drivers": [
                        {
                            "feature": d["feature"],
                            "team": f["home"] if d["favours"] == "home" else f["away"],
                        }
                        for d in f.get("drivers") or []
                    ],
                }
            )
        bt_bins += ((P.get("mistakes") or {}).get("bands") or {}).get("win_or_draw") or []
        for e in (P.get("record") or {}).get("matches") or []:
            if "result" not in e:
                continue
            fav, p = _dc(e["p"])
            t = _tier(p)
            if t is None:
                continue
            tiers[t]["season"]["n"] += 1
            tiers[t]["season"]["hit"] += e["result"] != ("A" if fav == 0 else "H")
    for t in tiers:
        t["backtest"] = _pool(bt_bins, t["from"], t["to"] + 1e-6, "from", "said", "happened")
        t["picks"].sort(key=lambda x: (-x["p"], x["kickoff"]))
    return tiers


def goals(leagues: dict[str, dict]) -> dict:
    picks: list[dict] = []
    bins: list[dict] = []
    season = {"over": {"n": 0, "hit": 0}, "under": {"n": 0, "hit": 0}}
    for key, lg in leagues.items():
        P = lg.get("predictions") or {}
        for f in P.get("next_round") or []:
            g = f.get("goals") or {}
            over = g.get("over_2_5")
            if over is None:
                continue
            if over >= GOALS_MIN or over <= 1 - GOALS_MIN:
                picks.append(
                    {
                        "league": key,
                        "competition": lg.get("competition"),
                        "id": f["id"],
                        "kickoff": f["kickoff"],
                        "home": f["home"],
                        "away": f["away"],
                        "call": "Over 2.5" if over >= GOALS_MIN else "Under 2.5",
                        "p": _r(over if over >= GOALS_MIN else 1 - over),
                        "expected_goals": _r(g.get("exp_home", 0) + g.get("exp_away", 0), 2),
                    }
                )
        bins += (P.get("backtest_goals") or {}).get("calibration_over") or []
        for e in (P.get("record") or {}).get("matches") or []:
            over = e.get("over_2_5")
            if over is None or "score" not in e:
                continue
            hg, ag = (int(x) for x in e["score"].split("-"))
            if over >= GOALS_MIN:
                season["over"]["n"] += 1
                season["over"]["hit"] += hg + ag > 2.5
            elif over <= 1 - GOALS_MIN:
                season["under"]["n"] += 1
                season["under"]["hit"] += hg + ag < 2.5
    over_bt = _pool(bins, GOALS_MIN, 1.01, "from", "predicted", "observed")
    under_bins = [
        b | {"predicted": 1 - b["predicted"], "observed": 1 - b["observed"]} for b in bins
    ]
    under_bt = _pool(under_bins, 0.0, 1 - GOALS_MIN, "from", "predicted", "observed")
    picks.sort(key=lambda x: (-x["p"], x["kickoff"]))
    return {
        "min": GOALS_MIN,
        "picks": picks,
        "backtest": {"over": over_bt, "under": under_bt},
        "season": season,
    }


def shooters(leagues: dict[str, dict]) -> dict:
    rows: list[dict] = []
    bins: list[dict] = []
    for key, lg in leagues.items():
        V = lg.get("previews") or {}
        P = {f["id"]: f for f in (lg.get("predictions") or {}).get("next_round") or []}
        for fid, fx in (V.get("fixtures") or {}).items():
            f = P.get(str(fid))
            if not f:
                continue
            for side in ("home", "away"):
                s = (fx.get("sides") or {}).get(side) or {}
                for sh in s.get("shooters") or []:
                    if sh.get("p_shot2") is None:
                        continue
                    rows.append(
                        {
                            "league": key,
                            "competition": lg.get("competition"),
                            "id": f["id"],
                            "kickoff": f["kickoff"],
                            "name": sh["name"],
                            "role": sh.get("role"),
                            "team": s.get("team"),
                            "opponent": f["away"] if side == "home" else f["home"],
                            "p_shot2": _r(sh["p_shot2"]),
                            "exp_shots": _r(sh.get("exp_shots"), 2),
                            "p_goal": _r(sh.get("p_goal")),
                        }
                    )
        for bt in ((V.get("backtest") or {}).get("shooters") or {}).values():
            bins += bt.get("calibration_shot2") or []
    rows.sort(key=lambda x: (-x["p_shot2"], x["name"]))
    top = rows[:SHOOTERS_TOP]
    for r in top:
        lo = int(r["p_shot2"] * 10) / 10
        r["band"] = _pool(bins, lo, lo + 0.1, "from", "predicted", "observed")
    return {"top": top, "n_starters": len(rows)}


def cards(leagues: dict[str, dict]) -> dict:
    picks: list[dict] = []
    n = hit = 0.0
    for key, lg in leagues.items():
        V = lg.get("previews") or {}
        P = {f["id"]: f for f in (lg.get("predictions") or {}).get("next_round") or []}
        for fid, fx in (V.get("fixtures") or {}).items():
            f, c = P.get(str(fid)), fx.get("cards") or {}
            if not f or not c:
                continue
            for side, p in (("home", c.get("p_home_more")), ("away", c.get("p_away_more"))):
                if p is not None and p >= CARDS_MIN:
                    picks.append(
                        {
                            "league": key,
                            "competition": lg.get("competition"),
                            "id": f["id"],
                            "kickoff": f["kickoff"],
                            "home": f["home"],
                            "away": f["away"],
                            "call": f"{f[side]} more yellows",
                            "p": _r(p),
                            "expected": [_r(c.get("exp_home"), 1), _r(c.get("exp_away"), 1)],
                        }
                    )
        bt = (V.get("backtest") or {}).get("cards") or {}
        if bt.get("matches") and bt.get("more_cards_side") is not None:
            n += bt["matches"]
            hit += bt["matches"] * bt["more_cards_side"]
    picks.sort(key=lambda x: (-x["p"], x["kickoff"]))
    return {
        "min": CARDS_MIN,
        "picks": picks,
        "backtest": {"n": int(n), "happened": _r(hit / n) if n else None},
    }


def build(leagues: dict[str, dict]) -> dict[str, Any]:
    """Everything the Picks tab shows, from the leagues' predictions and previews."""
    return {
        "double_chance": double_chance(leagues),
        "goals": goals(leagues),
        "shooters": shooters(leagues),
        "cards": cards(leagues),
        "leagues": {k: lg.get("competition") for k, lg in leagues.items()},
    }
