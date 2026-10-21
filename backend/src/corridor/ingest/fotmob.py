"""FotMob (unofficial web-app JSON) → per-team and per-player match records.

FotMob's xG model and physical provider differ from other sources; never mix its numbers
with Understat's or UEFA's inside one comparison (see docs/DATA_SOURCES.md).
"""

import math
import re
from typing import Any

from corridor.ingest.http import fetch_json

BASE = "https://www.fotmob.com/api/data"
PREMIER_LEAGUE = 47
CHAMPIONS_LEAGUE = 42
MAN_UTD = 10260
POSITION_GROUPS = {0: "GK", 1: "DEF", 2: "MID", 3: "FWD"}
ROLES = ("GK", "CB", "FB", "CM", "AM", "W", "ST")


def role_from_position_id(pos_id: int | None, usual: int | None = None) -> str | None:
    """FotMob lineup ``positionId`` is a formation-grid cell: tens digit(s) = line from own
    goal (1 GK, 3 back line, 5-7 midfield, 8 attacking midfield, 10-11 attack), last digit =
    lane (2 right … 5 centre … 8 left; 1/9 touchline). ``usual`` is FotMob's coarse usual
    position (1 DEF) and splits wing-backs from wingers on the wide midfield lanes."""
    if pos_id is None:
        return None
    line, lane = divmod(pos_id, 10)
    wide = lane in (1, 2, 8, 9)
    if line == 1:
        return "GK"
    if line <= 4:
        return "FB" if wide else "CB"
    if line <= 7:
        if wide:
            return "FB" if usual == 1 else "W"
        return "CM"
    if line == 8:
        return "W" if wide or lane in (3, 7) else "AM"
    return "W" if lane in (3, 7) or wide else "ST"


# FotMob team-stat key → our field name. Values come as [home, away].
TEAM_STATS = {
    "BallPossesion": "possession_pct",
    "expected_goals": "xg",
    "expected_goals_non_penalty": "npxg",
    "expected_goals_open_play": "xg_open_play",
    "expected_goals_set_play": "xg_set_play",
    "expected_goals_on_target": "xgot",
    "total_shots": "shots",
    "ShotsOnTarget": "shots_on_target",
    "shots_inside_box": "shots_inside_box",
    "touches_opp_box": "box_touches",
    "big_chance": "big_chances",
    "big_chance_missed_title": "big_chances_missed",
    "passes": "passes",
    "accurate_passes": "accurate_passes",
    "own_half_passes": "own_half_passes",
    "opposition_half_passes": "opp_half_passes",
    "long_balls_accurate": "accurate_long_balls",
    "matchstats.headers.tackles": "tackles",
    "interceptions": "interceptions",
    "shot_blocks": "blocks",
    "clearances": "clearances",
    "keeper_saves": "saves",
    "duel_won": "duels_won",
    "aerials_won": "aerials_won",
    "fouls": "fouls",
    "physical_metrics_distance_covered": "distance_m",
    "physical_metrics_running": "running_m",
    "physical_metrics_sprinting": "sprinting_m",
    "physical_metrics_number_of_sprints": "sprints",
    "corners": "corners",
    "yellow_cards": "yellow_cards",
    "red_cards": "red_cards",
}

# FotMob player-stat key → our field name.
PLAYER_STATS = {
    "minutes_played": "minutes",
    "rating_title": "rating",
    "goals": "goals",
    "assists": "assists",
    "expected_goals": "xg",
    "expected_goals_non_penalty": "npxg",
    "expected_assists": "xa",
    "total_shots": "shots",
    "chances_created": "chances_created",
    "touches": "touches",
    "touches_opp_box": "box_touches",
    "passes_into_final_third": "passes_into_final_third",
    "line_breaking_passes": "line_breaking_passes",
    "dribbles_succeeded": "dribbles_succeeded",
    "dispossessed": "dispossessed",
    "defensive_actions": "defensive_actions",
    "matchstats.headers.tackles": "tackles",
    "interceptions": "interceptions",
    "recoveries": "recoveries",
    "dribbled_past": "dribbled_past",
    "duel_won": "duels_won",
    "duel_lost": "duels_lost",
    "physical_metrics_distance_covered": "distance_m",
    "physical_metrics_running": "running_m",
    "physical_metrics_sprinting": "sprinting_m",
    "physical_metrics_number_of_sprints": "sprints",
    "physical_metrics_topspeed": "top_speed_kmh",
    "expected_goals_on_target_faced": "xgot_faced",
    "goals_prevented": "goals_prevented",
    "saves": "saves",
    "errors_led_to_goal": "errors_led_to_goal",
}

