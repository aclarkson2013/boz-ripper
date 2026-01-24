"""Job ORM model."""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class JobORM(Base):
    """ORM model for jobs table."""

    __tablename__ = "jobs"

    # Primary key
    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Job info
    job_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)

    # Source info
    disc_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    title_index: Mapped[Optional[int]] = mapped_column(Integer)
    input_file: Mapped[Optional[str]] = mapped_column(String(512))

    # Output info
    output_name: Mapped[Optional[str]] = mapped_column(String(255))
    output_file: Mapped[Optional[str]] = mapped_column(String(512))
    preset: Mapped[Optional[str]] = mapped_column(String(100))

    # Assignment
    assigned_agent_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    assigned_at: Mapped[Optional[datetime]] = mapped_column()

    # Approval workflow
    requires_approval: Mapped[bool] = mapped_column(default=False, index=True)
    source_disc_name: Mapped[Optional[str]] = mapped_column(String(255))
    input_file_size: Mapped[Optional[int]] = mapped_column(BigInteger)

    # Progress tracking
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    started_at: Mapped[Optional[datetime]] = mapped_column()
    completed_at: Mapped[Optional[datetime]] = mapped_column()
