"""Media file naming for Plex compatibility."""

import logging
import re
from pathlib import Path
from typing import Optional

from ..models.disc import MediaType, Title

logger = logging.getLogger(__name__)


class MediaNamer:
    """Generates Plex-compatible filenames and paths."""

    def __init__(self, base_path: str = "/data/output"):
        """
        Initialize media namer.

        Args:
            base_path: Base output directory
        """
        self.base_path = Path(base_path)

    @staticmethod
    def sanitize_filename(name: str) -> str:
        """
        Sanitize filename by removing invalid characters.

        Args:
            name: Raw filename

        Returns:
            Sanitized filename safe for filesystem
        """
        # Replace invalid characters
        sanitized = re.sub(r'[<>:"/\\|?*]', "", name)
        # Replace multiple spaces with single space
        sanitized = re.sub(r"\s+", " ", sanitized)
        # Trim whitespace
        sanitized = sanitized.strip()
        return sanitized

    def generate_tv_filename(
        self,
        show_name: str,
        season_number: int,
        episode_number: int,
        episode_title: Optional[str] = None,
    ) -> str:
        """
        Generate TV show filename following Plex conventions.

        Format: ShowName - S01E01 - EpisodeTitle.mkv

        Args:
            show_name: Name of the show
            season_number: Season number
            episode_number: Episode number
            episode_title: Optional episode title

        Returns:
            Filename (not including path)
        """
        sanitized_show = self.sanitize_filename(show_name)
        season_ep = f"S{season_number:02d}E{episode_number:02d}"

        if episode_title:
            sanitized_title = self.sanitize_filename(episode_title)
            filename = f"{sanitized_show} - {season_ep} - {sanitized_title}.mkv"
        else:
            filename = f"{sanitized_show} - {season_ep}.mkv"

        return filename

    def generate_tv_path(
        self,
        show_name: str,
        season_number: int,
        episode_number: int,
        episode_title: Optional[str] = None,
    ) -> str:
        """
        Generate full TV show path following Plex conventions.

        Format: /ShowName/Season 01/ShowName - S01E01 - EpisodeTitle.mkv

        Args:
            show_name: Name of the show
            season_number: Season number
            episode_number: Episode number
            episode_title: Optional episode title

        Returns:
            Full path relative to base output directory
        """
        sanitized_show = self.sanitize_filename(show_name)
        season_folder = f"Season {season_number:02d}"

        filename = self.generate_tv_filename(show_name, season_number, episode_number, episode_title)

        path = self.base_path / sanitized_show / season_folder / filename
        return str(path)

    def generate_movie_filename(self, movie_name: str, year: Optional[int] = None) -> str:
        """
        Generate movie filename following Plex conventions.

        Format: MovieName (Year).mkv

        Args:
            movie_name: Name of the movie
            year: Optional release year

        Returns:
            Filename (not including path)
        """
        sanitized_name = self.sanitize_filename(movie_name)

        if year:
            filename = f"{sanitized_name} ({year}).mkv"
        else:
            filename = f"{sanitized_name}.mkv"

        return filename

    def generate_movie_path(self, movie_name: str, year: Optional[int] = None) -> str:
        """
        Generate full movie path following Plex conventions.

        Format: /MovieName (Year)/MovieName (Year).mkv

        Args:
            movie_name: Name of the movie
            year: Optional release year

        Returns:
            Full path relative to base output directory
        """
        sanitized_name = self.sanitize_filename(movie_name)

        if year:
            folder_name = f"{sanitized_name} ({year})"
        else:
            folder_name = sanitized_name

        filename = self.generate_movie_filename(movie_name, year)

        path = self.base_path / folder_name / filename
        return str(path)

    def generate_extra_path(
        self,
        media_name: str,
        extra_name: str,
        media_type: MediaType = MediaType.MOVIE,
        year: Optional[int] = None,
        season_number: Optional[int] = None,
    ) -> str:
        """
        Generate path for extra/bonus content.

        Format:
        - Movie: /MovieName (Year)/Extras/extra_name.mkv
        - TV: /ShowName/Season 01/Extras/extra_name.mkv

        Args:
            media_name: Name of the movie or show
            extra_name: Name of the extra content
            media_type: Type of media
            year: Optional year (for movies)
            season_number: Optional season number (for TV)

        Returns:
            Full path relative to base output directory
        """
        sanitized_media = self.sanitize_filename(media_name)
        sanitized_extra = self.sanitize_filename(extra_name)

        if media_type == MediaType.TV_SHOW and season_number is not None:
            season_folder = f"Season {season_number:02d}"
            path = self.base_path / sanitized_media / season_folder / "Extras" / f"{sanitized_extra}.mkv"
        else:
            # Movie
            if year:
                folder_name = f"{sanitized_media} ({year})"
            else:
                folder_name = sanitized_media
            path = self.base_path / folder_name / "Extras" / f"{sanitized_extra}.mkv"

        return str(path)

    def apply_naming(
        self,
        title: Title,
        media_type: MediaType,
        show_name: Optional[str] = None,
        season_number: Optional[int] = None,
        movie_name: Optional[str] = None,
        year: Optional[int] = None,
    ) -> Title:
        """
        Apply naming to a title based on media type.

        Args:
            title: Title to name
            media_type: Type of media
            show_name: Show name (for TV)
            season_number: Season number (for TV)
            movie_name: Movie name (for movies)
            year: Release year (for movies)

        Returns:
            Title with proposed_filename and proposed_path set
        """
        if title.is_extra:
            # Generate extra path
            if media_type == MediaType.TV_SHOW and show_name and season_number:
                title.proposed_path = self.generate_extra_path(
                    show_name, title.name, media_type, season_number=season_number
                )
            elif movie_name:
                title.proposed_path = self.generate_extra_path(movie_name, title.name, media_type, year=year)
            else:
                title.proposed_path = self.generate_extra_path("Unknown", title.name, media_type)

            title.proposed_filename = Path(title.proposed_path).name

        elif media_type == MediaType.TV_SHOW:
            # Generate TV episode path
            if show_name and season_number and title.episode_number:
                title.proposed_path = self.generate_tv_path(
                    show_name, season_number, title.episode_number, title.episode_title
                )
                title.proposed_filename = Path(title.proposed_path).name
            else:
                logger.warning(f"Missing TV show metadata for title {title.index}")

        elif media_type == MediaType.MOVIE:
            # Generate movie path
            if movie_name:
                title.proposed_path = self.generate_movie_path(movie_name, year)
                title.proposed_filename = Path(title.proposed_path).name
            else:
                logger.warning(f"Missing movie metadata for title {title.index}")

        return title
