"""Leagues the site covers (D-029). One method, measured separately per league: each
league's lines, proof, tiers and prediction tests use only that league's data."""

from dataclasses import dataclass
from pathlib import Path

from corridor.ingest.http import DATA_DIR


@dataclass(frozen=True)
class League:
    key: str
    name: str
    fotmob_id: int
    understat: str  # Understat league slug
    odds_code: str  # football-data.co.uk file code
    sub: str  # sub-folder under data/processed/{season}/ and data/site/{season}/
    focus_team: str | None  # gets the AI analyst; None = no favourite


LEAGUES = {
    "pl": League("pl", "Premier League", 47, "EPL", "E0", "", "Manchester United"),
    "laliga": League("laliga", "La Liga", 87, "La_liga", "SP1", "laliga", None),
    "seriea": League("seriea", "Serie A", 55, "Serie_A", "I1", "seriea", None),
    "bundesliga": League("bundesliga", "Bundesliga", 54, "Bundesliga", "D1", "bundesliga", None),
}


def processed_dir(season: int, league: League) -> Path:
    return DATA_DIR / "processed" / str(season) / league.sub


def site_dir(season: int, league: League) -> Path:
    return DATA_DIR / "site" / str(season) / league.sub
