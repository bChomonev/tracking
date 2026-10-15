"""Absences (D-026): who was unavailable for a match, and how much of the team's output
they represent — known before kickoff.

FotMob's match page lists each side's unavailable players (injury, suspension,
international duty). For past matches the cached pages give a history to test on; for
upcoming ones the same list is the team news.

A player's weight is his share of the team's chance creation (non-penalty xG from the
shot map + expected assists) and of its minutes, counted over the team's earlier matches
this season plus last season at half weight — only matches before the one in question.
"""

import math
from collections import defaultdict
from typing import Any

from corridor.ingest import fotmob

LAST_SEASON_WEIGHT = 0.5


def unavailable(details: dict) -> dict[str, list[dict]]:
    """{'home': [{id, name, type}], 'away': [...]} from a FotMob match page."""
    lu = (details.get("content") or {}).get("lineup") or {}
    out = {}
    for key, side in (("homeTeam", "home"), ("awayTeam", "away")):
        out[side] = [
            {
                "id": u["id"],
                "name": u.get("name"),
                "type": (u.get("unavailability") or {}).get("type"),
            }
            for u in (lu.get(key) or {}).get("unavailable") or []
        ]
    return out


class Contributions:
    """Running per-team, per-player totals of output (npxG + xA) and minutes."""

    def __init__(self) -> None:
        self.player: dict[tuple[str, int], list[float]] = defaultdict(lambda: [0.0, 0.0])
        self.team: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])

    def add(self, p: dict, weight: float = 1.0) -> None:
        out = (p.get("npxg_shots") or 0.0) + (p.get("xa") or 0.0)
        for acc in (self.player[(p["team"], p["player_id"])], self.team[p["team"]]):
            acc[0] += weight * out
            acc[1] += weight * p["minutes"]

    def missing(self, team: str, ids: list[int]) -> dict[str, float]:
        t_out, t_min = self.team.get(team, (0.0, 0.0))
        m_out = sum(self.player.get((team, i), (0.0, 0.0))[0] for i in ids)
        m_min = sum(self.player.get((team, i), (0.0, 0.0))[1] for i in ids)
        return {
            "output": m_out / t_out if t_out else 0.0,
            "minutes": m_min / t_min if t_min else 0.0,
        }


def history(seasons: list[tuple[int, list[dict], list[dict]]]) -> dict[int, dict[str, Any]]:
    """For every FotMob league match: each side's missing share of output and minutes,
    from data before kickoff. ``seasons``: chronological (season, team_rows, player_rows).
    Returns {match_id: {"home": {...}, "away": {...}, "home_team", "away_team", "kickoff"}}."""
    out: dict[int, dict[str, Any]] = {}
    prev_players: list[dict] = []
    for _, team_rows, players in seasons:
        C = Contributions()
        for p in prev_players:
            C.add(p, LAST_SEASON_WEIGHT)
        by_match: dict[int, list[dict]] = defaultdict(list)
        for p in players:
            by_match[p["match_id"]].append(p)
        matches = {}
        for r in team_rows:
            m = matches.setdefault(r["match_id"], {"kickoff": r["kickoff_utc"]})
            m["home_team" if r["is_home"] else "away_team"] = r["team"]
        for mid in sorted(matches, key=lambda k: matches[k]["kickoff"]):
            m = matches[mid]
            try:
                un = unavailable(fotmob.match_details(mid))  # cached page
            except Exception:  # noqa: BLE001 — a missing page just means no data
                un = None
            if un is not None and "home_team" in m and "away_team" in m:
                out[mid] = m | {
                    side: C.missing(m[f"{side}_team"], [u["id"] for u in un[side]])
                    | {"n": len(un[side])}
                    for side in ("home", "away")
                }
            for p in by_match.get(mid, []):
                C.add(p)
        prev_players = players
    return out


# Fitted on 2024-25 (1.74) and 2025-26 (1.90) separately; pooled ≈ 1.8 (D-026).
K_MINUTES = 1.8


def adjust(p, home_missing_minutes: float, away_missing_minutes: float, k: float = K_MINUTES):
    """Shift home/draw/away probabilities towards the side missing less of its usual
    minutes: odds of a home win × exp(k·d), of an away win × exp(−k·d), d = away share −
    home share. One parameter, tested out of sample (small, consistent gain)."""
    d = away_missing_minutes - home_missing_minutes
    q = [p[0] * math.exp(k * d), p[1], p[2] * math.exp(-k * d)]
    s = sum(q)
    return [x / s for x in q]


def current_contributions(prev_players: list[dict], players: list[dict]) -> Contributions:
    C = Contributions()
    for p in prev_players:
        C.add(p, LAST_SEASON_WEIGHT)
    for p in players:
        C.add(p)
    return C
