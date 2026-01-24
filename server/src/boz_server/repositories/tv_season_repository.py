"""TV Season repository for database operations."""

import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database.models.tv_show import TVEpisodeORM, TVSeasonORM
from ..models.tv_show import TVEpisode, TVSeason
from .base import BaseRepository


class TVSeasonRepository(BaseRepository[TVSeasonORM]):
    """Repository for TV season database operations."""

    def __init__(self, session: AsyncSession):
        """Initialize TV season repository."""
        super().__init__(TVSeasonORM, session)

    async def create_from_pydantic(self, season: TVSeason) -> TVSeasonORM:
        """
        Create TV season from Pydantic model.

        Args:
            season: Pydantic TVSeason model

        Returns:
            ORM season instance
        """
        season_orm = TVSeasonORM(
            season_id=season.season_id,
            show_name=season.show_name,
            season_number=season.season_number,
            thetvdb_series_id=season.thetvdb_series_id,
            last_episode_assigned=season.last_episode_assigned,
            disc_ids=json.dumps(season.disc_ids),
            last_disc_name=season.last_disc_name,
        )

        # Create episode ORMs
        for episode in season.episodes:
            episode_orm = TVEpisodeORM(
                season_id=season.season_id,
                episode_number=episode.episode_number,
                episode_name=episode.episode_name,
                season_number=episode.season_number,
                runtime=episode.runtime,
                overview=episode.overview,
            )
            season_orm.episodes.append(episode_orm)

        return await self.create(season_orm)

    async def get_with_episodes(self, season_id: str) -> Optional[TVSeasonORM]:
        """
        Get season with episodes eagerly loaded.

        Args:
            season_id: Season ID

        Returns:
            Season ORM with episodes or None
        """
        result = await self.session.execute(
            select(TVSeasonORM)
            .where(TVSeasonORM.season_id == season_id)
            .options(selectinload(TVSeasonORM.episodes))
        )
        return result.scalar_one_or_none()

    def to_pydantic(self, season_orm: TVSeasonORM) -> TVSeason:
        """
        Convert ORM model to Pydantic model.

        Args:
            season_orm: ORM season instance

        Returns:
            Pydantic TVSeason model
        """
        episodes = [
            TVEpisode(
                episode_number=ep.episode_number,
                episode_name=ep.episode_name,
                season_number=ep.season_number,
                runtime=ep.runtime,
                overview=ep.overview,
            )
            for ep in season_orm.episodes
        ]

        disc_ids = json.loads(season_orm.disc_ids)

        return TVSeason(
            season_id=season_orm.season_id,
            show_name=season_orm.show_name,
            season_number=season_orm.season_number,
            thetvdb_series_id=season_orm.thetvdb_series_id,
            episodes=episodes,
            last_episode_assigned=season_orm.last_episode_assigned,
            disc_ids=disc_ids,
            last_disc_name=season_orm.last_disc_name,
        )

    async def get_or_create(
        self, show_name: str, season_number: int
    ) -> TVSeason:
        """
        Get existing season or create new one.

        Args:
            show_name: Show name
            season_number: Season number

        Returns:
            TVSeason instance
        """
        season_id = f"{show_name}:s{season_number}"
        season_orm = await self.get_with_episodes(season_id)

        if season_orm:
            return self.to_pydantic(season_orm)
        else:
            # Create new season
            season = TVSeason(
                season_id=season_id,
                show_name=show_name,
                season_number=season_number,
            )
            season_orm = await self.create_from_pydantic(season)
            return self.to_pydantic(season_orm)

    async def update_last_episode_assigned(
        self, season_id: str, episode_number: int
    ) -> Optional[TVSeason]:
        """
        Update last episode assigned.

        Args:
            season_id: Season ID
            episode_number: Episode number

        Returns:
            Updated season or None if not found
        """
        season_orm = await self.get_with_episodes(season_id)
        if not season_orm:
            return None

        if episode_number > season_orm.last_episode_assigned:
            season_orm.last_episode_assigned = episode_number

        await self.session.flush()
        await self.session.refresh(season_orm)
        return self.to_pydantic(season_orm)

    async def add_disc(
        self, season_id: str, disc_id: str, disc_name: str
    ) -> Optional[TVSeason]:
        """
        Add disc to season tracking.

        Args:
            season_id: Season ID
            disc_id: Disc ID
            disc_name: Disc name

        Returns:
            Updated season or None if not found
        """
        season_orm = await self.get_with_episodes(season_id)
        if not season_orm:
            return None

        disc_ids = json.loads(season_orm.disc_ids)
        if disc_id not in disc_ids:
            disc_ids.append(disc_id)
            season_orm.disc_ids = json.dumps(disc_ids)

        season_orm.last_disc_name = disc_name

        await self.session.flush()
        await self.session.refresh(season_orm)
        return self.to_pydantic(season_orm)

    async def set_episodes(
        self, season_id: str, episodes: list[TVEpisode], thetvdb_series_id: Optional[int] = None
    ) -> Optional[TVSeason]:
        """
        Set episodes for a season (replaces existing).

        Args:
            season_id: Season ID
            episodes: List of episodes
            thetvdb_series_id: Optional TheTVDB series ID

        Returns:
            Updated season or None if not found
        """
        season_orm = await self.get_with_episodes(season_id)
        if not season_orm:
            return None

        # Remove existing episodes
        season_orm.episodes = []

        # Add new episodes
        for episode in episodes:
            episode_orm = TVEpisodeORM(
                season_id=season_id,
                episode_number=episode.episode_number,
                episode_name=episode.episode_name,
                season_number=episode.season_number,
                runtime=episode.runtime,
                overview=episode.overview,
            )
            season_orm.episodes.append(episode_orm)

        if thetvdb_series_id:
            season_orm.thetvdb_series_id = thetvdb_series_id

        await self.session.flush()
        await self.session.refresh(season_orm)
        return self.to_pydantic(season_orm)

    async def get_by_show_and_season(
        self, show_name: str, season_number: int
    ) -> Optional[TVSeason]:
        """
        Get season by show name and season number.

        Args:
            show_name: Show name
            season_number: Season number

        Returns:
            TVSeason or None
        """
        result = await self.session.execute(
            select(TVSeasonORM)
            .where(TVSeasonORM.show_name == show_name)
            .where(TVSeasonORM.season_number == season_number)
            .options(selectinload(TVSeasonORM.episodes))
        )
        season_orm = result.scalar_one_or_none()
        return self.to_pydantic(season_orm) if season_orm else None
