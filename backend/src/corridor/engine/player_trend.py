"""Player form, plainly: each player's last few matches against his earlier ones (task 2 of
the trend work; teams are corridor.engine.trend, D-061).

**The per-match number.** A match is scored against every match played this season by a
player in the same role (CB, FB, CM, AM, W, ST — the role he played that day) for 60+
minutes: for each of the role's four metrics (``ROLE_METRICS``, per 90 minutes), the share
of those matches he beat (ties count half; for duels lost, fewer is better), and the
composite is the mean of the four. 50 is a typical match for the role; 80 means better
than four in five. Chosen for what a role is for, dropping the metrics that proved pure
noise season-half to season-half (interceptions for centre-backs, chances created for
full-backs and wingers).

**Opponent adjustment.** A winger looks god-mode against a weak side and anonymous against
a strong one: across the 2025-26 PL the composite fell 5–9 points per unit of opponent
strength (the opponent's season median npxG for minus against, relative to the league).
Each match is credited with what a typical player in his role loses or gains against that
opponent (one slope per role, fitted on the season's league matches), so a run of easy
fixtures is not a run of form. Chosen over adjusting by the team's own npxG difference in
the match, which cuts the noise a little more but strips out the player's own contribution
(between-player spread 8.2 → 7.5 points, season-half correlation 0.63 → 0.60).

**Window.** Recent = the last ``WINDOW`` counted matches, before = the earlier counted
matches, at least ``trend.MIN_BEFORE`` of them; players miss matches, so the window counts
his matches, not the team's. Up / down only when the gap is at least one standard error wide
(``trend.recent``), otherwise steady; with fewer than ``MIN_MATCHES`` counted matches no
call. Always show the count.

**What it is not.** A description, not a forecast: on 2025-26 PL data a player's last four
matches predicted his next four *worse* than his season average (mean error 9.0 against
7.4 points), and one match's deviation carries nothing into the next (lag-1 r = −0.02).
Pure functions on the processed rows, no I/O.
"""

from collections import defaultdict

import numpy as np

from corridor.engine import trend

WINDOW = 4  # the "recent" matches
MIN_MATCHES = WINDOW + trend.MIN_BEFORE
MIN_MINUTES = 60  # a match counts only from this many minutes: substitutes post inflated rates
MIN_POOL = 20  # same-role matches needed before a percentile means anything
# Per role: (metric key, words). Per 90 minutes; "xg_xa" = non-penalty xG from shots + xA.
ROLE_METRICS: dict[str, tuple[tuple[str, str], ...]] = {
    "CB": (
        ("duels_won", "duels won"),
        ("recoveries", "ball recoveries"),
        ("line_breaking_passes", "line-breaking passes"),
        ("duels_lost", "duels lost"),
    ),
    "FB": (
        ("duels_won", "duels won"),
        ("recoveries", "ball recoveries"),
        ("passes_into_final_third", "passes into the final third"),
        ("box_touches", "touches in the opponent's box"),
    ),
    "CM": (
        ("line_breaking_passes", "line-breaking passes"),
        ("passes_into_final_third", "passes into the final third"),
        ("recoveries", "ball recoveries"),
        ("duels_won", "duels won"),
    ),
    "AM": (
        ("xg_xa", "xG + xA"),
        ("chances_created", "chances created"),
        ("box_touches", "touches in the opponent's box"),
        ("line_breaking_passes", "line-breaking passes"),
    ),
    "W": (
        ("xg_xa", "xG + xA"),
        ("np_shots", "shots"),
        ("box_touches", "touches in the opponent's box"),
        ("duels_won", "duels won"),
    ),
    "ST": (
        ("xg_xa", "xG + xA"),
        ("np_shots", "shots"),
        ("box_touches", "touches in the opponent's box"),
        ("duels_won", "duels won"),
    ),
}
LOWER_IS_BETTER = frozenset({"duels_lost", "dispossessed", "dribbled_past"})


def _rate(p: dict, key: str) -> float:
    v = (p.get("npxg_shots") or 0) + (p.get("xa") or 0) if key == "xg_xa" else p.get(key) or 0
    return float(v) * 90 / p["minutes"]


def opponent_strength(team_rows: list[dict]) -> dict[str, float]:
    """Per team, how much better than the league it usually is: season median npxG for
    minus against, each relative to the league average of team medians. Positive = strong."""
    by_team: dict[str, list[dict]] = defaultdict(list)
    for r in team_rows:
        by_team[r["team"]].append(r)
    med_for = {t: float(np.median([r["npxg"] for r in rs])) for t, rs in by_team.items()}
    med_ag = {t: float(np.median([r["npxg_conceded"] for r in rs])) for t, rs in by_team.items()}
    if not by_team:
        return {}
    avg_for, avg_ag = np.mean(list(med_for.values())), np.mean(list(med_ag.values()))
    return {t: (med_for[t] - avg_for) - (med_ag[t] - avg_ag) for t in by_team}


