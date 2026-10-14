"""Seed the database with deterministic synthetic history and calibrate the corridor.

uv run python -m corridor.scripts.seed_synthetic [--seasons 5] [--seed 42] [--window-days 365]
"""

import argparse
import time

from sqlalchemy import func, select

from corridor.db.models import Match
from corridor.db.repository import calibrate, load_synthetic
from corridor.db.session import SessionLocal
from corridor.synthetic.generator import generate


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seasons", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--window-days", type=int, default=365)
    ap.add_argument("--physical-missing-rate", type=float, default=0.0)
    args = ap.parse_args()

    t0 = time.perf_counter()
    ds = generate(
        seasons=args.seasons, seed=args.seed, physical_missing_rate=args.physical_missing_rate
    )
    with SessionLocal.begin() as session:
        if session.scalar(select(func.count()).select_from(Match)):
            raise SystemExit(
                "database already has matches; reset it first (alembic downgrade "
                "base && alembic upgrade head)"
            )
        load_synthetic(session, ds)
        window_end = max(m.kickoff_utc for m in ds.matches)
        cal = calibrate(session, window_end=window_end, window_days=args.window_days)
    c = cal.lines
    print(f"seeded {len(ds.matches)} matches / {len(ds.performances)} performances")
    print(
        f"corridor #{cal.corridor_id}: window sample {cal.sample_size} rows, "
        f"win line npxGD ≥ {c.npxgd_win_threshold} (n={c.win_cohort_size}, "
        f"{c.win_cohort_win_pct}% W), loss line npxGD ≤ {c.npxgd_loss_threshold} "
        f"(n={c.loss_cohort_size}, {c.loss_cohort_loss_pct}% L)"
    )
    print(f"re-vectorized {cal.rows_vectorized} rows in {time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    main()
