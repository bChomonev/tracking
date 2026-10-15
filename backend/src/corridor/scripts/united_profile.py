"""Build season profiles for every Premier League team (lines, proof placement, focus
tiers, players, UCL) plus the overview table, and print a summary for the focus team.

    uv run python -m corridor.scripts.united_profile [--season 2026] [--team "Manchester United"]

Writes data/site/{season}/league.json (all teams + overview) and profile.json (the focus
team with the shared proof, read by the analyst). Both gitignored.
"""

import argparse
import json

from corridor import proof
from corridor.best_line import build_line, compare, hits_line
from corridor.ingest import understat
from corridor.ingest.http import DATA_DIR
from corridor.profile import player_profiles, shooting, team_profile


def _fmt(v, d):
    return "—" if v is None else f"{v:.{d}f}"


def _label(y: int) -> str:
    return f"{y}-{(y + 1) % 100:02d}"


def proof_record(season: int) -> dict:
    """Stage 3 proof, computed once per build and shared by every team (D-020, D-021)."""
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
    return {"fotmob": fm, "understat": us, "us_lines": us_lines, "us_rows": us_seasons[-1][1]}


def _understat_row(rec: dict, fm_row: dict) -> dict | None:
    """The Understat row for a FotMob team-match: same day, same score, and the same
    Understat PPDA and deep completions for/against (joined into FotMob rows at build
    time). A draw on the same day can share a score, so the score alone is not enough."""
    day = fm_row["kickoff_utc"][:10]
    for r in rec["us_rows"]:
        if (
            r["kickoff_utc"][:10] == day
            and r["goals_for"] == fm_row["goals_for"]
            and r["goals_against"] == fm_row["goals_against"]
            and r["deep_completions"] == fm_row.get("deep_completions")
            and r["deep_allowed"] == fm_row.get("deep_allowed")
            and fm_row.get("ppda") is not None
            and abs(r["ppda"] - fm_row["ppda"]) < 1e-6
        ):
            return r
    return None


def place(prof: dict, rows: list[dict], rec: dict) -> dict:
    """Place each of a team's matches (and its typical match) on the proof record."""
    fm, us = rec["fotmob"], rec["understat"]
    keys = fm["pairs"][-1]["metrics"]
    weights = fm["weighted"]["weights"]
    by_id = {r["match_id"]: r for r in rows if r["team"] == prof["team"]}
    placed = []
    for i, mt in enumerate(prof["matches"]):
        out: dict = {"match_id": mt["match_id"]}
        ur = _understat_row(rec, by_id[mt["match_id"]]) if mt["match_id"] in by_id else None
        for side in ("best", "worst"):
            by = {}
            for m in prof["metrics"]:
                ln = m.get(f"{side}_line")
                if m["key"] in keys and ln:
                    h = hits_line(m["matches"][i]["value"], ln["value"], m["direction"], side)
                    if h is not None:
                        by[m["key"]] = h
            hit, n = sum(by.values()), len(by)
            share = hit / n if n else None
            out[side] = {
                "hits": hit,
                "of": n,
                "share": share,
                "history": proof.place(share, fm[side]),
            }
            ws = proof.weighted_share(by, weights[side])
            out[f"{side}_weighted"] = {
                "share": ws,
                "history": proof.place(ws, {"bins": fm["weighted"]["bins"][side]}),
            }
            if ur:
                uh, un = proof.score(
                    ur,
                    rec["us_lines"][side],
                    proof.UNDERSTAT_METRICS,
                    [m.key for m in proof.UNDERSTAT_METRICS],
                )
                ushare = uh / un if un else None
                out[f"{side}_core"] = {
                    "hits": uh,
                    "of": un,
                    "share": ushare,
                    "history": proof.place(ushare, us[side]),
                }
        placed.append(out)
    typical = {}
    for side in ("best", "worst"):
        by = {
            m["key"]: bool(m[f"{side}_line"]["typical_hits"])
            for m in prof["metrics"]
            if m["key"] in keys and m.get(f"{side}_line")
        }
        ws = proof.weighted_share(by, weights[side])
        typical[side] = {
            "share": ws,
            "history": proof.place(ws, {"bins": fm["weighted"]["bins"][side]}),
        }
    return {"matches": placed, "typical_weighted": typical}


def focus(prof: dict, fm: dict) -> dict:
    """Tag every metric with its proven impact and count where the team stands on each tier
    (D-021): does it win the things that decide matches, or the things that don't?"""
    imp = proof.impact(fm)
    for comp in (prof, prof.get("ucl")):
        for m in comp["metrics"] if comp else []:
            if m["key"] in imp:
                m["impact"] = imp[m["key"]]
    tiers = {}
    for _, tier in proof.TIERS:
        ms = [m for m in prof["metrics"] if m.get("impact", {}).get("tier") == tier]
        ms.sort(key=lambda m: -m["impact"]["impact"])
        status = [
            "best"
            if m.get("best_line", {}).get("typical_hits")
            else "worst"
            if m.get("worst_line", {}).get("typical_hits")
            else "between"
            for m in ms
        ]
        tiers[tier] = {
            "metrics": [m["key"] for m in ms],
            "status": status,
            **{s: status.count(s) for s in ("best", "between", "worst")},
        }
    untested = [m["key"] for m in prof["metrics"] if "impact" not in m]
    return {"tiers": tiers, "untested": untested}


