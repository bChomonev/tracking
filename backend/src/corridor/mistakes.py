"""The mistakes log (D-058): why the favourite lost, and where the model is off.

Two questions, asked after every round on the held-out (walk-forward) predictions:

1. What kind of miss was it? When the side we made likelier to win lost, the match's own xG
   says whether the underdog deserved it, it was close, or the favourite made the better
   chances and didn't take them (finishing / luck). Only the first kind is the model reading
   the game wrong.
2. Where are we off? For slices of matches (home or away favourite, big favourites, promoted
   sides, early season, each team as favourite) we compare how often the favourite lost with
   how often our chances said it would. A slice is flagged only when the gap is clearly bigger
   than chance and points the same way in most seasons. A flag is not a fix: a correction is
   tested on later seasons only, and the model changes only if that test improves (logged in
   docs/DECISIONS.md).
"""

from collections import Counter, defaultdict
from collections.abc import Sequence

import numpy as np

from corridor import predict as P

XG_MARGIN = 0.5  # xG gap that counts as one side clearly making the better chances
EARLY = 6  # either side has played this many league games or fewer
Z_FLAG = 2.0  # slices of all matches
Z_FLAG_TEAM = 3.0  # per-team slices: many of them, so a stricter bar
MIN_TEAM = 60  # matches as favourite before a team gets its own slice


def favourite(p: Sequence[float]) -> int:
    """0 = home, 2 = away: the side we gave the bigger chance of winning."""
    return 0 if p[0] >= p[2] else 2


def miss_kind(fav: int, home_xg: float | None, away_xg: float | None) -> str | None:
    """For a favourite that lost: 'deserved' (underdog won xG by XG_MARGIN or more),
    'luck' (favourite won it by that much), otherwise 'close'."""
    if home_xg is None or away_xg is None:
        return None
    gap = (away_xg - home_xg) if fav == 0 else (home_xg - away_xg)  # underdog minus favourite
    return "deserved" if gap >= XG_MARGIN else "luck" if gap <= -XG_MARGIN else "close"


def match_xg(m: dict) -> tuple[float | None, float | None]:
    r = m.get("rows") or {}
    return (r.get("home") or {}).get("us_xg"), (r.get("away") or {}).get("us_xg")


def rows(cal: dict[int, tuple], seasons: Sequence[int], all_scored: list[dict]) -> list[dict]:
    """One row per held-out match: what we said, what happened and the slice tags."""
    teams = defaultdict(set)
    for m in all_scored:
        teams[m["season"]] |= {m["home"], m["away"]}
    out = []
    for s in seasons:
        if s not in cal:
            continue
        test, _, pm, _ = cal[s]
        played = Counter()
        for m, p in sorted(zip(test, pm, strict=True), key=lambda mp: mp[0]["kickoff"]):
            played[m["home"]] += 1
            played[m["away"]] += 1
            f = favourite(p)
            lost = m["result"] == ("A" if f == 0 else "H")
            hx, ax = match_xg(m)
            out.append(
                {
                    "season": s,
                    "fav": m["home"] if f == 0 else m["away"],
                    "dog": m["away"] if f == 0 else m["home"],
                    "home_fav": f == 0,
                    "p_dog": float(p[2 - f]),
                    "lost": lost,
                    "kind": miss_kind(f, hx, ax) if lost else None,
                    "early": min(played[m["home"]], played[m["away"]]) <= EARLY,
                    "promoted": bool(teams[s - 1])
                    and any(t not in teams[s - 1] for t in (m["home"], m["away"])),
                }
            )
    return out


def _slice(name: str, rs: list[dict], z_flag: float) -> dict | None:
    if not rs:
        return None
    n = len(rs)
    lost = sum(r["lost"] for r in rs)
    said = sum(r["p_dog"] for r in rs)
    sd = float(np.sqrt(sum(r["p_dog"] * (1 - r["p_dog"]) for r in rs)))
    z = (lost - said) / sd if sd else 0.0
    by_season = defaultdict(lambda: [0, 0.0])
    for r in rs:
        by_season[r["season"]][0] += r["lost"]
        by_season[r["season"]][1] += r["p_dog"]
    seasons = [lo - sa for lo, sa in by_season.values()]
    same_way = sum(np.sign(g) == np.sign(lost - said) for g in seasons if g)
    return {
        "slice": name,
        "n": n,
        "lost": lost,
        "said": round(said, 1),
        "z": round(z, 2),
        "seasons": len(seasons),
        "seasons_same_way": int(same_way),
        # Flag: clearly bigger than chance, and the same direction in most seasons.
        "flag": bool(abs(z) >= z_flag and same_way > len(seasons) / 2 and len(seasons) >= 2),
    }


