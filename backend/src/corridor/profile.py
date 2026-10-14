"""Season profile: a team's per-match metrics ranked against every team in the league.

All numbers come from one provider per metric (FotMob, or Understat for PPDA / deep
completions), so comparisons are always like-for-like.
"""

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean

import numpy as np

from corridor.engine.player_effort import percentile_ranks


@dataclass(frozen=True)
class ProfileMetric:
    key: str
    label: str
    stack: str
    direction: int  # +1 higher is better, -1 lower is better
    unit: str
    explain: str
    decimals: int = 1


STACKS = {
    "work": "Work rate & press",
    "progression": "Progression & territory",
    "attack": "Attack",
    "defence": "Defence",
}

METRICS: tuple[ProfileMetric, ...] = (
    ProfileMetric(
        "distance_km", "Distance covered", "work", +1, "km", "Total team running distance."
    ),
    ProfileMetric(
        "distance_gap_km",
        "Distance vs opponent",
        "work",
        +1,
        "km",
        "How much more (or less) the team ran than its opponent.",
    ),
    ProfileMetric("sprints", "Sprints", "work", +1, "", "Number of sprints by the whole team.", 0),
    ProfileMetric(
        "ppda",
        "Pressing (PPDA)",
        "work",
        -1,
        "",
        "Opponent passes allowed per defensive action. Lower = more aggressive press.",
    ),
    ProfileMetric("recoveries", "Ball recoveries", "work", +1, "", "Loose balls won back.", 0),
    ProfileMetric(
        "territory_pct",
        "Territory",
        "progression",
        +1,
        "%",
        "Share of all opposition-half passes in the match that were ours (a field-tilt proxy).",
    ),
    ProfileMetric(
        "line_breaking_passes",
        "Line-breaking passes",
        "progression",
        +1,
        "",
        "Passes that cut through an opponent line.",
        0,
    ),
    ProfileMetric(
        "passes_into_final_third",
        "Passes into final third",
        "progression",
        +1,
        "",
        "Completed passes that reach the attacking third.",
        0,
    ),
    ProfileMetric(
        "deep_completions",
        "Deep completions",
        "progression",
        +1,
        "",
        "Passes completed within ~20 m of goal (Understat).",
        0,
    ),
    ProfileMetric(
        "box_touches",
        "Touches in opp. box",
        "progression",
        +1,
        "",
        "How often we got the ball into the penalty area.",
        0,
    ),
    ProfileMetric(
        "npxg",
        "Chance quality created (npxG)",
        "attack",
        +1,
        "",
        "Non-penalty expected goals: how good our chances were.",
        2,
    ),
    ProfileMetric(
        "npxg_per_shot",
        "npxG per shot",
        "attack",
        +1,
        "",
        "Average quality of each shot. Low = speculative shooting.",
        3,
    ),
    ProfileMetric("big_chances", "Big chances", "attack", +1, "", "Clear-cut chances created.", 1),
    ProfileMetric(
        "finishing_delta",
        "Finishing (xGOT − xG)",
        "attack",
        +1,
        "",
        "Did shot placement add value? Positive = shots hit better than average.",
        2,
    ),
    ProfileMetric(
        "npxg_conceded",
        "Chance quality conceded (npxGA)",
        "defence",
        -1,
        "",
        "Non-penalty expected goals we allowed.",
        2,
    ),
    ProfileMetric(
        "npxg_per_shot_conceded",
        "npxGA per shot faced",
        "defence",
        -1,
        "",
        "Quality of the shots we allowed.",
        3,
    ),
    ProfileMetric(
        "big_chances_conceded",
        "Big chances conceded",
        "defence",
        -1,
        "",
        "Clear-cut chances we gave away.",
        1,
    ),
    ProfileMetric(
        "box_touches_conceded",
        "Opp. touches in our box",
        "defence",
        -1,
        "",
        "How often opponents got into our penalty area.",
        0,
    ),
    ProfileMetric(
        "goals_prevented",
        "GK goals prevented",
        "defence",
        +1,
        "",
        "Post-shot xG faced minus goals conceded. Positive = keeper saving us.",
        2,
    ),
)


