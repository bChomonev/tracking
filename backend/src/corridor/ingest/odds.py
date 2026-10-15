"""football-data.co.uk: free season CSVs of Premier League results with bookmaker odds.

Used only as a benchmark for our predictions (how close do we get to the market?). We
never republish the odds; the page shows aggregate scores only.
"""

import csv
import difflib
import io
from datetime import datetime

from corridor.ingest.http import fetch_text

URL = "https://football-data.co.uk/mmz4281/{code}/E0.csv"
# Pre-match average odds (collected before the weekend) and closing odds: Pinnacle's where
# available, else the market average at close. Older files name the average "BbAv".
BOOKS = {
    "avg": (("AvgH", "AvgD", "AvgA"), ("BbAvH", "BbAvD", "BbAvA")),
    "closing": (("PSCH", "PSCD", "PSCA"), ("AvgCH", "AvgCD", "AvgCA")),
}


def _code(season_start: int) -> str:
    return f"{season_start % 100:02d}{(season_start + 1) % 100:02d}"


def season_odds(season_start: int, *, current: bool = False) -> list[dict]:
    """[{date, home, away, odds: {book: (pH, pD, pA)}}] with the bookmaker margin removed."""
    text = fetch_text(
        "football_data", URL.format(code=_code(season_start)), max_age_h=24 if current else None
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
}


def name_map(odds_names: set[str], our_names: set[str]) -> dict[str, str]:
    """football-data short names → our (Understat) names: aliases, exact matches, then a
    close-enough unique similarity match. Doubtful or duplicate matches are left out (those
    matches simply get no benchmark) rather than risk pairing the wrong teams."""
    out: dict[str, str] = {}
    for n in odds_names:
        target = ALIAS.get(n, n)
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
