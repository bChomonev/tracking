"""Stage 5: match previews — expected corners, likely shooters and team news (D-024).

Corners: every team carries rolling (exponentially weighted) corners won and conceded,
relative to the league average. Expected corners for a side = league average for its
venue × its "won" rating × the opponent's "conceded" rating. Totals are Poisson (the match
total's variance is close to its mean); each side's count is over-dispersed, so per-side
lines use a negative binomial with the dispersion measured on past seasons.

Shooters: per-player non-penalty shots and npxG per 90 from the shot map, this season and
last (last season counts half), shrunk towards the average for the player's role, scaled
by expected minutes and by how many shots / how much npxG the opponent concedes relative
to the league. P(at least one shot) and P(non-penalty goal) are Poisson. Evaluated on
players who started, i.e. "if he starts" — line-ups are only known an hour before kickoff.

Both are tested walk-forward: every match is predicted from matches before it only.
"""

import math
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

import numpy as np

CORNER_HALF_LIFE = 30.0  # matches (chosen on 2025-26)
CORNER_CARRY = 0.7  # summer regression towards average
SHRINK_MIN = 270.0
# Expected shots are compressed (λ ** 0.85): high-volume shooters' counts don't hold up match
# to match. Chosen on PL 2025-26 (≥2 shots: 84% predicted had happened 70%), checked on
# La Liga 2025-26, which it never saw (D-033).
SHOT_POWER = 0.85  # minutes of role-average "prior" mixed into each player's rate
LAST_SEASON_WEIGHT = 0.5
# Opponent shots / npxG conceded: last season counts half (D-042: 15 of 16 checks better
# across four leagues; making the factor count more lost everywhere).
OPP_PREV_WEIGHT = 0.5


# ---------------------------------------------------------------------------- corners


def nb_pmf(mean: float, disp: float, kmax: int = 30) -> np.ndarray:
    r, p = disp, disp / (disp + mean)
    out = np.zeros(kmax + 1)
    out[0] = p**r
    for k in range(1, kmax + 1):
        out[k] = out[k - 1] * (k - 1 + r) / k * (1 - p)
    return out


def p_more(mean_a: float, mean_b: float, disp: float) -> tuple[float, float, float]:
    """(P(a > b), P(equal), P(b > a)) for independent negative-binomial counts."""
    pa, pb = nb_pmf(mean_a, disp), nb_pmf(mean_b, disp)
    joint = np.outer(pa, pb)
    return float(np.tril(joint, -1).sum()), float(np.trace(joint)), float(np.triu(joint, 1).sum())


def _poisson_cdf(k: int, lam: float) -> float:
    return float(sum(math.exp(-lam) * lam**i / math.factorial(i) for i in range(k + 1)))


def p_over(line: float, lam: float) -> float:
    """P(total > line) for a Poisson total (line like 9.5)."""
    return 1 - _poisson_cdf(math.floor(line), lam)


def nb_over(line: float, mean: float, disp: float) -> float:
    """P(count > line) for a negative binomial with variance = mean + mean² / disp."""
    r, p = disp, disp / (disp + mean)
    cdf, pmf = 0.0, p**r
    for k in range(math.floor(line) + 1):
        if k:
            pmf *= (k - 1 + r) / k * (1 - p)
        cdf += pmf
    return 1 - cdf


class CornerRatings:
    def __init__(self, half_life: float = CORNER_HALF_LIFE, carry: float = CORNER_CARRY):
        self.alpha = 1 - 0.5 ** (1 / half_life)
        self.carry = carry
        self.won: dict[str, float] = {}
        self.conceded: dict[str, float] = {}
        self.venue = {"home": 5.4, "away": 4.6}  # updated as matches come in

    def new_season(self, teams: set[str]) -> None:
        for d in (self.won, self.conceded):
            for t in list(d):
                d[t] = 1 + self.carry * (d[t] - 1)
        for t in teams:  # promoted teams: slightly below average
            self.won.setdefault(t, 0.9)
            self.conceded.setdefault(t, 1.1)

    def expect(self, home: str, away: str) -> tuple[float, float]:
        h = self.venue["home"] * self.won.get(home, 1) * self.conceded.get(away, 1)
        a = self.venue["away"] * self.won.get(away, 1) * self.conceded.get(home, 1)
        return h, a

    def update(self, home: str, away: str, ch: float, ca: float) -> None:
        v = 0.02  # venue averages move slowly
        self.venue["home"] += v * (ch - self.venue["home"])
        self.venue["away"] += v * (ca - self.venue["away"])
        # Credit relative to the venue norm, opponent-adjusted.
        for team, opp, got, venue in ((home, away, ch, "home"), (away, home, ca, "away")):
            base = self.venue[venue]
            won_obs = got / (base * self.conceded.get(opp, 1))
            conc_obs = got / (base * self.won.get(team, 1))
            self.won[team] = self.won.get(team, 1) + self.alpha * (won_obs - self.won.get(team, 1))
            self.conceded[opp] = self.conceded.get(opp, 1) + self.alpha * (
                conc_obs - self.conceded.get(opp, 1)
            )


