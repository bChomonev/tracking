"""Fetch a season and write clean per-match files.

    uv run python -m corridor.scripts.build_season [--season 2026] [--competition pl|laliga|ucl]

pl, laliga: FotMob + Understat (PPDA, deep completions) — see corridor.leagues
ucl: FotMob events + UEFA physical data (distance, sprints, running without the ball)

Outputs (gitignored): data/processed/{season}/[ucl/|laliga/]team_matches.json, player_matches.json
"""

import argparse
import difflib
import json
from collections import defaultdict

from corridor.ingest import fotmob, uefa, understat
from corridor.ingest.http import DATA_DIR
from corridor.leagues import LEAGUES, processed_dir


def _name_map(fm_fixtures: list[dict], us_dates: list[dict]) -> dict[str, str]:
    """Map Understat team titles → FotMob names by pairing matches with the same kickoff."""
    by_time: dict[str, list[dict]] = defaultdict(list)
    for m in fm_fixtures:
        by_time[m["status"]["utcTime"][:16].replace("T", " ")].append(m)
    votes: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for u in us_dates:
        candidates = by_time.get(u["datetime"][:16], [])
        if not candidates:
            continue
        best = max(
            candidates,
            key=lambda m: (
                difflib.SequenceMatcher(
                    None, u["h"]["title"].lower(), m["home"]["name"].lower()
                ).ratio()
                + difflib.SequenceMatcher(
                    None, u["a"]["title"].lower(), m["away"]["name"].lower()
                ).ratio()
            ),
        )
        votes[u["h"]["title"]][best["home"]["name"]] += 1
        votes[u["a"]["title"]][best["away"]["name"]] += 1
    mapping = {us: max(fm.items(), key=lambda kv: kv[1])[0] for us, fm in votes.items()}
    if len(set(mapping.values())) != len(mapping):
        raise RuntimeError(f"ambiguous team-name mapping: {mapping}")
    return mapping


def _fotmob_season(season: int, league_id: int) -> tuple[list[dict], list[dict], list[dict]]:
    fixtures = fotmob.league_matches(f"{season}/{season + 1}", league_id)
    finished = [
        m for m in fixtures if m["status"].get("finished") and not m["status"].get("cancelled")
    ]
    print(f"FotMob: {len(finished)} finished matches (league {league_id})")
    team_rows, player_rows = [], []
    for i, m in enumerate(finished, 1):
        teams, players = fotmob.parse_match(fotmob.match_details(m["id"]))
        for t in teams:
            t["fixture"] = m
        team_rows += teams
        player_rows += players
        if i % 10 == 0:
            print(f"  parsed {i}/{len(finished)}")
    return fixtures, team_rows, player_rows


def _join_uefa(season: int, team_rows: list[dict]) -> None:
    """Replace physical fields with UEFA's tracking data (FotMob has none for the UCL)."""
    dates = sorted(r["kickoff_utc"][:10] for r in team_rows)
    matches = uefa.season_matches(season, dates[0], dates[-1])
    joined = 0
    for r in team_rows:
        u = uefa.match_to_fotmob(r["fixture"], matches)
        if not u:
            continue
        stats = uefa.team_stats(u["id"])
        own, opp = ("homeTeam", "awayTeam") if r["is_home"] else ("awayTeam", "homeTeam")
        s_own, s_opp = stats.get(str(u[own]["id"])), stats.get(str(u[opp]["id"]))
        if s_own and s_opp:
            r.update(uefa.physical(s_own, s_opp))
            r["uefa_match_id"] = u["id"]
            joined += 1
    print(f"UEFA: joined physical data for {joined}/{len(team_rows)} team-matches")


def _write(out, team_rows: list[dict], player_rows: list[dict]) -> None:
    for r in team_rows:
        r.pop("fixture", None)
    out.mkdir(parents=True, exist_ok=True)
    (out / "team_matches.json").write_text(json.dumps(team_rows, indent=1))
    (out / "player_matches.json").write_text(json.dumps(player_rows, indent=1))
    print(f"wrote {len(team_rows)} team rows, {len(player_rows)} player rows → {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026, help="season start year")
    ap.add_argument("--competition", choices=("pl", "laliga", "ucl"), default="pl")
    args = ap.parse_args()
    season = args.season

    if args.competition == "ucl":
        _, team_rows, player_rows = _fotmob_season(season, fotmob.CHAMPIONS_LEAGUE)
        _join_uefa(season, team_rows)
        for p in player_rows:  # FotMob has no UCL tracking; players stay event-only
            p["competition"] = "ucl"
        _write(DATA_DIR / "processed" / str(season) / "ucl", team_rows, player_rows)
        return

    league = LEAGUES[args.competition]
    fixtures, team_rows, player_rows = _fotmob_season(season, league.fotmob_id)

    us_data = understat.league_data(league.understat, season, refresh=True)
    names = _name_map(fixtures, us_data["dates"])
    us_rows = {(names[r["team"]], r["kickoff"][:10]): r for r in understat.team_matches(us_data)}
    joined = 0
    for r in team_rows:
        u = us_rows.get((r["team"], r["kickoff_utc"][:10]))
        if u and u["goals_for"] == r["goals_for"] and u["goals_against"] == r["goals_against"]:
            r.update(
                {
                    k: u[k]
                    for k in (
                        "ppda",
                        "ppda_allowed",
                        "deep_completions",
                        "deep_allowed",
                        "us_xg",
                        "us_xga",
                        "us_xpts",
                    )
                }
            )
            joined += 1
    print(f"Understat: joined {joined}/{len(team_rows)} team-matches")

    _write(processed_dir(season, league), team_rows, player_rows)


if __name__ == "__main__":
    main()