def slices(rs: list[dict], surprise_at: float = P.SURPRISE_AT, focus: str | None = None) -> list:
    pct = round(100 * surprise_at)
    groups = [
        ("Home favourite", lambda r: r["home_fav"]),
        ("Away favourite", lambda r: not r["home_fav"]),
        (f"Big favourite (underdog {pct}% or less)", lambda r: r["p_dog"] <= surprise_at),
        (f"Close game (underdog over {pct}%)", lambda r: r["p_dog"] > surprise_at),
        (
            f"Home favourite, underdog {pct}% or less",
            lambda r: r["home_fav"] and r["p_dog"] <= surprise_at,
        ),
        (
            f"Away favourite, underdog {pct}% or less",
            lambda r: not r["home_fav"] and r["p_dog"] <= surprise_at,
        ),
        ("A promoted side playing", lambda r: r["promoted"]),
        (f"Early season ({EARLY} games or fewer)", lambda r: r["early"]),
    ]
    out = [_slice(name, [r for r in rs if f(r)], Z_FLAG) for name, f in groups]
    favs = Counter(r["fav"] for r in rs)
    for team in sorted(t for t, n in favs.items() if n >= MIN_TEAM or t == focus):
        out.append(_slice(f"{team} as favourite", [r for r in rs if r["fav"] == team], Z_FLAG_TEAM))
    return [s for s in out if s]


def kinds(rs: list[dict], surprise_at: float = P.SURPRISE_AT) -> dict:
    """How the favourite's defeats split by xG, for all of them and for real surprises."""
    lost = [r for r in rs if r["lost"] and r["kind"]]
    sur = [r for r in lost if r["p_dog"] <= surprise_at]
    return {
        "all": dict(Counter(r["kind"] for r in lost)),
        "surprises": dict(Counter(r["kind"] for r in sur)),
    }


def home_edge_test(cal: dict[int, tuple], seasons: Sequence[int], first: int) -> dict | None:
    """First candidate fix: are big home favourites over-rated? For each test season, fit one
    factor k on the earlier seasons only (scales the away underdog's chance in matches with a
    home favourite and an underdog at SURPRISE_AT or less, renormalised), then score the season.
    Kept only if the held-out RPS improves."""
    ks = np.round(np.arange(0.8, 1.41, 0.02), 2)

    def adjust(pm: np.ndarray, k: float) -> np.ndarray:
        q = pm.copy()
        sel = (q[:, 0] >= q[:, 2]) & (q[:, 2] <= P.SURPRISE_AT)
        q[sel, 2] *= k
        return q / q.sum(1, keepdims=True)

    def rps(pm: np.ndarray, res: list[str]) -> float:
        return float(np.mean([P.rps(p, r) for p, r in zip(pm, res, strict=True)]))

    before, after, fitted, better = [], [], {}, 0
    for s in seasons:
        prior = [cal[y] for y in cal if first <= y < s]
        if s not in cal or not prior:
            continue
        pm_prior = np.vstack([pc for _, _, pc, _ in prior])
        res_prior = [m["result"] for test, _, _, _ in prior for m in test]
        k = min(ks, key=lambda k: rps(adjust(pm_prior, k), res_prior))
        test, _, pm, _ = cal[s]
        res = [m["result"] for m in test]
        b = [P.rps(p, r) for p, r in zip(pm, res, strict=True)]
        a = [P.rps(p, r) for p, r in zip(adjust(pm, k), res, strict=True)]
        before += b
        after += a
        fitted[s] = float(k)
        better += int(np.mean(a) < np.mean(b))
    if not before:
        return None
    rb, ra = float(np.mean(before)), float(np.mean(after))
    return {
        "rps_before": rb,
        "rps_after": ra,
        "k": fitted,
        "seasons_better": int(better),
        "seasons": len(fitted),
        # Same bar as the other switches (D-031, D-036): better on the held-out seasons overall
        # and in most of them, so one lucky season can't turn it on.
        "helps": bool(ra < rb - 1e-5 and better > len(fitted) / 2),
    }


def build(
    cal: dict[int, tuple], seasons: Sequence[int], all_scored: list[dict], focus: str | None
) -> dict:
    rs = rows(cal, seasons, all_scored)
    return {
        "xg_margin": XG_MARGIN,
        "kinds": kinds(rs),
        "slices": slices(rs, focus=focus),
        "home_edge_test": home_edge_test(cal, seasons, min(cal)),
    }
