"""ORM models. The Alembic migrations are the source of truth for DDL; keep these in sync."""

from datetime import datetime
from decimal import Decimal

from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from corridor.engine.metrics import N_DIMS


class Base(DeclarativeBase):
    pass


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    short_code: Mapped[str] = mapped_column(String(10))
    league_code: Mapped[str] = mapped_column(String(16))
    elo_rating: Mapped[Decimal] = mapped_column(Numeric(6, 1), server_default="1500.0")
    is_benchmark_cohort: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (Index("idx_matches_kickoff_status", "kickoff_utc", "audit_status"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), unique=True)
    competition_code: Mapped[str] = mapped_column(String(32))
    season: Mapped[str] = mapped_column(String(12))
    kickoff_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    venue: Mapped[str | None] = mapped_column(String(120))
    # SCHEDULED → PASS1_PUBLISHED → PASS2_FINALIZED (HISTORICAL for backfilled rows)
    audit_status: Mapped[str] = mapped_column(String(24), server_default="SCHEDULED")
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    home_goals: Mapped[int | None] = mapped_column(SmallInteger)
    away_goals: Mapped[int | None] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BenchmarkCorridor(Base):
    __tablename__ = "benchmark_corridors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    window_label: Mapped[str] = mapped_column(String(32), unique=True)
    window_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    sample_matches_count: Mapped[int] = mapped_column(Integer)
    metric_means: Mapped[dict] = mapped_column(JSONB)
    metric_stds: Mapped[dict] = mapped_column(JSONB)
    metric_weights: Mapped[dict] = mapped_column(JSONB)
    calibration: Mapped[dict] = mapped_column(JSONB)  # thresholds, cohort sizes, targets
    win_90_ceiling_raw: Mapped[dict] = mapped_column(JSONB)
    loss_85_floor_raw: Mapped[dict] = mapped_column(JSONB)
    v_best_centroid = mapped_column(HALFVEC(N_DIMS), nullable=False)
    v_worst_centroid = mapped_column(HALFVEC(N_DIMS), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="false")


class TeamMatchPerformance(Base):
    __tablename__ = "team_match_performances"
    __table_args__ = (
        UniqueConstraint("match_id", "team_id"),
        CheckConstraint("result IN ('W','D','L')", name="ck_tmp_result"),
        Index(
            "idx_team_perf_halfvec_hnsw",
            "stats_vector",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"stats_vector": "halfvec_l2_ops"},
        ),
        Index("idx_team_perf_team_kickoff", "team_id", "kickoff_utc"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    opponent_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    corridor_version_id: Mapped[int | None] = mapped_column(ForeignKey("benchmark_corridors.id"))
    # Denormalized from matches so twin searches can exclude future matches without a join.
    kickoff_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    competition_tier: Mapped[int] = mapped_column(SmallInteger, server_default="1")
    is_home: Mapped[bool] = mapped_column(Boolean)
    result: Mapped[str] = mapped_column(String(1))
    points: Mapped[int] = mapped_column(SmallInteger)
    goals_for: Mapped[int] = mapped_column(SmallInteger)
    goals_against: Mapped[int] = mapped_column(SmallInteger)

    possession_pct: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    # Physical tracking is nullable: many sources don't provide it.
    distance_per_90_km: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    sprints_per_min_oop: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    ppda: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    field_tilt_pct: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    line_breaks_per_100_touches: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    box_touches_per_90: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    npxg_created: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    npxg_per_shot: Mapped[Decimal] = mapped_column(Numeric(4, 3))
    finishing_delta: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    npxg_conceded: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    npxga_per_shot_faced: Mapped[Decimal] = mapped_column(Numeric(4, 3))
    gk_goals_prevented: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    raw_metrics: Mapped[dict | None] = mapped_column(JSONB)  # source totals, for provenance

    # Null until vectorized against a benchmark corridor.
    overall_corridor_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    stack_01_work_rate_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    stack_02_progression_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    stack_03_attacking_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    stack_04_defensive_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    verdict_badge: Mapped[str | None] = mapped_column(String(32))
    stats_vector = mapped_column(HALFVEC(N_DIMS))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PlayerMatchPerformance(Base):
    __tablename__ = "player_match_performances"
    __table_args__ = (
        UniqueConstraint("match_id", "player_external_id"),
        Index("idx_player_perf_match_team", "match_id", "team_id"),
        Index("idx_player_perf_position_kickoff", "position_group", "kickoff_utc"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    kickoff_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    player_external_id: Mapped[str] = mapped_column(String(64))
    player_name: Mapped[str] = mapped_column(String(120))
    position_group: Mapped[str] = mapped_column(String(8))  # FWD, MID, FB, CB, GK
    minutes_played: Mapped[int] = mapped_column(SmallInteger)

    distance_per_90_km: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    sprints_per_90: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    top_speed_kmh: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    ball_recoveries_per_90: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    duels_contested_per_90: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    final_third_regains_per_90: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    line_breaking_actions_per_90: Mapped[Decimal] = mapped_column(Numeric(4, 1))

    effort_corridor_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    audit_status: Mapped[str | None] = mapped_column(String(24))


class MatchAuditSnapshot(Base):
    __tablename__ = "match_audit_snapshots"

    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True
    )
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), primary_key=True)
    pass_number: Mapped[int] = mapped_column(SmallInteger, server_default="1")
    schema_version: Mapped[str] = mapped_column(String(16))
    json_url: Mapped[str | None] = mapped_column(Text)
    receipt_png_url: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
