"""Post-match blog drafts (D-034): a one-match fact sheet and the charts for it.

The writer (scripts/post.py) turns the facts into a commentary-style draft. Everything here
comes from data the site already holds: the team's profile (each match's metrics against
the elite and worst lines, elite / danger scores and how teams with those scores did), the
FotMob match page (events, shot map) and the predictions log (what we said before kickoff).
"""

import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

INK, MUTED, RED, GREEN, RULE, BG = "#1d1718", "#6d6264", "#c4121a", "#1f7a4d", "#e4dcdc", "#f6f4f3"


def _r(x: float | None, d: int) -> float | None:
    return None if x is None else round(float(x), d)


def match_index(prof: dict, match_id: int) -> int:
    return next(i for i, m in enumerate(prof["matches"]) if m["match_id"] == match_id)


def events(details: dict, home: bool) -> list[dict]:
    """Goals, red cards and the first-half/second-half split from the FotMob match page."""
    out = []
    for e in (
        ((details.get("content") or {}).get("matchFacts") or {}).get("events", {}).get("events", [])
    ):
        if e.get("type") == "Goal":
            out.append(
                {
                    "minute": e.get("time"),
                    "type": "goal",
                    "for": "us" if bool(e.get("isHome")) == home else "them",
                    "player": e.get("nameStr") or e.get("fullName"),
                    "own_goal": bool(e.get("ownGoal")),
                    "penalty": e.get("goalDescription") == "Penalty"
                    or bool(e.get("isPenaltyShootoutEvent")),
                }
            )
        elif e.get("type") == "Card" and e.get("card") in ("Red", "YellowRed"):
            out.append(
                {
                    "minute": e.get("time"),
                    "type": "red card",
                    "for": "us" if bool(e.get("isHome")) == home else "them",
                    "player": e.get("nameStr") or e.get("fullName"),
                }
            )
    return sorted(out, key=lambda x: x["minute"] or 0)


# Running numbers in the Champions League come from UEFA's tracking, which measures
# differently from FotMob's league data: never placed against the (FotMob) league lines.
RUNNING = {
    "distance_km",
    "distance_gap_km",
    "sprints",
    "sprints_gap",
    "distance_oop_adj_km",
    "high_intensity_runs",
}
ROLE_NAMES = {
    "CB": "centre-back",
    "FB": "full-back",
    "CM": "central midfielder",
    "AM": "attacking midfielder",
    "W": "winger",
    "ST": "striker",
}
# (key, words, direction): the per-player numbers a column can compare with the same role.
STANDOUT_STATS = (
    ("duels_won", "duels won", 1),
    ("recoveries", "ball recoveries", 1),
    ("tackles", "tackles", 1),
    ("interceptions", "interceptions", 1),
    ("line_breaking_passes", "line-breaking passes", 1),
    ("passes_into_final_third", "passes into the final third", 1),
    ("chances_created", "chances created", 1),
    ("box_touches", "touches in the opponent's box", 1),
    ("sprints", "sprints", 1),
    ("duels_lost", "duels lost", -1),
    ("dispossessed", "times dispossessed", -1),
    ("dribbled_past", "times dribbled past", -1),
)


def ucl_view(prof: dict) -> dict:
    """The team's Champions League matches shaped like a league profile: each FotMob metric
    carries the league's elite and worst lines and tiers (same provider, same definitions);
    running metrics (UEFA) carry none."""
    league = {m["key"]: m for m in prof["metrics"]}
    metrics = []
    for m in prof["ucl"]["metrics"]:
        base = league.get(m["key"]) if m["key"] not in RUNNING else None
        metrics.append(
            m
            | {
                "best_line": (base or {}).get("best_line"),
                "worst_line": (base or {}).get("worst_line"),
                "impact": (base or {}).get("impact"),
            }
        )
    return {
        "matches": prof["ucl"]["matches"],
        "metrics": metrics,
        "focus": prof.get("focus"),
        "proof": {},
        "shooting": None,
    }


