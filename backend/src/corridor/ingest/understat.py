"""Understat (unofficial JSON) → per-team match records with PPDA and deep completions.

Understat has its own xG model; we only take the metrics FotMob lacks (PPDA, deep
completions) from it for current-season comparisons, plus its xG for multi-season history.
"""

from corridor.ingest.http import fetch_json

HEADERS = {"X-Requested-With": "XMLHttpRequest"}


def league_data(league: str, season_start_year: int, *, refresh: bool = False) -> dict:
    return fetch_json(
        "understat",
        f"https://understat.com/getLeagueData/{league}/{season_start_year}",
        headers=HEADERS,
        refresh=refresh,
    )


def team_matches(data: dict) -> list[dict]:
    """Flatten league data to one record per team per played match."""
    out = []
    for team in data["teams"].values():
        for h in team["history"]:
            att, dfn = h["ppda"]["att"], h["ppda"]["def"]
            a_att, a_def = h["ppda_allowed"]["att"], h["ppda_allowed"]["def"]
            out.append(
                {
                    "source": "understat",
                    "team": team["title"],
                    "kickoff": h["date"],
                    "is_home": h["h_a"] == "h",
                    "goals_for": int(h["scored"]),
                    "goals_against": int(h["missed"]),
                    "us_xg": float(h["xG"]),
                    "us_xga": float(h["xGA"]),
                    "us_npxg": float(h["npxG"]),
                    "us_npxga": float(h["npxGA"]),
                    "ppda": att / dfn if dfn else None,
                    "ppda_allowed": a_att / a_def if a_def else None,
                    "deep_completions": int(h["deep"]),
                    "deep_allowed": int(h["deep_allowed"]),
                    "us_xpts": float(h["xpts"]),
                }
            )
    return out