def derive(r: dict) -> dict:
    """Add derived per-match metrics to a FotMob/Understat team-match record."""
    d = dict(r)
    d["distance_km"] = r["distance_m"] / 1000 if r.get("distance_m") else None
    d["distance_gap_km"] = (
        (r["distance_m"] - r["opp_distance_m"]) / 1000
        if r.get("distance_m") and r.get("opp_distance_m")
        else None
    )
    own, opp = r.get("opp_half_passes"), r.get("opp_half_passes_conceded")
    d["territory_pct"] = 100 * own / (own + opp) if own is not None and own + opp else None
    d["npxg_per_shot"] = r["npxg"] / r["shots"] if r.get("shots") else None
    d["npxg_per_shot_conceded"] = (
        r["npxg_conceded"] / r["shots_conceded"] if r.get("shots_conceded") else None
    )
    d["finishing_delta"] = (
        r["xgot"] - r["xg"] if r.get("xgot") is not None and r.get("xg") is not None else None
    )
    d["points"] = {"W": 3, "D": 1, "L": 0}[r["result"]]
    return d


def _pct(value: float | None, pool: list[float], direction: int) -> float | None:
    """0–100 percentile where 100 is always best."""
    if value is None or not pool:
        return None
    arr = np.asarray(pool, dtype=float) * direction
    return round(float(percentile_ranks(np.array([value * direction]), arr)[0]), 0)


def _avg(rows: list[dict], key: str) -> float | None:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return mean(vals) if vals else None


def team_profile(rows: list[dict], team: str) -> dict:
    rows = [derive(r) for r in rows]
    by_team: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_team[r["team"]].append(r)
    if team not in by_team:
        raise KeyError(f"{team!r} not found; teams: {sorted(by_team)}")

    team_avgs = {t: {m.key: _avg(rs, m.key) for m in METRICS} for t, rs in by_team.items()}
    mine = sorted(by_team[team], key=lambda r: r["kickoff_utc"])

    metrics = []
    for m in METRICS:
        season_vals = {t: a[m.key] for t, a in team_avgs.items() if a[m.key] is not None}
        ordered = sorted(season_vals.items(), key=lambda kv: kv[1] * m.direction, reverse=True)
        rank = next(i for i, (t, _) in enumerate(ordered, 1) if t == team)
        all_match_vals = [r[m.key] for r in rows if r.get(m.key) is not None]
        metrics.append(
            {
                "key": m.key,
                "label": m.label,
                "stack": m.stack,
                "direction": m.direction,
                "unit": m.unit,
                "explain": m.explain,
                "decimals": m.decimals,
                "value": season_vals.get(team),
                "rank": rank,
                "of": len(ordered),
                "percentile": _pct(season_vals.get(team), list(season_vals.values()), m.direction),
                "league_avg": mean(season_vals.values()),
                "league_best": {"team": ordered[0][0], "value": ordered[0][1]},
                "league_worst": {"team": ordered[-1][0], "value": ordered[-1][1]},
                "matches": [
                    {
                        "match_id": r["match_id"],
                        "value": r.get(m.key),
                        "percentile": _pct(r.get(m.key), all_match_vals, m.direction),
                    }
                    for r in mine
                ],
            }
        )

    stacks = []
    for sid, name in STACKS.items():
        pcts = [
            x["percentile"] for x in metrics if x["stack"] == sid and x["percentile"] is not None
        ]
        stacks.append({"id": sid, "name": name, "score": round(mean(pcts)) if pcts else None})

    table = sorted(
        (
            (t, sum(r["points"] for r in rs), sum(r["goals_for"] - r["goals_against"] for r in rs))
            for t, rs in by_team.items()
        ),
        key=lambda x: (x[1], x[2]),
        reverse=True,
    )
    position = next(i for i, (t, *_) in enumerate(table, 1) if t == team)

    return {
        "team": team,
        "matches": [
            {
                k: r.get(k)
                for k in (
                    "match_id",
                    "kickoff_utc",
                    "round",
                    "opponent",
                    "is_home",
                    "goals_for",
                    "goals_against",
                    "result",
                    "possession_pct",
                    "xg",
                    "xg_conceded",
                    "us_xpts",
                )
            }
            for r in mine
        ],
        "record": {
            "played": len(mine),
            "points": sum(r["points"] for r in mine),
            "league_position": position,
            "teams": len(table),
        },
        "stacks": stacks,
        "metrics": metrics,
    }


