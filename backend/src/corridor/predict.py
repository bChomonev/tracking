"""Stage 4: pre-match predictions (D-023).

Every Premier League team carries a rolling rating, updated after each of its matches from
Understat (12 seasons of history): exponentially weighted non-penalty xG created and
conceded, goals, and the share of the core elite / worst lines it reached (the lines are
built from the previous season, as in corridor.proof). For a fixture, the two teams'
ratings *before kickoff* become a few features and a multinomial logistic model turns them
into home / draw / away probabilities.

Nothing a match produces is used to predict it: ratings are updated only after a match is
scored, and the model for season S is trained only on seasons before S. Parameters (rating
half-life, how much of a rating carries into a new season, feature set) are tuned on the
early test seasons and then frozen for the later ones, which are reported separately.

Scoring: ranked probability score (RPS, lower is better; the standard for football because
it respects that a draw sits between a home and an away win), log loss and hit rate,
against two baselines: base rates (home/draw/away frequencies) and the bookmakers (average
pre-match odds and Pinnacle's closing odds, margin removed).
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression

from corridor import proof
from corridor.best_line import build_line, hits_line
from corridor.ingest import odds as odds_src
from corridor.ingest import understat

OUTCOMES = ("H", "D", "A")
STATS = ("npxg", "npxga", "gf", "ga", "elite", "danger")
FEATURE_SETS: dict[str, tuple[str, ...]] = {
    "xg": ("xg_diff", "xg_total"),
    "xg+goals": ("xg_diff", "xg_total", "goal_diff"),
    "xg+lines": ("xg_diff", "xg_total", "elite_diff", "danger_diff"),
    "xg+goals+lines": ("xg_diff", "xg_total", "goal_diff", "elite_diff", "danger_diff"),
}


@dataclass(frozen=True)
class Params:
    half_life: float = 8.0  # matches
    carry: float = 0.7  # share of a rating's distance from the league mean kept over summer
    features: str = "xg+lines"
    C: float = 1.0  # inverse L2 strength of the logistic model
    adjust: bool = True  # opponent-adjust each match before it updates a rating


# ---------------------------------------------------------------------------- data


def season_matches(season: int, *, refresh: bool = False) -> list[dict]:
    """All fixtures of one Understat EPL season; played ones carry both teams' stats."""
    data = understat.league_data("EPL", season, refresh=refresh)
    rows = {(r["team"], r["kickoff"]): r for r in understat.team_matches(data)}
    out = []
    for d in data["dates"]:
        h, a, ko = d["h"]["title"], d["a"]["title"], d["datetime"]
        m: dict[str, Any] = {"id": d["id"], "season": season, "kickoff": ko, "home": h, "away": a}
        rh, ra = rows.get((h, ko)), rows.get((a, ko))
        if d["isResult"] and rh and ra:
            hg, ag = rh["goals_for"], rh["goals_against"]
            m |= {
                "played": True,
                "hg": hg,
                "ag": ag,
                "result": "H" if hg > ag else "D" if hg == ag else "A",
                "rows": {"home": rh, "away": ra},
            }
        else:
            m["played"] = False
        out.append(m)
    return sorted(out, key=lambda m: m["kickoff"])


def load_history(first: int, last: int, *, refresh_last: bool = False) -> list[dict]:
    out: list[dict] = []
    for s in range(first, last + 1):
        out += season_matches(s, refresh=refresh_last and s == last)
    return out


def _core_lines(history: list[dict]) -> dict[int, dict]:
    """Core elite / worst lines per season, built from the season before (D-019/D-020)."""
    by_season: dict[int, list[dict]] = defaultdict(list)
    for m in history:
        if m["played"]:
            for side in ("home", "away"):
                by_season[m["season"]].append(m["rows"][side])
    lines = {}
    for s in sorted(by_season):
        if s - 1 in by_season:
            prev = proof.understat_rows(by_season[s - 1])
            lines[s] = {
                side: build_line(
                    prev, str(s - 1), None, side, proof.UNDERSTAT_METRICS, derived=True
                )
                for side in ("best", "worst")
            }
    return lines


def _team_stats(row: dict, lines: dict | None) -> dict[str, float]:
    r = proof.understat_rows([row])[0]
    out = {
        "npxg": row["us_npxg"],
        "npxga": row["us_npxga"],
        "gf": row["goals_for"],
        "ga": row["goals_against"],
    }
    for side, key in (("best", "elite"), ("worst", "danger")):
        if lines:
            ln = lines[side]["metrics"]
            hits = [
                hits_line(r[m.key], ln[m.key]["value"], m.direction, side)
                for m in proof.UNDERSTAT_METRICS
                if m.key in ln
            ]
            hits = [h for h in hits if h is not None]
            out[key] = sum(hits) / len(hits) if hits else None
        else:
            out[key] = None
    return out