# Summed from player rows to team level (FotMob has no team total for these).
PLAYER_SUMS = ("line_breaking_passes", "passes_into_final_third", "recoveries", "goals_prevented")


def _num(v: Any) -> float | None:
    """'180 (70%)' → 180, '1.83' → 1.83, 28 → 28, None → None."""
    if v is None:
        return None
    if isinstance(v, int | float):
        return float(v)
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)", str(v))
    return float(m.group(1)) if m else None


def league_matches(season: str, league_id: int = PREMIER_LEAGUE) -> list[dict]:
    """All fixtures for a season ('2026/2027'). Refreshed each call (results change)."""
    d = fetch_json("fotmob", f"{BASE}/leagues?id={league_id}&season={season}", refresh=True)
    return d["fixtures"]["allMatches"]


def match_details(match_id: str | int) -> dict:
    return fetch_json("fotmob", f"{BASE}/matchDetails?matchId={match_id}")


_SHOT_ZERO = {
    "np_shots": 0,
    "np_shots_on_target": 0,
    "npxg_shots": 0.0,
    "penalties": 0,
    "np_goals": 0,
    "np_shots_outside_box": 0,
    "np_shots_blocked": 0,
    "np_shots_headed": 0,
    "np_shot_distance_sum_m": 0.0,
}


def parse_match(d: dict) -> tuple[list[dict], list[dict]]:
    """Return ([home_record, away_record], player_records)."""
    g = d["general"]
    sides = [g["homeTeam"], g["awayTeam"]]
    home_goals, away_goals = (int(x) for x in d["header"]["status"]["scoreStr"].split(" - "))

    team_vals: list[dict[str, float | None]] = [{}, {}]
    for group in d["content"]["stats"]["Periods"]["All"]["stats"]:
        for s in group["stats"]:
            field = TEAM_STATS.get(s.get("key"))
            vals = s.get("stats") or [None, None]
            if field and field not in team_vals[0] and s.get("type") != "title":
                team_vals[0][field], team_vals[1][field] = _num(vals[0]), _num(vals[1])

    lineup_pos: dict[int, tuple[int | None, int | None]] = {}
    for side in ("homeTeam", "awayTeam"):
        for lp in ((d["content"].get("lineup") or {}).get(side) or {}).get("starters", []):
            lineup_pos[lp["id"]] = (lp.get("positionId"), lp.get("usualPlayingPositionId"))

    team_names = {side["id"]: side["name"] for side in sides}
    players = []
    for p in (d["content"].get("playerStats") or {}).values():
        pos_id, usual = lineup_pos.get(p["id"], (None, p.get("usualPosition")))
        rec: dict[str, Any] = {
            "match_id": int(g["matchId"]),
            "player_id": p["id"],
            "name": p["name"],
            "team_id": p["teamId"],
            # The match's own team name: FotMob's player blocks sometimes spell clubs
            # differently ("Bournemouth" vs "AFC Bournemouth").
            "team": team_names.get(p["teamId"], p["teamName"]),
            "position": POSITION_GROUPS.get(p.get("usualPosition"), "UNK"),
            "started": p["id"] in lineup_pos,
            "position_id": pos_id,
            "role": role_from_position_id(pos_id, usual),
        }
        for block in p.get("stats", []):
            for s in block["stats"].values():
                field = PLAYER_STATS.get(s.get("key"))
                if field and field not in rec:
                    rec[field] = _num(s.get("stat", {}).get("value"))
        if rec.get("minutes"):
            players.append(rec)

    shots = (d["content"].get("shotmap") or {}).get("shots") or []
    # Per-player shooting from the shot map (FotMob's player stat blocks don't reliably
    # carry shots/xG): non-penalty shots, shots on target, npxG, penalties taken.
    by_player: dict[int, dict[str, float]] = {}
    for sh in shots:
        if sh.get("isOwnGoal") or sh.get("playerId") is None:
            continue
        b = by_player.setdefault(sh["playerId"], dict(_SHOT_ZERO))
        if sh.get("situation") == "Penalty":
            b["penalties"] += 1
            continue
        b["np_shots"] += 1
        # FotMob's isOnTarget is also true for blocked shots; excluding them matches its
        # official "shots on target" team stat exactly.
        b["np_shots_on_target"] += bool(sh.get("isOnTarget")) and not sh.get("isBlocked")
        b["npxg_shots"] += sh.get("expectedGoals") or 0.0
        b["np_goals"] += sh.get("eventType") == "Goal"
        b["np_shots_outside_box"] += not sh.get("isFromInsideBox")
        b["np_shots_blocked"] += bool(sh.get("isBlocked"))
        b["np_shots_headed"] += sh.get("shotType") == "Header"
        b["np_shot_distance_sum_m"] += math.hypot(105 - sh["x"], 34 - sh["y"])
    cards = player_cards(d)
    for pl in players:
        pl |= by_player.get(pl["player_id"], _SHOT_ZERO)
        pl.setdefault("errors_led_to_goal", 0.0)
        pl["yellow"], pl["red"] = cards.get(pl["player_id"], (0, 0))
    reds = red_card_minutes(d)
    goals = goal_times(d)
    records = []
    for i, side in enumerate(sides):
        own, opp = team_vals[i], team_vals[1 - i]
        gf, ga = (home_goals, away_goals) if i == 0 else (away_goals, home_goals)
        rec = {
            "source": "fotmob",
            "match_id": int(g["matchId"]),
            "kickoff_utc": g["matchTimeUTCDate"],
            "round": g.get("matchRound"),
            "team_id": side["id"],
            "team": side["name"],
            "opponent_id": sides[1 - i]["id"],
            "opponent": sides[1 - i]["name"],
            "is_home": i == 0,
            "goals_for": gf,
            "goals_against": ga,
            "result": "W" if gf > ga else "D" if gf == ga else "L",
            **own,
            **{f"{k}_conceded": v for k, v in opp.items() if k in _CONCEDED},
            "red_card_min": reds[i],
            "referee": referee(d),
            "opp_red_card_min": reds[1 - i],
            "opp_distance_m": opp.get("distance_m"),
            "opp_sprints": opp.get("sprints"),
        }
        own_shots = shot_profile(shots, side["id"])
        opp_shots = shot_profile(shots, sides[1 - i]["id"])
        rec |= own_shots | {f"{k}_conceded": v for k, v in opp_shots.items()}
        rec |= state_profile(shots, goals, side["id"], i == 0)
        team_players = [pl for pl in players if pl["team_id"] == side["id"]]
        for k in PLAYER_SUMS:
            vals = [pl[k] for pl in team_players if pl.get(k) is not None]
            rec[k] = float(sum(vals)) if vals else None
        records.append(rec)
    return records, players


