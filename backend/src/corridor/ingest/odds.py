"""football-data.co.uk: free season CSVs of Premier League results with bookmaker odds.

Used only as a benchmark for our predictions (how close do we get to the market?). We
never republish the odds; the page shows aggregate scores only.
"""

import csv
import difflib
import io
from datetime import datetime

from corridor.ingest.http import fetch_text

URL = "https://football-data.co.uk/mmz4281/{season}/{code}.csv"
# Pre-match average odds (collected before the weekend) and closing odds: Pinnacle's where
# available, else the market average at close. Older files name the average "BbAv".
BOOKS = {
    "avg": (("AvgH", "AvgD", "AvgA"), ("BbAvH", "BbAvD", "BbAvA")),
    "closing": (("PSCH", "PSCD", "PSCA"), ("AvgCH", "AvgCD", "AvgCA")),
    # Over / under 2.5 goals (pre-match average).
    "ou25": (("Avg>2.5", "Avg<2.5"), ("BbAv>2.5", "BbAv<2.5")),
}


def _code(season_start: int) -> str:
    return f"{season_start % 100:02d}{(season_start + 1) % 100:02d}"


def season_odds(season_start: int, *, current: bool = False, code: str = "E0") -> list[dict]:
    """[{date, home, away, odds: {book: (pH, pD, pA)}}] with the bookmaker margin removed."""
    text = fetch_text(
        "football_data",
        URL.format(season=_code(season_start), code=code),
        max_age_h=24 if current else None,
    )
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        if not r.get("HomeTeam"):
            continue
        odds = {}
        for book, choices in BOOKS.items():
            for cols in choices:
                try:
                    inv = [1 / float(r[c]) for c in cols]
                except (KeyError, ValueError, ZeroDivisionError):
                    continue
                tot = sum(inv)
                odds[book] = tuple(x / tot for x in inv)
                break
        out.append(
            {
                "date": datetime.strptime(
                    r["Date"], "%d/%m/%Y" if len(r["Date"]) == 10 else "%d/%m/%y"
                ).date(),
                "home": r["HomeTeam"],
                "away": r["AwayTeam"],
                "odds": odds,
            }
        )
    return out


ALIAS = {
    "Man United": "Manchester United",
    "Man City": "Manchester City",
    "Nott'm Forest": "Nottingham Forest",
    "Wolves": "Wolverhampton Wanderers",
    "West Brom": "West Bromwich Albion",
    "Sheffield United": "Sheffield United",
    "QPR": "Queens Park Rangers",
    "Newcastle": "Newcastle United",
    # La Liga
    "Ath Madrid": "Atletico Madrid",
    "Ath Bilbao": "Athletic Club",
    "Betis": "Real Betis",
    "Sociedad": "Real Sociedad",
    "Celta": "Celta Vigo",
    "Espanol": "Espanyol",
    "Vallecano": "Rayo Vallecano",
    "La Coruna": "Deportivo La Coruna",
    "Sp Gijon": "Sporting Gijon",
    "Las Palmas": "Las Palmas",
    "Leganes": "Leganes",
    "Alaves": "Alaves",
    "Cadiz": "Cadiz",
    "Almeria": "Almeria",
    "Malaga": "Malaga",
    "Huesca": "SD Huesca",
    "Eibar": "Eibar",
    "Granada": "Granada",
    "Mallorca": "Mallorca",
    "Valladolid": "Real Valladolid",
    "Oviedo": "Real Oviedo",
    "Santander": "Racing Santander",
    # Serie A
    "Spal": "SPAL 2013",
    "Parma": "Parma Calcio 1913",
    # Bundesliga
    "Dortmund": "Borussia Dortmund",
    "M'gladbach": "Borussia M.Gladbach",
    "FC Koln": "FC Cologne",
    "Hamburg": "Hamburger SV",
    "Hertha": "Hertha Berlin",
    "RB Leipzig": "RasenBallsport Leipzig",
    "Bielefeld": "Arminia Bielefeld",
}


def name_map(odds_names: set[str], our_names: set[str]) -> dict[str, str]:
    """football-data short names → our (Understat) names: aliases, exact matches, then a
    close-enough unique similarity match. Doubtful or duplicate matches are left out (those
    matches simply get no benchmark) rather than risk pairing the wrong teams."""
    out: dict[str, str] = {}
    for n in odds_names:
        target = ALIAS.get(n, n)
        if target not in our_names and n in our_names:
            target = n  # the alias is for another era's name (e.g. Parma in 2014-15)
        if target in our_names:
            out[n] = target
            continue
        scored = sorted(
            (
                (difflib.SequenceMatcher(None, target.lower(), o.lower()).ratio(), o)
                for o in our_names
            ),
            reverse=True,
        )
        if (
            scored
            and scored[0][0] >= 0.75
            and (len(scored) < 2 or scored[0][0] - scored[1][0] > 0.1)
        ):
            out[n] = scored[0][1]
    dupes = {v for v in out.values() if list(out.values()).count(v) > 1}
    return {k: v for k, v in out.items() if v not in dupes}