# ---------------------------------------------------------------------------- ratings


class Ratings:
    """Rolling per-team ratings, updated strictly after each match."""

    def __init__(self, p: Params):
        self.alpha = 1 - 0.5 ** (1 / p.half_life)
        self.carry = p.carry
        self.state: dict[str, dict[str, float]] = {}
        self.season: int | None = None

    def start_season(self, season: int, teams: set[str]) -> None:
        if self.state:
            mean = {k: float(np.mean([s[k] for s in self.state.values()])) for k in STATS}
            old = {t: s for t, s in self.state.items() if t in teams}
            gone = [s for t, s in self.state.items() if t not in teams]
            # Promoted teams start where the relegated teams they replace finished.
            prior = {k: float(np.mean([s[k] for s in gone])) for k in STATS} if gone else dict(mean)
            self.state = {
                t: (
                    {k: mean[k] + self.carry * (old[t][k] - mean[k]) for k in STATS}
                    if t in old
                    else dict(prior)
                )
                for t in teams
            }
        self.season = season

    def update(self, team: str, x: dict[str, float | None]) -> None:
        s = self.state.get(team)
        if s is None:
            self.state[team] = {k: (x[k] if x[k] is not None else 0.0) for k in STATS}
            return
        for k in STATS:
            if x[k] is not None:
                s[k] += self.alpha * (x[k] - s[k])

    def opponent_adjusted(self, home: str, away: str, xs: dict[str, dict]) -> dict[str, dict]:
        """Credit chances and goals relative to the opponent: 1.5 npxG against a side that
        usually concedes 2.0 counts as below par. Uses ratings from before the match."""
        h, a = self.state.get(home), self.state.get(away)
        if not h or not a or len(self.state) < 2:
            return xs
        mean = {k: float(np.mean([s[k] for s in self.state.values()])) for k in STATS}
        out = {}
        for side, opp in (("home", a), ("away", h)):
            x = dict(xs[side])
            for k, ok in (("npxg", "npxga"), ("npxga", "npxg"), ("gf", "ga"), ("ga", "gf")):
                x[k] = x[k] - (opp[ok] - mean[ok])
            out[side] = x
        return out

    def features(self, home: str, away: str) -> dict[str, float]:
        h, a = self.state[home], self.state[away]
        xh, xa = (h["npxg"] + a["npxga"]) / 2, (a["npxg"] + h["npxga"]) / 2
        return {
            "xg_diff": xh - xa,
            "xg_total": xh + xa,
            "goal_diff": (h["gf"] - h["ga"]) - (a["gf"] - a["ga"]),
            "elite_diff": h["elite"] - a["elite"],
            "danger_diff": h["danger"] - a["danger"],
            "exp_home": xh,
            "exp_away": xa,
        }


def walk(history: list[dict], p: Params) -> tuple[list[dict], Ratings]:
    """Run the ratings through history. Returns each match with its pre-kickoff features
    (unplayed fixtures get features from the latest ratings) and the final ratings."""
    lines = _core_lines(history)
    R = Ratings(p)
    out = []
    by_season: dict[int, list[dict]] = defaultdict(list)
    for m in history:
        by_season[m["season"]].append(m)
    for s in sorted(by_season):
        ms = by_season[s]
        R.start_season(s, {t for m in ms for t in (m["home"], m["away"])})
        for m in ms:  # chronological
            if R.state.get(m["home"]) and R.state.get(m["away"]):
                out.append(m | {"x": R.features(m["home"], m["away"])})
            if m["played"]:
                xs = {side: _team_stats(m["rows"][side], lines.get(s)) for side in ("home", "away")}
                if p.adjust:
                    xs = R.opponent_adjusted(m["home"], m["away"], xs)
                for side in ("home", "away"):
                    R.update(m[side], xs[side])
    # Unplayed fixtures must see the ratings after *every* played match.
    for m in out:
        if not m["played"]:
            m["x"] = R.features(m["home"], m["away"])
    return out, R


# ---------------------------------------------------------------------------- model


def _X(ms: Sequence[dict], feats: Sequence[str]) -> np.ndarray:
    return np.array([[m["x"][f] for f in feats] for m in ms], dtype=float)