def referee(d: dict) -> str | None:
    ib = ((d.get("content") or {}).get("matchFacts") or {}).get("infoBox") or {}
    return (ib.get("Referee") or {}).get("text")


def player_cards(d: dict) -> dict[int, tuple[int, int]]:
    """player id → (yellow cards, red cards); a second yellow counts as one yellow + red."""
    out: dict[int, list[int]] = {}
    events = ((d["content"].get("matchFacts") or {}).get("events") or {}).get("events") or []
    for e in events:
        if e.get("type") != "Card":
            continue
        pid = (e.get("player") or {}).get("id") or e.get("playerId")
        if pid is None:
            continue
        c = out.setdefault(pid, [0, 0])
        if e.get("card") == "Yellow":
            c[0] += 1
        elif e.get("card") in ("Red", "YellowRed"):
            c[1] += 1
    return {k: (min(v[0], 1), v[1]) for k, v in out.items()}


def red_card_minutes(d: dict) -> tuple[int | None, int | None]:
    """Minute of the first red card (straight or second yellow) for (home, away)."""
    first: list[int | None] = [None, None]
    events = ((d["content"].get("matchFacts") or {}).get("events") or {}).get("events") or []
    for e in events:
        if e.get("type") == "Card" and e.get("card") in ("Red", "YellowRed"):
            side = 0 if e.get("isHome") else 1
            minute = int(e.get("time") or 0)
            if first[side] is None or minute < first[side]:
                first[side] = minute
    return first[0], first[1]


SET_PIECES = {"FromCorner", "SetPiece", "ThrowInSetPiece", "FreeKick"}


