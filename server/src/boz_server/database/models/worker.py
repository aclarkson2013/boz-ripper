"""Worker ORM model."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class WorkerORM(Base):
    """ORM model for workers table."""

    __tablename__ = "workers"

    # Primary key
    worker_id: Mapped[str] = mapped_column(String(100), primary_key=True)

    # Basic info
    worker_type: Mapped[str] = mapped_column(String(20), nullable=False)
    hostname: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)

    # Capabilities (stored as JSON string)
    capabilities: Mapped[str] = mapped_column(Text, nullable=False)

    # Priority and status
    priority: Mapped[int] = mapped_column(Integer, default=50, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(
        String(20), default="available", index=True
    )  # available, busy, offline

    # Current work (stored as JSON array string)
    current_jobs: Mapped[str] = mapped_column(Text, default="[]")

    # Health tracking
    last_heartbeat: Mapped[datetime] = mapped_column(default=func.now())
    registered_at: Mapped[datetime] = mapped_column(default=func.now())

    # Stats
    total_jobs_completed: Mapped[int] = mapped_column(Integer, default=0)
    avg_transcode_time_seconds: Mapped[float] = mapped_column(Float, default=0.0)

    # Resource usage
    cpu_usage: Mapped[Optional[float]] = mapped_column(Float)
    gpu_usage: Mapped[Optional[float]] = mapped_column(Float)
