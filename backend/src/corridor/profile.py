"""Season profile: a team's per-match metrics ranked against every team in the league.

All numbers come from one provider per metric (FotMob, or Understat for PPDA / deep
completions), so comparisons are always like-for-like.
"""

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean, median

import numpy as np

from corridor.engine.player_effort import percentile_ranks
from corridor.ingest.fotmob import STATES

MIN_STATE_MINUTES = 20.0  # a match counts for a state only if it spent this long in it
MIN_STATE_SHOTS = 3  # per-shot quality needs at least this many shots in the state


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
    "state": "By game state",
}

STATE_WORDS = {"level": "level", "ahead": "ahead", "behind": "behind"}


def _state_metrics() -> tuple["ProfileMetric", ...]:
    """Shot-derived metrics split by the score at the time (D-051). Each is measured over
    the minutes the team spent in that state, so a match counts only if it spent 20+
    minutes there; per-shot quality also needs 3+ shots."""
    out = []
    for s in STATES:
        w = STATE_WORDS[s]
        guard = f" Only matches with 20+ minutes {w} count."
        out += [
            ProfileMetric(
                f"{s}_npxg_p90",
                f"When {w}: chance quality created (npxG per 90)",
                "state",
                +1,
                "",
                f"Expected goals created per 90 minutes while the score was {w}, penalties "
                f"excluded.{guard} Higher is better.",
                2,
            ),
            ProfileMetric(
                f"{s}_npxg_p90_conceded",
                f"When {w}: chance quality conceded (npxGA per 90)",
                "state",
                -1,
                "",
                f"Expected goals the opponent created per 90 minutes while the score was {w}, "
                f"penalties excluded.{guard} Lower is better.",
                2,
            ),
            ProfileMetric(
                f"{s}_npxg_per_shot",
                f"When {w}: npxG per shot",
                "state",
                +1,
                "",
                f"How good the average shot was while the score was {w} (0.10 = 1 in 10)."
                f"{guard} Higher is better.",
                3,
            ),
            ProfileMetric(
                f"{s}_npxg_per_shot_conceded",
                f"When {w}: npxGA per shot faced",
                "state",
                -1,
                "",
                f"How good the average shot the team allowed was while the score was {w}."
                f"{guard} Lower is better.",
                3,
            ),
            ProfileMetric(
                f"{s}_shots_p90",
                f"When {w}: shots per 90",
                "state",
                +1,
                "",
                f"Non-penalty shots per 90 minutes while the score was {w}.{guard} Higher is "
                "better, but read it with npxG per shot: many hopeful shots are not a plan.",
                1,
            ),
            ProfileMetric(
                f"{s}_shots_p90_conceded",
                f"When {w}: shots faced per 90",
                "state",
                -1,
                "",
                f"Non-penalty shots the opponent took per 90 minutes while the score was {w}."
                f"{guard} Lower is better.",
                1,
            ),
            ProfileMetric(
                f"{s}_shot_distance_m",
                f"When {w}: shot distance",
                "state",
                -1,
                "m",
                f"Average distance from goal of the team's shots while the score was {w}."
                f"{guard} Lower is better: closer shots are better chances.",
            ),
        ]
    return tuple(out)


