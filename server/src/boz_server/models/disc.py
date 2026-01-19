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


class Title(BaseModel):
    """A title (movie/episode) on a disc."""

    index: int
    name: str
    duration_seconds: int
    size_bytes: int
    chapters: int = 0
    selected: bool = False  # Whether to rip this title

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

    @property
    def main_feature(self) -> Optional[Title]:
        """Get the likely main feature (longest title)."""
        if not self.titles:
            return None
        return max(self.titles, key=lambda t: t.duration_seconds)