class Model:
    def __init__(self, p: Params):
        self.p = p
        self.feats = FEATURE_SETS[p.features]

    def fit(self, ms: Sequence[dict]) -> "Model":
        X = _X(ms, self.feats)
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        y = [m["result"] for m in ms]
        self.lr = LogisticRegression(C=self.p.C, max_iter=1000).fit((X - self.mu) / self.sd, y)
        self.order = [list(self.lr.classes_).index(o) for o in OUTCOMES]
        return self

    def predict(self, ms: Sequence[dict]) -> np.ndarray:
        X = (_X(ms, self.feats) - self.mu) / self.sd
        return self.lr.predict_proba(X)[:, self.order]

    def contributions(self, m: dict) -> dict[str, float]:
        """Each feature's push towards a home win (log-odds of H vs A), for explanations."""
        x = (np.array([m["x"][f] for f in self.feats]) - self.mu) / self.sd
        coef = self.lr.coef_
        h, a = list(self.lr.classes_).index("H"), list(self.lr.classes_).index("A")
        return {f: float((coef[h][i] - coef[a][i]) * x[i]) for i, f in enumerate(self.feats)}


# ---------------------------------------------------------------------------- scoring


def rps(p: Sequence[float], result: str) -> float:
    o = [1.0 if r == result else 0.0 for r in OUTCOMES]
    c1, c2 = p[0] - o[0], p[0] + p[1] - o[0] - o[1]
    return (c1 * c1 + c2 * c2) / 2


def score(probs: np.ndarray, results: Sequence[str]) -> dict[str, float]:
    idx = [OUTCOMES.index(r) for r in results]
    n = len(idx)
    return {
        "n": n,
        "rps": float(np.mean([rps(p, r) for p, r in zip(probs, results, strict=True)])),
        "log_loss": float(-np.mean(np.log(np.clip(probs[np.arange(n), idx], 1e-12, 1)))),
        "hit_rate": float(np.mean(np.argmax(probs, 1) == np.array(idx))),
    }


def base_rates(ms: Iterable[dict]) -> np.ndarray:
    rs = [m["result"] for m in ms]
    return np.array([rs.count(o) / len(rs) for o in OUTCOMES])


def attach_odds(ms: list[dict], seasons: Iterable[int], current: int | None = None) -> None:
    """Add bookmaker probabilities (margin removed) to played matches, where available."""
    for s in seasons:
        try:
            rows = odds_src.season_odds(s, current=s == current)
        except Exception:  # noqa: BLE001 — the benchmark is optional
            continue
        ours = {t for m in ms if m["season"] == s for t in (m["home"], m["away"])}
        names = odds_src.name_map({r["home"] for r in rows} | {r["away"] for r in rows}, ours)
        idx = {(names[r["home"]], names[r["away"]]): r for r in rows}
        for m in ms:
            if m["season"] != s:
                continue
            r = idx.get((m["home"], m["away"]))
            ko = datetime.fromisoformat(m["kickoff"]).date()
            if r and abs((r["date"] - ko).days) <= 1 and r["odds"]:
                m["odds"] = r["odds"]


def evaluate(scored: list[dict], p: Params, seasons: Sequence[int], first_train: int) -> dict:
    """Walk-forward: for each test season S, fit on seasons [first_train, S) and score S."""
    per_season = []
    pooled: dict[str, list] = defaultdict(list)
    for s in seasons:
        train = [m for m in scored if first_train <= m["season"] < s and m["played"]]
        test = [m for m in scored if m["season"] == s and m["played"]]
        if not train or not test:
            continue
        model = Model(p).fit(train)
        pm = model.predict(test)
        pb = np.tile(base_rates(train), (len(test), 1))
        res = [m["result"] for m in test]
        row = {"season": s, "model": score(pm, res), "base": score(pb, res)}
        for book in ("avg", "closing"):
            with_odds = [i for i, m in enumerate(test) if book in m.get("odds", {})]
            if len(with_odds) >= 0.8 * len(test):
                po = np.array([test[i]["odds"][book] for i in with_odds])
                rr = [res[i] for i in with_odds]
                row[book] = score(po, rr)
                row[f"model_on_{book}_matches"] = score(pm[with_odds], rr)
                pooled[book] += [(po[j], rr[j], pm[i]) for j, i in enumerate(with_odds)]
        pooled["model"] += list(zip(pm, res, strict=True))
        pooled["base"] += list(zip(pb, res, strict=True))
        pooled["calibration"] += list(zip(pm, res, strict=True))
        per_season.append(row)
    summary = {}
    for k in ("model", "base"):
        if pooled[k]:
            summary[k] = score(np.array([p for p, _ in pooled[k]]), [r for _, r in pooled[k]])
    for book in ("avg", "closing"):
        if pooled[book]:
            summary[book] = score(
                np.array([x[0] for x in pooled[book]]), [x[1] for x in pooled[book]]
            )
            summary[f"model_on_{book}_matches"] = score(
                np.array([x[2] for x in pooled[book]]), [x[1] for x in pooled[book]]
            )
    return {
        "seasons": per_season,
        "pooled": summary,
        "calibration": calibration(pooled["calibration"]),
    }


