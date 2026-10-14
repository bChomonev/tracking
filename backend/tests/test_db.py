"""Integration tests against Postgres + pgvector. Skipped when the DB isn't reachable."""

import numpy as np
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from corridor.config import settings
from corridor.db.models import BenchmarkCorridor, TeamMatchPerformance
from corridor.db.repository import calibrate, find_twins, load_synthetic
from corridor.synthetic.generator import generate

pytestmark = pytest.mark.db

TEST_DB = "corridor_test"


@pytest.fixture(scope="module")
def engine():
    admin_url = make_url(settings.database_url)
    try:
        admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin.connect() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
            c.execute(text(f"CREATE DATABASE {TEST_DB}"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Postgres not reachable ({exc.__class__.__name__}); run docker compose up -d")
    url = admin_url.set(database=TEST_DB)
    cfg = Config("alembic.ini")
    cfg.attributes["database_url"] = url.render_as_string(hide_password=False)
    command.upgrade(cfg, "head")
    eng = create_engine(url)
    ds = generate(seasons=2, seed=42)
    with Session(eng) as s, s.begin():
        load_synthetic(s, ds)
        calibrate(s, window_end=max(m.kickoff_utc for m in ds.matches), window_days=730)
    yield eng
    eng.dispose()
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))


def test_pgvector_supports_halfvec(engine):
    with engine.connect() as c:
        version = c.scalar(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
    assert tuple(int(x) for x in version.split(".")[:2]) >= (0, 7)


def test_calibration_persisted_and_all_rows_vectorized(engine):
    with Session(engine) as s:
        active = s.scalars(select(BenchmarkCorridor).where(BenchmarkCorridor.is_active)).one()
        missing = s.scalar(select(func.count()).where(TeamMatchPerformance.stats_vector.is_(None)))
        stale = s.scalar(
            select(func.count()).where(TeamMatchPerformance.corridor_version_id != active.id)
        )
    assert active.calibration["win_cohort_win_pct"] >= 85
    assert missing == 0 and stale == 0


def _latest(s: Session) -> TeamMatchPerformance:
    return s.scalars(
        select(TeamMatchPerformance).order_by(TeamMatchPerformance.kickoff_utc.desc()).limit(1)
    ).one()


def test_twin_query_uses_hnsw_index(engine):
    with Session(engine) as s, s.begin():
        target = _latest(s)
        s.execute(text("SET LOCAL enable_seqscan = off"))  # small table: make the planner honest
        plan = "\n".join(
            r[0]
            for r in s.execute(
                text(
                    "EXPLAIN SELECT id FROM team_match_performances "
                    "ORDER BY stats_vector <-> CAST(:v AS halfvec(12)) LIMIT 50"
                ),
                {"v": "[" + ",".join(map(str, target.stats_vector)) + "]"},
            )
        )
    assert "idx_team_perf_halfvec_hnsw" in plan


def test_twins_exclude_self_and_future_and_match_bruteforce(engine):
    with Session(engine) as s, s.begin():
        target = _latest(s)
        twins = find_twins(
            s,
            np.asarray(target.stats_vector),
            before=target.kickoff_utc,
            exclude_match_id=target.match_id,
        )
        rows = s.execute(
            select(TeamMatchPerformance.id, TeamMatchPerformance.stats_vector).where(
                TeamMatchPerformance.kickoff_utc < target.kickoff_utc,
                TeamMatchPerformance.match_id != target.match_id,
            )
        ).all()
        target_match_id, q = target.match_id, np.asarray(target.stats_vector, dtype=np.float64)
    assert len(twins) == 50
    assert all(t.match_id != target_match_id for t in twins)
    dists = [t.l2_distance for t in twins]
    assert dists == sorted(dists)

    ids = np.array([r[0] for r in rows])
    mat = np.array([r[1] for r in rows], dtype=np.float64)
    exact = set(ids[np.argsort(np.linalg.norm(mat - q, axis=1))[:50]])
    recall = len(exact & {t.performance_id for t in twins}) / 50
    assert recall >= 0.9
