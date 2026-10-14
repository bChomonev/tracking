"""Build the team season profile + player profiles and print a terminal summary.

    uv run python -m corridor.scripts.united_profile [--season 2026] [--team "Manchester United"]

Writes data/site/{season}/profile.json (gitignored).
"""

import argparse
import json

from corridor.ingest.http import DATA_DIR
from corridor.profile import player_profiles, team_profile


def _fmt(v, d):
    return "—" if v is None else f"{v:.{d}f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--team", default="Manchester United")
    args = ap.parse_args()

    src = DATA_DIR / "processed" / str(args.season)
    teams = json.loads((src / "team_matches.json").read_text())
    players = json.loads((src / "player_matches.json").read_text())
    prof = team_profile(teams, args.team)
    prof["players"] = player_profiles(players, args.team)
    prof["season"] = f"{args.season}-{(args.season + 1) % 100:02d}"

    out = DATA_DIR / "site" / str(args.season)
    out.mkdir(parents=True, exist_ok=True)
    (out / "profile.json").write_text(json.dumps(prof, indent=1))

    rec = prof["record"]
    print(
        f"\n{args.team} — {prof['season']}: {rec['played']} played, {rec['points']} pts, "
        f"{rec['league_position']}th of {rec['teams']}\n"
    )
    for m in prof["matches"]:
        ha = "H" if m["is_home"] else "A"
        print(
            f"  {m['kickoff_utc'][:10]} {ha} {m['opponent']:<22} {m['goals_for']}-"
            f"{m['goals_against']}  xG {m['xg']:.2f}–{m['xg_conceded']:.2f}"
        )
    for s in prof["stacks"]:
        print(f"\n■ {s['name'].upper()}  (avg percentile {s['score']})")
        for m in (x for x in prof["metrics"] if x["stack"] == s["id"]):
            print(
                f"  {m['label']:<34} {_fmt(m['value'], m['decimals']):>7}  "
                f"rank {m['rank']:>2}/{m['of']}  pct {m['percentile']:>3.0f}  "
                f"(PL avg {_fmt(m['league_avg'], m['decimals'])}, best "
                f"{m['league_best']['team']} {_fmt(m['league_best']['value'], m['decimals'])})"
            )
    print("\nPLAYERS (percentile vs PL players in same position, ≥90 min)")
    for p in prof["players"]:
        ms = p["metrics"]
        print(
            f"  {p['name']:<24} {p['position']:<3} {p['minutes']:>4}′  effort pct "
            f"{_fmt(p['effort_percentile'], 0):>3} | dist {_fmt(ms['distance_m']['value'], 1)} "
            f"({_fmt(ms['distance_m']['percentile'], 0)}) spr {_fmt(ms['sprints']['value'], 1)} "
            f"({_fmt(ms['sprints']['percentile'], 0)}) rec {_fmt(ms['recoveries']['value'], 1)} "
            f"({_fmt(ms['recoveries']['percentile'], 0)})"
        )
    print(f"\nwrote {out / 'profile.json'}")


if __name__ == "__main__":
    main()
