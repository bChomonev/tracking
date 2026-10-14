"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-14 14:30:21.688409
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")  # pgvector >= 0.7 for halfvec
    op.create_table(
        "benchmark_corridors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("window_label", sa.String(length=32), nullable=False),
        sa.Column("window_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sample_matches_count", sa.Integer(), nullable=False),
        sa.Column("metric_means", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metric_stds", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metric_weights", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("calibration", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("win_90_ceiling_raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("loss_85_floor_raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("v_best_centroid", pgvector.sqlalchemy.halfvec.HALFVEC(dim=12), nullable=False),
        sa.Column("v_worst_centroid", pgvector.sqlalchemy.halfvec.HALFVEC(dim=12), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("window_label"),
    )
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("short_code", sa.String(length=10), nullable=False),
        sa.Column("league_code", sa.String(length=16), nullable=False),
        sa.Column(
            "elo_rating", sa.Numeric(precision=6, scale=1), server_default="1500.0", nullable=False
        ),
        sa.Column("is_benchmark_cohort", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_id"),
    )
    op.create_table(
        "matches",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("competition_code", sa.String(length=32), nullable=False),
        sa.Column("season", sa.String(length=12), nullable=False),
        sa.Column("kickoff_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("venue", sa.String(length=120), nullable=True),
        sa.Column("audit_status", sa.String(length=24), server_default="SCHEDULED", nullable=False),
        sa.Column("home_team_id", sa.Integer(), nullable=False),
        sa.Column("away_team_id", sa.Integer(), nullable=False),
        sa.Column("home_goals", sa.SmallInteger(), nullable=True),
        sa.Column("away_goals", sa.SmallInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["away_team_id"],
            ["teams.id"],
        ),
        sa.ForeignKeyConstraint(
            ["home_team_id"],
            ["teams.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_id"),
    )
    op.create_index(
        "idx_matches_kickoff_status", "matches", ["kickoff_utc", "audit_status"], unique=False
    )
    op.create_table(
        "match_audit_snapshots",
        sa.Column("match_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("pass_number", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("json_url", sa.Text(), nullable=True),
        sa.Column("receipt_png_url", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
        ),
        sa.PrimaryKeyConstraint("match_id", "team_id"),
    )
    op.create_table(
        "player_match_performances",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("match_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("kickoff_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("player_external_id", sa.String(length=64), nullable=False),
        sa.Column("player_name", sa.String(length=120), nullable=False),
        sa.Column("position_group", sa.String(length=8), nullable=False),
        sa.Column("minutes_played", sa.SmallInteger(), nullable=False),
        sa.Column("distance_per_90_km", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("sprints_per_90", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("top_speed_kmh", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("ball_recoveries_per_90", sa.Numeric(precision=4, scale=1), nullable=False),
        sa.Column("duels_contested_per_90", sa.Numeric(precision=4, scale=1), nullable=False),
        sa.Column("final_third_regains_per_90", sa.Numeric(precision=4, scale=1), nullable=False),
        sa.Column("line_breaking_actions_per_90", sa.Numeric(precision=4, scale=1), nullable=False),
        sa.Column("effort_corridor_score", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("audit_status", sa.String(length=24), nullable=True),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "player_external_id"),
    )
    op.create_index(
        "idx_player_perf_match_team",
        "player_match_performances",
        ["match_id", "team_id"],
        unique=False,
    )
    op.create_index(
        "idx_player_perf_position_kickoff",
        "player_match_performances",
        ["position_group", "kickoff_utc"],
        unique=False,
    )
    op.create_table(
        "team_match_performances",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("match_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("opponent_id", sa.Integer(), nullable=False),
        sa.Column("corridor_version_id", sa.Integer(), nullable=True),
        sa.Column("kickoff_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("competition_tier", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("is_home", sa.Boolean(), nullable=False),
        sa.Column("result", sa.String(length=1), nullable=False),
        sa.Column("points", sa.SmallInteger(), nullable=False),
        sa.Column("goals_for", sa.SmallInteger(), nullable=False),
        sa.Column("goals_against", sa.SmallInteger(), nullable=False),
        sa.Column("possession_pct", sa.Numeric(precision=4, scale=1), nullable=False),
        sa.Column("distance_per_90_km", sa.Numeric(precision=5, scale=1), nullable=True),
        sa.Column("sprints_per_min_oop", sa.Numeric(precision=4, scale=2), nullable=True),
        sa.Column("ppda", sa.Numeric(precision=4, scale=1), nullable=False),
        sa.Column("field_tilt_pct", sa.Numeric(precision=4, scale=1), nullable=False),
        sa.Column("line_breaks_per_100_touches", sa.Numeric(precision=4, scale=2), nullable=False),
        sa.Column("box_touches_per_90", sa.Numeric(precision=4, scale=1), nullable=False),
        sa.Column("npxg_created", sa.Numeric(precision=4, scale=2), nullable=False),
        sa.Column("npxg_per_shot", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("finishing_delta", sa.Numeric(precision=4, scale=2), nullable=False),
        sa.Column("npxg_conceded", sa.Numeric(precision=4, scale=2), nullable=False),
        sa.Column("npxga_per_shot_faced", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("gk_goals_prevented", sa.Numeric(precision=4, scale=2), nullable=False),
        sa.Column("raw_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("overall_corridor_score", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("stack_01_work_rate_score", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("stack_02_progression_score", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("stack_03_attacking_score", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("stack_04_defensive_score", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("verdict_badge", sa.String(length=32), nullable=True),
        sa.Column("stats_vector", pgvector.sqlalchemy.halfvec.HALFVEC(dim=12), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("result IN ('W','D','L')", name="ck_tmp_result"),
        sa.ForeignKeyConstraint(
            ["corridor_version_id"],
            ["benchmark_corridors.id"],
        ),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["opponent_id"],
            ["teams.id"],
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "team_id"),
    )
    op.create_index(
        "idx_team_perf_halfvec_hnsw",
        "team_match_performances",
        ["stats_vector"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"stats_vector": "halfvec_l2_ops"},
    )
    op.create_index(
        "idx_team_perf_team_kickoff",
        "team_match_performances",
        ["team_id", "kickoff_utc"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_team_perf_team_kickoff", table_name="team_match_performances")
    op.drop_index(
        "idx_team_perf_halfvec_hnsw",
        table_name="team_match_performances",
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"stats_vector": "halfvec_l2_ops"},
    )
    op.drop_table("team_match_performances")
    op.drop_index("idx_player_perf_position_kickoff", table_name="player_match_performances")
    op.drop_index("idx_player_perf_match_team", table_name="player_match_performances")
    op.drop_table("player_match_performances")
    op.drop_table("match_audit_snapshots")
    op.drop_index("idx_matches_kickoff_status", table_name="matches")
    op.drop_table("matches")
    op.drop_table("teams")
    op.drop_table("benchmark_corridors")