def _fixtures(team_rows: list[dict]) -> list[dict]:
    """FotMob team-match rows → one record per match (home perspective), chronological."""
    by_id: dict[int, dict] = {}
    for r in team_rows:
        m = by_id.setdefault(
            r["match_id"], {"match_id": r["match_id"], "kickoff": r["kickoff_utc"]}
        )
        m["home" if r["is_home"] else "away"] = r
    return sorted(
        (m for m in by_id.values() if "home" in m and "away" in m), key=lambda m: m["kickoff"]
    )


def corner_walk(seasons: Sequence[tuple[int, list[dict]]]) -> tuple[list[dict], CornerRatings]:
    """Predict every match's corners from earlier matches only; return predictions + the
    final ratings (for upcoming fixtures)."""
    R = CornerRatings()
    out = []
    for season, rows in seasons:
        fx = _fixtures(rows)
        R.new_season({r["team"] for r in rows})
        for m in fx:
            h, a = m["home"], m["away"]
            eh, ea = R.expect(h["team"], a["team"])
            if h.get("corners") is None or a.get("corners") is None:
                continue
            out.append(
                {
                    "season": season,
                    "exp_home": eh,
                    "exp_away": ea,
                    "home": h["corners"],
                    "away": a["corners"],
                }
            )
            R.update(h["team"], a["team"], h["corners"], a["corners"])
    return out, R


def corner_backtest(preds: list[dict], from_season: int) -> dict[str, Any]:
    ps = [p for p in preds if p["season"] >= from_season]
    tot = np.array([p["home"] + p["away"] for p in ps], float)
    exp = np.array([p["exp_home"] + p["exp_away"] for p in ps])
    sides = np.array([[p["home"], p["away"]] for p in ps], float)
    exp_sides = np.array([[p["exp_home"], p["exp_away"]] for p in ps])
    naive = np.full_like(tot, tot.mean())
    # Dispersion of a side's count: var = mu + mu² / disp, by moments on residuals.
    resid = ((sides - exp_sides) ** 2 - exp_sides).sum()
    disp = float((exp_sides**2).sum() / resid) if resid > 0 else 50.0
    calib = []
    for line in (8.5, 9.5, 10.5, 11.5):
        p = np.array([p_over(line, e) for e in exp])
        calib.append(
            {"line": line, "predicted": float(p.mean()), "observed": float((tot > line).mean())}
        )
    brier = float(
        np.mean([(p_over(9.5, e) - (t > 9.5)) ** 2 for e, t in zip(exp, tot, strict=True)])
    )
    brier_naive = float(np.mean([(np.mean(tot > 9.5) - (t > 9.5)) ** 2 for t in tot]))
    diff_exp, diff = exp_sides[:, 0] - exp_sides[:, 1], sides[:, 0] - sides[:, 1]
    decided = diff != 0
    return {
        "matches": len(ps),
        "mae_side": float(np.abs(sides - exp_sides).mean()),
        "mae_side_naive": float(np.abs(sides - sides.mean(0)).mean()),
        "favourite_more_corners": float(
            np.mean(np.sign(diff_exp[decided]) == np.sign(diff[decided]))
        ),
        "corr_total": float(np.corrcoef(exp, tot)[0, 1]),
        "mae_total": float(np.abs(tot - exp).mean()),
        "mae_total_naive": float(np.abs(tot - naive).mean()),
        "brier_over_9_5": brier,
        "brier_over_9_5_naive": brier_naive,
        "side_dispersion": disp,
        "calibration": calib,
    }


# ---------------------------------------------------------------------------- shooters