def standouts(players: list[dict], match_id: int, team: str, min_minutes: int = 45) -> list:
    """Each player's match numbers against every game this season (same competition, same
    role, 60+ minutes): how many of those games had more (or, for bad numbers, worse). The
    column picks the best and worst from here; it never has to work out a rank itself."""
    pool = [
        p for p in players if (p.get("minutes") or 0) >= 60 and p.get("role") not in (None, "GK")
    ]
    out = []
    for p in players:
        if p["match_id"] != match_id or p["team"] != team or p.get("role") in (None, "GK"):
            continue
        if (p.get("minutes") or 0) < min_minutes:
            continue
        top, bottom = [], []
        for k, words, d in STANDOUT_STATS:
            v = p.get(k)
            peers = [
                q[k] for q in pool if q["role"] == p["role"] and q.get(k) is not None and q is not p
            ]
            if v is None or len(peers) < 20:
                continue
            better = sum((x > v) if d > 0 else (x < v) for x in peers)
            worse = sum((x < v) if d > 0 else (x > v) for x in peers)
            same = len(peers) - better - worse
            row = {"stat": words, "value": _r(v, 2), "games_compared": len(peers)}
            # Notable only when few games matched it: 0 dispossessions ties with hundreds.
            if better + same <= 0.1 * len(peers):
                top.append(row | {"games_with_better": better, "games_with_the_same": same})
            elif worse + same <= 0.1 * len(peers):
                bottom.append(row | {"games_with_worse": worse, "games_with_the_same": same})
        out.append(
            {
                "name": p["name"],
                "role": ROLE_NAMES.get(p["role"], p["role"]),
                "minutes": int(p["minutes"]),
                "fotmob_rating": p.get("rating"),
                "goals": int(p.get("goals") or 0),
                "assists": int(p.get("assists") or 0),
                "duels_won": p.get("duels_won"),
                "duels_lost": p.get("duels_lost"),
                "touches": p.get("touches"),
                "best_of_the_season_for_his_role": sorted(
                    top, key=lambda r: r["games_with_better"]
                )[:3],
                "worst_of_the_season_for_his_role": sorted(
                    bottom, key=lambda r: r["games_with_worse"]
                )[:3],
            }
        )
    return sorted(out, key=lambda r: -r["minutes"])