METRICS: tuple[ProfileMetric, ...] = (
    ProfileMetric(
        "distance_km",
        "Distance covered",
        "work",
        +1,
        "km",
        "Total distance the whole team ran. More is better.",
    ),
    ProfileMetric(
        "distance_gap_km",
        "Distance vs opponent",
        "work",
        +1,
        "km",
        (
            "How much further the team ran than the opponent; negative = the opponent ran "
            "more. Higher is better."
        ),
    ),
    ProfileMetric(
        "sprints",
        "Sprints",
        "work",
        +1,
        "",
        "Number of sprints by the whole team. More is better.",
        0,
    ),
    ProfileMetric(
        "sprints_gap",
        "Sprints vs opponent",
        "work",
        +1,
        "",
        (
            "How many more sprints the team made than the opponent; negative = fewer. Higher "
            "is better."
        ),
        0,
    ),
    ProfileMetric(
        "distance_oop_adj_km",
        "Running without the ball",
        "work",
        +1,
        "km",
        (
            "Distance run while the opponent had the ball, scaled to a match where they have "
            "it half the time, so possession doesn't flatter or punish it (UEFA data, "
            "Champions League only). More is better."
        ),
    ),
    ProfileMetric(
        "high_intensity_runs",
        "High-intensity runs",
        "work",
        +1,
        "",
        (
            "Runs above high-intensity speed by the whole team (UEFA data, Champions League "
            "only). More is better."
        ),
        0,
    ),
    ProfileMetric(
        "ppda",
        "Pressing (PPDA)",
        "work",
        -1,
        "",
        (
            "Pressing: how many passes the opponent is allowed before the team wins the ball "
            "back or makes a tackle. Lower is better: a low number means an aggressive press."
        ),
    ),
    ProfileMetric(
        "recoveries",
        "Ball recoveries",
        "work",
        +1,
        "",
        "Loose balls the team won back. More is better.",
        0,
    ),
    ProfileMetric(
        "territory_pct",
        "Territory",
        "progression",
        +1,
        "%",
        (
            "How much of the match was played in the opponent's half: the team's share of all"
            " passes made in the opponent's half. Higher is better."
        ),
    ),
    ProfileMetric(
        "pass_accuracy_pct",
        "Pass accuracy",
        "progression",
        +1,
        "%",
        "Share of the team's passes that found a teammate. Higher is better.",
    ),
    ProfileMetric(
        "opp_half_pass_pct",
        "Passes in opp. half",
        "progression",
        +1,
        "%",
        (
            "Share of the team's completed passes played in the opponent's half: how far up"
            " the pitch it keeps the ball. Higher is better."
        ),
        0,
    ),
    ProfileMetric(
        "long_ball_pct",
        "Long balls",
        "progression",
        -1,
        "%",
        (
            "Share of the team's completed passes that were long balls. A style number: "
            "better sides usually play shorter, so lower counts as better."
        ),
    ),
    ProfileMetric(
        "line_breaking_passes",
        "Line-breaking passes",
        "progression",
        +1,
        "",
        "Passes that go through a line of opponents. More is better.",
        0,
    ),
    ProfileMetric(
        "passes_into_final_third",
        "Passes into final third",
        "progression",
        +1,
        "",
        "Completed passes into the attacking third of the pitch. More is better.",
        0,
    ),
    ProfileMetric(
        "deep_completions",
        "Deep completions",
        "progression",
        +1,
        "",
        ("Passes completed within about 20 m of the opponent's goal (Understat). More is better."),
        0,
    ),
    ProfileMetric(
        "box_touches",
        "Touches in opp. box",
        "progression",
        +1,
        "",
        "Touches the team had in the opponent's penalty area. More is better.",
        0,
    ),
    ProfileMetric(
        "npxg",
        "Chance quality created (npxG)",
        "attack",
        +1,
        "",
        (
            "Expected goals without penalties: how many goals the team's chances were worth "
            "on average. Higher is better."
        ),
        2,
    ),
    ProfileMetric(
        "npxg_per_shot",
        "npxG per shot",
        "attack",
        +1,
        "",
        (
            "How good the team's average shot is: its chance of going in (0.10 = 1 in 10). "
            "Higher is better; a low number means lots of long-range or difficult shots."
        ),
        3,
    ),
    ProfileMetric(
        "big_chances",
        "Big chances",
        "attack",
        +1,
        "",
        "Clear-cut chances the team created. More is better.",
        1,
    ),
    ProfileMetric(
        "finishing_delta",
        "Finishing (xGOT − xG)",
        "attack",
        +1,
        "",
        (
            "How well shots were placed: expected goals on target minus expected goals. "
            "Positive = shots placed better than average. Higher is better."
        ),
        2,
    ),
    ProfileMetric(
        "shot_distance_m",
        "Average shot distance",
        "attack",
        -1,
        "m",
        (
            "Average distance from goal of the team's shots (penalties excluded). Lower is "
            "better: closer shots are better chances."
        ),
    ),
    ProfileMetric(
        "outside_box_shot_pct",
        "Shots from outside the box",
        "attack",
        -1,
        "%",
        "Share of the team's shots taken from outside the penalty area. Lower is better.",
        0,
    ),
    ProfileMetric(
        "blocked_shot_pct",
        "Shots blocked",
        "attack",
        -1,
        "%",
        (
            "Share of the team's shots blocked by a defender, often a sign of shooting into a"
            " crowd. Lower is better."
        ),
        0,
    ),
    ProfileMetric(
        "big_chances_missed",
        "Big chances missed",
        "attack",
        -1,
        "",
        "Clear-cut chances the team didn't score. Fewer is better.",
        1,
    ),
    ProfileMetric(
        "npxg_set_piece",
        "Set-piece chance quality",
        "attack",
        +1,
        "",
        (
            "Expected goals from the team's corners, free kicks and throw-in routines. Higher"
            " is better."
        ),
        2,
    ),
    ProfileMetric(
        "shots_conceded",
        "Shots conceded",
        "defence",
        -1,
        "",
        (
            "Shots the opponent took at the team's goal. Fewer is better: each one is a "
            "chance to concede. How good those shots were (npxGA per shot) matters even more."
        ),
        1,
    ),
    ProfileMetric(
        "npxg_conceded",
        "Chance quality conceded (npxGA)",
        "defence",
        -1,
        "",
        (
            "Expected goals the team allowed, without penalties: how many goals the "
            "opponent's chances were worth on average. Lower is better."
        ),
        2,
    ),
    ProfileMetric(
        "npxg_per_shot_conceded",
        "npxGA per shot faced",
        "defence",
        -1,
        "",
        (
            "How good the average shot the team allowed was: its chance of going in (0.10 = 1"
            " in 10). Lower is better: it means the opponent only got hopeful shots."
        ),
        3,
    ),
    ProfileMetric(
        "big_chances_conceded",
        "Big chances conceded",
        "defence",
        -1,
        "",
        "Clear-cut chances the team allowed the opponent. Fewer is better.",
        1,
    ),
    ProfileMetric(
        "box_touches_conceded",
        "Opp. touches in our box",
        "defence",
        -1,
        "",
        "Touches the opponent had in the team's penalty area. Fewer is better.",
        0,
    ),
    ProfileMetric(
        "shot_distance_conceded_m",
        "Distance of shots conceded",
        "defence",
        +1,
        "m",
        (
            "Average distance from the team's goal of the opponent's shots. Higher is better:"
            " it means they were kept further out."
        ),
    ),
    ProfileMetric(
        "npxg_fast_break_conceded",
        "Counter-attack chances conceded",
        "defence",
        -1,
        "",
        "Expected goals the opponent created from counter-attacks. Lower is better.",
        2,
    ),
    ProfileMetric(
        "npxg_set_piece_conceded",
        "Set-piece chances conceded",
        "defence",
        -1,
        "",
        (
            "Expected goals the opponent created from corners, free kicks and throw-ins. "
            "Lower is better."
        ),
        2,
    ),
    ProfileMetric(
        "goals_prevented",
        "GK goals prevented",
        "defence",
        +1,
        "",
        (
            "How many goals the goalkeeper saved beyond what was expected: expected goals on "
            "target faced minus goals conceded. Positive = the keeper is saving the team. "
            "Higher is better."
        ),
        2,
    ),
    *_state_metrics(),
)
STATE_KEYS = frozenset(m.key for m in METRICS if m.stack == "state")