def role_rates(players: list[dict]) -> dict[str, dict[str, float]]:
    acc: dict[str, list[float]] = defaultdict(lambda: [0.0] * 5)
    on_target: dict[str, float] = defaultdict(float)
    for p in players:
        on_target[p.get("role") or "UNK"] += p.get("np_shots_on_target", 0)
        a = acc[p.get("role") or "UNK"]
        a[0] += p["np_shots"]
        a[1] += p["npxg_shots"]
        a[2] += p.get("xa") or 0.0
        a[3] += p.get("yellow", 0)
        a[4] += p["minutes"]
    return {
        r: {
            "shots90": 90 * s / m,
            "npxg90": 90 * x / m,
            "xa90": 90 * xa / m,
            "yellow90": 90 * y / m,
            "accuracy": on_target[r] / s if s else 0.33,
        }
        for r, (s, x, xa, y, m) in acc.items()
        if m
    }


class PlayerRates:
    """Accumulates each player's shooting (this season full weight, last season half)."""

    def __init__(self, roles: dict[str, dict[str, float]]):
        self.roles = roles
        self.acc: dict[int, list[float]] = defaultdict(lambda: [0.0] * 5)
        self.starts: dict[int, list[float]] = defaultdict(list)
        self.on_target: dict[int, float] = defaultdict(float)

    def add(self, p: dict, weight: float = 1.0) -> None:
        a = self.acc[p["player_id"]]
        a[0] += weight * p["np_shots"]
        a[1] += weight * p["npxg_shots"]
        a[2] += weight * p["minutes"]
        a[3] += weight * (p.get("xa") or 0.0)
        a[4] += weight * p.get("yellow", 0)
        self.on_target[p["player_id"]] += weight * p.get("np_shots_on_target", 0)
        if p["started"] and weight == 1.0:
            self.starts[p["player_id"]].append(p["minutes"])

    def rate(self, pid: int, role: str | None) -> tuple[float, float]:
        prior = self.roles.get(role or "UNK") or {"shots90": 1.0, "npxg90": 0.1}
        s, x, m, *_ = self.acc.get(pid, (0.0, 0.0, 0.0, 0.0, 0.0))
        k = SHRINK_MIN
        return (
            90 * (s + prior["shots90"] * k / 90) / (m + k),
            90 * (x + prior["npxg90"] * k / 90) / (m + k),
        )

    def extra(self, pid: int, role: str | None) -> tuple[float, float]:
        """(xA per 90, yellow cards per 90), shrunk towards the role average. Bookings are
        rare, so they get a heavier prior (900 minutes)."""
        prior = self.roles.get(role or "UNK") or {"xa90": 0.1, "yellow90": 0.15}
        _, _, m, xa, y = self.acc.get(pid, (0.0, 0.0, 0.0, 0.0, 0.0))
        pxa, py = prior.get("xa90", 0.1), prior.get("yellow90", 0.15)
        return (
            90 * (xa + pxa * SHRINK_MIN / 90) / (m + SHRINK_MIN),
            90 * (y + py * 900 / 90) / (m + 900),
        )

    def accuracy(self, pid: int, role: str | None) -> float:
        """Share of a player's shots on target, shrunk towards his role (10 shots of prior)."""
        prior = (self.roles.get(role or "UNK") or {}).get("accuracy", 0.33)
        shots = self.acc.get(pid, (0.0,) * 5)[0]
        return (self.on_target.get(pid, 0.0) + prior * 10) / (shots + 10)

    def minutes_if_starting(self, pid: int) -> float:
        st = self.starts.get(pid, [])[-6:]
        return float(np.mean(st)) if st else 78.0


def p_at_least(k: int, lam: float) -> float:
    """P(X >= k) for a Poisson count with mean ``lam``."""
    return 1 - sum(math.exp(-lam) * lam**i / math.factorial(i) for i in range(k))


def expect_player(
    rates: PlayerRates,
    pid: int,
    role: str | None,
    minutes: float,
    opp_shot_factor: float,
    opp_xg_factor: float,
    card_factor: float = 1.0,
) -> dict[str, float]:
    s90, x90 = rates.rate(pid, role)
    a90, y90 = rates.extra(pid, role)
    lam_s = (s90 * minutes / 90 * opp_shot_factor) ** SHOT_POWER
    lam_x = x90 * minutes / 90 * opp_xg_factor
    lam_a = a90 * minutes / 90 * opp_xg_factor
    lam_y = y90 * minutes / 90 * card_factor
    lam_t = lam_s * rates.accuracy(pid, role)
    return {
        "exp_shots": lam_s,
        "p_shot": 1 - math.exp(-lam_s),
        "p_shot2": p_at_least(2, lam_s),
        "p_shot3": p_at_least(3, lam_s),
        "exp_on_target": lam_t,
        "accuracy": rates.accuracy(pid, role),
        "p_on_target": 1 - math.exp(-lam_t),
        "p_on_target2": p_at_least(2, lam_t),
        "exp_npxg": lam_x,
        "p_goal": 1 - math.exp(-lam_x),
        "exp_xa": lam_a,
        "p_assist": 1 - math.exp(-lam_a),
        "p_involved": 1 - math.exp(-(lam_x + lam_a)),
        "p_booked": 1 - math.exp(-lam_y),
    }