def match_scores(players: list[dict], team_rows: list[dict]) -> list[dict]:
    """Every counted player-match (role known, not GK, ``MIN_MINUTES``+) scored against the
    same role's season, in kickoff order. Each row: player_id, name, team, match_id,
    opponent, kickoff_utc, role, minutes, percentiles per metric, score (their mean) and
    adjusted (score credited for the opponent's strength)."""
    kick = {(r["match_id"], r["team"]): (r["kickoff_utc"], r["opponent"]) for r in team_rows}
    rows = [
        p
        for p in players
        if p.get("role") in ROLE_METRICS
        and (p.get("minutes") or 0) >= MIN_MINUTES
        and (p["match_id"], p["team"]) in kick
    ]
    rates = {id(p): {k: _rate(p, k) for k, _ in ROLE_METRICS[p["role"]]} for p in rows}
    pools: dict[str, dict[str, np.ndarray]] = {}
    for role, ms in ROLE_METRICS.items():
        rs = [p for p in rows if p["role"] == role]
        pools[role] = {k: np.sort([rates[id(p)][k] for p in rs]) for k, _ in ms}

    out = []
    for p in rows:
        pcts: dict[str, float] = {}
        for k, _ in ROLE_METRICS[p["role"]]:
            pool = pools[p["role"]][k]
            if len(pool) - 1 < MIN_POOL:
                continue
            v = rates[id(p)][k]
            lo = int(np.searchsorted(pool, v, "left"))
            ties = int(np.searchsorted(pool, v, "right")) - lo - 1  # the others at his value
            pct = 100 * (lo + 0.5 * ties) / (len(pool) - 1)
            pcts[k] = 100 - pct if k in LOWER_IS_BETTER else pct
        if not pcts:
            continue
        ko, opp = kick[(p["match_id"], p["team"])]
        out.append(
            {
                "player_id": p["player_id"],
                "name": p["name"],
                "team": p["team"],
                "match_id": p["match_id"],
                "opponent": opp,
                "kickoff_utc": ko,
                "role": p["role"],
                "minutes": int(p["minutes"]),
                "percentiles": pcts,
                "score": float(np.mean(list(pcts.values()))),
                "adjusted": None,
            }
        )
    out.sort(key=lambda r: (r["kickoff_utc"], r["match_id"], r["player_id"]))

    # One slope per role: what a typical player in the role loses against a stronger side.
    strength = opponent_strength(team_rows)
    for role in ROLE_METRICS:
        rs = [r for r in out if r["role"] == role and r["opponent"] in strength]
        slope = 0.0
        if len(rs) >= MIN_POOL:
            x = np.array([strength[r["opponent"]] for r in rs])
            y = np.array([r["score"] for r in rs])
            if np.ptp(x) > 0:
                slope = float(np.polyfit(x, y, 1)[0])
        for r in rs:
            r["adjusted"] = r["score"] - slope * strength[r["opponent"]]
            r["opponent_strength"] = strength[r["opponent"]]
    return out


def build(players: list[dict], team_rows: list[dict], window: int = WINDOW) -> dict[int, dict]:
    """Per player_id: his counted matches, the trend of the adjusted score (``trend.recent``
    over the last ``window`` counted matches against the earlier ones), the same for the raw
    score, and per metric. Players with no counted match are absent."""
    by_player: dict[int, list[dict]] = defaultdict(list)
    for r in match_scores(players, team_rows):
        by_player[r["player_id"]].append(r)
    out = {}
    for pid, rs in by_player.items():
        roles = sorted({r["role"] for r in rs})
        keys = sorted({k for r in rs for k in r["percentiles"]})
        out[pid] = {
            "window": window,
            "min_matches": window + trend.MIN_BEFORE,
            "min_minutes": MIN_MINUTES,
            "n_counted": len(rs),
            "roles": roles,
            "matches": [
                {
                    "match_id": r["match_id"],
                    "opponent": r["opponent"],
                    "minutes": r["minutes"],
                    "role": r["role"],
                    "score": round(r["score"], 1),
                    "adjusted": None if r["adjusted"] is None else round(r["adjusted"], 1),
                }
                for r in rs
            ],
            "composite": trend.recent(
                [r["adjusted"] if r["adjusted"] is not None else r["score"] for r in rs], window
            ),
            "raw": trend.recent([r["score"] for r in rs], window),
            "metrics": {
                k: trend.recent([r["percentiles"].get(k) for r in rs], window) for k in keys
            },
        }
    return out


def words(t: dict, name: str) -> str | None:
    """One sentence for a player's composite trend, saying what it counts."""
    c = t.get("composite")
    if not c or c["call"] is None:
        return None
    n_before = c["n"] - c["n_recent"]
    head = {
        "up": "trending up",
        "down": "trending down",
        "steady": "about the same",
    }[c["call"]]
    return (
        f"{name}: {head} — his last {c['n_recent']} matches rate {c['recent']:.0f} against "
        f"{c['before']:.0f} in the {n_before} before (role percentile per match, adjusted for "
        f"the opponent; 50 is typical for the role)."
    )