def match_facts(
    league: dict,
    team: str,
    match_id: int,
    details: dict,
    players: list[dict],
    pre: dict | None,
    nxt: list[dict] | dict | None,
    competition: str = "league",
) -> dict[str, Any]:
    ucl = competition == "ucl"
    prof = ucl_view(league["teams"][team]) if ucl else league["teams"][team]
    i = match_index(prof, match_id)
    mt = prof["matches"][i]
    home = mt["is_home"]
    tiers = (prof.get("focus") or {}).get("tiers", {})
    decisive = set(tiers.get("decisive", {}).get("metrics", [])) - (RUNNING if ucl else set())

    def metric_row(m: dict) -> dict:
        v = m["matches"][i]["value"]
        bl, wl = m.get("best_line"), m.get("worst_line")
        status = None
        if v is not None and bl and wl:
            d = m["direction"]
            status = (
                "at or beyond the elite line"
                if v * d >= bl["value"] * d
                else "at or beyond the worst line"
                if v * d <= wl["value"] * d
                else "between the lines"
            )
        return {
            "key": m["key"],
            "metric": m["label"],
            "meaning": m["explain"],
            "this_match": _r(v, m["decimals"] + 1),
            "elite_line": _r(bl["value"], m["decimals"] + 1) if bl else None,
            "worst_line": _r(wl["value"], m["decimals"] + 1) if wl else None,
            "status": status,
            "season_typical_match": _r(m["value"], m["decimals"] + 1),
            "decides_matches": m.get("impact", {}).get("tier") == "decisive",
        }

    metrics = [metric_row(m) for m in prof["metrics"] if m.get("impact")]
    pr = prof.get("proof", {}).get("matches", [])
    place = pr[i] if i < len(pr) else {}
    hist = lambda x, k: None if not x or not x.get("history") else round(100 * x["history"][k])  # noqa: E731

    mine = [p for p in players if p["match_id"] == match_id and p["team"] == team]
    shooters = sorted(
        (
            {
                "name": p["name"],
                "role": p.get("role"),
                "minutes": int(p["minutes"]),
                "shots": p["np_shots"],
                "on_target": p.get("np_shots_on_target", 0),
                "npxg": _r(p["npxg_shots"], 2),
                "goals": int(p.get("goals") or 0),
                "assists": int(p.get("assists") or 0),
                "xa": _r(p.get("xa"), 2),
                "avg_shot_distance_m": _r(p["np_shot_distance_sum_m"] / p["np_shots"], 1)
                if p["np_shots"]
                else None,
                "outside_box": p.get("np_shots_outside_box", 0),
                "blocked": p.get("np_shots_blocked", 0),
                "distance_km": _r((p.get("distance_m") or 0) / 1000, 1)
                if p.get("distance_m")
                else None,
                "sprints": p.get("sprints"),
            }
            for p in mine
        ),
        key=lambda r: (-r["shots"], -r["minutes"]),
    )
    table = next((r for r in league["table"] if r["team"] == team), {})
    rec = (league["teams"][team].get("ucl") or {}).get("record", {}) if ucl else {}
    out: dict[str, Any] = {
        "team": team,
        "competition": "UEFA Champions League" if ucl else league["competition"],
        "season": league["season"],
        "match": {
            "opponent": mt["opponent"],
            "venue": "home" if home else "away",
            "date": mt["kickoff_utc"][:10],
            "score": f"{mt['goals_for']}-{mt['goals_against']}",
            "result": {"W": "win", "D": "draw", "L": "defeat"}[mt["result"]],
            "possession_pct": mt.get("possession_pct"),
            "xg_for": mt.get("xg"),
            "xg_against": mt.get("xg_conceded"),
            "opponent_league_position_now": mt.get("opponent_league_position"),
        },
        "events": events(details, home),
        "shots_summary": shots_summary(details, home),
        "running_vs_opponent": running(prof, i)
        | (
            {"measured_by": "UEFA tracking (not comparable with league running numbers)"}
            if ucl
            else {}
        )
        if running(prof, i)
        else None,
        "lines": {
            "what_they_are": (
                "Elite line = what last season's top four looked like in their typical league "
                "win; worst line = the bottom four in their typical defeat. 'decides_matches' "
                "marks the metrics that, tested on later seasons, moved results the most."
                + (
                    " This is a Champions League match measured against the "
                    f"{league['competition']} lines (same data provider, same definitions). "
                    "Running is measured by UEFA in"
                    " the Champions League, so it is not placed against the lines."
                    if ucl
                    else ""
                )
            ),
            "decisive_metrics_at_elite_line": sum(
                1
                for x in metrics
                if x["key"] in decisive and x["status"] == "at or beyond the elite line"
            ),
            "decisive_metrics_at_worst_line": sum(
                1
                for x in metrics
                if x["key"] in decisive and x["status"] == "at or beyond the worst line"
            ),
            "decisive_metrics_total": len(decisive),
            "metrics": metrics,
        },
        "performance_score": {
            "what_it_is": (
                "Elite score / danger score: share of the elite / worst lines this match "
                "reached, weighted by how much each decides matches (0-100), and how often "
                "past teams with the same score won / lost."
            ),
            "elite_score": round(100 * place["best_weighted"]["share"])
            if place.get("best_weighted")
            else None,
            "pct_of_such_teams_won": hist(place.get("best_weighted"), "W"),
            "danger_score": round(100 * place["worst_weighted"]["share"])
            if place.get("worst_weighted")
            else None,
            "pct_of_such_teams_lost": hist(place.get("worst_weighted"), "L"),
        },
        "players": shooters[:14],
        "standouts": {
            "how_to_read": (
                "Each player's numbers in this match, compared with every "
                + ("Champions League" if ucl else league["competition"])
                + " game this season by a player in the same role who played 60+ minutes. "
                "games_with_better / games_with_the_same = how many of those games had a better "
                "or the same number (0 and 0 = the best of the season); games_with_worse likewise "
                "for the worst. Only numbers that 10% of games or fewer matched are listed."
            ),
            "players": standouts(players, match_id, team),
        },
        "season_so_far": {
            "champions_league_league_phase_position": rec.get("league_position"),
            "champions_league_teams": rec.get("teams"),
            "champions_league_points": rec.get("points"),
            "champions_league_played": rec.get("played"),
            "league_competition": league["competition"],
        }
        if ucl
        else {
            "league_position": table.get("position"),
            "points": table.get("points"),
            "played": table.get("played"),
            "points_the_performances_deserved": _r(table.get("deserved_points"), 1),
            "npxg_wasted_per_match_season": _r(
                (prof.get("shooting") or {}).get("quality_gap_per_match"), 2
            ),
            "league_rank_for_npxg_wasted": (prof.get("shooting") or {}).get("league_rank_wasted"),
        },
        "prediction_before_kickoff": pre,
        "prediction_note": "No prediction: we don't predict Champions League games."
        if ucl
        else None,
        "next_matches": nxt if isinstance(nxt, list) else ([nxt] if nxt else []),
        "not_measured": [
            "tactics, formations and instructions",
            "individual defensive errors other than errors leading directly to a goal",
            "injuries during the match, referee decisions beyond the cards",
            "anything a player or coach said",
        ],
    }
    # FotMob's headline xG and the sum of its shot map occasionally disagree (Atlético v
    # United: 1.47 vs 1.79). The lines use the headline figure, so the column must too.
    sh, m = out["shots_summary"], out["match"]
    gaps = [
        f"{who}: match xG {m[k]} vs shot-map sum {sh[side]['npxg']}"
        for who, side, k in (("us", "us", "xg_for"), ("them", "them", "xg_against"))
        if m.get(k) is not None and abs(m[k] - sh[side]["npxg"]) > 0.1
    ]
    if gaps:
        out["xg_note"] = (
            "FotMob's match xG and its shot map disagree ("
            + "; ".join(gaps)
            + "). Quote the match xG (xg_for / xg_against) for totals; use the shot map only "
            "for counts and where shots came from."
        )
    return out