def opponent_factors(
    team_rows: list[dict],
    before: str | None = None,
    prev_rows: list[dict] | None = None,
    prev_weight: float = OPP_PREV_WEIGHT,
) -> dict[str, tuple[float, float]]:
    """Team → (shots conceded / league avg, npxG conceded / league avg), from matches before
    ``before`` (kickoff string) in the given rows, plus last season's matches (``prev_rows``)
    at ``prev_weight`` each, shrunk towards average by three average matches (D-042)."""

    def ratios(rows: list[dict]) -> dict[str, tuple[int, float, float]]:
        rows = [r for r in rows if r.get("np_shots_conceded") is not None]
        if not rows:
            return {}
        lg_s = np.mean([r["np_shots_conceded"] for r in rows])
        lg_x = np.mean([r.get("npxg_conceded") or 0 for r in rows])
        by: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            by[r["team"]].append(r)
        return {
            t: (
                len(rs),
                float(np.mean([r["np_shots_conceded"] for r in rs]) / lg_s),
                float(np.mean([r.get("npxg_conceded") or 0 for r in rs]) / lg_x),
            )
            for t, rs in by.items()
        }

    cur = ratios([r for r in team_rows if before is None or r["kickoff_utc"] < before])
    if not cur:
        return {}
    prev = ratios(prev_rows or []) if prev_weight else {}
    k = 3  # shrink: three league-average matches
    out = {}
    for t in cur:  # teams in this league now (promoted sides have no last season here)
        n, fs, fx = cur[t]
        m, ps, px = prev.get(t, (0, 1.0, 1.0))
        m *= prev_weight
        out[t] = ((n * fs + m * ps + k) / (n + m + k), (n * fx + m * px + k) / (n + m + k))
    return out


