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

from corridor import matchup
from corridor import preview as V
from corridor.ingest import fotmob
from corridor.ingest.fotmob import BASE, role_from_position_id
from corridor.ingest.http import fetch_json
from corridor.leagues import LEAGUES, League, processed_dir, site_dir

SHOOTERS_SHOWN = 6
CORNER_LINES = (8.5, 9.5, 10.5, 11.5)


def _load(season: int, name: str, league: League = LEAGUES["pl"]) -> list[dict]:
    p = processed_dir(season, league) / f"{name}.json"
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
    ap.add_argument("--league", choices=tuple(LEAGUES), default="pl")
    args = ap.parse_args()
    lg = LEAGUES[args.league]
    season = args.season
    out_dir = site_dir(season, lg)
    pred = json.loads((out_dir / "predictions.json").read_text())
    league_json = out_dir / "league.json"
    league = json.loads(league_json.read_text()) if league_json.exists() else {}

    teams_now, players_now = _load(season, "team_matches", lg), _load(season, "player_matches", lg)
    players_prev = _load(season - 1, "player_matches", lg)

    # Corners: ratings through every played match, plus the backtest for the page.
    corner_seasons = [
        (s, rows) for s in range(season - 2, season + 1) if (rows := _load(s, "team_matches", lg))
    ]
    corner_preds, CR = V.corner_walk(corner_seasons)
    corner_bt = V.corner_backtest(corner_preds, season - 1)
    disp = corner_bt["side_dispersion"]
    # Cards (D-030): same idea; totals and reds use league rates (not predictable).
    card_preds, KR = V.card_walk(corner_seasons)
    card_bt = V.card_backtest(card_preds, season - 1)
    n_now = max(1, len({r["match_id"] for r in teams_now}))
    league_yellows = sum(r.get("yellow_cards") or 0 for r in teams_now) / n_now
    league_red = card_bt["red_rate"]  # this season + last: reds are rare
    ref_games: dict[str, list[int]] = {}
    for r in teams_now:
        if r.get("referee") and r["is_home"]:
            g = ref_games.setdefault(r["referee"], [0, 0])
            g[0] += 1
            g[1] += sum(
                x.get("yellow_cards") or 0 for x in teams_now if x["match_id"] == r["match_id"]
            )
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
    facs = V.opponent_factors(teams_now, prev_rows=_load(season - 1, "team_matches", lg))
    # Shooter backtest on every season we have player data for (each from its own past).
    shooter_bt = {
        str(s): V.shooter_backtest(
            prev, cur, _load(s, "team_matches", lg), _load(s - 1, "team_matches", lg)
        )
        for s in range(season - 1, season + 1)
        if (prev := _load(s - 1, "player_matches", lg)) and (cur := _load(s, "player_matches", lg))
    }
    season_stats = _season_players(players_now)
    team_totals: dict[str, dict[str, float]] = defaultdict(lambda: {"npxg_xa": 0.0, "minutes": 0.0})
    for s in season_stats.values():
        team_totals[s["team"]]["npxg_xa"] += s["npxg"] + s["xa"]
        team_totals[s["team"]]["minutes"] += s["minutes"]

    fm_fixtures = {
        (m["home"]["name"], m["away"]["name"]): m
        for m in fotmob.league_matches(f"{season}/{season + 1}", lg.fotmob_id)
        if not m["status"].get("finished")
    }

    # Each team's last league starting XI from our own data: the fallback when FotMob has no
    # line-up yet (days before a match its page often has none), so shooters still show.
    ko = {r["match_id"]: r["kickoff_utc"] for r in teams_now}
    last_match: dict[str, int] = {}
    for p in players_now:
        if p.get("started") and ko.get(p["match_id"], "") >= ko.get(
            last_match.get(p["team"], 0), ""
        ):
            last_match[p["team"]] = p["match_id"]
    our_last_xi = {
        team: [
            {"id": p["player_id"], "name": p["name"], "role": p.get("role")}
            for p in players_now
            if p["team"] == team and p["match_id"] == mid and p.get("started")
        ]
        for team, mid in last_match.items()
    }

    previews = {}
    for f in pred["next_round"]:
        fm = fm_fixtures.get((f["home"], f["away"]))
        if not fm:
            continue
        # `predictions` fetched this page moments ago; reuse it (one request per fixture).
        d = fetch_json("fotmob_upcoming", f"{BASE}/matchDetails?matchId={fm['id']}")
        lineup = d["content"].get("lineup") or {}
        # "standard" = the confirmed XI; "predicted" = FotMob's predicted XI (from its data
        # partner); "lastStarting11" = each side's previous XI; "unavailable" = none yet.
        lineup_type = lineup.get("lineupType")
        has_xi = any((lineup.get(k) or {}).get("starters") for k in ("homeTeam", "awayTeam"))
        official = lineup_type == "standard" and has_xi
        fallback = False
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
            starters = t.get("starters") or []
            if not starters and our_last_xi.get(team):
                starters, fallback = our_last_xi[team], True
            for s in starters:
                role = s.get("role") or role_from_position_id(
                    s.get("positionId"), s.get("usualPlayingPositionId")
                )
                unavailable = s["id"] in out_ids
                xi.append({"name": s["name"], "role": role, "out": unavailable})
                if unavailable or role == "GK":
                    continue
                e = V.expect_player(R, s["id"], role, R.minutes_if_starting(s["id"]), fs, fx)
                shooters.append(
                    {"name": s["name"], "role": role} | {k: round(v, 4) for k, v in e.items()}
                )
            booked = sorted(shooters, key=lambda x: -x["p_booked"])[:3]
            shooters.sort(key=lambda x: -x["exp_shots"])
            sides["home" if key == "homeTeam" else "away"] = {
                "team": team,
                "formation": t.get("formation"),
                "xi": xi,
                "news": news,
                "missing_share_output": round(sum(n["share_output"] for n in news), 3),
                "shooters": shooters[:SHOOTERS_SHOWN],
                "exp_shots": round(sum(x["exp_shots"] for x in shooters), 2),
                "likely_booked": [
                    {"name": x["name"], "role": x["role"], "p": x["p_booked"]} for x in booked
                ],
                "assisters": sorted(
                    (
                        {
                            "name": x["name"],
                            "role": x["role"],
                            "p_assist": x["p_assist"],
                            "p_involved": x["p_involved"],
                        }
                        for x in shooters
                    ),
                    key=lambda x: -x["p_assist"],
                )[:4],
            }
        eh, ea = CR.expect(f["home"], f["away"])
        more = V.p_more(eh, ea, disp)
        ref = V.referee_name(d)
        yh, ya = KR.expect(f["home"], f["away"], ref, use_ref=False)
        ymore = V.p_more(yh, ya, 50.0)
        rg = ref_games.get(ref or "", [0, 0])
        previews[f["id"]] = {
            "fotmob_id": fm["id"],
            # D-054: both sides played against each other, from the season profiles.
            "matchup": matchup.build(
                league,
                f["home"],
                f["away"],
                sides["home"]["xi"],
                sides["away"]["xi"],
                (f.get("exp_home"), f.get("exp_away")) if f.get("exp_home") is not None else None,
            ),
            "lineup": "last_xi"
            if fallback and not has_xi
            else {
                "standard": "official",
                "predicted": "predicted",
                "lastStarting11": "last_xi",
            }.get(lineup_type or "", "none")
            if has_xi
            else "none",
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
            "cards": {
                "referee": ref,
                "referee_games": rg[0],
                "referee_yellows_per_game": round(rg[1] / rg[0], 2) if rg[0] else None,
                "league_yellows_per_game": round(league_yellows, 2),
                "exp_home": round(yh, 2),
                "exp_away": round(ya, 2),
                "p_home_more": round(ymore[0], 3),
                "p_equal": round(ymore[1], 3),
                "p_away_more": round(ymore[2], 3),
                # Totals and red cards aren't predictable (D-030): league rates.
                "p_over": {str(x): round(V.p_over(x, league_yellows), 3) for x in (3.5, 4.5, 5.5)},
                "p_red": round(league_red, 3),
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
        "backtest": {"corners": corner_bt, "shooters": shooter_bt, "cards": card_bt},
    }
    (out_dir / "previews.json").write_text(json.dumps(out, indent=1))
    print(f"wrote {out_dir / 'previews.json'} ({len(previews)} fixtures)")


if __name__ == "__main__":
    main()