def derive(r: dict) -> dict:
    """Add derived per-match metrics to a FotMob/Understat team-match record."""
    d = dict(r)
    d["distance_km"] = r["distance_m"] / 1000 if r.get("distance_m") else None
    d["distance_gap_km"] = (
        (r["distance_m"] - r["opp_distance_m"]) / 1000
        if r.get("distance_m") and r.get("opp_distance_m")
        else None
    )
    oop, opp_poss = r.get("distance_oop_km"), r.get("opp_possession_pct_uefa")
    d["distance_oop_adj_km"] = oop * 50 / opp_poss if oop is not None and opp_poss else None
    d["sprints_gap"] = (
        r["sprints"] - r["opp_sprints"]
        if r.get("sprints") is not None and r.get("opp_sprints") is not None
        else None
    )
    own, opp = r.get("opp_half_passes"), r.get("opp_half_passes_conceded")
    d["territory_pct"] = 100 * own / (own + opp) if own is not None and own + opp else None
    passes, acc = r.get("passes"), r.get("accurate_passes")
    d["pass_accuracy_pct"] = 100 * acc / passes if passes and acc is not None else None
    d["opp_half_pass_pct"] = 100 * own / acc if acc and own is not None else None
    d["long_ball_pct"] = (
        100 * r["accurate_long_balls"] / acc
        if acc and r.get("accurate_long_balls") is not None
        else None
    )
    d["npxg_per_shot"] = r["npxg"] / r["shots"] if r.get("shots") else None
    d["npxg_per_shot_conceded"] = (
        r["npxg_conceded"] / r["shots_conceded"] if r.get("shots_conceded") else None
    )
    d["finishing_delta"] = (
        r["xgot"] - r["xg"] if r.get("xgot") is not None and r.get("xg") is not None else None
    )
    for side in ("", "_conceded"):
        n = r.get(f"np_shots{side}")
        has = n is not None and n > 0
        d[f"shot_distance{side}_m"] = r[f"shot_distance_sum_m{side}"] / n if has else None
        if not side:
            d["outside_box_shot_pct"] = 100 * r["shots_outside_box"] / n if has else None
            d["blocked_shot_pct"] = 100 * r["shots_blocked"] / n if has else None
    for s in STATES:
        mins = r.get(f"{s}_minutes")
        ok = mins is not None and mins >= MIN_STATE_MINUTES
        for side in ("", "_conceded"):
            n, xg = r.get(f"{s}_np_shots{side}"), r.get(f"{s}_npxg{side}")
            d[f"{s}_shots_p90{side}"] = 90 * n / mins if ok and n is not None else None
            d[f"{s}_npxg_p90{side}"] = 90 * xg / mins if ok and xg is not None else None
            d[f"{s}_npxg_per_shot{side}"] = (
                xg / n if ok and n and n >= MIN_STATE_SHOTS and xg is not None else None
            )
        n = r.get(f"{s}_np_shots")
        d[f"{s}_shot_distance_m"] = (
            r[f"{s}_shot_distance_sum_m"] / n if ok and n and n >= MIN_STATE_SHOTS else None
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


SKEW_MIN_MATCHES = 4


def _med(rows: list[dict], key: str) -> float | None:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return median(vals) if vals else None


def _order(vals: dict[str, float], direction: int) -> list[str]:
    """Teams best-first."""
    return sorted(vals, key=lambda t: vals[t] * direction, reverse=True)


def _skew(mine: list[dict], m: ProfileMetric, averages: dict[str, float], team: str) -> dict | None:
    """Is the season average carried by one match? Finds the match whose removal moves the
    average most, and flags the metric when dropping it moves the team's average-based rank
    by at least a fifth of the league (min 3 places)."""
    vals = [(r, r[m.key]) for r in mine if r.get(m.key) is not None]
    if len(vals) < SKEW_MIN_MATCHES:
        return None
    total = sum(v for _, v in vals)
    without = {r["match_id"]: (total - v) / (len(vals) - 1) for r, v in vals}
    driver, value = max(vals, key=lambda rv: abs(without[rv[0]["match_id"]] - averages[team]))
    rank_with = _order(averages, m.direction).index(team) + 1
    rank_without = (
        _order(averages | {team: without[driver["match_id"]]}, m.direction).index(team) + 1
    )
    threshold = max(3, round(len(averages) / 5))
    return {
        "flag": abs(rank_with - rank_without) >= threshold,
        "match_id": driver["match_id"],
        "match_value": value,
        "average_without": without[driver["match_id"]],
        "rank_without": rank_without,
    }


def team_profile(rows: list[dict], team: str) -> dict:
    rows = [derive(r) for r in rows]
    by_team: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_team[r["team"]].append(r)
    if team not in by_team:
        raise KeyError(f"{team!r} not found; teams: {sorted(by_team)}")

    team_avgs = {t: {m.key: _avg(rs, m.key) for m in METRICS} for t, rs in by_team.items()}
    team_meds = {t: {m.key: _med(rs, m.key) for m in METRICS} for t, rs in by_team.items()}
    mine = sorted(by_team[team], key=lambda r: r["kickoff_utc"])

    metrics = []
    for m in METRICS:
        # Rank on the typical (median) match so one freak game can't carry a season.
        typical = {t: a[m.key] for t, a in team_meds.items() if a[m.key] is not None}
        if team not in typical:
            continue  # metric not available in this competition
        ordered = _order(typical, m.direction)
        averages = {t: a[m.key] for t, a in team_avgs.items() if a[m.key] is not None}
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
                "value": typical[team],
                "rank": ordered.index(team) + 1,
                "of": len(ordered),
                "percentile": _pct(typical[team], list(typical.values()), m.direction),
                "league_avg": mean(typical.values()),
                "league_best": {"team": ordered[0], "value": typical[ordered[0]]},
                "league_worst": {"team": ordered[-1], "value": typical[ordered[-1]]},
                "season_average": averages[team],
                "rank_by_average": _order(averages, m.direction).index(team) + 1,
                "skew": _skew(mine, m, averages, team),
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
    positions = {t: i for i, (t, *_) in enumerate(table, 1)}
    position = positions[team]

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
                    "ppda",
                    *(f"{s}_minutes" for s in STATES),
                )
            }
            | {"opponent_league_position": positions[r["opponent"]]}
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
        "context": _context(rows, team_avgs, mine, positions, team),
    }


