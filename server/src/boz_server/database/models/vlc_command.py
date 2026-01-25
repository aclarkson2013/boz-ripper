"""VLC command ORM model."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class VLCCommandORM(Base):
    """ORM model for vlc_commands table.

    Stores VLC preview commands queued by the server for agents to execute.
    Uses polling model - agent fetches pending commands on each poll cycle.
    """

    __tablename__ = "vlc_commands"

    # Primary key
    command_id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Target agent
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Command details
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    fullscreen: Mapped[bool] = mapped_column(default=True)

    # Status tracking
    # pending: Waiting for agent to pick up
    # sent: Agent received command
    # completed: VLC launched successfully
    # failed: Error launching VLC
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    sent_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