def shooter_backtest(
    prev_players: list[dict],
    players: list[dict],
    team_rows: list[dict],
    prev_team_rows: list[dict] | None = None,
) -> dict:
    """Walk through a season: before each match, predict every starter's chance of a shot and
    of a non-penalty goal from earlier data only; score calibration and Brier vs a naive
    role-rate baseline."""
    roles = role_rates(prev_players)
    R = PlayerRates(roles)
    for p in prev_players:
        R.add(p, LAST_SEASON_WEIGHT)
    by_match: dict[int, list[dict]] = defaultdict(list)
    for p in players:
        by_match[p["match_id"]].append(p)
    ko = {r["match_id"]: r["kickoff_utc"] for r in team_rows}
    opp_of = {(r["match_id"], r["team"]): r["opponent"] for r in team_rows}
    preds = []
    for mid in sorted(by_match, key=lambda m: ko.get(m, "")):
        facs = opponent_factors(team_rows, ko.get(mid), prev_team_rows)
        for p in by_match[mid]:
            if not p["started"] or p.get("role") == "GK":
                continue
            opp = opp_of.get((mid, p["team"]))
            fs, fx = facs.get(opp, (1.0, 1.0))
            e = expect_player(
                R, p["player_id"], p.get("role"), R.minutes_if_starting(p["player_id"]), fs, fx
            )
            base = roles.get(
                p.get("role") or "UNK",
                {"shots90": 1.0, "npxg90": 0.1, "xa90": 0.1, "yellow90": 0.15},
            )
            preds.append(
                e
                | {
                    "naive_p_shot": 1 - math.exp(-base["shots90"] * 80 / 90),
                    "naive_p_goal": 1 - math.exp(-base["npxg90"] * 80 / 90),
                    "naive_p_assist": 1 - math.exp(-base.get("xa90", 0.1) * 80 / 90),
                    "naive_p_shot2": p_at_least(2, base["shots90"] * 80 / 90),
                    "naive_p_on_target": 1
                    - math.exp(-base["shots90"] * 80 / 90 * base.get("accuracy", 0.33)),
                    "naive_p_on_target2": p_at_least(
                        2, base["shots90"] * 80 / 90 * base.get("accuracy", 0.33)
                    ),
                    "shot2": p["np_shots"] >= 2,
                    "on_target": p.get("np_shots_on_target", 0) >= 1,
                    "on_target2": p.get("np_shots_on_target", 0) >= 2,
                    "naive_p_booked": 1 - math.exp(-base.get("yellow90", 0.15) * 80 / 90),
                    "shot": p["np_shots"] > 0,
                    "goal": p.get("np_goals", 0) > 0,
                    "assist": (p.get("assists") or 0) > 0,
                    "booked": p.get("yellow", 0) + p.get("red", 0) > 0,
                }
            )
        for p in by_match[mid]:
            R.add(p)

    def calib(key: str, obs: str) -> list[dict]:
        bins = defaultdict(list)
        for q in preds:
            bins[min(int(q[key] * 10), 9)].append(q)
        return [
            {
                "from": b / 10,
                "n": len(v),
                "predicted": float(np.mean([q[key] for q in v])),
                "observed": float(np.mean([q[obs] for q in v])),
            }
            for b, v in sorted(bins.items())
            if len(v) >= 30
        ]

    def brier(key: str, obs: str) -> float:
        return float(np.mean([(q[key] - q[obs]) ** 2 for q in preds]))

    return {
        "starters": len(preds),
        "brier_shot": brier("p_shot", "shot"),
        "brier_shot_naive": brier("naive_p_shot", "shot"),
        "brier_goal": brier("p_goal", "goal"),
        "brier_goal_naive": brier("naive_p_goal", "goal"),
        "brier_shot2": brier("p_shot2", "shot2"),
        "brier_shot2_naive": brier("naive_p_shot2", "shot2"),
        "brier_on_target": brier("p_on_target", "on_target"),
        "brier_on_target_naive": brier("naive_p_on_target", "on_target"),
        "brier_on_target2": brier("p_on_target2", "on_target2"),
        "brier_on_target2_naive": brier("naive_p_on_target2", "on_target2"),
        "calibration_shot2": calib("p_shot2", "shot2"),
        "calibration_on_target": calib("p_on_target", "on_target"),
        "brier_assist": brier("p_assist", "assist"),
        "brier_assist_naive": brier("naive_p_assist", "assist"),
        "brier_booked": brier("p_booked", "booked"),
        "brier_booked_naive": brier("naive_p_booked", "booked"),
        "calibration_shot": calib("p_shot", "shot"),
        "calibration_goal": calib("p_goal", "goal"),
        "calibration_assist": calib("p_assist", "assist"),
        "calibration_booked": calib("p_booked", "booked"),
    }


# ---------------------------------------------------------------------------- cards (D-030)


def referee_name(details: dict) -> str | None:
    ib = ((details.get("content") or {}).get("matchFacts") or {}).get("infoBox") or {}
    return (ib.get("Referee") or {}).get("text")


REF_PRIOR_MATCHES = 8.0  # a referee's factor is shrunk towards 1 by this many average games


class CardRatings:
    """Rolling yellow-card ratings: how often a team is booked, how many bookings it draws
    from opponents, and each referee's own rate (shrunk towards average)."""

    def __init__(self, half_life: float = CORNER_HALF_LIFE, carry: float = CORNER_CARRY):
        self.alpha = 1 - 0.5 ** (1 / half_life)
        self.carry = carry
        self.booked: dict[str, float] = {}
        self.draws: dict[str, float] = {}
        self.ref: dict[str, list[float]] = {}  # name → [sum of obs/expected, matches]
        self.venue = {"home": 1.75, "away": 2.0}
        self.red_rate = 0.06  # per team-match

    def new_season(self, teams: set[str]) -> None:
        for d in (self.booked, self.draws):
            for t in list(d):
                d[t] = 1 + self.carry * (d[t] - 1)
            for t in teams:
                d.setdefault(t, 1.0)

    def ref_factor(self, name: str | None) -> float:
        s, n = self.ref.get(name or "", (0.0, 0.0))
        return (REF_PRIOR_MATCHES + s) / (REF_PRIOR_MATCHES + n)

    def expect(
        self, home: str, away: str, referee: str | None, use_ref: bool = True
    ) -> tuple[float, float]:
        f = self.ref_factor(referee) if use_ref else 1.0
        h = self.venue["home"] * self.booked.get(home, 1) * self.draws.get(away, 1) * f
        a = self.venue["away"] * self.booked.get(away, 1) * self.draws.get(home, 1) * f
        return h, a

    def update(
        self, home: str, away: str, referee: str | None, yh: float, ya: float, reds: float
    ) -> None:
        eh, ea = self.expect(home, away, None, use_ref=False)
        if referee and eh + ea > 0:
            r = self.ref.setdefault(referee, [0.0, 0.0])
            r[0] += (yh + ya) / (eh + ea)
            r[1] += 1
        v = 0.02
        self.venue["home"] += v * (yh - self.venue["home"])
        self.venue["away"] += v * (ya - self.venue["away"])
        self.red_rate += v * (reds / 2 - self.red_rate)
        f = self.ref_factor(referee)
        for team, opp, got, venue in ((home, away, yh, "home"), (away, home, ya, "away")):
            base = self.venue[venue] * f
            b_obs = got / (base * self.draws.get(opp, 1))
            d_obs = got / (base * self.booked.get(team, 1))
            self.booked[team] = self.booked.get(team, 1) + self.alpha * (
                b_obs - self.booked.get(team, 1)
            )
            self.draws[opp] = self.draws.get(opp, 1) + self.alpha * (d_obs - self.draws.get(opp, 1))