GOAL_TYPES = ("open_play", "fast_break", "set_piece", "penalty")


def _context(
    rows: list[dict],
    team_avgs: dict[str, dict],
    mine: list[dict],
    positions: dict[str, int],
    team: str,
) -> dict:
    """Pre-computed comparisons the analyst would otherwise be tempted to guess or
    calculate: how goals came, whether possession explains running, and whether the
    press changes with the opponent."""
    goals = {
        side: {g: sum(r.get(f"goals_{g}{suffix}") or 0 for r in mine) for g in GOAL_TYPES}
        for side, suffix in (("scored", ""), ("conceded", "_conceded"))
    }
    for side, suffix in (("scored", ""), ("conceded", "_conceded")):
        total = sum(r["goals_for" if side == "scored" else "goals_against"] for r in mine)
        goals[side]["own_goals"] = total - sum(goals[side].values())
        goals[side]["total"] = total
        goals[side]["of_which_from_outside_box"] = sum(
            r.get(f"goals_outside_box{suffix}") or 0 for r in mine
        )

    pairs = [
        (r["possession_pct"], r["distance_km"])
        for r in rows
        if r.get("possession_pct") is not None and r.get("distance_km") is not None
    ]
    corr = float(np.corrcoef(*zip(*pairs, strict=True))[0, 1]) if len(pairs) > 2 else None
    poss = {t: _avg_list([r["possession_pct"] for r in rs]) for t, rs in _by_team(rows).items()}
    high = sorted(
        (t for t, p in poss.items() if p is not None and p >= 55),
        key=lambda t: -(team_avgs[t]["distance_km"] or 0),
    )

    half = len(positions) // 2
    top = [
        r["ppda"] for r in mine if r.get("ppda") is not None and positions[r["opponent"]] <= half
    ]
    bottom = [
        r["ppda"] for r in mine if r.get("ppda") is not None and positions[r["opponent"]] > half
    ]

    return {
        "goals_by_type": goals,
        "game_state_minutes": _state_minutes_context(rows, mine, team),
        "possession_vs_distance": {
            "correlation_all_team_matches": round(corr, 2) if corr is not None else None,
            "team_avg_possession_pct": round(poss[team], 1),
            "high_possession_teams": [
                {
                    "team": t,
                    "avg_possession_pct": round(poss[t], 1),
                    "avg_distance_km": round(team_avgs[t]["distance_km"], 1),
                }
                for t in high
                if team_avgs[t]["distance_km"] is not None
            ],
            "rank_for_distance_among_high_possession_teams": (
                high.index(team) + 1 if team in high else None
            ),
        },
        "ppda_by_opponent_strength": {
            "vs_top_half": {"matches": len(top), "avg_ppda": _round(_avg_list(top), 1)},
            "vs_bottom_half": {"matches": len(bottom), "avg_ppda": _round(_avg_list(bottom), 1)},
            "note": "Opponent strength = current league position. Lower PPDA = harder press.",
        },
    }


