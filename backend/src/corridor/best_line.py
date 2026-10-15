"""Stages 2–3: the elite "best line" and the "worst line".

best line  — what last season's top four looked like when they won: the median (and
             middle-half range) of every metric over their league wins, minus wins where
             the opponent played 20+ minutes a man down (D-019).
worst line — the mirror: what last season's bottom four looked like when they lost, minus
             losses where they themselves were down to 10 men from before the 70th minute
             (D-020).

Lines are fixed for a season and rebuilt each summer. Only same-provider data is used, and
metrics whose league-wide level moved between seasons (a provider redefinition) get no
line. The functions are generic over any rows/metrics with ``key`` and ``direction``, so the
historical proof (corridor.proof) reuses them on Understat data too.
"""

from collections import defaultdict
from collections.abc import Sequence
from statistics import median
from typing import Any, Literal

import numpy as np

from corridor.profile import METRICS, derive

Side = Literal["best", "worst"]
GROUP_N = 4
RED_CARD_BEFORE = 70  # sent off before this minute → 11 v 10 for 20+ minutes
DRIFT_SD = 0.5  # league-wide mean moved this many SDs between seasons → not comparable
MIN_GAMES = 10


def final_table(rows: list[dict]) -> list[str]:
    """Teams ordered by points, then goal difference."""
    pts: dict[str, int] = defaultdict(int)
    gd: dict[str, int] = defaultdict(int)
    for r in rows:
        pts[r["team"]] += {"W": 3, "D": 1, "L": 0}[r["result"]]
        gd[r["team"]] += r["goals_for"] - r["goals_against"]
    return sorted(pts, key=lambda t: (pts[t], gd[t]), reverse=True)


def _excluded_reason(r: dict, side: Side) -> str | None:
    if side == "best":
        red = r.get("opp_red_card_min")
        if red is not None and red < RED_CARD_BEFORE:
            return f"{r.get('opponent', 'opponent')} down to 10 men from {red}'"
    else:
        red = r.get("red_card_min")
        if red is not None and red < RED_CARD_BEFORE:
            return f"{r['team']} down to 10 men from {red}'"
    return None


def drift(prev_rows: list[dict], cur_rows: list[dict], metrics: Sequence = METRICS) -> dict:
    """League-wide shift of each metric between seasons, in last season's SDs. A big shift
    means the provider changed its definition (e.g. FotMob's line-breaking passes nearly
    doubled in 2026-27), so last season's line would be meaningless this season."""
    out = {}
    for m in metrics:
        a = [r[m.key] for r in prev_rows if r.get(m.key) is not None]
        b = [r[m.key] for r in cur_rows if r.get(m.key) is not None]
        sd = float(np.std(a)) if len(a) > 1 else 0.0
        if a and b and sd > 0:
            out[m.key] = (float(np.mean(b)) - float(np.mean(a))) / sd
    return out


def build_line(
    rows: list[dict],
    season: str,
    current_rows: list[dict] | None = None,
    side: Side = "best",
    metrics: Sequence = METRICS,
    derived: bool = False,
) -> dict[str, Any]:
    if not derived:
        rows = [derive(r) for r in rows]
        current_rows = [derive(r) for r in current_rows] if current_rows else None
    shifts = drift(rows, current_rows, metrics) if current_rows else {}
    not_comparable = {k: round(v, 2) for k, v in shifts.items() if abs(v) > DRIFT_SD}
    table = final_table(rows)
    teams = table[:GROUP_N] if side == "best" else table[-GROUP_N:]
    result = "W" if side == "best" else "L"
    games, excluded = [], []
    for r in rows:
        if r["team"] in teams and r["result"] == result:
            reason = _excluded_reason(r, side)
            if reason:
                excluded.append(
                    {"team": r["team"], "match": f"v {r.get('opponent', '?')}", "why": reason}
                )
            else:
                games.append(r)

    lines = {}
    for m in metrics:
        vals = [r[m.key] for r in games if r.get(m.key) is not None]
        if len(vals) < MIN_GAMES or m.key in not_comparable:
            continue
        p25, p75 = (float(x) for x in np.percentile(vals, [25, 75]))
        lines[m.key] = {"value": median(vals), "p25": p25, "p75": p75, "n": len(vals)}
    return {
        "side": side,
        "season": season,
        "teams": teams,
        "games": len(games),
        "games_by_team": {t: sum(r["team"] == t for r in games) for t in teams},
        "excluded": excluded,
        "not_comparable": not_comparable,
        "metrics": lines,
    }


def hits_line(value: float | None, line_value: float, direction: int, side: Side) -> bool | None:
    """best: at least as good as the line. worst: at least as bad as the line."""
    if value is None:
        return None
    if side == "best":
        return value * direction >= line_value * direction
    return value * direction <= line_value * direction


def compare(profile: dict, line: dict) -> dict:
    """Annotate a team profile (in place) with a line and summarise how often the team hits
    it. For the best line a hit is good (reached the elite median); for the worst line a hit
    is bad (as bad as the bottom four's median in defeat)."""
    side: Side = line["side"]
    hits_per_match = [0] * len(profile["matches"])
    counted_per_match = [0] * len(profile["matches"])
    typical_hits = 0
    compared = 0
    for m in profile["metrics"]:
        ln = line["metrics"].get(m["key"])
        if not ln:
            continue
        d = m["direction"]
        weak_end = ln["p25"] if d > 0 else ln["p75"]
        hits = []
        for i, x in enumerate(m["matches"]):
            hit = hits_line(x["value"], ln["value"], d, side)
            hits.append(hit)
            if hit is not None:
                counted_per_match[i] += 1
                hits_per_match[i] += hit
        typical_hit = hits_line(m["value"], ln["value"], d, side)
        compared += 1
        typical_hits += bool(typical_hit)
        m[f"{side}_line"] = {
            **ln,
            "weak_end": weak_end,
            "gap": m["value"] - ln["value"],
            # Gap in units of the line's middle-half range, signed so positive = better than
            # the line; makes gaps comparable across metrics with different scales.
            "gap_in_ranges": (m["value"] - ln["value"]) * d / ((ln["p75"] - ln["p25"]) or 1),
            "typical_hits": typical_hit,
            "typical_in_range": hits_line(m["value"], weak_end, d, "best"),
            "matches_hit": sum(1 for h in hits if h),
            "matches_counted": sum(1 for h in hits if h is not None),
        }
    summary = {
        "side": side,
        "season": line["season"],
        "teams": line["teams"],
        "games": line["games"],
        "games_by_team": line["games_by_team"],
        "excluded": line["excluded"],
        "not_comparable": line.get("not_comparable", {}),
        "metrics_compared": compared,
        "typical_hits": typical_hits,
        "per_match": [
            {"match_id": mt["match_id"], "hits": h, "of": c}
            for mt, h, c in zip(profile["matches"], hits_per_match, counted_per_match, strict=True)
        ],
    }
    profile[f"{side}_line"] = summary
    return summary