def running(prof: dict, i: int) -> dict | None:
    """Plain statement of who ran more (so a column can't call a side 'outworked' wrongly)."""
    by = {m["key"]: m["matches"][i]["value"] for m in prof["metrics"]}
    gap, spr = by.get("distance_gap_km"), by.get("sprints_gap")
    if gap is None and spr is None:
        return None
    return {
        "outrun_by_opponent": None if gap is None else gap < 0,
        "distance_more_than_opponent_km": None if gap is None else round(gap, 1),
        "outsprinted_by_opponent": None if spr is None else spr < 0,
        "sprints_more_than_opponent": None if spr is None else int(spr),
    }


def shots_summary(details: dict, home: bool) -> dict:
    """Both sides' non-penalty shots: count, inside / outside the box, on target (blocked
    shots excluded — FotMob marks them on target), blocked, xG."""
    g = details["general"]
    ids = {"us": g["homeTeam"]["id"] if home else g["awayTeam"]["id"]}
    ids["them"] = g["awayTeam"]["id"] if home else g["homeTeam"]["id"]
    shots = ((details.get("content") or {}).get("shotmap") or {}).get("shots", [])
    out = {}
    for side, tid in ids.items():
        ss = [
            s
            for s in shots
            if s["teamId"] == tid and not s.get("isOwnGoal") and s.get("situation") != "Penalty"
        ]
        out[side] = {
            "shots": len(ss),
            "inside_box": sum(bool(s.get("isFromInsideBox")) for s in ss),
            "outside_box": sum(not s.get("isFromInsideBox") for s in ss),
            "on_target": sum(bool(s.get("isOnTarget")) and not s.get("isBlocked") for s in ss),
            "blocked": sum(bool(s.get("isBlocked")) for s in ss),
            "npxg": round(sum(s.get("expectedGoals") or 0 for s in ss), 2),
        }
    return out


