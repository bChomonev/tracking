"""Pre-match "How they play" (D-054): the two sides played against each other.

Three layers, all from numbers the season profiles already hold (nothing is fetched):

* **Season shape** — position, points against the points the performances deserved, the
  elite and danger scores, and the share of minutes level / ahead / behind.
* **Pairings** — each decisive or helpful metric as attack against defence: the home side's
  chance quality against the away side's chance quality conceded, and the other way round,
  with league ranks, the elite / worst line markers, and an "if both play as usual" number:
  attack × defence ÷ league average, the classic way to combine the two. It differs from the
  model's expectation on the preview page because the model uses rolling, opponent-adjusted
  ratings rather than this season's typical match; showing both says which way the season's
  numbers lean against the ratings.
* **Battles by role** — from the likely line-ups: wingers against full-backs, strikers
  against centre-backs, attacking midfielders against central midfielders. Attackers are
  measured on creation (xG + xA, touches in the box, shot quality against the role);
  defenders on duels won, recoveries and effort. The data cannot say which defender allowed a
  chance, so the defensive side is work rate, never chances conceded — said on the page.

The read at the end is written from the ranks by code, never a model.
"""

from statistics import mean
from typing import Any

# attack metric, defence metric, label, (attack words: best, worst), (defence words: best, worst)
PAIRINGS = (
    ("npxg", "npxg_conceded", "Chance quality (npxG)", ("most", "least"), ("least", "most")),
    (
        "npxg_per_shot",
        "npxg_per_shot_conceded",
        "npxG per shot",
        ("best", "worst"),
        ("lowest", "highest"),
    ),
    ("shots", "shots_conceded", "Shots", ("most", "fewest"), ("fewest", "most")),
    ("big_chances", "big_chances_conceded", "Big chances", ("most", "fewest"), ("fewest", "most")),
    (
        "box_touches",
        "box_touches_conceded",
        "Touches in the box",
        ("most", "fewest"),
        ("fewest", "most"),
    ),
    (
        "npxg_set_piece",
        "npxg_set_piece_conceded",
        "Set-piece chances (npxG)",
        ("most", "least"),
        ("least", "most"),
    ),
    (
        "npxg_fast_break",
        "npxg_fast_break_conceded",
        "Counter-attack chances (npxG)",
        ("most", "least"),
        ("least", "most"),
    ),
)
SENTENCES = {
    "npxg": "{A} create the {a} chance quality in the league and {D} concede the {d}",
    "npxg_per_shot": (
        "{A}'s shots are the {a} in the league for quality and {D} allow the {d} quality"
    ),
    "shots": "{A} take the {a} shots in the league and {D} allow the {d}",
    "big_chances": "{A} create the {a} big chances in the league and {D} concede the {d}",
    "box_touches": "{A} have the {a} touches in the box in the league and {D} allow the {d}",
    "npxg_set_piece": "{A} create the {a} from set pieces in the league and {D} concede the {d}",
    "npxg_fast_break": "{A} create the {a} on the counter in the league and {D} concede the {d}",
}
BOTH_WAYS = (("distance_gap_km", "Running vs opponent (km)"),)
BATTLES = (
    ("W", "FB", "wingers", "full-backs"),
    ("ST", "CB", "strikers", "centre-backs"),
    ("AM", "CM", "attacking midfielders", "central midfielders"),
)
ATTACK_STATS = ("xg_xa", "box_touches")
DEFENCE_STATS = ("duels_won", "recoveries")
MISMATCH = 0.4  # attack strength minus defence strength (0-1 each) worth a sentence
EDGE = 20  # percentile points between attackers and defenders worth calling an edge
LUCK = 3.0  # points between deserved and actual worth a sentence


def _r(v: float | None, d: int) -> float | int | None:
    if v is None:
        return None
    return round(v) if d == 0 else round(v, d)


def ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def rank_words(rank: int, of: int, words: tuple[str, str]) -> str:
    """1 of 20 → 'most'; 2 → '2nd-most'; 20 → 'fewest'; 19 → '2nd-fewest'; 12 → '12th-most'."""
    from_bottom = of - rank + 1
    if rank == 1:
        return words[0]
    if from_bottom == 1:
        return words[1]
    if from_bottom <= 3:
        return f"{ordinal(from_bottom)}-{words[1]}"
    return f"{ordinal(rank)}-{words[0]}"


def _cell(m: dict) -> dict:
    return {
        "value": _r(m["value"], m["decimals"]),
        "rank": m["rank"],
        "of": m["of"],
        "percentile": m["percentile"],
        "at_elite_line": bool((m.get("best_line") or {}).get("typical_hits")),
        "at_worst_line": bool((m.get("worst_line") or {}).get("typical_hits")),
        "decides_matches": (m.get("impact") or {}).get("tier"),
    }