def card_walk(seasons: Sequence[tuple[int, list[dict]]]) -> tuple[list[dict], CardRatings]:
    """Predict every match's yellows (with and without the referee) and the chance of a red
    card from earlier matches only."""
    R = CardRatings()
    out = []
    for season, rows in seasons:
        R.new_season({r["team"] for r in rows})
        for m in _fixtures(rows):
            h, a = m["home"], m["away"]
            if h.get("yellow_cards") is None or a.get("yellow_cards") is None:
                continue
            ref = h.get("referee")
            eh, ea = R.expect(h["team"], a["team"], ref)
            nh, na = R.expect(h["team"], a["team"], ref, use_ref=False)
            reds = (h.get("red_cards") or 0) + (a.get("red_cards") or 0)
            out.append(
                {
                    "season": season,
                    "exp": eh + ea,
                    "exp_noref": nh + na,
                    "exp_home": eh,
                    "exp_away": ea,
                    "p_red": 1 - math.exp(-2 * R.red_rate * R.ref_factor(ref) ** 0.5),
                    "yellows": h["yellow_cards"] + a["yellow_cards"],
                    "home": h["yellow_cards"],
                    "away": a["yellow_cards"],
                    "red": reds > 0,
                }
            )
            R.update(h["team"], a["team"], ref, h["yellow_cards"], a["yellow_cards"], reds)
    return out, R


def card_backtest(preds: list[dict], from_season: int) -> dict[str, Any]:
    ps = [p for p in preds if p["season"] >= from_season]
    y = np.array([p["yellows"] for p in ps], float)
    e, e0 = np.array([p["exp"] for p in ps]), np.array([p["exp_noref"] for p in ps])
    naive = y.mean()
    over = {}
    for line in (3.5, 4.5, 5.5):
        obs = y > line
        over[str(line)] = {
            "brier": float(
                np.mean([(p_over(line, x) - o) ** 2 for x, o in zip(e, obs, strict=True)])
            ),
            "brier_noref": float(
                np.mean([(p_over(line, x) - o) ** 2 for x, o in zip(e0, obs, strict=True)])
            ),
            "brier_naive": float(np.mean((obs.mean() - obs) ** 2)),
        }
    red = np.array([p["red"] for p in ps], float)
    pr = np.array([p["p_red"] for p in ps])
    sides = np.array([[p["home"], p["away"]] for p in ps], float)
    exp_sides = np.array([[p["exp_home"], p["exp_away"]] for p in ps])
    decided = sides[:, 0] != sides[:, 1]
    return {
        "matches": len(ps),
        "mae": float(np.abs(y - e).mean()),
        "mae_noref": float(np.abs(y - e0).mean()),
        "mae_naive": float(np.abs(y - naive).mean()),
        "corr": float(np.corrcoef(e, y)[0, 1]),
        "corr_noref": float(np.corrcoef(e0, y)[0, 1]),
        "more_cards_side": float(
            np.mean(
                np.sign(exp_sides[decided, 0] - exp_sides[decided, 1])
                == np.sign(sides[decided, 0] - sides[decided, 1])
            )
        ),
        "over": over,
        "red_rate": float(red.mean()),
        "red_brier": float(np.mean((pr - red) ** 2)),
        "red_brier_naive": float(np.mean((red.mean() - red) ** 2)),
        "variance_to_mean": float(y.var() / y.mean()),
    }
