"""Understat stand-ins from FotMob (D-078), for matches Understat has not published.

Each Understat field the site or the model needs is fitted as a straight line on a FotMob
quantity, on the matches of the same season that have both sources, then applied to the
matches that lack Understat. Rows filled this way carry ``understat_proxy: True`` and are
replaced by the real join as soon as Understat catches up. Lines are never built on them.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

MIN_PAIRS = 30  # fewer matched matches than this and the field stays missing


def _ppda(mine: dict, opp: dict) -> float | None:
    """Opponent passes per defensive action (tackles, interceptions, fouls): the closest
    FotMob quantity to Understat's PPDA, r ≈ 0.84 on the 2026-27 PL (D-078)."""
    actions = sum(mine.get(k) or 0 for k in ("tackles", "interceptions", "fouls"))
    passes = opp.get("passes")
    return None if passes is None or not actions else passes / actions


# Understat field → (FotMob quantity of (own row, opponent row), description).
PROXIES: dict[str, tuple[Callable[[dict, dict], float | None], str]] = {
    "us_xg": (lambda m, o: m.get("xg"), "FotMob xG"),
    "us_xga": (lambda m, o: m.get("xg_conceded"), "FotMob xG conceded"),
    "us_npxg": (lambda m, o: m.get("npxg"), "FotMob npxG"),
    "us_npxga": (lambda m, o: m.get("npxg_conceded"), "FotMob npxG conceded"),
    "ppda": (_ppda, "opponent passes per tackle, interception or foul"),
    "ppda_allowed": (lambda m, o: _ppda(o, m), "own passes per opponent defensive action"),
    "deep_completions": (lambda m, o: m.get("box_touches"), "box touches"),
    "deep_allowed": (lambda m, o: m.get("box_touches_conceded"), "box touches conceded"),
}


def fit(pairs: list[tuple[dict, dict, dict]]) -> dict[str, dict]:
    """Per field, the line a + b·x from (understat row, own FotMob row, opponent FotMob row)
    triples; fields with too few pairs are left out."""
    out = {}
    for field, (fn, desc) in PROXIES.items():
        xy = [
            (x, u[field])
            for u, m, o in pairs
            if u.get(field) is not None and (x := fn(m, o)) is not None
        ]
        if len(xy) < MIN_PAIRS:
            continue
        x, y = (np.array(v, dtype=float) for v in zip(*xy, strict=True))
        b, a = np.polyfit(x, y, 1)
        r = float(np.corrcoef(x, y)[0, 1])
        out[field] = {"a": float(a), "b": float(b), "n": len(xy), "r": r, "from": desc}
    return out


def apply(mine: dict, opp: dict, fits: dict[str, dict]) -> dict:
    """The proxy fields for one FotMob team-match, from its own and its opponent's rows."""
    out: dict = {}
    for field, f in fits.items():
        x = PROXIES[field][0](mine, opp)
        if x is None:
            continue
        v = f["a"] + f["b"] * x
        out[field] = int(round(v)) if field.startswith("deep") else round(v, 3)
    if out:
        out["understat_proxy"] = True
    return out


def opponents(team_rows: list[dict]) -> dict[tuple[str, str], dict]:
    """(match id, team) → the opponent's row."""
    by = {(r["match_id"], r["team"]): r for r in team_rows}
    return {
        (mid, t): by[(mid, r["opponent"])]
        for (mid, t), r in by.items()
        if (mid, r["opponent"]) in by
    }