def _strength(m: dict) -> float:
    """0 = worst in the league, 1 = best (percentile already points the right way)."""
    return (m["percentile"] or 0) / 100


def pairings(att: dict, de: dict) -> list[dict]:
    """``att`` and ``de`` are team profiles (league.json ``teams[...]``)."""
    am = {m["key"]: m for m in att["metrics"]}
    dm = {m["key"]: m for m in de["metrics"]}
    out = []
    for ak, dk, label, aw, dw in PAIRINGS:
        a, d = am.get(ak), dm.get(dk)
        if not a or not d or a["value"] is None or d["value"] is None:
            continue
        avg = a.get("league_avg")
        out.append(
            {
                "key": ak,
                "label": label,
                "attack": _cell(a),
                "defence": _cell(d),
                "league_average": _r(avg, a["decimals"]),
                "if_both_play_as_usual": _r(a["value"] * d["value"] / avg, a["decimals"])
                if avg
                else None,
                "decides_matches": (a.get("impact") or {}).get("tier"),
                "mismatch": round(_strength(a) - _strength(d), 2),
                "words": (aw, dw),
            }
        )
    return out


def shape(league: dict, team: str) -> dict:
    row = next((r for r in league["table"] if r["team"] == team), {})
    ctx = (league["teams"][team].get("context") or {}).get("game_state_minutes") or {}
    return {
        "position": row.get("position"),
        "played": row.get("played"),
        "points": row.get("points"),
        "points_the_performances_deserved": _r(row.get("deserved_points"), 1),
        "elite_score": _r(100 * row["elite_score"], 0)
        if row.get("elite_score") is not None
        else None,
        "danger_score": _r(100 * row["danger_score"], 0)
        if row.get("danger_score") is not None
        else None,
        "form": row.get("form"),
        "minutes_pct": {s: ctx[s]["team_pct"] for s in ("level", "ahead", "behind") if s in ctx},
    }


def _profile_by_name(prof: dict) -> tuple[dict, dict]:
    players = {p["name"]: p for p in prof.get("players") or []}
    shooters = {p["name"]: p for p in (prof.get("shooting") or {}).get("players") or []}
    return players, shooters


def battles(att: dict, de: dict, att_xi: list[dict], de_xi: list[dict]) -> list[dict]:
    ap, ash = _profile_by_name(att)
    dp, _ = _profile_by_name(de)
    out = []
    for a_role, d_role, a_name, d_name in BATTLES:
        attackers, defenders = [], []
        for x in att_xi:
            if x.get("out") or x.get("role") != a_role:
                continue
            p, s = ap.get(x["name"]), ash.get(x["name"])
            if not p:
                continue
            pcts = [
                p["metrics"][k]["percentile"]
                for k in ATTACK_STATS
                if p["metrics"].get(k) and p["metrics"][k]["percentile"] is not None
            ]
            attackers.append(
                {
                    "name": x["name"],
                    "minutes": p["minutes"],
                    "xg_xa_per_90": p["metrics"].get("xg_xa", {}).get("value"),
                    "xg_xa_percentile": p["metrics"].get("xg_xa", {}).get("percentile"),
                    "box_touches_percentile": p["metrics"].get("box_touches", {}).get("percentile"),
                    "shots": s["shots"] if s else None,
                    "npxg_per_shot": _r(s["npxg_per_shot"], 3) if s else None,
                    "role_npxg_per_shot": _r(s["role_npxg_per_shot"], 3) if s else None,
                    "creation_percentile": round(mean(pcts)) if pcts else None,
                }
            )
        for x in de_xi:
            if x.get("out") or x.get("role") != d_role:
                continue
            p = dp.get(x["name"])
            if not p:
                continue
            pcts = [
                p["metrics"][k]["percentile"]
                for k in DEFENCE_STATS
                if p["metrics"].get(k) and p["metrics"][k]["percentile"] is not None
            ]
            defenders.append(
                {
                    "name": x["name"],
                    "minutes": p["minutes"],
                    "duels_won_percentile": p["metrics"].get("duels_won", {}).get("percentile"),
                    "recoveries_percentile": p["metrics"].get("recoveries", {}).get("percentile"),
                    "effort_percentile": p.get("effort_percentile"),
                    "defending_percentile": round(mean(pcts)) if pcts else None,
                }
            )
        a_p = [x["creation_percentile"] for x in attackers if x["creation_percentile"] is not None]
        d_p = [
            x["defending_percentile"] for x in defenders if x["defending_percentile"] is not None
        ]
        edge = round(mean(a_p) - mean(d_p)) if a_p and d_p else None
        out.append(
            {
                "attackers_role": a_name,
                "defenders_role": d_name,
                "attackers": attackers,
                "defenders": defenders,
                "attackers_percentile": round(mean(a_p)) if a_p else None,
                "defenders_percentile": round(mean(d_p)) if d_p else None,
                "edge": edge,
                "verdict": None
                if edge is None
                else "attackers"
                if edge >= EDGE
                else "defenders"
                if edge <= -EDGE
                else "even",
            }
        )
    return out


