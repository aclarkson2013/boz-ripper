"""Add VLC preview support.

Revision ID: 002
Revises: 001
Create Date: 2026-01-25

This migration adds VLC preview support:
- vlc_commands table for queuing preview commands to agents
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create vlc_commands table
    op.create_table(
        "vlc_commands",
        sa.Column("command_id", sa.String(36), primary_key=True),
        sa.Column("agent_id", sa.String(100), nullable=False, index=True),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("fullscreen", sa.Boolean, default=True),
        sa.Column("status", sa.String(20), nullable=False, default="pending", index=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("vlc_commands")
