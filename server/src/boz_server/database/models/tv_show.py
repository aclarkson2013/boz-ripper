"""TV Show ORM models."""

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base


class TVSeasonORM(Base):
    """ORM model for tv_seasons table."""

    __tablename__ = "tv_seasons"

    # Primary key
    season_id: Mapped[str] = mapped_column(String(100), primary_key=True)

    # Basic info
    show_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    season_number: Mapped[int] = mapped_column(Integer, nullable=False)
    thetvdb_series_id: Mapped[Optional[int]] = mapped_column(Integer)

    # Episode tracking
    last_episode_assigned: Mapped[int] = mapped_column(Integer, default=0)

    # Multi-disc tracking (stored as JSON array string)
    disc_ids: Mapped[str] = mapped_column(Text, default="[]")
    last_disc_name: Mapped[Optional[str]] = mapped_column(String(255))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    # Relationship to episodes
    episodes: Mapped[list["TVEpisodeORM"]] = relationship(
        "TVEpisodeORM", back_populates="season", cascade="all, delete-orphan"
    )


class TVEpisodeORM(Base):
    """ORM model for tv_episodes table."""

    __tablename__ = "tv_episodes"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key
    season_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("tv_seasons.season_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Basic info
    episode_number: Mapped[int] = mapped_column(Integer, nullable=False)
    episode_name: Mapped[str] = mapped_column(String(255), nullable=False)
    season_number: Mapped[int] = mapped_column(Integer, nullable=False)
    runtime: Mapped[Optional[int]] = mapped_column(Integer)  # minutes
    overview: Mapped[Optional[str]] = mapped_column(Text)

    # Relationship to season
    season: Mapped["TVSeasonORM"] = relationship("TVSeasonORM", back_populates="episodes")
