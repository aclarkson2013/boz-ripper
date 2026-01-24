"""Disc and Title ORM models."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base


class DiscORM(Base):
    """ORM model for discs table."""

    __tablename__ = "discs"

    # Primary key
    disc_id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Basic info
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    drive: Mapped[str] = mapped_column(String(10), nullable=False)
    disc_name: Mapped[str] = mapped_column(String(255), nullable=False)
    disc_type: Mapped[str] = mapped_column(String(20), default="Unknown")
    detected_at: Mapped[datetime] = mapped_column(default=func.now())
    status: Mapped[str] = mapped_column(
        String(20), default="detected", index=True
    )  # detected, ripping, completed, ejected

    # Preview/approval fields
    media_type: Mapped[str] = mapped_column(String(20), default="unknown")
    preview_status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True
    )

    # TV show fields
    tv_show_name: Mapped[Optional[str]] = mapped_column(String(255))
    tv_season_number: Mapped[Optional[int]] = mapped_column(Integer)
    tv_season_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    thetvdb_series_id: Mapped[Optional[int]] = mapped_column(Integer)
    starting_episode_number: Mapped[Optional[int]] = mapped_column(Integer)

    # Movie fields
    movie_title: Mapped[Optional[str]] = mapped_column(String(255))
    movie_year: Mapped[Optional[int]] = mapped_column(Integer)
    omdb_imdb_id: Mapped[Optional[str]] = mapped_column(String(20))
    movie_confidence: Mapped[float] = mapped_column(Float, default=0.0)

    # Relationship to titles
    titles: Mapped[list["TitleORM"]] = relationship(
        "TitleORM", back_populates="disc", cascade="all, delete-orphan"
    )


class TitleORM(Base):
    """ORM model for titles table."""

    __tablename__ = "titles"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key
    disc_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("discs.disc_id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Basic info
    title_index: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chapters: Mapped[int] = mapped_column(Integer, default=0)
    selected: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Preview/approval fields
    is_extra: Mapped[bool] = mapped_column(Boolean, default=False)
    proposed_filename: Mapped[Optional[str]] = mapped_column(String(255))
    proposed_path: Mapped[Optional[str]] = mapped_column(String(512))
    episode_number: Mapped[Optional[int]] = mapped_column(Integer)
    episode_title: Mapped[Optional[str]] = mapped_column(String(255))
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)

    # Relationship to disc
    disc: Mapped["DiscORM"] = relationship("DiscORM", back_populates="titles")
