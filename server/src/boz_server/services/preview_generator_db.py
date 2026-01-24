"""Database-backed preview generation orchestrator."""

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..database.session import SessionLocal
from ..models.disc import Disc, MediaType, PreviewStatus
from ..models.tv_show import TVSeason
from ..repositories.tv_season_repository import TVSeasonRepository
from .episode_matcher import EpisodeMatcher
from .extras_filter import ExtrasFilter
from .media_namer import MediaNamer
from .thetvdb_client import TheTVDBClient
from .tv_detector import TVShowDetector

logger = logging.getLogger(__name__)


class PreviewGenerator:
    """Orchestrates preview generation for detected discs with database persistence."""

    def __init__(
        self,
        thetvdb_client: Optional[TheTVDBClient] = None,
        output_dir: str = "/data/output",
    ):
        """
        Initialize preview generator.

        Args:
            thetvdb_client: Optional TheTVDB client (None if API key not configured)
            output_dir: Base output directory for media files
        """
        self.thetvdb_client = thetvdb_client
        self.tv_detector = TVShowDetector()
        self.extras_filter = ExtrasFilter(
            min_duration_seconds=settings.extras_min_duration_seconds,
            duration_variance_threshold=settings.extras_duration_variance,
        )
        self.episode_matcher = EpisodeMatcher()
        self.media_namer = MediaNamer(base_path=output_dir)

    async def _get_session(self) -> AsyncSession:
        """Get a new database session."""
        return SessionLocal()

    async def get_or_create_season(
        self, show_name: str, season_number: int
    ) -> TVSeason:
        """
        Get or create TV season tracking object.

        Args:
            show_name: Show name
            season_number: Season number

        Returns:
            TVSeason object for tracking episodes across discs
        """
        normalized_name = TVShowDetector.normalize_show_name(show_name)

        async with await self._get_session() as session:
            repo = TVSeasonRepository(session)
            season = await repo.get_or_create(normalized_name, season_number)
            await session.commit()
            return season

    async def get_season(self, season_id: str) -> Optional[TVSeason]:
        """
        Get TV season by ID.

        Args:
            season_id: Season ID

        Returns:
            TVSeason or None if not found
        """
        async with await self._get_session() as session:
            repo = TVSeasonRepository(session)
            season_orm = await repo.get_with_episodes(season_id)
            return repo.to_pydantic(season_orm) if season_orm else None

    async def update_season_episodes(
        self,
        season_id: str,
        episodes: list,
        thetvdb_series_id: Optional[int] = None,
    ) -> Optional[TVSeason]:
        """
        Update season with episode list from TheTVDB.

        Args:
            season_id: Season ID
            episodes: List of TVEpisode objects
            thetvdb_series_id: TheTVDB series ID

        Returns:
            Updated season or None
        """
        async with await self._get_session() as session:
            repo = TVSeasonRepository(session)
            season = await repo.set_episodes(season_id, episodes, thetvdb_series_id)
            if season:
                await session.commit()
            return season

    async def mark_episode_assigned(
        self, season_id: str, episode_number: int
    ) -> None:
        """
        Mark an episode as assigned.

        Args:
            season_id: Season ID
            episode_number: Episode number
        """
        async with await self._get_session() as session:
            repo = TVSeasonRepository(session)
            await repo.update_last_episode_assigned(season_id, episode_number)
            await session.commit()

    async def add_disc_to_season(
        self, season_id: str, disc_id: str, disc_name: str
    ) -> None:
        """
        Add disc to season tracking.

        Args:
            season_id: Season ID
            disc_id: Disc ID
            disc_name: Disc name
        """
        async with await self._get_session() as session:
            repo = TVSeasonRepository(session)
            await repo.add_disc(season_id, disc_id, disc_name)
            await session.commit()

    async def clear_season_cache(self) -> None:
        """
        Clear TV season cache.

        Note: With database persistence, this is a no-op.
        Kept for API compatibility.
        """
        pass

    async def generate_preview(self, disc: Disc) -> Disc:
        """
        Generate preview for a detected disc.

        This orchestrates:
        1. TV show detection
        2. TheTVDB metadata lookup (if TV show)
        3. Extras filtering
        4. Episode matching (if TV show)
        5. Filename generation
        6. Preview status setting

        Args:
            disc: Detected disc

        Returns:
            Disc with preview data populated
        """
        logger.info(f"Generating preview for disc: {disc.disc_name}")

        # 1. Detect TV show
        is_tv_show, show_name, season_number = self.tv_detector.detect(
            disc.disc_name
        )

        if is_tv_show and show_name and season_number:
            logger.info(
                f"Detected TV show: {show_name} Season {season_number}"
            )
            disc.media_type = MediaType.TV_SHOW
            disc.tv_show_name = show_name
            disc.tv_season_number = season_number

            # Get or create season tracker
            tv_season = await self.get_or_create_season(show_name, season_number)
            disc.tv_season_id = tv_season.season_id

            # 2. Query TheTVDB for metadata (if available)
            if self.thetvdb_client and not tv_season.episodes:
                logger.info(f"Querying TheTVDB for {show_name} S{season_number}")
                try:
                    series_results = await self.thetvdb_client.search_series(
                        show_name
                    )
                    if series_results:
                        series_id = series_results[0]["tvdb_id"]
                        disc.thetvdb_series_id = series_id

                        episodes = await self.thetvdb_client.get_season_episodes(
                            series_id, season_number
                        )

                        if episodes:
                            logger.info(
                                f"Found {len(episodes)} episodes from TheTVDB"
                            )
                            # Update season with episodes
                            await self.update_season_episodes(
                                tv_season.season_id, episodes, series_id
                            )
                            tv_season.episodes = episodes
                            tv_season.thetvdb_series_id = series_id
                except Exception as e:
                    logger.error(f"TheTVDB lookup failed: {e}")

            # Handle re-insertion: Check if this disc was already processed
            if (
                disc.disc_name == tv_season.last_disc_name
                and disc.starting_episode_number is None
            ):
                logger.warning(
                    f"Disc '{disc.disc_name}' appears to be re-inserted. "
                    f"Resetting episode continuation to avoid duplicates."
                )
                disc.starting_episode_number = (
                    tv_season.last_episode_assigned + 1
                )

            # 3. Filter extras
            self.extras_filter.filter_extras(disc.titles)
            main_titles = self.extras_filter.get_main_titles(disc.titles)

            # 4. Match episodes
            if tv_season.episodes:
                # Determine starting episode
                if disc.starting_episode_number:
                    start_episode = disc.starting_episode_number
                else:
                    start_episode = tv_season.next_episode_number

                self.episode_matcher.match_episodes(
                    main_titles, tv_season, start_episode
                )

                # Update last assigned episode
                for title in main_titles:
                    if title.episode_number:
                        await self.mark_episode_assigned(
                            tv_season.season_id, title.episode_number
                        )

            # 5. Generate TV show filenames
            for title in disc.titles:
                if not title.is_extra and title.episode_number:
                    path = self.media_namer.generate_tv_path(
                        show_name,
                        season_number,
                        title.episode_number,
                        title.episode_title or "",
                    )
                    title.proposed_path = path
                    title.proposed_filename = path.split("/")[-1]
                elif title.is_extra:
                    path = self.media_namer.generate_extra_path(
                        show_name, season_number, title.name
                    )
                    title.proposed_path = path
                    title.proposed_filename = path.split("/")[-1]

            # Add disc to season tracking
            await self.add_disc_to_season(
                tv_season.season_id, disc.disc_id, disc.disc_name
            )

        else:
            # Assume movie
            logger.info(f"Detected as movie: {disc.disc_name}")
            disc.media_type = MediaType.MOVIE

            # Filter extras
            self.extras_filter.filter_extras(disc.titles)

            # Generate movie filenames
            movie_name = disc.disc_name
            for title in disc.titles:
                if not title.is_extra:
                    path = self.media_namer.generate_movie_path(movie_name)
                    title.proposed_path = path
                    title.proposed_filename = path.split("/")[-1]
                else:
                    path = self.media_namer.generate_extra_path(
                        movie_name, None, title.name
                    )
                    title.proposed_path = path
                    title.proposed_filename = path.split("/")[-1]

        # Set preview status
        if settings.auto_approve_previews:
            disc.preview_status = PreviewStatus.APPROVED
            disc.titles = [
                title for title in disc.titles if not title.is_extra
            ]
            for title in disc.titles:
                title.selected = True
        else:
            disc.preview_status = PreviewStatus.PENDING

        logger.info(
            f"Preview generated: {len(disc.titles)} titles, "
            f"status={disc.preview_status.value}"
        )

        return disc