def captions(facts: dict) -> dict[str, str]:
    """Chart captions written from the data (the writer can't see the charts)."""
    ln, sh, ev = facts["lines"], facts["shots_summary"], facts["events"]
    us, them = sh["us"], sh["them"]
    goals = ", ".join(f"{e['player']} {e['minute']}'" for e in ev if e["type"] == "goal")
    reds = ", ".join(f"{e['player']} {e['minute']}'" for e in ev if e["type"] == "red card")
    return {
        "lines": (
            f"The {ln['decisive_metrics_total']} metrics that decide matches: "
            f"{ln['decisive_metrics_at_elite_line']} at the elite line, "
            f"{ln['decisive_metrics_at_worst_line']} at the worst line."
        ),
        "shots": (
            f"{facts['team']}'s {us['shots']} non-penalty shots: {us['inside_box']} inside the "
            f"box, {us['on_target']} on target, {us['blocked']} blocked, {us['npxg']:.2f} xG."
        ),
        "xg": (
            f"Chances added up minute by minute: {us['npxg']:.2f} xG to {them['npxg']:.2f}"
            + (f"; goals: {goals}" if goals else "")
            + (f"; sent off: {reds}" if reds else "")
            + "."
        ),
    }


# ---------------------------------------------------------------------------- charts


def _style(ax) -> None:
    ax.set_facecolor("white")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(RULE)
    ax.tick_params(colors=MUTED, labelsize=9)


