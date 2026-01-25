"""Initial database schema.

Revision ID: 001
Revises:
Create Date: 2026-01-25

This migration creates all initial tables for the Boz Ripper database.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create agents table
    op.create_table(
        "agents",
        sa.Column("agent_id", sa.String(100), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), default="online", index=True),
        sa.Column("capabilities", sa.Text, nullable=False),
        sa.Column("current_job_id", sa.String(36), nullable=True),
        sa.Column("last_heartbeat", sa.DateTime, server_default=sa.func.now()),
        sa.Column("registered_at", sa.DateTime, server_default=sa.func.now()),
    )

    # Create workers table
    op.create_table(
        "workers",
        sa.Column("worker_id", sa.String(100), primary_key=True),
        sa.Column("worker_type", sa.String(20), nullable=False),
        sa.Column("hostname", sa.String(100), nullable=False),
        sa.Column("agent_id", sa.String(100), nullable=True, index=True),
        sa.Column("capabilities", sa.Text, nullable=False),
        sa.Column("priority", sa.Integer, default=50, index=True),
        sa.Column("enabled", sa.Boolean, default=True),
        sa.Column("status", sa.String(20), default="available", index=True),
        sa.Column("current_jobs", sa.Text, default="[]"),
        sa.Column("last_heartbeat", sa.DateTime, server_default=sa.func.now()),
        sa.Column("registered_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("total_jobs_completed", sa.Integer, default=0),
        sa.Column("avg_transcode_time_seconds", sa.Float, default=0.0),
        sa.Column("cpu_usage", sa.Float, nullable=True),
        sa.Column("gpu_usage", sa.Float, nullable=True),
    )

    # Create discs table
    op.create_table(
        "discs",
        sa.Column("disc_id", sa.String(36), primary_key=True),
        sa.Column("agent_id", sa.String(100), nullable=False, index=True),
        sa.Column("drive", sa.String(10), nullable=False),
        sa.Column("disc_name", sa.String(255), nullable=False),
        sa.Column("disc_type", sa.String(20), default="Unknown"),
        sa.Column("detected_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("status", sa.String(20), default="detected", index=True),
        sa.Column("media_type", sa.String(20), default="unknown"),
        sa.Column("preview_status", sa.String(20), default="pending", index=True),
        # TV show fields
        sa.Column("tv_show_name", sa.String(255), nullable=True),
        sa.Column("tv_season_number", sa.Integer, nullable=True),
        sa.Column("tv_season_id", sa.String(100), nullable=True, index=True),
        sa.Column("thetvdb_series_id", sa.Integer, nullable=True),
        sa.Column("starting_episode_number", sa.Integer, nullable=True),
        # Movie fields
        sa.Column("movie_title", sa.String(255), nullable=True),
        sa.Column("movie_year", sa.Integer, nullable=True),
        sa.Column("omdb_imdb_id", sa.String(20), nullable=True),
        sa.Column("movie_confidence", sa.Float, default=0.0),
    )

    # Create titles table
    op.create_table(
        "titles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "disc_id",
            sa.String(36),
            sa.ForeignKey("discs.disc_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("title_index", sa.Integer, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("duration_seconds", sa.Integer, nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("chapters", sa.Integer, default=0),
        sa.Column("selected", sa.Boolean, default=False, index=True),
        sa.Column("is_extra", sa.Boolean, default=False),
        sa.Column("proposed_filename", sa.String(255), nullable=True),
        sa.Column("proposed_path", sa.String(512), nullable=True),
        sa.Column("episode_number", sa.Integer, nullable=True),
        sa.Column("episode_title", sa.String(255), nullable=True),
        sa.Column("confidence_score", sa.Float, default=0.0),
    )

    # Create jobs table
    op.create_table(
        "jobs",
        sa.Column("job_id", sa.String(36), primary_key=True),
        sa.Column("job_type", sa.String(20), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("priority", sa.Integer, default=0),
        sa.Column("disc_id", sa.String(36), nullable=True, index=True),
        sa.Column("title_index", sa.Integer, nullable=True),
        sa.Column("input_file", sa.String(512), nullable=True),
        sa.Column("output_name", sa.String(255), nullable=True),
        sa.Column("output_file", sa.String(512), nullable=True),
        sa.Column("preset", sa.String(100), nullable=True),
        sa.Column("assigned_agent_id", sa.String(100), nullable=True, index=True),
        sa.Column("assigned_at", sa.DateTime, nullable=True),
        sa.Column("requires_approval", sa.Boolean, default=False, index=True),
        sa.Column("source_disc_name", sa.String(255), nullable=True),
        sa.Column("input_file_size", sa.BigInteger, nullable=True),
        sa.Column("thumbnails_json", sa.Text, nullable=True),
        sa.Column("thumbnail_timestamps_json", sa.Text, nullable=True),
        sa.Column("progress", sa.Float, default=0.0),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )

    # Create tv_seasons table
    op.create_table(
        "tv_seasons",
        sa.Column("season_id", sa.String(100), primary_key=True),
        sa.Column("show_name", sa.String(255), nullable=False, index=True),
        sa.Column("season_number", sa.Integer, nullable=False),
        sa.Column("thetvdb_series_id", sa.Integer, nullable=True),
        sa.Column("last_episode_assigned", sa.Integer, default=0),
        sa.Column("disc_ids", sa.Text, default="[]"),
        sa.Column("last_disc_name", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # Create tv_episodes table
    op.create_table(
        "tv_episodes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "season_id",
            sa.String(100),
            sa.ForeignKey("tv_seasons.season_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("episode_number", sa.Integer, nullable=False),
        sa.Column("episode_name", sa.String(255), nullable=False),
        sa.Column("season_number", sa.Integer, nullable=False),
        sa.Column("runtime", sa.Integer, nullable=True),
        sa.Column("overview", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("tv_episodes")
    op.drop_table("tv_seasons")
    op.drop_table("jobs")
    op.drop_table("titles")
    op.drop_table("discs")
    op.drop_table("workers")
    op.drop_table("agents")
