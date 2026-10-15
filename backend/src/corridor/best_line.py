"""Stage 2: the elite "best line" — what last season's top teams looked like when they won.

For every profile metric: the median (and middle-half range) over all league wins by the
previous season's top four, excluding wins where the opponent played 20+ minutes a man
down. It is fixed for the whole season and rebuilt each summer (D-019). Only same-provider
data is used: a PL line from FotMob/Understat PL data, compared with PL matches.
"""

from collections import defaultdict
from statistics import median

import numpy as np

from corridor.profile import METRICS, derive

ELITE_N = 4
RED_CARD_BEFORE = 70  # opponent sent off before this minute → 11 v 10 for 20+ minutes


def final_table(rows: list[dict]) -> list[str]:
    """Teams ordered by points, then goal difference."""
    pts: dict[str, int] = defaultdict(int)
    gd: dict[str, int] = defaultdict(int)
    for r in rows:
        pts[r["team"]] += {"W": 3, "D": 1, "L": 0}[r["result"]]
        gd[r["team"]] += r["goals_for"] - r["goals_against"]
    return sorted(pts, key=lambda t: (pts[t], gd[t]), reverse=True)


def _excluded_reason(r: dict) -> str | None:
    red = r.get("opp_red_card_min")
    if red is not None and red < RED_CARD_BEFORE:
        return f"{r['opponent']} down to 10 men from {red}'"
    return None


DRIFT_SD = 0.5  # league-wide mean moved this many SDs between seasons → not comparable


def drift(prev_rows: list[dict], cur_rows: list[dict]) -> dict[str, float]:
    """League-wide shift of each metric between seasons, in last season's SDs. A big shift
    means the provider changed its definition (e.g. FotMob's line-breaking passes nearly
    doubled in 2026-27), so last season's line would be meaningless this season."""
    out = {}
    for m in METRICS:
        a = [r[m.key] for r in prev_rows if r.get(m.key) is not None]
        b = [r[m.key] for r in cur_rows if r.get(m.key) is not None]
        sd = float(np.std(a)) if len(a) > 1 else 0.0
        if a and b and sd > 0:
            out[m.key] = (float(np.mean(b)) - float(np.mean(a))) / sd
    return out


def build_line(rows: list[dict], season: str, current_rows: list[dict] | None = None) -> dict:
    rows = [derive(r) for r in rows]
    shifts = drift(rows, [derive(r) for r in current_rows]) if current_rows else {}
    not_comparable = {k: round(v, 2) for k, v in shifts.items() if abs(v) > DRIFT_SD}
    elite = final_table(rows)[:ELITE_N]
    wins, excluded = [], []
    for r in rows:
        if r["team"] in elite and r["result"] == "W":
            reason = _excluded_reason(r)
            if reason:
                excluded.append({"team": r["team"], "match": f"v {r['opponent']}", "why": reason})
            else:
                wins.append(r)

    metrics = {}
    for m in METRICS:
        vals = [r[m.key] for r in wins if r.get(m.key) is not None]
        if len(vals) < 10 or m.key in not_comparable:  # too few games / definition changed
            continue
        p25, p75 = (float(x) for x in np.percentile(vals, [25, 75]))
        metrics[m.key] = {
            "value": median(vals),
            "p25": p25,
            "p75": p75,
            "n": len(vals),
        }
    return {
        "season": season,
        "elite": elite,
        "wins": len(wins),
        "wins_by_team": {t: sum(r["team"] == t for r in wins) for t in elite},
        "excluded": excluded,
        "not_comparable": not_comparable,
        "metrics": metrics,
    }


def _at_least(v: float | None, target: float, direction: int) -> bool | None:
    if v is None:
        return None
    return v * direction >= target * direction


def compare(profile: dict, line: dict) -> dict:
    """Annotate a team profile (in place) with the line, and summarise how often the team
    reaches it. "Reached" = at least as good as the elite median; "in range" = at least as
    good as the weaker end of the elite middle half."""
    reached_per_match = [0] * len(profile["matches"])
    counted_per_match = [0] * len(profile["matches"])
    at_line = 0
    compared = 0
    for m in profile["metrics"]:
        bl = line["metrics"].get(m["key"])
        if not bl:
            continue
        d = m["direction"]
        weak_end = bl["p25"] if d > 0 else bl["p75"]
        hits = []
        for i, x in enumerate(m["matches"]):
            hit = _at_least(x["value"], bl["value"], d)
            hits.append(hit)
            if hit is not None:
                counted_per_match[i] += 1
                reached_per_match[i] += hit
        typical_reaches = _at_least(m["value"], bl["value"], d)
        compared += 1
        at_line += bool(typical_reaches)
        m["best_line"] = {
            **bl,
            "weak_end": weak_end,
            "gap": m["value"] - bl["value"],
            # Gap in units of the elite middle-half range, signed so negative = below the
            # line; makes gaps comparable across metrics with different scales.
            "gap_in_ranges": (m["value"] - bl["value"]) * d / ((bl["p75"] - bl["p25"]) or 1),
            "typical_reaches": typical_reaches,
            "typical_in_range": _at_least(m["value"], weak_end, d),
            "matches_reached": sum(1 for h in hits if h),
            "matches_counted": sum(1 for h in hits if h is not None),
        }
    summary = {
        "season": line["season"],
        "elite": line["elite"],
        "wins": line["wins"],
        "wins_by_team": line["wins_by_team"],
        "excluded": line["excluded"],
        "not_comparable": line.get("not_comparable", {}),
        "metrics_compared": compared,
        "typical_at_or_above_line": at_line,
        "per_match": [
            {"match_id": mt["match_id"], "reached": r, "of": c}
            for mt, r, c in zip(
                profile["matches"], reached_per_match, counted_per_match, strict=True
            )
        ],
    }
    profile["best_line"] = summary
    return summary