def calibration(pairs: list) -> list[dict]:
    """Predicted vs observed frequency, all three outcomes pooled, in 10% bins."""
    bins = [[] for _ in range(10)]
    for p, r in pairs:
        for i, o in enumerate(OUTCOMES):
            bins[min(int(p[i] * 10), 9)].append((p[i], r == o))
    return [
        {
            "from": i / 10,
            "n": len(b),
            "predicted": float(np.mean([x for x, _ in b])),
            "observed": float(np.mean([y for _, y in b])),
        }
        for i, b in enumerate(bins)
        if len(b) >= 20
    ]


# ---------------------------------------------------------------------------- tuning


GRID = {
    "half_life": (8.0, 12.0, 16.0, 24.0, 32.0, 48.0),
    "carry": (0.7, 0.85, 1.0),
    "features": tuple(FEATURE_SETS),
    "adjust": (False, True),
    "C": (0.05, 1.0),
}


def tune(history: list[dict], tune_seasons: Sequence[int], first_train: int) -> tuple[Params, list]:
    """Pick parameters by pooled RPS on the tuning seasons only."""
    trials = []
    for hl in GRID["half_life"]:
        for carry in GRID["carry"]:
            for adj in GRID["adjust"]:
                scored, _ = walk(history, Params(hl, carry, adjust=adj))
                for f in GRID["features"]:
                    for c in GRID["C"]:
                        p = Params(hl, carry, f, c, adj)
                        ev = evaluate(scored, p, tune_seasons, first_train)
                        trials.append((ev["pooled"]["model"]["rps"], p))
    trials.sort(key=lambda t: t[0])
    return trials[0][1], [{"rps": r, **vars(p)} for r, p in trials[:10]]


# ---------------------------------------------------------------------------- season sim


def simulate(
    table: dict[str, dict], fixtures: list[dict], probs: np.ndarray, n: int = 20000, seed: int = 42
) -> dict[str, dict]:
    """Monte Carlo of the rest of the season from fixed probabilities. ``table``: team →
    {points, gd}. Returns per team: mean points and P(title / top 4 / relegation)."""
    rng = np.random.default_rng(seed)
    teams = sorted(table)
    ix = {t: i for i, t in enumerate(teams)}
    pts = np.tile(np.array([table[t]["points"] for t in teams], float), (n, 1))
    gd = np.array([table[t]["gd"] for t in teams], float)
    u = rng.random((n, len(fixtures)))
    for j, (m, p) in enumerate(zip(fixtures, probs, strict=True)):
        h, a = ix[m["home"]], ix[m["away"]]
        home = u[:, j] < p[0]
        draw = (u[:, j] >= p[0]) & (u[:, j] < p[0] + p[1])
        pts[:, h] += 3 * home + draw
        pts[:, a] += 3 * (~home & ~draw) + draw
    # Rank by points, then current goal difference, then a random tiebreak.
    key = pts + gd[None, :] * 1e-3 + rng.random(pts.shape) * 1e-6
    rank = (-key).argsort(1).argsort(1) + 1
    nt = len(teams)
    return {
        t: {
            "points": float(pts[:, i].mean()),
            "points_p10": float(np.percentile(pts[:, i], 10)),
            "points_p90": float(np.percentile(pts[:, i], 90)),
            "title": float((rank[:, i] == 1).mean()),
            "top4": float((rank[:, i] <= 4).mean()),
            "relegation": float((rank[:, i] > nt - 3).mean()),
            "position": float(rank[:, i].mean()),
        }
        for t, i in ix.items()
    }


def next_round(fixtures: list[dict], now: datetime, days: int = 8) -> list[dict]:
    """Unplayed fixtures in the window starting at the next kickoff (one matchweek)."""
    ahead = sorted(
        (m for m in fixtures if not m["played"] and datetime.fromisoformat(m["kickoff"]) > now),
        key=lambda m: m["kickoff"],
    )
    if not ahead:
        return []
    first = datetime.fromisoformat(ahead[0]["kickoff"])
    return [
        m for m in ahead if datetime.fromisoformat(m["kickoff"]) < first + timedelta(days=days)
    ][:10]


def today() -> date:
    return datetime.now().date()
