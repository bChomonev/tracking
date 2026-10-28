"""Recent form, plainly: the last few matches against the ones before them.

A per-match series (elite score, danger score, opponent-adjusted chance quality
difference) is summarised as *recent* (the mean of the last ``WINDOW`` matches) against
*before* (the mean of the earlier matches). The gap is called "up" or "down" only when it
is at least one standard error wide, given how much the team's matches vary. That is a
plain-reading bar, not a significance test: it stops a two-match wobble being called a
trend, nothing more. With fewer than ``MIN_MATCHES`` matches there is no call at all.

Pure functions, no I/O. Used for description (site, previews, the analyst's fact sheet).
Whether form *predicts* is a separate question answered in corridor.predict (form ratings)
and reported by the predictions step.
"""

from statistics import mean, pstdev

WINDOW = 5  # the "recent" matches
MIN_BEFORE = 3  # at least this many earlier matches before a call is made
MIN_MATCHES = WINDOW + MIN_BEFORE


def recent(values: list[float | None], window: int = WINDOW) -> dict | None:
    """Summarise a chronological per-match series. ``None`` entries (no data) are skipped.

    Returns None when there is nothing to summarise, else a dict with the series, the
    recent and earlier means, their gap, the noise band (one standard error of the gap)
    and a call: "up", "down", "steady", or None when there are too few matches."""
    xs = [float(v) for v in values if v is not None]
    if not xs:
        return None
    n = len(xs)
    rec = xs[-window:]
    before = xs[:-window] if n > window else []
    out = {
        "series": xs,
        "n": n,
        "n_recent": len(rec),
        "recent": mean(rec),
        "before": mean(before) if before else None,
        "delta": None,
        "noise": None,
        "call": None,
    }
    if len(before) < MIN_BEFORE:
        return out
    sd = pstdev(xs)
    noise = sd * (1 / len(rec) + 1 / len(before)) ** 0.5
    delta = out["recent"] - out["before"]
    out |= {
        "delta": delta,
        "noise": noise,
        "call": "up" if delta >= noise > 0 else "down" if -delta >= noise > 0 else "steady",
    }
    return out


def words(
    t: dict | None, what: str, decimals: int = 2, lower_is_better: bool = False
) -> str | None:
    """One plain sentence about a trend: what it counts, both numbers, and the call."""
    if not t or t["call"] is None:
        return None
    d = t["delta"] if not lower_is_better else -t["delta"]
    head = "better" if d > 0 else "worse"
    rec, bef = f"{t['recent']:.{decimals}f}", f"{t['before']:.{decimals}f}"
    if t["call"] == "steady":
        return (
            f"{what}: about the same over the last {t['n_recent']} matches "
            f"({rec} against {bef} before)."
        )
    return (
        f"{what}: {head} over the last {t['n_recent']} matches, {rec} against {bef} in the "
        f"{t['n'] - t['n_recent']} before."
    )