def build_team(
    team: str, ctx: dict, rec: dict | None, lines: dict, ucl_rows: list[dict] | None
) -> dict:
    prof = team_profile(ctx["rows"], team)
    prof["players"] = player_profiles(ctx["players"], team)
    prof["shooting"] = shooting(ctx["players"], team)
    prof["season"] = ctx["season"]
    prof["competition"] = "Premier League"
    for line in lines.values():
        compare(prof, line)
    if rec and "best_line" in prof:
        prof["proof"] = place(prof, ctx["rows"], rec)
        prof["focus"] = focus(prof, rec["fotmob"])
    if ucl_rows and any(r["team"] == team for r in ucl_rows):
        # Separate pool, separate providers: ranked only against other UCL team-matches.
        ucl = team_profile(ucl_rows, team)
        prof["ucl"] = ucl | {"competition": "Champions League", "season": prof["season"]}
        if "focus" in prof:
            imp = {m["key"]: m["impact"] for m in prof["metrics"] if "impact" in m}
            for m in prof["ucl"]["metrics"]:
                if m["key"] in imp:
                    m["impact"] = imp[m["key"]]
    return prof


def _expected_points(x: dict) -> float | None:
    """Points a match's performance 'deserved': the average of the W/D rates of past
    team-matches with the same elite score and with the same danger score."""
    hs = [x[k]["history"] for k in ("best_weighted", "worst_weighted") if x[k].get("history")]
    hs = [h for h in hs if h["n"]]
    if not hs:
        return None
    return sum(3 * h["W"] + h["D"] for h in hs) / len(hs)


def table_row(prof: dict) -> dict:
    """One overview row: results, xG, and where the team stands on what decides matches."""
    ms = prof["matches"]
    row = {
        "team": prof["team"],
        "position": prof["record"]["league_position"],
        "played": len(ms),
        "w": sum(m["result"] == "W" for m in ms),
        "d": sum(m["result"] == "D" for m in ms),
        "l": sum(m["result"] == "L" for m in ms),
        "gf": sum(m["goals_for"] for m in ms),
        "ga": sum(m["goals_against"] for m in ms),
        "points": prof["record"]["points"],
        "xg": sum(m["xg"] or 0 for m in ms),
        "xga": sum(m["xg_conceded"] or 0 for m in ms),
        "understat_xpts": sum(m["us_xpts"] or 0 for m in ms)
        if all(m.get("us_xpts") is not None for m in ms)
        else None,
        "stacks": {st["id"]: st["score"] for st in prof["stacks"]},
        "form": [m["result"] for m in ms[-5:]],
    }
    if "focus" in prof:
        pr, dec = prof["proof"], prof["focus"]["tiers"]["decisive"]
        xp = [_expected_points(x) for x in pr["matches"]]
        row |= {
            "decisive": {k: dec[k] for k in ("best", "between", "worst")}
            | {"of": len(dec["metrics"])},
            "elite_score": pr["typical_weighted"]["best"]["share"],
            "danger_score": pr["typical_weighted"]["worst"]["share"],
            "elite_score_matches": [x["best_weighted"]["share"] for x in pr["matches"]],
            "danger_score_matches": [x["worst_weighted"]["share"] for x in pr["matches"]],
            "deserved_points": sum(v for v in xp if v is not None) if xp else None,
        }
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--team", default="Manchester United")
    args = ap.parse_args()

    src = DATA_DIR / "processed" / str(args.season)
    rows = json.loads((src / "team_matches.json").read_text())
    ctx = {
        "rows": rows,
        "players": json.loads((src / "player_matches.json").read_text()),
        "season": _label(args.season),
    }
    lines: dict = {}
    prev = DATA_DIR / "processed" / str(args.season - 1) / "team_matches.json"
    if prev.exists():
        # Stages 2-3: last season's top-4 wins / bottom-4 losses define this season's
        # best and worst lines (PL only), the same lines for every team.
        prev_rows = json.loads(prev.read_text())
        lines = {
            side: build_line(prev_rows, _label(args.season - 1), rows, side=side)
            for side in ("best", "worst")
        }
    rec = proof_record(args.season) if lines else None
    ucl_src = src / "ucl" / "team_matches.json"
    ucl_rows = json.loads(ucl_src.read_text()) if ucl_src.exists() else None

    names = sorted({r["team"] for r in rows})
    teams = {t: build_team(t, ctx, rec, lines, ucl_rows) for t in names}
    gaps = sorted(
        (p["shooting"]["quality_gap_per_match"] or 0 for p in teams.values()), reverse=True
    )
    for p in teams.values():
        p["shooting"]["league_rank_wasted"] = (
            gaps.index(p["shooting"]["quality_gap_per_match"] or 0) + 1
        )
        p["shooting"]["teams"] = len(gaps)
    prof = teams[args.team]
    out = DATA_DIR / "site" / str(args.season)
    out.mkdir(parents=True, exist_ok=True)
    shared = {"fotmob": rec["fotmob"], "understat": rec["understat"]} if rec else None
    # The focus team's file carries the shared proof too: the analyst reads it.
    focus_prof = prof | ({"proof": prof["proof"] | shared} if shared else {})
    (out / "profile.json").write_text(json.dumps(focus_prof, indent=1))
    league = {
        "season": ctx["season"],
        "competition": "Premier League",
        "focus_team": args.team,
        "proof": shared,
        "table": sorted((table_row(p) for p in teams.values()), key=lambda r: r["position"]),
        "teams": teams,
    }
    (out / "league.json").write_text(json.dumps(league, separators=(",", ":")))
    prof = focus_prof

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
    print(f"\nwrote {out / 'profile.json'} and league.json ({len(teams)} teams)")


if __name__ == "__main__":
    main()
