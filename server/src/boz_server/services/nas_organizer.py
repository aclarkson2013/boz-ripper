"""NAS file organization service."""

import asyncio
import logging
import re
import shutil
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from boz_server.core.config import settings

if TYPE_CHECKING:
    from boz_server.services.discord_client import DiscordClient
    from boz_server.services.plex_client import PlexClient

logger = logging.getLogger(__name__)


class NASOrganizer:
    """Organizes completed files to NAS storage."""

    def __init__(
        self,
        plex_client: Optional["PlexClient"] = None,
        discord_client: Optional["DiscordClient"] = None,
    ):
        self._nas_mounted = False
        self._mount_path: Optional[Path] = None
        self._plex_client = plex_client
        self._discord_client = discord_client

    async def start(self) -> None:
        """Initialize NAS connection."""
        if not settings.nas_enabled:
            logger.info("NAS organization disabled")
            return

        # For Docker, NAS should be mounted as a volume
        # Check if the mount point exists
        self._mount_path = Path("/nas")
        if self._mount_path.exists():
            self._nas_mounted = True
            logger.info(f"NAS mount detected at {self._mount_path}")
        else:
            logger.warning("NAS mount point not found - files will stay in output dir")

    async def stop(self) -> None:
        """Cleanup NAS connection."""
        pass

    async def organize_movie(
        self,
        source_file: Path,
        movie_name: str,
        year: Optional[int] = None,
    ) -> Optional[Path]:
        """Organize a movie file to the NAS.

        Args:
            source_file: Path to the transcoded file
            movie_name: Name of the movie
            year: Release year (optional)

        Returns:
            Final path on NAS, or None if failed
        """
        if not self._nas_mounted or not self._mount_path:
            logger.warning("NAS not available, keeping file in place")
            return source_file

        # Clean movie name for filesystem
        clean_name = self._clean_filename(movie_name)

        # Build folder name: "Movie Name (Year)" or just "Movie Name"
        if year:
            folder_name = f"{clean_name} ({year})"
        else:
            folder_name = clean_name

        # Create destination path
        dest_dir = self._mount_path / settings.nas_movie_path / folder_name
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Build destination filename
        dest_file = dest_dir / f"{folder_name}{source_file.suffix}"

        try:
            logger.info(f"Moving {source_file} to {dest_file}")
            shutil.move(str(source_file), str(dest_file))

            # S19: Trigger Plex library scan after successful organization
            await self._trigger_plex_scan("movie", str(dest_dir))

            # S20: Send Discord notification
            await self._send_discord_notification(
                filename=folder_name,
                destination=str(dest_file),
                media_type="movie",
            )

            return dest_file
        except Exception as e:
            logger.error(f"Failed to move file to NAS: {e}")
            return None

    async def organize_tv_episode(
        self,
        source_file: Path,
        show_name: str,
        season: int,
        episode: int,
        episode_title: Optional[str] = None,
    ) -> Optional[Path]:
        """Organize a TV episode to the NAS.

        Args:
            source_file: Path to the transcoded file
            show_name: Name of the TV show
            season: Season number
            episode: Episode number
            episode_title: Episode title (optional)

        Returns:
            Final path on NAS, or None if failed
        """
        if not self._nas_mounted or not self._mount_path:
            logger.warning("NAS not available, keeping file in place")
            return source_file

        # Clean show name
        clean_show = self._clean_filename(show_name)

        # Build paths
        show_dir = self._mount_path / settings.nas_tv_path / clean_show
        season_dir = show_dir / f"Season {season:02d}"
        season_dir.mkdir(parents=True, exist_ok=True)

        # Build filename: "Show Name - S01E01 - Episode Title.mkv"
        ep_code = f"S{season:02d}E{episode:02d}"
        if episode_title:
            clean_title = self._clean_filename(episode_title)
            filename = f"{clean_show} - {ep_code} - {clean_title}{source_file.suffix}"
        else:
            filename = f"{clean_show} - {ep_code}{source_file.suffix}"

        dest_file = season_dir / filename

        try:
            logger.info(f"Moving {source_file} to {dest_file}")
            shutil.move(str(source_file), str(dest_file))

            # S19: Trigger Plex library scan after successful organization
            await self._trigger_plex_scan("tv", str(show_dir))

            # S20: Send Discord notification
            await self._send_discord_notification(
                filename=filename.replace(source_file.suffix, ""),
                destination=str(dest_file),
                media_type="tv",
            )

            return dest_file
        except Exception as e:
            logger.error(f"Failed to move file to NAS: {e}")
            return None

    async def _send_discord_notification(
        self,
        filename: str,
        destination: str,
        media_type: str,
    ) -> None:
        """S20: Send Discord notification after file organization.

        Args:
            filename: Name of the organized file
            destination: Destination path
            media_type: Type of media ("movie" or "tv")
        """
        if not self._discord_client:
            return

        try:
            await self._discord_client.notify_file_organized(
                filename=filename,
                destination=destination,
                media_type=media_type,
            )
        except Exception as e:
            logger.warning(f"Failed to send Discord notification: {e}")

    async def _trigger_plex_scan(
        self, media_type: str, path: Optional[str] = None
    ) -> None:
        """S19: Trigger Plex library scan after file organization.

        Args:
            media_type: Type of media ("movie" or "tv")
            path: Path to scan (for more efficient scanning)
        """
        if not self._plex_client:
            return

        try:
            # Delay to allow filesystem to sync
            if settings.plex_scan_delay_seconds > 0:
                await asyncio.sleep(settings.plex_scan_delay_seconds)

            if media_type == "movie":
                success = await self._plex_client.scan_movie_library(path)
            else:
                success = await self._plex_client.scan_tv_library(path)

            if success:
                logger.info(f"Plex {media_type} library scan triggered")
            else:
                logger.debug(f"Plex {media_type} scan not triggered (not configured)")

        except Exception as e:
            logger.warning(f"Failed to trigger Plex scan: {e}")

    def _clean_filename(self, name: str) -> str:
        """Clean a string for use as a filename."""
        # Remove or replace invalid characters
        clean = re.sub(r'[<>:"/\\|?*]', "", name)
        # Replace multiple spaces with single space
        clean = re.sub(r"\s+", " ", clean)
        # Strip leading/trailing whitespace
        clean = clean.strip()
        # Limit length
        if len(clean) > 200:
            clean = clean[:200]
        return clean

    def get_status(self) -> dict:
        """Get NAS organizer status."""
        plex_status = None
        if self._plex_client:
            plex_status = self._plex_client.get_status()

        return {
            "enabled": settings.nas_enabled,
            "mounted": self._nas_mounted,
            "mount_path": str(self._mount_path) if self._mount_path else None,
            "movie_path": settings.nas_movie_path,
            "tv_path": settings.nas_tv_path,
            "plex": plex_status,
        }
