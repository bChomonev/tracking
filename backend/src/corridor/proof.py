"""Stage 3: does reaching the lines actually decide matches? An out-of-sample test.

For every pair of consecutive seasons, the best and worst lines are built from the earlier
season (corridor.best_line) and every team-match of the later season — all teams, not just
United — is scored: what share of the lines did it reach (best) or sink to (worst)? Then
we count how those matches ended. Lines never see the matches they are tested on.

Two datasets, never mixed (different providers):
  fotmob    — all profile metrics; 2024-25 → 2025-26 and 2025-26 → 2026-27 (running data only
              exists in the last pair, so the share uses the metrics with a line in that pair)
  understat — 5 core metrics back to 2014-15 (npxG for/against, PPDA, deep completions
              for/against): a much longer record on fewer metrics.

Caveat (stated on the page): metrics are whole-match totals, so they are partly shaped by
the scoreline (a team 2-0 up may sit back). This is association, not a controlled
experiment.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from corridor.best_line import Side, build_line, hits_line
from corridor.profile import METRICS, derive

# FotMob shares in 10% steps; Understat's 5 metrics give shares 0, .2 … 1, one bin each.
FOTMOB_BINS = tuple(round(x * 0.1, 1) for x in range(10)) + (1.0001,)
UNDERSTAT_BINS = (0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0001)
THRESHOLD_STEPS = [round(x * 0.05, 2) for x in range(6, 21)]  # 30% … 100%
MIN_N = 30
TARGET = {"best": ("W", 0.90), "worst": ("L", 0.85)}


@dataclass(frozen=True)
class CoreMetric:
    key: str
    label: str
    direction: int


UNDERSTAT_METRICS = (
    CoreMetric("npxg", "Chance quality created (npxG)", +1),
    CoreMetric("npxg_conceded", "Chance quality conceded (npxGA)", -1),
    CoreMetric("ppda", "Pressing (PPDA)", -1),
    CoreMetric("deep_completions", "Deep completions", +1),
    CoreMetric("deep_allowed", "Deep completions allowed", -1),
)


def understat_rows(team_matches: list[dict]) -> list[dict]:
    """Understat team-match records → rows keyed like the profile metrics."""
    out = []
    for r in team_matches:
        gf, ga = r["goals_for"], r["goals_against"]
        out.append(
            {
                "team": r["team"],
                "kickoff_utc": r["kickoff"],
                "goals_for": gf,
                "goals_against": ga,
                "result": "W" if gf > ga else "D" if gf == ga else "L",
                "npxg": r["us_npxg"],
                "npxg_conceded": r["us_npxga"],
                "ppda": r["ppda"],
                "deep_completions": r["deep_completions"],
                "deep_allowed": r["deep_allowed"],
            }
        )
    return out


def score(row: dict, line: dict, metrics: Sequence, keys: Sequence[str]) -> tuple[int, int]:
    """(lines hit, lines with data) for one team-match against one line, over ``keys``."""
    hit = n = 0
    for m in metrics:
        ln = line["metrics"].get(m.key)
        if m.key not in keys or not ln:
            continue
        h = hits_line(row.get(m.key), ln["value"], m.direction, line["side"])
        if h is not None:
            n += 1
            hit += h
    return hit, n


def _rates(rows: list[dict]) -> dict[str, Any]:
    n = len(rows)
    return {
        "n": n,
        **{k: (sum(r["result"] == k for r in rows) / n if n else None) for k in "WDL"},
    }


def evaluate(
    seasons: list[tuple[str, list[dict]]], metrics: Sequence, bins: Sequence[float]
) -> dict[str, Any]:
    """``seasons``: chronological (label, derived rows). Returns the proof summary."""
    scored: list[dict] = []
    per_metric: dict[str, dict[str, list[int]]] = {}
    pairs = []
    for (prev_label, prev), (label, rows) in zip(seasons, seasons[1:], strict=False):
        lines = {
            side: build_line(prev, prev_label, rows, side=side, metrics=metrics, derived=True)
            for side in ("best", "worst")
        }
        keys = [m.key for m in metrics if all(m.key in ln["metrics"] for ln in lines.values())]
        pairs.append({"lines_from": prev_label, "tested_on": label, "metrics": keys})
        for r in rows:
            rec = {"season": label, "result": r["result"]}
            for side, ln in lines.items():
                hit, n = score(r, ln, metrics, keys)
                rec[f"{side}_hits"], rec[f"{side}_of"] = hit, n
                rec[f"{side}_share"] = hit / n if n else None
                for m in metrics:
                    if m.key not in keys:
                        continue
                    h = hits_line(r.get(m.key), ln["metrics"][m.key]["value"], m.direction, side)
                    if h is None:
                        continue
                    bucket = per_metric.setdefault(f"{side}:{m.key}", {"hit": [], "miss": []})
                    outcome = 1 if r["result"] == TARGET[side][0] else 0
                    bucket["hit" if h else "miss"].append(outcome)
            scored.append(rec)
    return {
        "pairs": pairs,
        "team_matches": len(scored),
        "baseline": _rates(scored),
        "best": _side_summary(scored, "best", metrics, per_metric, bins),
        "worst": _side_summary(scored, "worst", metrics, per_metric, bins),
    }


def _side_summary(
    scored: list[dict], side: Side, metrics: Sequence, per_metric: dict, edges: Sequence[float]
) -> dict:
    target_result, target_rate = TARGET[side]
    rows = [r for r in scored if r[f"{side}_share"] is not None]
    bins = []
    for lo, hi in zip(edges, edges[1:], strict=False):
        in_bin = [r for r in rows if lo <= r[f"{side}_share"] < hi]
        bins.append({"from": lo, "to": min(hi, 1.0), **_rates(in_bin)})
    curve = []
    for t in THRESHOLD_STEPS:
        sub = [r for r in rows if r[f"{side}_share"] >= t - 1e-9]
        curve.append({"share_at_least": t, **_rates(sub)})
    meets = [c for c in curve if c["n"] >= MIN_N and (c[target_result] or 0) >= target_rate]
    by_metric = []
    labels = {m.key: m.label for m in metrics}
    for key, b in per_metric.items():
        s, k = key.split(":", 1)
        if s != side or not b["hit"] or not b["miss"]:
            continue
        hit_rate = sum(b["hit"]) / len(b["hit"])
        miss_rate = sum(b["miss"]) / len(b["miss"])
        by_metric.append(
            {
                "key": k,
                "label": labels.get(k, k),
                "rate_when_hit": hit_rate,
                "rate_when_not": miss_rate,
                "lift": hit_rate - miss_rate,
                "n_hit": len(b["hit"]),
                "n_not": len(b["miss"]),
            }
        )
    by_metric.sort(key=lambda x: -x["lift"])
    return {
        "target": {"result": target_result, "rate": target_rate},
        "bins": bins,
        "curve": curve,
        "threshold": meets[0] if meets else None,
        "by_metric": by_metric,
    }


def place(share: float | None, summary: dict) -> dict | None:
    """Historical outcome rates for matches in the same share bin."""
    if share is None:
        return None
    for b in summary["bins"]:
        if b["from"] <= share < b["to"] or (share >= 1.0 and b["to"] >= 1.0):
            return b
    return None


def fotmob_seasons(raw: list[tuple[str, list[dict]]]) -> list[tuple[str, list[dict]]]:
    return [(label, [derive(r) for r in rows]) for label, rows in raw]


# Metrics that partly *contain* the result are left out of the proof: goals prevented is
# post-shot xG minus goals conceded, finishing (xGOT − xG) tracks goals scored, and big
# chances missed is the flip side of big chances scored. Testing them against results
# would be circular.
OUTCOME_LINKED = {"goals_prevented", "finishing_delta", "big_chances_missed"}
FOTMOB_METRICS = tuple(m for m in METRICS if m.key not in OUTCOME_LINKED)
