"""Fetch a Premier League season from FotMob + Understat and write clean per-match files.

    uv run python -m corridor.scripts.build_season [--season 2026]

Outputs (gitignored): data/processed/{season}/team_matches.json, player_matches.json
"""

import argparse
import difflib
import json
from collections import defaultdict

from corridor.ingest import fotmob, understat
from corridor.ingest.http import DATA_DIR


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026, help="season start year")
    args = ap.parse_args()
    season = args.season

    fixtures = fotmob.league_matches(f"{season}/{season + 1}")
    finished = [
        m for m in fixtures if m["status"].get("finished") and not m["status"].get("cancelled")
    ]
    print(f"FotMob: {len(finished)} finished PL matches")

    team_rows, player_rows = [], []
    for i, m in enumerate(finished, 1):
        teams, players = fotmob.parse_match(fotmob.match_details(m["id"]))
        team_rows += teams
        player_rows += players
        if i % 10 == 0:
            print(f"  parsed {i}/{len(finished)}")

    us_data = understat.league_data("EPL", season, refresh=True)
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

    out = DATA_DIR / "processed" / str(season)
    out.mkdir(parents=True, exist_ok=True)
    (out / "team_matches.json").write_text(json.dumps(team_rows, indent=1))
    (out / "player_matches.json").write_text(json.dumps(player_rows, indent=1))
    print(f"wrote {len(team_rows)} team rows, {len(player_rows)} player rows → {out}")


if __name__ == "__main__":
    main()