# (key, label, decimals). Distance is converted to km per 90.
PLAYER_METRICS = (
    ("distance_m", "Distance (km) / 90", 1),
    ("sprints", "Sprints / 90", 1),
    ("recoveries", "Recoveries / 90", 1),
    ("duels_won", "Duels won / 90", 1),
    ("line_breaking_passes", "Line-breaking passes / 90", 1),
    ("box_touches", "Box touches / 90", 1),
    ("xg_xa", "xG + xA / 90", 2),
)


def player_profiles(players: list[dict], team: str, min_minutes: int = 90) -> list[dict]:
    """Per-90 rates for a team's players, percentile-ranked within their position group
    across every league player with at least ``min_minutes``."""
    totals: dict[int, dict] = {}
    for p in players:
        t = totals.setdefault(
            p["player_id"],
            {
                "player_id": p["player_id"],
                "name": p["name"],
                "team": p["team"],
                "position": p["position"],
                "apps": 0,
                "minutes": 0.0,
                "top_speed_kmh": None,
                **{k: 0.0 for k, *_ in PLAYER_METRICS},
                "_phys_minutes": 0.0,
            },
        )
        mins = p.get("minutes") or 0
        t["apps"] += 1
        t["minutes"] += mins
        for k, *_ in PLAYER_METRICS:
            if k == "xg_xa":
                t[k] += (p.get("xg") or 0) + (p.get("xa") or 0)
            elif k in ("distance_m", "sprints"):
                if p.get(k) is not None:
                    t[k] += p[k]
            else:
                t[k] += p.get(k) or 0
        if p.get("distance_m") is not None:
            t["_phys_minutes"] += mins
        if p.get("top_speed_kmh"):
            t["top_speed_kmh"] = max(t["top_speed_kmh"] or 0, p["top_speed_kmh"])

    pool = [t for t in totals.values() if t["minutes"] >= min_minutes and t["position"] != "GK"]
    for t in pool:
        for k, *_ in PLAYER_METRICS:
            base = t["_phys_minutes"] if k in ("distance_m", "sprints") else t["minutes"]
            scale = 1 / 1000 if k == "distance_m" else 1
            t[f"{k}_p90"] = t[k] * scale / base * 90 if base else None

    out = []
    for t in pool:
        if t["team"] != team:
            continue
        peers = [o for o in pool if o["position"] == t["position"]]
        row = {k: t[k] for k in ("player_id", "name", "position", "apps", "top_speed_kmh")}
        row["minutes"] = int(t["minutes"])
        row["peers"] = len(peers)
        row["metrics"] = {}
        for k, label, decimals in PLAYER_METRICS:
            v = t[f"{k}_p90"]
            row["metrics"][k] = {
                "label": label,
                "value": v,
                "decimals": decimals,
                "percentile": _pct(
                    v, [o[f"{k}_p90"] for o in peers if o[f"{k}_p90"] is not None], +1
                ),
            }
        effort = [
            row["metrics"][k]["percentile"]
            for k in ("distance_m", "sprints", "recoveries", "duels_won")
            if row["metrics"][k]["percentile"] is not None
        ]
        row["effort_percentile"] = round(mean(effort)) if effort else None
        out.append(row)
    return sorted(out, key=lambda r: -r["minutes"])