def _state_minutes_context(rows: list[dict], mine: list[dict], team: str) -> dict | None:
    """Share of the team's minutes spent level, ahead and behind, against the league and
    ranked (most time ahead = 1st). A result, not a performance: context, not a line."""
    if not any(r.get("level_minutes") is not None for r in mine):
        return None
    shares = {}
    for t, rs in _by_team(rows).items():
        tot = sum(sum(r.get(f"{s}_minutes") or 0 for s in STATES) for r in rs)
        if tot:
            shares[t] = {s: 100 * sum(r.get(f"{s}_minutes") or 0 for r in rs) / tot for s in STATES}
    out = {
        "note": (
            "Share of minutes played level, ahead and behind on a 90-minute clock. This "
            "follows from results, so it has no line; it says which state the other "
            "numbers come from."
        )
    }
    for s in STATES:
        ordered = sorted(shares, key=lambda t: shares[t][s], reverse=True)
        out[s] = {
            "team_pct": round(shares[team][s], 1),
            "league_avg_pct": round(mean(v[s] for v in shares.values()), 1),
            "rank_most_time": ordered.index(team) + 1,
            "of": len(ordered),
        }
    return out


def _by_team(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r["team"]].append(r)
    return out


def _avg_list(vals: list[float]) -> float | None:
    return mean(vals) if vals else None


