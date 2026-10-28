"""Every match a league team plays, in any competition (D-067): the league (from the model's
Understat history), the domestic cups and Europe (FotMob fixture lists, back to 2016-17), so
the prediction can know how long a side has rested and whether it played in Europe in the
week (the features themselves are computed in corridor.predict.rest_features). FotMob names
are mapped onto the Understat names by name similarity, one to one, through the league
fixture list of the same season.

Past seasons' fixture lists are cached once; the current season is refreshed each run.
"""

import difflib
import unicodedata
from collections import defaultdict

from corridor.ingest import fotmob
from corridor.ingest.http import fetch_json
from corridor.leagues import League

# FotMob competition ids and the first season each list is good for.
EUROPE = {42: 2016, 73: 2016, 10216: 2021}  # Champions League, Europa League, Conference League
CUPS = {"pl": (132, 133), "laliga": (138,), "seriea": (141,), "bundesliga": (209,)}
LEAGUE = "league"
CUP = "cup"
EUROPE_KIND = "europe"


def _fixtures(season: int, comp: int, current: int) -> list[dict]:
    label = f"{season}/{season + 1}"
    if season >= current:
        return fotmob.league_matches(label, comp)
    d = fetch_json("fotmob", f"{fotmob.BASE}/leagues?id={comp}&season={label}")
    return d["fixtures"]["allMatches"]


def _plain(name: str) -> str:
    return (
        unicodedata.normalize("NFKD", name)
        .encode("ascii", "ignore")
        .decode()
        .lower()
        .replace("fc", "")
        .strip()
    )


def _names(fm_fixtures: list[dict], us_teams: set[str]) -> dict[str, str]:
    """FotMob name → Understat name for one season, by name similarity, one to one (best
    pairs first). Kickoff-time pairing is not reliable across time zones for old seasons."""
    fm_teams = {m[side]["name"] for m in fm_fixtures for side in ("home", "away")}
    pairs = sorted(
        (
            (difflib.SequenceMatcher(None, _plain(us), _plain(fm)).ratio(), fm, us)
            for fm in fm_teams
            for us in us_teams
        ),
        reverse=True,
    )
    out: dict[str, str] = {}
    taken: set[str] = set()
    for score, fm, us in pairs:
        if score < 0.5:
            break
        if fm not in out and us not in taken:
            out[fm] = us
            taken.add(us)
    return out


def build(league: League, history: list[dict], current: int) -> dict[str, list[tuple[str, str]]]:
    """Team (Understat name) → sorted [(kickoff 'YYYY-MM-DD HH:MM', kind)] over every season
    in ``history``. League matches come from ``history`` itself; cups and Europe from FotMob,
    for teams that were in the league that season."""
    out: dict[str, set[tuple[str, str]]] = defaultdict(set)
    by_season: dict[int, list[dict]] = defaultdict(list)
    for m in history:
        by_season[m["season"]].append(m)
        if m["played"]:
            for side in ("home", "away"):
                out[m[side]].add((m["kickoff"][:16], LEAGUE))
    for season, ms in sorted(by_season.items()):
        try:
            fm_league = _fixtures(season, league.fotmob_id, current)
        except Exception:  # noqa: BLE001 — no fixture list, no cup / Europe dates that season
            continue
        to_us = _names(fm_league, {m[side] for m in ms for side in ("home", "away")})
        comps = [(c, CUP) for c in CUPS.get(league.key, ())] + [
            (c, EUROPE_KIND) for c, first in EUROPE.items() if season >= first
        ]
        for comp, kind in comps:
            try:
                fixtures = _fixtures(season, comp, current)
            except Exception:  # noqa: BLE001
                continue
            for f in fixtures:
                st = f.get("status") or {}
                if not st.get("finished") or not st.get("utcTime"):
                    continue
                when = st["utcTime"][:16].replace("T", " ")
                for side in ("home", "away"):
                    t = to_us.get(f[side]["name"])
                    if t:
                        out[t].add((when, kind))
    return {t: sorted(v) for t, v in out.items()}
