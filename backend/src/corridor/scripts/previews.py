"""Stage 5: build a preview for every fixture of the next round (D-024).

    uv run python -m corridor.scripts.previews [--season 2026]

Needs predictions.json (run `predictions` first). Fetches each upcoming match's FotMob page
once per run (team news, last starting XI or the official line-up once it is out) and
writes data/site/{season}/previews.json (gitignored).
"""

import argparse
import json
from collections import defaultdict
from datetime import UTC, datetime

from corridor import preview as V
from corridor.ingest import fotmob
from corridor.ingest.fotmob import BASE, role_from_position_id
from corridor.ingest.http import DATA_DIR, fetch_json

SHOOTERS_SHOWN = 6
CORNER_LINES = (8.5, 9.5, 10.5, 11.5)


def _load(season: int, name: str, sub: str = "") -> list[dict]:
    p = DATA_DIR / "processed" / str(season) / sub / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else []


def _season_players(players: list[dict]) -> dict[int, dict]:
    """player_id → this season's minutes, npxG, xA, starts, and team."""
    out: dict[int, dict] = {}
    for p in players:
        a = out.setdefault(
            p["player_id"],
            {
                "name": p["name"],
                "team": p["team"],
                "minutes": 0.0,
                "npxg": 0.0,
                "xa": 0.0,
                "starts": 0,
                "apps": 0,
            },
        )
        a["minutes"] += p["minutes"]
        a["npxg"] += p["npxg_shots"]
        a["xa"] += p.get("xa") or 0.0
        a["starts"] += bool(p["started"])
        a["apps"] += 1
        a["team"] = p["team"]
        a["role"] = p.get("role")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    args = ap.parse_args()
    season = args.season
    out_dir = DATA_DIR / "site" / str(season)
    pred = json.loads((out_dir / "predictions.json").read_text())

    teams_now, players_now = _load(season, "team_matches"), _load(season, "player_matches")
    players_prev = _load(season - 1, "player_matches")

    # Corners: ratings through every played match, plus the backtest for the page.
    corner_seasons = [
        (s, rows) for s in range(season - 2, season + 1) if (rows := _load(s, "team_matches"))
    ]
    corner_preds, CR = V.corner_walk(corner_seasons)
    corner_bt = V.corner_backtest(corner_preds, season - 1)
    disp = corner_bt["side_dispersion"]
    league_total = sum(r["corners"] for r in teams_now if r.get("corners") is not None) / max(
        1, len({r["match_id"] for r in teams_now})
    )

    # Shooters: rates from last season (half weight) + this season.
    roles = V.role_rates(players_prev or players_now)
    R = V.PlayerRates(roles)
    for p in players_prev:
        R.add(p, V.LAST_SEASON_WEIGHT)
    for p in sorted(players_now, key=lambda p: p["match_id"]):
        R.add(p)
    facs = V.opponent_factors(teams_now)
    # Shooter backtest on every season we have player data for (each from its own past).
    shooter_bt = {
        str(s): V.shooter_backtest(prev, cur, _load(s, "team_matches"))
        for s in range(season - 1, season + 1)
        if (prev := _load(s - 1, "player_matches")) and (cur := _load(s, "player_matches"))
    }
    season_stats = _season_players(players_now)
    team_totals: dict[str, dict[str, float]] = defaultdict(lambda: {"npxg_xa": 0.0, "minutes": 0.0})
    for s in season_stats.values():
        team_totals[s["team"]]["npxg_xa"] += s["npxg"] + s["xa"]
        team_totals[s["team"]]["minutes"] += s["minutes"]

    fm_fixtures = {
        (m["home"]["name"], m["away"]["name"]): m
        for m in fotmob.league_matches(f"{season}/{season + 1}")
        if not m["status"].get("finished")
    }

    previews = {}
    for f in pred["next_round"]:
        fm = fm_fixtures.get((f["home"], f["away"]))
        if not fm:
            continue
        d = fetch_json("fotmob_upcoming", f"{BASE}/matchDetails?matchId={fm['id']}", refresh=True)
        lineup = d["content"].get("lineup") or {}
        official = lineup.get("lineupType") not in (None, "lastStarting11", "predicted")
        sides = {}
        for key, team, opp in (
            ("homeTeam", f["home"], f["away"]),
            ("awayTeam", f["away"], f["home"]),
        ):
            t = lineup.get(key) or {}
            out_ids = {u["id"] for u in t.get("unavailable") or []}
            news = []
            tot = team_totals.get(team, {"npxg_xa": 0.0, "minutes": 0.0})
            for u in t.get("unavailable") or []:
                st = season_stats.get(u["id"], {})
                news.append(
                    {
                        "name": u["name"],
                        "type": (u.get("unavailability") or {}).get("type"),
                        "back": (u.get("unavailability") or {}).get("expectedReturn"),
                        "minutes": round(st.get("minutes", 0)),
                        "starts": st.get("starts", 0),
                        "share_output": (st.get("npxg", 0) + st.get("xa", 0)) / tot["npxg_xa"]
                        if tot["npxg_xa"]
                        else 0.0,
                    }
                )
            news.sort(key=lambda x: -x["minutes"])
            fs, fx = facs.get(opp, (1.0, 1.0))
            xi, shooters = [], []
            for s in t.get("starters") or []:
                role = role_from_position_id(s.get("positionId"), s.get("usualPlayingPositionId"))
                unavailable = s["id"] in out_ids
                xi.append({"name": s["name"], "role": role, "out": unavailable})
                if unavailable or role == "GK":
                    continue
                e = V.expect_player(R, s["id"], role, R.minutes_if_starting(s["id"]), fs, fx)
                shooters.append(
                    {"name": s["name"], "role": role} | {k: round(v, 4) for k, v in e.items()}
                )
            shooters.sort(key=lambda x: -x["exp_shots"])
            sides["home" if key == "homeTeam" else "away"] = {
                "team": team,
                "formation": t.get("formation"),
                "xi": xi,
                "news": news,
                "missing_share_output": round(sum(n["share_output"] for n in news), 3),
                "shooters": shooters[:SHOOTERS_SHOWN],
                "exp_shots": round(sum(x["exp_shots"] for x in shooters), 2),
            }
        eh, ea = CR.expect(f["home"], f["away"])
        more = V.p_more(eh, ea, disp)
        previews[f["id"]] = {
            "fotmob_id": fm["id"],
            "lineup": "official" if official else "last_xi",
            "fetched_at": datetime.now(UTC).isoformat(),
            "sides": sides,
            "corners": {
                "exp_home": round(eh, 2),
                "exp_away": round(ea, 2),
                "p_home_more": round(more[0], 3),
                "p_equal": round(more[1], 3),
                "p_away_more": round(more[2], 3),
                "league_total": round(league_total, 2),
                # Totals are barely predictable (D-024): use the league average.
                "p_over": {str(x): round(V.p_over(x, league_total), 3) for x in CORNER_LINES},
            },
        }
        h, a = sides["home"], sides["away"]
        print(
            f"{f['home']:>24} – {f['away']:<24} {'official' if official else 'last XI'}; out "
            f"{len(h['news'])}/{len(a['news'])}; corners {eh:.1f}–{ea:.1f}; top shooter "
            f"{h['shooters'][0]['name'] if h['shooters'] else '—'} / "
            f"{a['shooters'][0]['name'] if a['shooters'] else '—'}"
        )

    out = {
        "generated_at": datetime.now(UTC).isoformat(),
        "fixtures": previews,
        "backtest": {"corners": corner_bt, "shooters": shooter_bt},
    }
    (out_dir / "previews.json").write_text(json.dumps(out, indent=1))
    print(f"wrote {out_dir / 'previews.json'} ({len(previews)} fixtures)")


if __name__ == "__main__":
    main()