def chart_lines(facts: dict, path: Path) -> None:
    """Each decisive metric: this match placed between the worst and the elite line."""
    rows = [
        m
        for m in facts["lines"]["metrics"]
        if m["decides_matches"] and m["elite_line"] is not None and m["this_match"] is not None
    ]
    fig, ax = plt.subplots(figsize=(8, 0.55 * len(rows) + 1.2), dpi=160)
    fig.patch.set_facecolor("white")
    for y, m in enumerate(reversed(rows)):
        w, e, v = m["worst_line"], m["elite_line"], m["this_match"]
        t = (v - w) / (e - w) if e != w else 0.5
        t = max(-0.15, min(1.15, t))
        ax.plot([0, 1], [y, y], color=RULE, lw=2, zorder=1)
        ax.plot([0, 0], [y - 0.22, y + 0.22], color=RED, lw=2)
        ax.plot([1, 1], [y - 0.22, y + 0.22], color=GREEN, lw=2)
        col = (
            GREEN
            if m["status"] and "elite" in m["status"]
            else RED
            if m["status"] and "worst" in m["status"]
            else INK
        )
        ax.scatter([t], [y], s=110, color=col, zorder=3, edgecolor="white", linewidth=1.5)
        ax.text(-0.2, y, m["metric"], ha="right", va="center", fontsize=10, color=INK)
        ax.text(
            t, y + 0.3, f"{v:g}", ha="center", va="bottom", fontsize=9, color=col, weight="bold"
        )
        ax.text(0, y - 0.32, f"{w:g}", ha="center", va="top", fontsize=7, color=RED)
        ax.text(1, y - 0.32, f"{e:g}", ha="center", va="top", fontsize=7, color=GREEN)
    ax.set_xlim(-0.2, 1.2)
    ax.set_ylim(-0.7, len(rows) - 0.3)
    ax.axis("off")
    ax.text(0, len(rows) - 0.25, "worst line", color=RED, fontsize=8, ha="center")
    ax.text(1, len(rows) - 0.25, "elite line", color=GREEN, fontsize=8, ha="center")
    mt = facts["match"]
    gf, ga = mt["score"].split("-")
    fixture = (
        f"{mt['opponent']} {ga}-{gf} {facts['team']}"
        if mt.get("venue") == "away"
        else f"{facts['team']} {gf}-{ga} {mt['opponent']}"
    )
    fig.suptitle(
        f"{fixture}: the metrics that decide matches",
        fontsize=11,
        color=INK,
        x=0.02,
        ha="left",
    )
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def chart_shots(details: dict, team_id: int, team: str, path: Path) -> None:
    """The team's non-penalty shots on half a pitch: size = xG, colour = outcome."""
    shots = [
        s
        for s in ((details.get("content") or {}).get("shotmap") or {}).get("shots", [])
        if s["teamId"] == team_id and not s.get("isOwnGoal") and s.get("situation") != "Penalty"
    ]
    fig, ax = plt.subplots(figsize=(6, 5), dpi=160)
    fig.patch.set_facecolor("white")
    L, W = 105, 68
    ax.add_patch(plt.Rectangle((52.5, 0), 52.5, W, color="#e8efe8", zorder=0))
    pitch = {"color": "#b9c9b9", "lw": 1.5, "zorder": 1}
    ax.plot([52.5, L, L, 52.5, 52.5], [0, 0, W, W, 0], **pitch)
    ax.plot([L - 16.5, L - 16.5, L, L, L - 16.5], [13.84, 54.16, 54.16, 13.84, 13.84], **pitch)
    ax.plot([L, L - 5.5, L - 5.5, L], [24.84, 24.84, 43.16, 43.16], **pitch)
    ax.plot([L, L], [30.34, 37.66], color=INK, lw=4)
    for s in shots:
        goal = s.get("eventType") == "Goal"
        on = s.get("isOnTarget") and not s.get("isBlocked")
        col = GREEN if goal else INK if on else MUTED
        ax.scatter(
            s["x"],
            W - s["y"],
            s=40 + 900 * (s.get("expectedGoals") or 0),
            color=col,
            alpha=0.9 if goal or on else 0.45,
            edgecolor="white",
            linewidth=1,
            zorder=3,
        )
    ax.set_xlim(52, 106)
    ax.set_ylim(-1, 69)
    ax.set_aspect("equal")
    ax.axis("off")
    n, xg = len(shots), sum(s.get("expectedGoals") or 0 for s in shots)
    ax.set_title(f"{team}: {n} shots, {xg:.2f} non-penalty xG", fontsize=11, color=INK, loc="left")
    ax.text(
        53,
        -0.5,
        "size = chance quality (xG) · green = goal · dark = on target · "
        "grey = off target / blocked",
        fontsize=7,
        color=MUTED,
        va="top",
    )
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def chart_xg_race(details: dict, home_id: int, names: tuple[str, str], path: Path) -> None:
    """Cumulative xG through the match for both sides, goals marked."""
    shots = sorted(
        ((details.get("content") or {}).get("shotmap") or {}).get("shots", []),
        key=lambda s: (s.get("min") or 0) + (s.get("minAdded") or 0) / 10,
    )
    fig, ax = plt.subplots(figsize=(8, 3.6), dpi=160)
    fig.patch.set_facecolor("white")
    _style(ax)
    end = max(95, max(((s.get("min") or 0) for s in shots), default=90) + 3)
    for side, (team_name, col) in enumerate(((names[0], RED), (names[1], INK))):
        own = [
            s for s in shots if (s["teamId"] == home_id) == (side == 0) and not s.get("isOwnGoal")
        ]
        xs, ys, tot = [0], [0.0], 0.0
        for s in own:
            m = (s.get("min") or 0) + (s.get("minAdded") or 0) / 10
            xs += [m, m]
            ys += [tot, tot + (s.get("expectedGoals") or 0)]
            tot += s.get("expectedGoals") or 0
            if s.get("eventType") == "Goal":
                ax.scatter([m], [tot], color=col, s=60, zorder=4)
                ax.text(m, tot + 0.05, "goal", color=col, fontsize=8, ha="center", va="bottom")
        xs.append(end)
        ys.append(tot)
        ax.plot(xs, ys, color=col, lw=2, label=f"{team_name} {tot:.2f} xG")
    ax.axvline(45, color=RULE, lw=1, ls="--")
    ax.set_xlim(0, end)
    ax.set_xlabel("minute", color=MUTED, fontsize=9)
    ax.set_ylabel("cumulative xG", color=MUTED, fontsize=9)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    ax.set_title("How the chances added up", fontsize=11, color=INK, loc="left")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def slug(text: str) -> str:
    import re
    import unicodedata

    t = unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def pct(x: float | None) -> int | None:
    return None if x is None else int(round(100 * x)) if not math.isnan(x) else None
