"""Build the team season profile + player profiles and print a terminal summary.

    uv run python -m corridor.scripts.united_profile [--season 2026] [--team "Manchester United"]

Writes data/site/{season}/profile.json (gitignored).
"""

import argparse
import json

from corridor import proof
from corridor.best_line import build_line, compare, hits_line
from corridor.ingest import understat
from corridor.ingest.http import DATA_DIR
from corridor.profile import player_profiles, team_profile


def _fmt(v, d):
    return "—" if v is None else f"{v:.{d}f}"


def _label(y: int) -> str:
    return f"{y}-{(y + 1) % 100:02d}"


def _proof(season: int, team: str, prof: dict) -> dict:
    """Stage 3: out-of-sample test of the lines on every team-match, then place each of the
    team's matches on that record (D-020)."""
    fot = [
        (_label(y), json.loads(p.read_text()))
        for y in range(season - 2, season + 1)
        if (p := DATA_DIR / "processed" / str(y) / "team_matches.json").exists()
    ]
    fm = proof.evaluate(proof.fotmob_seasons(fot), proof.FOTMOB_METRICS, proof.FOTMOB_BINS)
    us_seasons = [
        (_label(y), proof.understat_rows(understat.team_matches(understat.league_data("EPL", y))))
        for y in range(2014, season + 1)
    ]
    us = proof.evaluate(us_seasons, proof.UNDERSTAT_METRICS, proof.UNDERSTAT_BINS)

    # Place each match: FotMob share over the latest pair's proven metrics, against this
    # season's lines (already on the profile); Understat share over the 5 core metrics.
    keys = fm["pairs"][-1]["metrics"]
    us_lines = {
        side: build_line(
            us_seasons[-2][1],
            us_seasons[-2][0],
            us_seasons[-1][1],
            side,
            proof.UNDERSTAT_METRICS,
            derived=True,
        )
        for side in ("best", "worst")
    }
    us_mine = {r["kickoff_utc"][:10]: r for r in us_seasons[-1][1] if r["team"] == team}
    placed = []
    for i, mt in enumerate(prof["matches"]):
        rec: dict = {"match_id": mt["match_id"]}
        for side in ("best", "worst"):
            hit = n = 0
            for m in prof["metrics"]:
                ln = m.get(f"{side}_line")
                if m["key"] in keys and ln:
                    h = hits_line(m["matches"][i]["value"], ln["value"], m["direction"], side)
                    if h is not None:
                        n += 1
                        hit += h
            share = hit / n if n else None
            rec[side] = {
                "hits": hit,
                "of": n,
                "share": share,
                "history": proof.place(share, fm[side]),
            }
            ur = us_mine.get(mt["kickoff_utc"][:10])
            if ur:
                uh, un = proof.score(
                    ur,
                    us_lines[side],
                    proof.UNDERSTAT_METRICS,
                    [m.key for m in proof.UNDERSTAT_METRICS],
                )
                ushare = uh / un if un else None
                rec[f"{side}_core"] = {
                    "hits": uh,
                    "of": un,
                    "share": ushare,
                    "history": proof.place(ushare, us[side]),
                }
        placed.append(rec)
    return {"fotmob": fm, "understat": us, "matches": placed}


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
    prof["competition"] = "Premier League"
    prev = DATA_DIR / "processed" / str(args.season - 1) / "team_matches.json"
    if prev.exists():
        # Stages 2-3: last season's top-4 wins / bottom-4 losses define this season's
        # best and worst lines (PL only).
        prev_rows = json.loads(prev.read_text())
        label = f"{args.season - 1}-{args.season % 100:02d}"
        for side in ("best", "worst"):
            compare(prof, build_line(prev_rows, label, teams, side=side))
    if "best_line" in prof:
        prof["proof"] = _proof(args.season, args.team, prof)
    ucl_src = src / "ucl" / "team_matches.json"
    if ucl_src.exists():
        # Separate pool, separate providers: ranked only against other UCL team-matches.
        ucl = team_profile(json.loads(ucl_src.read_text()), args.team)
        prof["ucl"] = ucl | {"competition": "Champions League", "season": prof["season"]}

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
    for side in ("best", "worst"):
        if f"{side}_line" not in prof:
            continue
        bl = prof[f"{side}_line"]
        print(
            f"\n{side.upper()} LINE — {bl['season']} ({', '.join(bl['teams'])}): {bl['games']} "
            f"{'wins' if side == 'best' else 'losses'}, {len(bl['excluded'])} excluded (red "
            f"cards); not comparable: {bl['not_comparable'] or 'none'}"
        )
        print(f"  typical match hits it on {bl['typical_hits']} of {bl['metrics_compared']}")
        for m in prof["metrics"]:
            if b := m.get(f"{side}_line"):
                print(
                    f"  {m['label']:<34} {_fmt(m['value'], m['decimals']):>7} vs line "
                    f"{_fmt(b['value'], m['decimals']):>7} ({_fmt(b['p25'], m['decimals'])}–"
                    f"{_fmt(b['p75'], m['decimals'])}, n={b['n']})  "
                    f"{'✓' if b['typical_hits'] else '·'} hit in "
                    f"{b['matches_hit']}/{b['matches_counted']}"
                )
    if "ucl" in prof:
        u = prof["ucl"]
        print(
            f"\nCHAMPIONS LEAGUE — {u['record']['played']} played "
            f"(ranked vs {u['metrics'][0]['of']} teams)"
        )
        for m in u["metrics"]:
            print(
                f"  {m['label']:<34} {_fmt(m['value'], m['decimals']):>7}  "
                f"rank {m['rank']:>2}/{m['of']}  pct {m['percentile']:>3.0f}"
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
