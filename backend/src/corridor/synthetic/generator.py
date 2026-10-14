"""Deterministic synthetic Top-5-league-like data for building and testing the engine.

Each match yields two team performances whose metrics are *paired* the way real data is:
one side's npxG conceded is the other's npxG created, field tilt and possession sum to 100,
and goalkeeper goals prevented derive from the opponent's on-target quality and goals.
Results come from Poisson goals on post-shot xG, so performance → outcome is noisy but real.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import numpy as np

from corridor.engine.metrics import METRIC_KEYS

LEAGUES = ("EPL", "LALIGA", "SERIEA", "BUNDESLIGA", "LIGUE1")
TEAMS_PER_LEAGUE = 20
HOME_ADVANTAGE = 0.25


@dataclass
class SyntheticTeam:
    external_id: str
    name: str
    short_code: str
    league_code: str
    strength: float


@dataclass
class SyntheticMatch:
    external_id: str
    competition_code: str
    season: str
    kickoff_utc: datetime
    home: int  # index into teams
    away: int
    home_goals: int
    away_goals: int


@dataclass
class SyntheticPerformance:
    match: int  # index into matches
    team: int
    opponent: int
    is_home: bool
    goals_for: int
    goals_against: int
    possession_pct: float
    metrics: dict[str, float]

    @property
    def result(self) -> str:
        if self.goals_for > self.goals_against:
            return "W"
        return "D" if self.goals_for == self.goals_against else "L"

    @property
    def points(self) -> int:
        return {"W": 3, "D": 1, "L": 0}[self.result]


@dataclass
class SyntheticDataset:
    teams: list[SyntheticTeam] = field(default_factory=list)
    matches: list[SyntheticMatch] = field(default_factory=list)
    performances: list[SyntheticPerformance] = field(default_factory=list)

    def raw_matrix(self) -> np.ndarray:
        return np.array(
            [[p.metrics[k] for k in METRIC_KEYS] for p in self.performances], dtype=np.float64
        )

    def npxgd(self) -> np.ndarray:
        return np.array(
            [p.metrics["npxg_created"] - p.metrics["npxg_conceded"] for p in self.performances]
        )

    def results(self) -> np.ndarray:
        return np.array([p.result for p in self.performances])


def _attack_profile(rng: np.random.Generator, q: float) -> dict[str, float]:
    """Metrics owned by one side given its latent match quality ``q``."""
    npxg = float(max(0.05, 1.35 * np.exp(0.38 * q + rng.normal(0, 0.28))))
    per_shot = float(np.clip(0.105 + 0.016 * q + rng.normal(0, 0.022), 0.03, 0.35))
    return {
        "distance_per_90_km": float(113.5 + 1.4 * q + rng.normal(0, 3.8)),
        "sprints_per_min_oop": float(max(0.8, 2.45 + 0.16 * q + rng.normal(0, 0.35))),
        "ppda": float(max(4.0, 12.0 - 1.6 * q + rng.normal(0, 2.4))),
        "line_breaks_per_100_touches": float(max(1.0, 6.0 + 0.7 * q + rng.normal(0, 1.2))),
        "box_touches_per_90": float(max(2.0, 24.0 + 6.5 * q + rng.normal(0, 5.5))),
        "npxg_created": round(npxg, 2),
        "npxg_per_shot": round(per_shot, 3),
        "finishing_delta": round(float(rng.normal(0, 0.28 * np.sqrt(npxg))), 2),
    }


def generate(
    *,
    seasons: int = 5,
    seed: int = 42,
    physical_missing_rate: float = 0.0,
    start: datetime = datetime(2021, 8, 13, 19, 0, tzinfo=UTC),
) -> SyntheticDataset:
    """Double round-robin per league per season (380 matches × 5 leagues × ``seasons``)."""
    rng = np.random.default_rng(seed)
    ds = SyntheticDataset()

    for league in LEAGUES:
        for i in range(TEAMS_PER_LEAGUE):
            code = f"{league[:3]}{i:02d}"
            ds.teams.append(
                SyntheticTeam(
                    external_id=f"syn-{code.lower()}",
                    name=f"{league.title()} Club {i:02d}",
                    short_code=code,
                    league_code=league,
                    strength=float(rng.normal(0, 0.7)),
                )
            )

    for s in range(seasons):
        season = f"{start.year + s}-{(start.year + s + 1) % 100:02d}"
        season_start = start.replace(year=start.year + s)
        for li, league in enumerate(LEAGUES):
            idx = list(range(li * TEAMS_PER_LEAGUE, (li + 1) * TEAMS_PER_LEAGUE))
            fixtures = [(h, a) for h in idx for a in idx if h != a]
            rng.shuffle(fixtures)
            for n, (h, a) in enumerate(fixtures):
                kickoff = season_start + timedelta(days=(n // 10) * 7, hours=li)
                _add_match(ds, rng, league, season, kickoff, h, a, physical_missing_rate)
    return ds


def _add_match(
    ds: SyntheticDataset,
    rng: np.random.Generator,
    league: str,
    season: str,
    kickoff: datetime,
    h: int,
    a: int,
    physical_missing_rate: float,
) -> None:
    delta = ds.teams[h].strength - ds.teams[a].strength + HOME_ADVANTAGE + rng.normal(0, 0.6)
    q_home, q_away = delta / 2 + rng.normal(0, 0.35), -delta / 2 + rng.normal(0, 0.35)
    home, away = _attack_profile(rng, q_home), _attack_profile(rng, q_away)

    tilt_home = float(100 / (1 + np.exp(-(0.9 * (q_home - q_away) + rng.normal(0, 0.35)))))
    poss_home = float(np.clip(50 + 9 * (q_home - q_away) + rng.normal(0, 5), 22, 78))

    # Goals on post-shot xG (npxG + finishing) plus the occasional penalty.
    xgot_home = max(0.0, home["npxg_created"] + home["finishing_delta"])
    xgot_away = max(0.0, away["npxg_created"] + away["finishing_delta"])
    g_home = int(rng.poisson(xgot_home) + rng.poisson(0.09))
    g_away = int(rng.poisson(xgot_away) + rng.poisson(0.09))

    m = len(ds.matches)
    ds.matches.append(
        SyntheticMatch(
            external_id=f"syn-{league.lower()}-{season}-{ds.teams[h].short_code}-"
            f"{ds.teams[a].short_code}",
            competition_code=league,
            season=season,
            kickoff_utc=kickoff,
            home=h,
            away=a,
            home_goals=g_home,
            away_goals=g_away,
        )
    )

    for team, opp, own, other, tilt, poss, gf, ga, xgot_faced, is_home in (
        (h, a, home, away, tilt_home, poss_home, g_home, g_away, xgot_away, True),
        (a, h, away, home, 100 - tilt_home, 100 - poss_home, g_away, g_home, xgot_home, False),
    ):
        metrics = {
            **own,
            "field_tilt_pct": round(tilt, 1),
            "npxg_conceded": other["npxg_created"],
            "npxga_per_shot_faced": other["npxg_per_shot"],
            "gk_goals_prevented": round(xgot_faced - ga, 2),
        }
        if rng.random() < physical_missing_rate:
            metrics["distance_per_90_km"] = np.nan
            metrics["sprints_per_min_oop"] = np.nan
        ds.performances.append(
            SyntheticPerformance(
                match=m,
                team=team,
                opponent=opp,
                is_home=is_home,
                goals_for=gf,
                goals_against=ga,
                possession_pct=round(poss, 1),
                metrics=metrics,
            )
        )


def generate_player_cohort(
    n: int, *, seed: int = 42, physical_missing_rate: float = 0.0
) -> np.ndarray:
    """(n, 5) per-90 effort rates in ``player_effort.EFFORT_KEYS`` order, one position group."""
    rng = np.random.default_rng(seed)
    effort = rng.normal(0, 1, n)  # latent work rate drives all five, plus metric noise
    cohort = np.column_stack(
        [
            10.8 + 0.5 * effort + rng.normal(0, 0.4, n),  # distance_per_90_km
            12.0 + 2.5 * effort + rng.normal(0, 2.0, n),  # sprints_per_90
            6.0 + 1.5 * effort + rng.normal(0, 1.5, n),  # ball_recoveries_per_90
            12.0 + 2.5 * effort + rng.normal(0, 2.5, n),  # duels_contested_per_90
            9.0 + 2.0 * effort + rng.normal(0, 2.5, n),  # line_breaking_actions_per_90
        ]
    )
    missing = rng.random(n) < physical_missing_rate
    cohort[missing, :2] = np.nan
    return cohort
