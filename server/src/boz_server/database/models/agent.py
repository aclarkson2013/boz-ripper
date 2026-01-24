"""Agent ORM model."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class AgentORM(Base):
    """ORM model for agents table."""

    __tablename__ = "agents"

    # Primary key
    agent_id: Mapped[str] = mapped_column(String(100), primary_key=True)

    # Basic info
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="online", index=True
    )  # online, offline, busy

    # Capabilities (stored as JSON string)
    capabilities: Mapped[str] = mapped_column(Text, nullable=False)

    # Current work
    current_job_id: Mapped[Optional[str]] = mapped_column(String(36))

    # Health tracking
    last_heartbeat: Mapped[datetime] = mapped_column(default=func.now())
    registered_at: Mapped[datetime] = mapped_column(default=func.now())
