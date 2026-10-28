"""Absences (D-026): who was unavailable for a match, and how much of the team's output
they represent — known before kickoff.

FotMob's match page lists each side's unavailable players (injury, suspension,
international duty). For past matches the cached pages give a history to test on; for
upcoming ones the same list is the team news.

A player's weight is his share of the team's chance creation (non-penalty xG from the
shot map + expected assists) and of its minutes, counted over the team's earlier matches
this season plus last season at half weight — only matches before the one in question.

Official line-ups (D-065) are the stronger signal once they are out (about an hour before
kickoff): the share of a side's usual XI — the 11 players with the most earlier minutes —
that is not starting. The post-match job scores every prediction with that number too, so
the record says what the line-ups would have been worth even when they were not out when
the prediction was made.
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


def lineups(details: dict) -> dict[str, set[int]] | None:
    """{'home': {starter ids}, 'away': {...}} from a FotMob match page, only when the
    line-up is official (``lineupType == "standard"``); None before that."""
    lu = (details.get("content") or {}).get("lineup") or {}
    if lu.get("lineupType") != "standard":
        return None
    out = {}
    for key, side in (("homeTeam", "home"), ("awayTeam", "away")):
        starters = (lu.get(key) or {}).get("starters") or []
        if len(starters) != 11:
            return None
        out[side] = {x["id"] for x in starters}
    return out


class Contributions:
    """Running per-team, per-player totals of output (npxG + xA) and minutes."""

    def __init__(self) -> None:
        self.player: dict[tuple[str, int], list[float]] = defaultdict(lambda: [0.0, 0.0])
        self.team: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        # This season only: who has been in a squad, and how many matches the team has had.
        self.seen: dict[str, set[int]] = defaultdict(set)
        self.matches: dict[str, set[int]] = defaultdict(set)

    def add(self, p: dict, weight: float = 1.0) -> None:
        if weight == 1.0:
            self.seen[p["team"]].add(p["player_id"])
            if "match_id" in p:
                self.matches[p["team"]].add(p["match_id"])
        out = (p.get("npxg_shots") or 0.0) + (p.get("xa") or 0.0)
        for acc in (self.player[(p["team"], p["player_id"])], self.team[p["team"]]):
            acc[0] += weight * out
            acc[1] += weight * p["minutes"]

    def regulars(self, team: str, n: int = 11) -> list[int]:
        """The team's usual XI: its ``n`` players with the most earlier minutes (last season
        at half weight) among those who have been in one of its squads this season — so a
        player who left in the summer is not "missing" every week. Empty until the team has
        played ``MIN_TEAM_MATCHES`` this season."""
        if len(self.matches.get(team, ())) < MIN_TEAM_MATCHES:
            return []
        seen = self.seen.get(team, set())
        mine = [
            (k[1], v[1])
            for k, v in self.player.items()
            if k[0] == team and v[1] > 0 and k[1] in seen
        ]
        return [pid for pid, _ in sorted(mine, key=lambda kv: -kv[1])[:n]]

    def regulars_missing(self, team: str, xi: set[int]) -> float | None:
        """Share of the usual XI not in the starting line-up (D-065): 3 of 11 → 0.27. None
        when the usual XI is not yet known."""
        reg = self.regulars(team)
        return sum(1 for pid in reg if pid not in xi) / len(reg) if reg else None

    def regulars_split(
        self, team: str, xi: set[int], unavailable: set[int]
    ) -> tuple[float, float] | None:
        """The same share split into regulars on the unavailable list (injured, suspended)
        and regulars fit but not picked (D-066): injuries cost every side, resting costs
        only the thin squads."""
        reg = self.regulars(team)
        if not reg:
            return None
        out = [pid for pid in reg if pid not in xi]
        unav = sum(1 for pid in out if pid in unavailable)
        return unav / len(reg), (len(out) - unav) / len(reg)

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
                details = fotmob.match_details(mid)  # cached page
                un = unavailable(details)
            except Exception:  # noqa: BLE001 — a missing page just means no data
                details, un = None, None
            if un is not None and "home_team" in m and "away_team" in m:
                out[mid] = m | {
                    side: C.missing(m[f"{side}_team"], [u["id"] for u in un[side]])
                    | {"n": len(un[side])}
                    for side in ("home", "away")
                }
                # Official line-ups (D-065): the share of each side's usual XI not starting.
                xi = lineups(details) if details is not None else None
                if xi:
                    for side in ("home", "away"):
                        rm = C.regulars_missing(m[f"{side}_team"], xi[side])
                        if rm is not None:
                            out[mid][side]["regulars_missing"] = rm
                            ru, rr = C.regulars_split(
                                m[f"{side}_team"], xi[side], {u["id"] for u in un[side]}
                            )
                            out[mid][side]["regulars_unavailable"] = ru
                            out[mid][side]["regulars_rested"] = rr
            for p in by_match.get(mid, []):
                C.add(p)
        prev_players = players
    return out


# Fitted on 2024-25 (1.74) and 2025-26 (1.90) separately; pooled ≈ 1.8 (D-026).
K_MINUTES = 1.8
# The frozen out-of-sample test behind K_MINUTES (D-026), shown on the "How we know" page.
TEST = {
    "matches": 820,
    "fits": [
        {
            "fit_on": "2024-25",
            "tested_on": "2025-26 + 2026-27",
            "n": 440,
            "k": 1.74,
            "rps_base": 0.2107,
            "rps_adjusted": 0.2100,
        },
        {
            "fit_on": "2025-26",
            "tested_on": "2024-25",
            "n": 380,
            "k": 1.90,
            "rps_base": 0.2033,
            "rps_adjusted": 0.2010,
        },
    ],
    "big_gap": {"n": 30, "base_home_win": 0.38, "adjusted_home_win": 0.30, "actual_home_win": 0.20},
}


# Official line-ups (D-065): the share of the usual XI not starting. Measured, not applied:
# fitted on the PL the weight was 1.2 on 2024-25 and 0.6 on 2025-26, and one of the two
# cross-season folds lost, so it fails the D-031 bar for now. The post-match job scores every
# prediction with it anyway ("with the official line-ups, had we known them"); revisit at the
# end of 2026-27 with three seasons.
MIN_TEAM_MATCHES = 3
K_LINEUP = 0.9  # the mean of the two fits, used for the logged measurement
LINEUP_TEST = {
    "matches": 750,
    "fits": [
        {
            "fit_on": "2024-25",
            "tested_on": "2025-26 + 2026-27",
            "n": 400,
            "k": 1.2,
            "rps_base": 0.2086,
            "rps_adjusted": 0.2091,
        },
        {
            "fit_on": "2025-26",
            "tested_on": "2024-25 + 2026-27",
            "n": 400,
            "k": 0.6,
            "rps_base": 0.2078,
            "rps_adjusted": 0.2046,
        },
    ],
    "big_gap": {"n": 73, "base_home_win": 0.44, "adjusted_home_win": 0.34, "actual_home_win": 0.32},
}


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
