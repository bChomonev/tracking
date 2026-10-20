"""The focus team's next Champions League game, for the site: the fixture and each side's
numbers so far. No prediction: the model is built and tested on league games only (D-049).

Pure: callers pass in the fixture list, the league files and the Champions League rows.
"""

from statistics import mean


def _league_side(team: str, leagues: dict) -> dict | None:
    """The team's league season so far, from whichever of our leagues it plays in."""
    for key, lg in leagues.items():
        row = next((r for r in lg.get("table", []) if r["team"] == team), None)
        if not row or not row["played"]:
            continue
        n = row["played"]
        ms = (lg.get("teams", {}).get(team) or {}).get("matches", [])
        poss = [m["possession_pct"] for m in ms if m.get("possession_pct") is not None]
        return {
            "league_key": key,
            "competition": lg["competition"],
            "position": row["position"],
            "teams_in_league": len(lg["table"]),
            "played": n,
            "w": row["w"],
            "d": row["d"],
            "l": row["l"],
            "points": row["points"],
            "goals_for_pg": round(row["gf"] / n, 2),
            "goals_against_pg": round(row["ga"] / n, 2),
            "xg_for_pg": round(row["xg"] / n, 2),
            "xg_against_pg": round(row["xga"] / n, 2),
            "possession_pct": round(mean(poss)) if poss else None,
            "form": list(row.get("form") or [])[-5:],
        }
    return None


def _cup_side(team: str, rows: list[dict]) -> list[dict]:
    out = [
        {
            "date": r["kickoff_utc"][:10],
            "opponent": r["opponent"],
            "venue": "home" if r["is_home"] else "away",
            "goals_for": r["goals_for"],
            "goals_against": r["goals_against"],
            "xg_for": r.get("xg"),
            "xg_against": r.get("xg_conceded"),
        }
        for r in rows
        if r["team"] == team
    ]
    return sorted(out, key=lambda m: m["date"])


def next_cup_match(
    team: str, fixtures: list[dict], leagues: dict, cup_rows: list[dict], now: str
) -> dict | None:
    """``fixtures``: FotMob Champions League fixtures; ``now``: ISO time (UTC)."""
    ahead = sorted(
        (
            m
            for m in fixtures
            if team in (m["home"]["name"], m["away"]["name"])
            and not m["status"].get("finished")
            and not m["status"].get("cancelled")
            and m["status"]["utcTime"][:16] > now[:16]
        ),
        key=lambda m: m["status"]["utcTime"],
    )
    if not ahead:
        return None
    m = ahead[0]
    home, away = m["home"]["name"], m["away"]["name"]
    return {
        "competition": "Champions League",
        "home": home,
        "away": away,
        "kickoff": m["status"]["utcTime"][:19].replace("T", " "),  # UTC, like next_round
        "sides": {
            t: {"league": _league_side(t, leagues), "cup": _cup_side(t, cup_rows)}
            for t in (home, away)
        },
    }
