"""Disc and title models."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DiscType(str, Enum):
    """Type of disc."""

    DVD = "DVD"
    BLURAY = "Blu-ray"
    UNKNOWN = "Unknown"


class MediaType(str, Enum):
    """Type of media content."""

    MOVIE = "movie"
    TV_SHOW = "tv_show"
    UNKNOWN = "unknown"


class PreviewStatus(str, Enum):
    """Preview/approval status for disc."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Title(BaseModel):
    """A title (movie/episode) on a disc."""

    index: int
    name: str
    duration_seconds: int
    size_bytes: int
    chapters: int = 0
    selected: bool = False  # Whether to rip this title

    # Preview/approval fields
    is_extra: bool = False  # Detected as bonus content
    proposed_filename: Optional[str] = None  # Generated filename
    proposed_path: Optional[str] = None  # Full path including directory structure
    episode_number: Optional[int] = None  # For TV shows
    episode_title: Optional[str] = None  # Episode name from TheTVDB
    confidence_score: float = 0.0  # Matching confidence (0-1)

    @property
    def duration_formatted(self) -> str:
        """Return duration as HH:MM:SS."""
        hours, remainder = divmod(self.duration_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class DiscDetected(BaseModel):
    """Request when agent detects a disc."""

    agent_id: str
    drive: str
    disc_name: str
    disc_type: str
    titles: list[Title] = Field(default_factory=list)


class DiscEjected(BaseModel):
    """Request when agent ejects a disc."""

    agent_id: str
    drive: str


class Disc(BaseModel):
    """A detected disc in the system."""

    disc_id: str
    agent_id: str
    drive: str
    disc_name: str
    disc_type: DiscType = DiscType.UNKNOWN
    titles: list[Title] = Field(default_factory=list)
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "detected"  # detected, ripping, completed, ejected

    # Preview/approval fields
    media_type: MediaType = MediaType.UNKNOWN
    preview_status: PreviewStatus = PreviewStatus.PENDING

    # TV show fields
    tv_show_name: Optional[str] = None
    tv_season_number: Optional[int] = None
    tv_season_id: Optional[str] = None  # Internal tracking ID for multi-disc seasons
    thetvdb_series_id: Optional[int] = None
    starting_episode_number: Optional[int] = None  # Episode number to start from (overrides auto-continuation)

    @property
    def main_feature(self) -> Optional[Title]:
        """Get the likely main feature (longest title)."""
        if not self.titles:
            return None
        return max(self.titles, key=lambda t: t.duration_seconds)
