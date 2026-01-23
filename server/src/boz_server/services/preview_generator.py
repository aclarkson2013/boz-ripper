"""Preview generation orchestrator."""

import logging
from typing import Dict, Optional

from ..core.config import settings
from ..models.disc import Disc, MediaType, PreviewStatus
from ..models.tv_show import TVSeason
from .episode_matcher import EpisodeMatcher
from .extras_filter import ExtrasFilter
from .media_namer import MediaNamer
from .thetvdb_client import TheTVDBClient
from .tv_detector import TVShowDetector

logger = logging.getLogger(__name__)


class PreviewGenerator:
    """Orchestrates preview generation for detected discs."""

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

        # In-memory storage for TV season tracking
        # Key: "{show_name}:s{season_number}" -> TVSeason
        self._tv_seasons: Dict[str, TVSeason] = {}

    def get_or_create_season(self, show_name: str, season_number: int) -> TVSeason:
        """
        Get or create TV season tracking object.

        Args:
            show_name: Show name
            season_number: Season number

        Returns:
            TVSeason object for tracking episodes across discs
        """
        normalized_name = TVShowDetector.normalize_show_name(show_name)
        season_id = f"{normalized_name}:s{season_number}"

        if season_id not in self._tv_seasons:
            logger.info(f"Creating new TV season tracker: {season_id}")
            self._tv_seasons[season_id] = TVSeason(
                season_id=season_id,
                show_name=normalized_name,
                season_number=season_number,
            )

        return self._tv_seasons[season_id]

    async def generate_preview(self, disc: Disc) -> Disc:
        """
        Generate preview for a detected disc.

        This orchestrates:
        1. TV show detection
        2. TheTVDB metadata lookup (if TV show)
        3. Extras filtering
        4. Episode matching (if TV show)
        5. Filename generation

        Args:
            disc: Detected disc

        Returns:
            Disc with preview data populated
        """
        logger.info(f"========================================")
        logger.info(f"PREVIEW GENERATION START")
        logger.info(f"Disc: {disc.disc_name} (ID: {disc.disc_id})")
        logger.info(f"Titles: {len(disc.titles)}")
        logger.info(f"========================================")

        try:
            # Step 1: Detect if this is a TV show
            logger.info(f"STEP 1: TV Show Detection")
            is_tv, show_name, season_number = self.tv_detector.detect(disc.disc_name)
            logger.info(f"Result: is_tv={is_tv}, show_name={show_name}, season={season_number}")

            if is_tv and show_name and season_number:
                logger.info(f"✓ Detected TV show: {show_name}, Season {season_number}")
                disc.media_type = MediaType.TV_SHOW
                disc.tv_show_name = show_name
                disc.tv_season_number = season_number

                # Get or create season tracker
                tv_season = self.get_or_create_season(show_name, season_number)
                disc.tv_season_id = tv_season.season_id
                tv_season.disc_ids.append(disc.disc_id)
                logger.info(f"Season tracker: {tv_season.season_id} (last_episode: {tv_season.last_episode_assigned})")

                # Step 2: Query TheTVDB for episode metadata (if client available)
                logger.info(f"STEP 2: TheTVDB Metadata Lookup")
                if self.thetvdb_client and not tv_season.episodes:
                    logger.info(f"Searching TheTVDB for series: '{show_name}'")
                    series_id = await self.thetvdb_client.search_series(show_name)

                    if series_id:
                        logger.info(f"✓ Found series on TheTVDB - ID: {series_id}")
                        disc.thetvdb_series_id = series_id
                        tv_season.thetvdb_series_id = series_id

                        logger.info(f"Fetching episodes for season {season_number}")
                        episodes = await self.thetvdb_client.get_season_episodes(series_id, season_number)
                        tv_season.episodes = episodes
                        logger.info(f"✓ Loaded {len(episodes)} episodes from TheTVDB")
                        for ep in episodes[:5]:  # Log first 5 episodes
                            logger.info(f"  Episode {ep.episode_number}: {ep.episode_name} ({ep.runtime}min)")
                    else:
                        logger.warning(f"✗ Could not find series on TheTVDB: {show_name}")
                elif tv_season.episodes:
                    logger.info(f"Using cached episodes ({len(tv_season.episodes)} episodes)")
                else:
                    logger.warning("TheTVDB client not configured, skipping metadata lookup")

                # Step 3: Filter extras
                logger.info(f"STEP 3: Extras Filtering")
                logger.info(f"Analyzing {len(disc.titles)} titles")
                self.extras_filter.filter_extras(disc.titles)
                extras_count = sum(1 for t in disc.titles if t.is_extra)
                logger.info(f"✓ Identified {extras_count} extras, {len(disc.titles) - extras_count} main titles")

                # Step 4: Match episodes
                logger.info(f"STEP 4: Episode Matching")
                main_titles = self.extras_filter.get_main_titles(disc.titles)
                if main_titles:
                    logger.info(f"Matching {len(main_titles)} main titles to episodes")
                    self.episode_matcher.match_episodes(main_titles, tv_season)
                    logger.info(f"✓ Episode matching complete")
                    for title in main_titles[:5]:  # Log first 5
                        logger.info(f"  Title {title.index} → Episode {title.episode_number}: {title.episode_title} (confidence: {title.confidence_score:.2f})")
                else:
                    logger.warning("No main titles found for episode matching")

                # Step 5: Generate filenames
                logger.info(f"STEP 5: Filename Generation")
                for title in disc.titles:
                    self.media_namer.apply_naming(
                        title,
                        MediaType.TV_SHOW,
                        show_name=show_name,
                        season_number=season_number,
                    )
                logger.info(f"✓ Generated filenames for {len(disc.titles)} titles")

            else:
                # Assume movie
                logger.info(f"✓ Detected as movie: {disc.disc_name}")
                disc.media_type = MediaType.MOVIE

                # Step 3: Filter extras
                logger.info(f"STEP 3: Extras Filtering (Movie)")
                logger.info(f"Analyzing {len(disc.titles)} titles")
                self.extras_filter.filter_extras(disc.titles)
                extras_count = sum(1 for t in disc.titles if t.is_extra)
                logger.info(f"✓ Identified {extras_count} extras, {len(disc.titles) - extras_count} main titles")

                # Step 5: Generate filenames (use disc name as movie name)
                logger.info(f"STEP 5: Filename Generation (Movie)")
                movie_name = disc.disc_name
                # Try to extract year from disc name (e.g., "Movie Name (2023)")
                import re

                year_match = re.search(r"\((\d{4})\)", disc.disc_name)
                year = int(year_match.group(1)) if year_match else None

                if year_match:
                    # Remove year from movie name
                    movie_name = disc.disc_name[: year_match.start()].strip()
                    logger.info(f"Extracted movie name: '{movie_name}' ({year})")
                else:
                    logger.info(f"No year found in disc name, using: '{movie_name}'")

                for title in disc.titles:
                    self.media_namer.apply_naming(
                        title,
                        MediaType.MOVIE,
                        movie_name=movie_name,
                        year=year,
                    )
                logger.info(f"✓ Generated filenames for {len(disc.titles)} titles")

            # Set preview status
            if settings.auto_approve_previews:
                disc.preview_status = PreviewStatus.APPROVED
                logger.info("✓ Auto-approved preview (auto_approve_previews enabled)")
            else:
                disc.preview_status = PreviewStatus.PENDING
                logger.info("✓ Preview generated, awaiting user approval")

            logger.info(f"========================================")
            logger.info(f"PREVIEW GENERATION COMPLETE")
            logger.info(f"Media Type: {disc.media_type}")
            logger.info(f"Preview Status: {disc.preview_status}")
            if disc.tv_show_name:
                logger.info(f"TV Show: {disc.tv_show_name} S{disc.tv_season_number:02d}")
            logger.info(f"========================================")
            return disc

        except Exception as e:
            logger.error(f"========================================")
            logger.error(f"PREVIEW GENERATION FAILED")
            logger.error(f"Disc: {disc.disc_name}")
            logger.error(f"Error: {e}", exc_info=True)
            logger.error(f"========================================")
            # Set media type to unknown and pending status
            disc.media_type = MediaType.UNKNOWN
            disc.preview_status = PreviewStatus.PENDING
            return disc

    def clear_season_cache(self, season_id: Optional[str] = None) -> None:
        """
        Clear TV season cache.

        Args:
            season_id: Specific season ID to clear, or None to clear all
        """
        if season_id:
            if season_id in self._tv_seasons:
                del self._tv_seasons[season_id]
                logger.info(f"Cleared season cache for: {season_id}")
        else:
            self._tv_seasons.clear()
            logger.info("Cleared all season caches")

    def get_season(self, season_id: str) -> Optional[TVSeason]:
        """
        Get TV season tracking object by ID.

        Args:
            season_id: Season ID

        Returns:
            TVSeason if found, None otherwise
        """
        return self._tv_seasons.get(season_id)