def shot_profile(shots: list[dict], team_id: int) -> dict[str, float | int]:
    """Summarise one team's shot map (penalties and own goals excluded). Coordinates are
    metres on a 105 x 68 pitch with every shot attacking the goal at x = 105."""
    own = [s for s in shots if s["teamId"] == team_id and not s.get("isOwnGoal")]
    np_ = [s for s in own if s.get("situation") != "Penalty"]
    goals = [s for s in own if s.get("eventType") == "Goal"]

    def xg(ss: list[dict]) -> float:
        return float(sum(s.get("expectedGoals") or 0 for s in ss))

    n = len(np_)
    return {
        "np_shots": n,
        "shots_outside_box": sum(not s.get("isFromInsideBox") for s in np_),
        "shots_blocked": sum(bool(s.get("isBlocked")) for s in np_),
        "shots_headed": sum(s.get("shotType") == "Header" for s in np_),
        "shot_distance_sum_m": float(sum(math.hypot(105 - s["x"], 34 - s["y"]) for s in np_)),
        "npxg_set_piece": xg([s for s in np_ if s.get("situation") in SET_PIECES]),
        "npxg_fast_break": xg([s for s in np_ if s.get("situation") == "FastBreak"]),
        "shots_fast_break": sum(s.get("situation") == "FastBreak" for s in np_),
        "goals_open_play": sum(
            s.get("situation") not in SET_PIECES | {"Penalty", "FastBreak"} for s in goals
        ),
        "goals_set_piece": sum(s.get("situation") in SET_PIECES for s in goals),
        "goals_fast_break": sum(s.get("situation") == "FastBreak" for s in goals),
        "goals_penalty": sum(s.get("situation") == "Penalty" for s in goals),
        "goals_outside_box": sum(not s.get("isFromInsideBox") for s in goals),
    }


STATES = ("level", "ahead", "behind")
"""Game states from the team's point of view (D-051). Set by the score on a 90-minute
clock: added-time goals and shots sit at the end of their half, red cards are ignored."""
MATCH_MINUTES = 90.0


def goal_times(d: dict) -> list[tuple[float, bool]]:
    """(minute, counts for the home side) for every goal, in order. Own goals are credited
    by FotMob to the side that benefits (``isHome``), so no special case is needed."""
    events = ((d["content"].get("matchFacts") or {}).get("events") or {}).get("events") or []
    out = []
    for e in events:
        if e.get("type") == "Goal":
            minute = float(e.get("time") or 0) + (e.get("overloadTime") or 0) / 100
            out.append((minute, bool(e.get("isHome"))))
    return sorted(out)


def _state(goals: list[tuple[float, bool]], minute: float, is_home: bool) -> str:
    h = sum(1 for t, home in goals if t < minute and home)
    a = sum(1 for t, home in goals if t < minute and not home)
    diff = h - a if is_home else a - h
    return "level" if diff == 0 else "ahead" if diff > 0 else "behind"


def state_minutes(goals: list[tuple[float, bool]], is_home: bool) -> dict[str, float]:
    """Minutes spent in each state on a 90-minute clock."""
    out = dict.fromkeys(STATES, 0.0)
    prev = 0.0
    for t, _ in [*goals, (MATCH_MINUTES, None)]:
        t = min(t, MATCH_MINUTES)
        if t > prev:
            out[_state(goals, prev + 1e-6, is_home)] += t - prev
            prev = t
    return out


def state_profile(
    shots: list[dict], goals: list[tuple[float, bool]], team_id: int, is_home: bool
) -> dict[str, float | int]:
    """Shots for and against by the score at the time of the shot (penalties and own
    goals excluded), plus minutes in each state. Rates are derived in corridor.profile."""
    out: dict[str, float | int] = {}
    for s, mins in state_minutes(goals, is_home).items():
        out[f"{s}_minutes"] = round(mins, 2)
        for suffix in ("", "_conceded"):
            out[f"{s}_np_shots{suffix}"] = 0
            out[f"{s}_npxg{suffix}"] = 0.0
            out[f"{s}_shots_inside_box{suffix}"] = 0
        out[f"{s}_shot_distance_sum_m"] = 0.0
    for sh in shots:
        if sh.get("isOwnGoal") or sh.get("situation") == "Penalty":
            continue
        minute = float(sh.get("min") or 0) + (sh.get("minAdded") or 0) / 100
        s = _state(goals, minute, is_home)
        suffix = "" if sh["teamId"] == team_id else "_conceded"
        out[f"{s}_np_shots{suffix}"] += 1
        out[f"{s}_npxg{suffix}"] += sh.get("expectedGoals") or 0.0
        out[f"{s}_shots_inside_box{suffix}"] += bool(sh.get("isFromInsideBox"))
        if not suffix:
            out[f"{s}_shot_distance_sum_m"] += math.hypot(105 - sh["x"], 34 - sh["y"])
    return out


_CONCEDED = {
    "corners",
    "yellow_cards",
    "red_cards",
    "fouls",
    "xg",
    "npxg",
    "xgot",
    "shots",
    "shots_on_target",
    "box_touches",
    "big_chances",
    "opp_half_passes",
    "passes",
}
