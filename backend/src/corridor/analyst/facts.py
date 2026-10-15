"""Turn a season profile into the fact sheet the analyst writes from.

Every number the analyst may quote is computed here, rounded to the precision it should
be quoted at. The LLM does no arithmetic: if a comparison is worth making ("out-run in 5
of 6 matches"), it is pre-computed as a fact.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any


def _r(v: float | None, d: int) -> float | int | None:
    """Round half away from zero, like the page's JavaScript (Python's round() would turn
    98.5 into 98 while the page shows 99)."""
    if v is None:
        return None
    q = Decimal(str(v)).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP)
    return int(q) if d == 0 else float(q)


def _skew_fact(m: dict, labels_by_id: dict, dec: int) -> dict | None:
    s = m.get("skew")
    if not s or not s["flag"]:
        return None
    return {
        "match": labels_by_id[s["match_id"]],
        "value_in_that_match": _r(s["match_value"], dec),
        "season_average_without_it": _r(s["average_without"], dec),
        "league_rank_by_average_without_it": s["rank_without"],
    }


def _line_fact(m: dict, dec: int, side: str) -> dict | None:
    b = m.get(f"{side}_line")
    if not b:
        return None
    lo, hi = (b["p25"], b["p75"]) if m["direction"] > 0 else (b["p75"], b["p25"])
    if side == "best":
        return {
            "value": _r(b["value"], dec),
            "elite_range": [_r(lo, dec), _r(hi, dec)],
            "typical_match_reaches_line": b["typical_hits"],
            "typical_match_within_elite_range": b["typical_in_range"],
            "matches_reaching_line": b["matches_hit"],
            "matches_with_data": b["matches_counted"],
        }
    return {
        "value": _r(b["value"], dec),
        "typical_match_at_or_below_worst_line": b["typical_hits"],
        "matches_at_or_below_worst_line": b["matches_hit"],
        "matches_with_data": b["matches_counted"],
    }


def build_facts(profile: dict) -> dict[str, Any]:
    matches = profile["matches"]
    labels = [f"{m['opponent']} ({'H' if m['is_home'] else 'A'})" for m in matches]
    w = sum(m["result"] == "W" for m in matches)
    d = sum(m["result"] == "D" for m in matches)

    labels_by_id = {m["match_id"]: lbl for m, lbl in zip(matches, labels, strict=True)}
    metrics = []
    for m in profile["metrics"]:
        dec = m["decimals"]
        per_match = [
            {"match": lbl, "value": _r(x["value"], dec), "match_percentile": x["percentile"]}
            for lbl, x in zip(labels, m["matches"], strict=True)
        ]
        vals = [
            (x["value"], lbl)
            for x, lbl in zip(m["matches"], labels, strict=True)
            if x["value"] is not None
        ]
        better = (lambda a, b: a > b) if m["direction"] > 0 else (lambda a, b: a < b)
        n_better = sum(better(v, m["league_avg"]) for v, _ in vals)
        best = max(vals, key=lambda t: t[0] * m["direction"]) if vals else None
        worst = min(vals, key=lambda t: t[0] * m["direction"]) if vals else None
        metrics.append(
            {
                "key": m["key"],
                "label": m["label"],
                "stack": m["stack"],
                "better": "higher" if m["direction"] > 0 else "lower",
                "meaning": m["explain"],
                "typical_match": _r(m["value"], dec),
                "season_average": _r(m["season_average"], dec),
                "league_rank_by_season_average": m["rank_by_average"],
                "one_match_effect": _skew_fact(m, labels_by_id, dec),
                "decides_matches": _impact_fact(m),
                "elite_line": _line_fact(m, dec, "best"),
                "worst_line": _line_fact(m, dec, "worst"),
                "unit": m["unit"],
                "league_rank": m["rank"],
                "teams_ranked": m["of"],
                "league_percentile": m["percentile"],
                "league_average": _r(m["league_avg"], dec),
                "league_best": {
                    "team": m["league_best"]["team"],
                    "value": _r(m["league_best"]["value"], dec),
                },
                "league_worst": {
                    "team": m["league_worst"]["team"],
                    "value": _r(m["league_worst"]["value"], dec),
                },
                "matches_better_than_league_average": n_better,
                "matches_worse_than_league_average": len(vals) - n_better,
                "best_match": {"match": best[1], "value": _r(best[0], dec)} if best else None,
                "worst_match": {"match": worst[1], "value": _r(worst[0], dec)} if worst else None,
                "per_match": per_match,
            }
        )

    def behind(key: str) -> tuple[int, int]:
        """(matches where the opponent did more, matches with data)."""
        vals = [x["value"] for x in by_key[key]["matches"] if x["value"] is not None]
        return sum(v < 0 for v in vals), len(vals)

    by_key = {m["key"]: m for m in profile["metrics"]}
    outrun, n_dist = behind("distance_gap_km")
    outsprinted, n_spr = behind("sprints_gap")

    players = []
    for p in profile["players"]:
        players.append(
            {
                "name": p["name"],
                "role": p["position"],
                "minutes": p["minutes"],
                "appearances": p["apps"],
                "compared_with": f"{p['peers']} Premier League {p['position']}s",
                "effort_percentile": p["effort_percentile"],
                "top_speed_kmh": _r(p["top_speed_kmh"], 1),
                "per_90": {
                    v["label"]: {
                        "value": _r(v["value"], v["decimals"]),
                        "percentile": v["percentile"],
                    }
                    for v in p["metrics"].values()
                },
            }
        )

    return {
        "team": profile["team"],
        "season": profile["season"],
        "competition": "Premier League",
        "record": {
            "played": len(matches),
            "wins": w,
            "draws": d,
            "losses": len(matches) - w - d,
            "points": profile["record"]["points"],
            "league_position": profile["record"]["league_position"],
            "teams_in_league": profile["record"]["teams"],
            "goals_for": sum(m["goals_for"] for m in matches),
            "goals_against": sum(m["goals_against"] for m in matches),
            "xg_for": round(sum(m["xg"] for m in matches), 2),
            "xg_against": round(sum(m["xg_conceded"] for m in matches), 2),
            "matches_outrun_by_opponent": outrun,
            "matches_outran_opponent": n_dist - outrun,
            "matches_outsprinted_by_opponent": outsprinted,
            "matches_outsprinted_opponent": n_spr - outsprinted,
        },
        "matches": [
            {
                "match": lbl,
                "date": m["kickoff_utc"][:10],
                "score": f"{m['goals_for']}-{m['goals_against']}",
                "result": m["result"],
                "opponent_league_position": m.get("opponent_league_position"),
                "possession_pct": m["possession_pct"],
                "ppda": _r(m.get("ppda"), 1),
                "xg": m["xg"],
                "xg_conceded": m["xg_conceded"],
            }
            for lbl, m in zip(labels, matches, strict=True)
        ],
        "stacks": [
            {"name": s["name"], "key": s["id"], "average_league_percentile": s["score"]}
            for s in profile["stacks"]
        ],
        "metrics": metrics,
        "context": profile.get("context"),
        "best_line": _line_summary(profile, labels, "best"),
        "worst_line": _line_summary(profile, labels, "worst"),
        "proof": _proof_facts(profile, labels),
        "what_decides_matches": _focus_facts(profile, labels),
        "players": players,
        "notes": [
            "typical_match is the team's median match; league_rank, league_percentile and "
            "league_average/best/worst compare every team's median match, so one extreme game "
            "cannot carry a season. season_average is the plain mean. one_match_effect is set "
            "when a single match moves the average-based rank a lot; name that match when "
            "the average is mentioned.",
            "Percentiles: 100 = best in the league, 0 = worst, always oriented so higher is "
            "better.",
            "Player percentiles compare against Premier League players in the same role "
            "(CB, FB, CM, AM, W, ST) with at least 90 minutes.",
            f"Small sample: {len(matches)} matches so far.",
            "Shot-map metrics (shot distance, outside-box share, blocked share, set-piece and "
            "counter-attack npxG) exclude penalties and own goals. In goals_by_type, "
            "of_which_from_outside_box is a subset of the other categories.",
        ],
        "not_measured": NOT_MEASURED,
    }


def _line_summary(profile: dict, labels: list[str], side: str) -> dict | None:
    bl = profile.get(f"{side}_line")
    if not bl:
        return None
    if side == "best":
        what = (
            f"Median of each metric across the {bl['games']} league wins of the {bl['season']} "
            f"top four ({', '.join(bl['teams'])}); wins against 10 men from before the 70th "
            "minute excluded. elite_range is the middle half of those wins."
        )
    else:
        what = (
            f"Median of each metric across the {bl['games']} league defeats of the "
            f"{bl['season']} bottom four ({', '.join(bl['teams'])}); defeats where they were "
            "down to 10 men from before the 70th minute excluded. Hitting it is bad."
        )
    return {
        "what_it_is": what,
        "games_by_team": bl["games_by_team"],
        "typical_match_hits_line_on": bl["typical_hits"],
        "metrics_with_a_line": bl["metrics_compared"],
        "per_match": [
            {"match": lbl, "metrics_hitting_line": p["hits"], "of": p["of"]}
            for lbl, p in zip(labels, bl["per_match"], strict=True)
        ],
        "no_line_because_definition_changed": sorted(bl.get("not_comparable", {})),
    }


def _pct(x: float | None) -> int | None:
    return None if x is None else _r(100 * x, 0)


def _placement(label: str, x: dict) -> dict:
    """Where one match sits on the long (5 core lines) record."""
    out: dict[str, Any] = {"match": label}
    for side, res, word in (("best", "W", "won"), ("worst", "L", "lost")):
        core = x.get(f"{side}_core")
        if not core:
            continue
        out[f"core_{side}_lines_hit"] = f"{core['hits']} of {core['of']}"
        if core.get("history"):
            out[f"pct_of_such_matches_{word}"] = _pct(core["history"][res])
    return out


TIER_WORDS = {
    "decisive": "decides matches",
    "helps": "helps a little",
    "no_effect": "does not decide matches",
}
STATUS_WORDS = {
    "best": "at or above the elite line",
    "between": "between the lines",
    "worst": "at or below the relegation (worst) line",
}


def _impact_fact(m: dict) -> dict | None:
    imp = m.get("impact")
    if not imp:
        return None
    return {
        "tier": TIER_WORDS[imp["tier"]],
        "pct_won_when_reached_elite_line": _pct(imp["won_when_reached"]),
        "pct_won_when_not": _pct(imp["won_when_not"]),
        "pct_lost_when_at_worst_line": _pct(imp["lost_when_at_worst"]),
        "pct_lost_when_not": _pct(imp["lost_when_not"]),
        "team_matches_tested": imp["n"],
        "provisional": imp["provisional"],
    }


def _focus_facts(profile: dict, labels: list[str]) -> dict | None:
    f, pr = profile.get("focus"), profile.get("proof")
    if not f or not pr:
        return None
    by_key = {m["key"]: m["label"] for m in profile["metrics"]}
    tiers = {}
    for tier, t in f["tiers"].items():
        tiers[TIER_WORDS[tier]] = {
            "metrics": [
                {"metric": by_key[k], "united_typical_match": STATUS_WORDS[s]}
                for k, s in zip(t["metrics"], t["status"], strict=True)
            ],
            "count_at_elite_line": t["best"],
            "count_between": t["between"],
            "count_at_worst_line": t["worst"],
        }
    wf = pr["fotmob"]["weighted"]["walk_forward"]
    us_wf = pr["understat"]["weighted"]["walk_forward"]

    def score(x: dict, res: str) -> dict:
        h = x.get("history") or {}
        return {"score_0_to_100": _pct(x["share"]), f"pct_{res}": _pct(h.get(res[0].upper()))}

    return {
        "what_it_is": (
            "Every metric is put in a tier by how much reaching the elite line (or sinking to "
            "the worst line) changed results out of sample. The impact score counts the lines "
            "reached, each weighted by how much it decides matches; the history says how "
            "teams with that score did. Lead with the 'decides matches' tier; a strength on a "
            "metric that does not decide matches does not make up for weakness on one that "
            "does."
        ),
        "tiers": tiers,
        "weighting_check": {
            "what": "Weights learned only from earlier seasons, then tested on later ones. "
            "AUC: 0.5 = no better than a coin, 1 = perfect.",
            "long_record_auc_equal_lines": round(us_wf["best"]["auc_equal"], 2),
            "long_record_auc_weighted_lines": round(us_wf["best"]["auc_weighted"], 2),
            "this_season_auc_equal_lines": round(wf["best"]["auc_equal"], 2),
            "this_season_auc_weighted_lines": round(wf["best"]["auc_weighted"], 2),
        },
        "united_typical_match": {
            "elite_impact": score(pr["typical_weighted"]["best"], "won"),
            "relegation_impact": score(pr["typical_weighted"]["worst"], "lost"),
        },
        "united_matches": [
            {
                "match": lbl,
                "elite_impact": score(x["best_weighted"], "won"),
                "relegation_impact": score(x["worst_weighted"], "lost"),
            }
            for lbl, x in zip(labels, pr["matches"], strict=True)
        ],
    }


def _proof_facts(profile: dict, labels: list[str]) -> dict | None:
    pr = profile.get("proof")
    if not pr:
        return None
    us, fm = pr["understat"], pr["fotmob"]

    def bins(side: str, res: str) -> list[dict]:
        word = "won" if res == "W" else "lost"
        return [
            {
                "lines_hit_of_5": i,
                "matches": b["n"],
                f"pct_{word}": _pct(b[res]),
            }
            for i, b in enumerate(us[side]["bins"])
        ]

    lines = [
        {
            "line": m["label"],
            "pct_won_when_reached_best_line": _pct(m["rate_when_hit"]),
            "pct_won_when_not": _pct(m["rate_when_not"]),
            "matches_tested": m["n_hit"] + m["n_not"],
        }
        for m in fm["best"]["by_metric"]
    ]
    return {
        "what_it_is": (
            "Out-of-sample test: each season's best/worst lines were built from the previous "
            "season and tested on every Premier League team-match of the next season. Whole-"
            "match numbers are partly shaped by the scoreline, so this is association, not "
            "proof of cause."
        ),
        "long_record": {
            "source": "Understat, 5 core metrics: npxG for/against, PPDA, deep completions "
            "for/against",
            "team_matches": us["team_matches"],
            "seasons_tested": f"{us['pairs'][0]['tested_on']} to {us['pairs'][-1]['tested_on']}",
            "baseline_pct_won": _pct(us["baseline"]["W"]),
            "baseline_pct_lost": _pct(us["baseline"]["L"]),
            "best_lines": bins("best", "W"),
            "worst_lines": bins("worst", "L"),
        },
        "detailed_record": {
            "source": "FotMob, all profile metrics except goals prevented, finishing and big "
            "chances missed (they partly contain the result)",
            "team_matches": fm["team_matches"],
            "lines_ranked_by_how_much_they_separate_wins": lines,
        },
        "united_matches": [
            _placement(lbl, x) for lbl, x in zip(labels, pr["matches"], strict=True)
        ],
    }


# Things fans (and models) like to explain results with that our data cannot see. The
# analyst must not state or imply them as facts.
NOT_MEASURED = [
    "defensive line height and team shape / compactness",
    "where on the pitch the press happens or what triggers it",
    "off-the-ball movement, runs into space, and player positioning",
    "passing tempo or speed of ball circulation",
    "crosses, cut-backs or how a specific chance was created",
    "individual errors leading to goals",
    "tactical instructions, fitness, injuries, morale or confidence",
    "player-level shooting (shots, shot quality) — only team-level shot data is in this sheet",
]