def _read(
    home: str,
    away: str,
    sh: dict,
    sa: dict,
    p_home: list[dict],
    p_away: list[dict],
    b_home: list[dict],
    b_away: list[dict],
) -> list[str]:
    lines: list[str] = []
    for t, s in ((home, sh), (away, sa)):
        d, p = s.get("points_the_performances_deserved"), s.get("points")
        if d is None or p is None:
            continue
        if d - p >= LUCK:
            lines.append(f"{t}'s performances have been worth {d:.1f} points and they have {p}.")
        elif p - d >= LUCK:
            lines.append(f"{t} have {p} points from performances worth {d:.1f}.")
    cands = []
    for A, D, ps in ((home, away, p_home), (away, home, p_away)):
        for x in ps:
            if x["decides_matches"] in ("decisive", "helps") and abs(x["mismatch"]) >= MISMATCH:
                cands.append((abs(x["mismatch"]), A, D, x))
    for _, A, D, x in sorted(cands, key=lambda c: -c[0])[:2]:
        aw, dw = x["words"]
        lines.append(
            SENTENCES[x["key"]].format(
                A=A,
                D=D,
                a=rank_words(x["attack"]["rank"], x["attack"]["of"], aw),
                d=rank_words(x["defence"]["rank"], x["defence"]["of"], dw),
            )
            + "."
        )
    best = None
    for A, D, bs in ((home, away, b_home), (away, home, b_away)):
        for b in bs:
            if (
                b["edge"] is not None
                and abs(b["edge"]) >= EDGE
                and (best is None or abs(b["edge"]) > abs(best[2]["edge"]))
            ):
                best = (A, D, b)
    if best:
        A, D, b = best
        who = ", ".join(x["name"] for x in b["attackers"])
        whom = ", ".join(x["name"] for x in b["defenders"])
        lines.append(
            f"{A}'s {b['attackers_role']} ({who}) are better than {b['attackers_percentile']}% of "
            f"players in their role for creation; {D}'s {b['defenders_role']} ({whom}) better "
            f"than {b['defenders_percentile']}% of theirs for duels and recoveries."
        )
    return lines


def build(
    league: dict,
    home: str,
    away: str,
    home_xi: list[dict] | None = None,
    away_xi: list[dict] | None = None,
    model_expectation: tuple[float, float] | None = None,
) -> dict[str, Any] | None:
    teams = league.get("teams") or {}
    if home not in teams or away not in teams:
        return None
    H, A = teams[home], teams[away]
    hm = {m["key"]: m for m in H["metrics"]}
    am = {m["key"]: m for m in A["metrics"]}
    p_home, p_away = pairings(H, A), pairings(A, H)
    b_home = battles(H, A, home_xi or [], away_xi or [])
    b_away = battles(A, H, away_xi or [], home_xi or [])
    sh, sa = shape(league, home), shape(league, away)
    both = [
        {"key": k, "label": label, "home": _cell(hm[k]), "away": _cell(am[k])}
        for k, label in BOTH_WAYS
        if k in hm and k in am and hm[k]["value"] is not None and am[k]["value"] is not None
    ]
    strip = lambda ps: [{k: v for k, v in x.items() if k != "words"} for x in ps]  # noqa: E731
    return {
        "how_to_read": (
            "Both sides' typical (median) league match this season. Pairings put one side's "
            "attack against the other's defence; 'if_both_play_as_usual' is attack × defence ÷ "
            "league average (a strong attack against a weak defence gives more than either "
            "number alone). The model's expectation differs because it uses rolling, "
            "opponent-adjusted ratings. Battles come from the likely line-ups: attackers are "
            "measured on creation, defenders on duels won and recoveries — the data cannot say "
            "which defender allowed a chance. A percentile of 60 means better than 60% of "
            "league players in the same role; say it that way. E / W = the typical match "
            "reaches the elite line / sits at the worst line."
        ),
        "home": home,
        "away": away,
        "shape": {home: sh, away: sa},
        "pairings": {
            "home_attack_v_away_defence": strip(p_home),
            "away_attack_v_home_defence": strip(p_away),
        },
        "both_ways": both,
        "model_expectation": {"home_npxg": model_expectation[0], "away_npxg": model_expectation[1]}
        if model_expectation
        else None,
        "battles": {"home_attack": b_home, "away_attack": b_away},
        "read": _read(home, away, sh, sa, p_home, p_away, b_home, b_away),
    }
