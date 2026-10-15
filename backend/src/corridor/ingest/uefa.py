"""UEFA match centre (unofficial JSON) → physical data for Champions League matches.

UEFA's tracking (distance, sprints, in/out of possession) is a different provider from
FotMob's PL physical data: UCL numbers are only ever compared with other UCL matches.
Stats appear ~17 h after kickoff.
"""

import difflib
from typing import Any

from corridor.ingest.http import fetch_json

MATCHES = "https://match.uefa.com/v5/matches"
STATS = "https://matchstats.uefa.com/v1/team-statistics"
CHAMPIONS_LEAGUE = 1
MAN_UTD = 52682


def season_matches(season: int, from_date: str, to_date: str) -> list[dict]:
    """Finished UCL matches between two dates. ``season`` is the start year (2026 → UEFA's
    seasonYear 2027). Refreshed each call."""
    url = (
        f"{MATCHES}?competitionId={CHAMPIONS_LEAGUE}&seasonYear={season + 1}"
        f"&fromDate={from_date}&toDate={to_date}&limit=200&offset=0&order=ASC"
    )
    return [m for m in fetch_json("uefa", url, refresh=True) if m.get("status") == "FINISHED"]


def team_stats(match_id: str | int) -> dict[str, dict[str, Any]]:
    """{uefa_team_id: {stat_name: value}}. Re-fetched if the cached copy predates the
    tracking data."""
    url = f"{STATS}/{match_id}"
    data = fetch_json("uefa", url)
    if not _has_physical(data):
        data = fetch_json("uefa", url, refresh=True)
    return {
        str(side["teamId"]): {s["name"]: s.get("value") for s in side["statistics"]}
        for side in data
    }


def _has_physical(data: list[dict]) -> bool:
    return bool(data) and all(
        any(s["name"] == "distance_covered" for s in side.get("statistics", [])) for side in data
    )


def _f(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def physical(stats: dict[str, Any], opp: dict[str, Any]) -> dict[str, float | None]:
    """Physical fields in the same units as the FotMob records (metres, counts)."""
    km = _f(stats.get("distance_covered"))
    opp_km = _f(opp.get("distance_covered"))
    oop = _f(stats.get("distance_covered_not_in_possession"))
    opp_poss = _f(opp.get("ball_possession"))
    return {
        "distance_m": km * 1000 if km is not None else None,
        "sprints": _f(stats.get("sprints")),
        "opp_distance_m": opp_km * 1000 if opp_km is not None else None,
        "opp_sprints": _f(opp.get("sprints")),
        "high_intensity_runs": _f(stats.get("high_intensity_runs")),
        "distance_oop_km": oop,
        "opp_possession_pct_uefa": opp_poss,
    }


def match_to_fotmob(fm: dict, uefa: list[dict]) -> dict | None:
    """Find the UEFA match for a FotMob fixture: same date and score, best name match."""
    date = fm["status"]["utcTime"][:10]
    hg, ag = (int(x) for x in fm["status"]["scoreStr"].split(" - "))
    cands = [
        u
        for u in uefa
        if u["kickOffTime"]["date"] == date
        and u["score"]["regular"]["home"] == hg
        and u["score"]["regular"]["away"] == ag
    ]

    def sim(u: dict) -> float:
        return sum(
            difflib.SequenceMatcher(
                None, u[side]["internationalName"].lower(), fm[fs]["name"].lower()
            ).ratio()
            for side, fs in (("homeTeam", "home"), ("awayTeam", "away"))
        )

    return max(cands, key=sim) if cands else None
