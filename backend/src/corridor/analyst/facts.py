"""Turn a season profile into the fact sheet the analyst writes from.

Every number the analyst may quote is computed here, rounded to the precision it should
be quoted at. The LLM does no arithmetic: if a comparison is worth making ("out-run in 5
of 6 matches"), it is pre-computed as a fact.
"""

from typing import Any


def _r(v: float | None, d: int) -> float | int | None:
    if v is None:
        return None
    return round(v) if d == 0 else round(v, d)


def build_facts(profile: dict) -> dict[str, Any]:
    matches = profile["matches"]
    labels = [f"{m['opponent']} ({'H' if m['is_home'] else 'A'})" for m in matches]
    w = sum(m["result"] == "W" for m in matches)
    d = sum(m["result"] == "D" for m in matches)

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
                "per_match_average": _r(m["value"], dec),
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
        "players": players,
        "notes": [
            "All metric values are per-match averages unless labelled per_match.",
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