def _round(v: float | None, d: int) -> float | None:
    return None if v is None else round(v, d)


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


_FALLBACK_ROLE = {"GK": "GK", "DEF": "CB", "MID": "CM", "FWD": "ST"}


def player_profiles(players: list[dict], team: str, min_minutes: int = 90) -> list[dict]:
    """Per-90 rates for a team's players, percentile-ranked within their role (CB, FB, CM,
    AM, W, ST — the one they played most minutes in) across every league player with at
    least ``min_minutes``."""
    totals: dict[int, dict] = {}
    role_minutes: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
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
        role = p.get("role") or _FALLBACK_ROLE.get(p["position"])
        if role:
            # Starts decide the role; sub minutes only count when a player never started.
            role_minutes[p["player_id"]][role] += mins if p.get("started") else mins / 1000
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

    for pid, t in totals.items():
        roles = role_minutes.get(pid)
        t["position"] = max(roles.items(), key=lambda kv: kv[1])[0] if roles else "UNK"
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


MIN_SHOTS_LISTED = 3
GROUP_ROLE = {"GK": "GK", "DEF": "CB", "MID": "CM", "FWD": "ST"}  # subs without a line-up slot


def shooting(players: list[dict], team: str) -> dict:
    """Who takes the team's shots, and how good are they (D-025)? Per player, from the shot
    map: non-penalty shots, npxG, quality per shot, distance, outside-box / blocked / headed
    shares, and the **quality gap** — npxG the shots would have produced at the league
    average quality for the player's role, minus what they did produce. Summed over the
    squad it splits the team's shot-quality problem by player."""
    role_acc: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    role_ot: dict[str, float] = defaultdict(float)
    per: dict[int, dict] = {}
    for p in players:
        r = role_acc[p.get("role") or "UNK"]
        role_ot[p.get("role") or "UNK"] += p.get("np_shots_on_target", 0)
        r[0] += p["np_shots"]
        r[1] += p["npxg_shots"]
        a = per.setdefault(
            p["player_id"],
            {
                "name": p["name"],
                "team": p["team"],
                "minutes": 0.0,
                "shots": 0,
                "npxg": 0.0,
                "goals": 0,
                "on_target": 0,
                "outside": 0,
                "blocked": 0,
                "headed": 0,
                "distance_sum": 0.0,
                "errors_led_to_goal": 0,
                "roles": defaultdict(float),
            },
        )
        a["team"] = p["team"]
        a["minutes"] += p["minutes"]
        a["shots"] += p["np_shots"]
        a["npxg"] += p["npxg_shots"]
        a["goals"] += p.get("np_goals", 0)
        a["on_target"] += p.get("np_shots_on_target", 0)
        a["outside"] += p.get("np_shots_outside_box", 0)
        a["blocked"] += p.get("np_shots_blocked", 0)
        a["headed"] += p.get("np_shots_headed", 0)
        a["distance_sum"] += p.get("np_shot_distance_sum_m", 0.0)
        a["errors_led_to_goal"] += int(p.get("errors_led_to_goal") or 0)
        a["roles"][p.get("role") or "UNK"] += p["minutes"]
        a["fallback_role"] = GROUP_ROLE.get(p.get("position"), "UNK")
    role_q = {r: x / s for r, (s, x) in role_acc.items() if s}
    league_q = sum(x for _, x in role_acc.values()) / max(1, sum(s for s, _ in role_acc.values()))

    def row(a: dict) -> dict:
        known = {r: m for r, m in a["roles"].items() if r != "UNK"}
        role = max(known, key=known.get) if known else a["fallback_role"]
        q = a["npxg"] / a["shots"] if a["shots"] else None
        base = role_q.get(role, league_q)
        return {
            "name": a["name"],
            "role": role,
            "minutes": round(a["minutes"]),
            "shots": a["shots"],
            "shots_per90": 90 * a["shots"] / a["minutes"] if a["minutes"] else None,
            "npxg": a["npxg"],
            "goals": a["goals"],
            "on_target": a["on_target"],
            "on_target_pct": 100 * a["on_target"] / a["shots"] if a["shots"] else None,
            "role_on_target_pct": 100 * role_ot[role] / role_acc[role][0]
            if role_acc[role][0]
            else None,
            "npxg_per_shot": q,
            "role_npxg_per_shot": base,
            "avg_distance_m": a["distance_sum"] / a["shots"] if a["shots"] else None,
            "outside_pct": 100 * a["outside"] / a["shots"] if a["shots"] else None,
            "blocked_pct": 100 * a["blocked"] / a["shots"] if a["shots"] else None,
            "headed_pct": 100 * a["headed"] / a["shots"] if a["shots"] else None,
            "quality_gap": a["shots"] * base - a["npxg"],
            "errors_led_to_goal": a["errors_led_to_goal"],
        }

    rows = [row(a) for a in per.values() if a["team"] == team]
    shooters = sorted((r for r in rows if r["shots"]), key=lambda r: -r["shots"])
    total_shots = sum(r["shots"] for r in shooters)
    for r in shooters:
        r["share_of_shots"] = 100 * r["shots"] / total_shots if total_shots else None
    matches = len({p["match_id"] for p in players if p["team"] == team})
    team_npxg = sum(r["npxg"] for r in shooters)
    return {
        "matches": matches,
        "shots": total_shots,
        "npxg": team_npxg,
        "npxg_per_shot": team_npxg / total_shots if total_shots else None,
        "league_npxg_per_shot": league_q,
        "quality_gap": sum(r["quality_gap"] for r in shooters),
        "quality_gap_per_match": sum(r["quality_gap"] for r in shooters) / matches
        if matches
        else None,
        "players": [r for r in shooters if r["shots"] >= MIN_SHOTS_LISTED],
        "others": {
            "players": sum(1 for r in shooters if r["shots"] < MIN_SHOTS_LISTED),
            "shots": sum(r["shots"] for r in shooters if r["shots"] < MIN_SHOTS_LISTED),
            "quality_gap": sum(r["quality_gap"] for r in shooters if r["shots"] < MIN_SHOTS_LISTED),
        },
        "errors_led_to_goal": sorted(
            (
                {"name": r["name"], "role": r["role"], "errors": r["errors_led_to_goal"]}
                for r in rows
                if r["errors_led_to_goal"]
            ),
            key=lambda e: -e["errors"],
        ),
    }
