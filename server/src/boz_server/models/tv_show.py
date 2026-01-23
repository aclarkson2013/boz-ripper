"""TV show models for tracking seasons across discs."""

from typing import Optional

from pydantic import BaseModel, Field


class TVEpisode(BaseModel):
    """An episode from TheTVDB."""

    episode_number: int
    episode_name: str
    season_number: int
    runtime: Optional[int] = None  # Duration in minutes
    overview: Optional[str] = None


class TVSeason(BaseModel):
    """Tracks a TV season state across multiple discs."""

    season_id: str  # Format: "{show_name}:s{season_number}"
    show_name: str
    season_number: int
    thetvdb_series_id: Optional[int] = None

    # Episode tracking
    episodes: list[TVEpisode] = Field(default_factory=list)
    last_episode_assigned: int = 0  # Last episode number assigned to a disc

    # Multi-disc tracking
    disc_ids: list[str] = Field(default_factory=list)  # All discs for this season
    last_disc_name: Optional[str] = None  # Track last disc name to detect re-insertions

    @property
    def next_episode_number(self) -> int:
        """Get the next episode number to assign."""
        return self.last_episode_assigned + 1

    def mark_episode_assigned(self, episode_number: int) -> None:
        """Mark an episode as assigned to a disc."""
        if episode_number > self.last_episode_assigned:
            self.last_episode_assigned = episode_number

    def get_episode(self, episode_number: int) -> Optional[TVEpisode]:
        """Get episode metadata by number."""
        for episode in self.episodes:
            if episode.episode_number == episode_number:
                return episode
        return None
