"""Thumbnail storage service for disc preview verification."""

import base64
import logging
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ThumbnailStorage:
    """Manages temporary thumbnail storage for disc previews."""

    def __init__(self, storage_path: str = "/data/thumbnails"):
        """
        Initialize thumbnail storage.

        Args:
            storage_path: Base path for thumbnail storage
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Thumbnail storage initialized at {self.storage_path}")

    def save_thumbnails(
        self,
        disc_id: str,
        title_index: int,
        thumbnails: list[str],
        timestamps: list[int],
    ) -> list[str]:
        """
        Save base64-encoded thumbnails to filesystem.

        Args:
            disc_id: Disc ID
            title_index: Title index on the disc
            thumbnails: List of base64-encoded JPEG images
            timestamps: List of timestamps corresponding to each thumbnail

        Returns:
            List of thumbnail URLs/paths
        """
        if not thumbnails:
            return []

        # Create disc directory
        disc_dir = self.storage_path / disc_id
        disc_dir.mkdir(parents=True, exist_ok=True)

        urls = []
        for i, (thumbnail, timestamp) in enumerate(zip(thumbnails, timestamps)):
            try:
                # Decode base64
                image_data = base64.b64decode(thumbnail)

                # Save to file
                filename = f"title_{title_index}_{timestamp}.jpg"
                filepath = disc_dir / filename
                filepath.write_bytes(image_data)

                # Return URL path (relative to thumbnail endpoint)
                url = f"/api/thumbnails/{disc_id}/{filename}"
                urls.append(url)

                logger.debug(
                    f"Saved thumbnail: {filepath} ({len(image_data)} bytes)"
                )
            except Exception as e:
                logger.error(f"Failed to save thumbnail: {e}")
                continue

        logger.info(
            f"Saved {len(urls)} thumbnails for disc {disc_id}, title {title_index}"
        )
        return urls

    def get_thumbnail(self, disc_id: str, filename: str) -> Optional[bytes]:
        """
        Get a thumbnail file.

        Args:
            disc_id: Disc ID
            filename: Thumbnail filename

        Returns:
            Image bytes or None if not found
        """
        filepath = self.storage_path / disc_id / filename

        # Security check - prevent path traversal
        try:
            filepath = filepath.resolve()
            if not str(filepath).startswith(str(self.storage_path.resolve())):
                logger.warning(f"Path traversal attempt: {filepath}")
                return None
        except Exception:
            return None

        if filepath.exists():
            return filepath.read_bytes()

        return None

    def delete_disc_thumbnails(self, disc_id: str) -> bool:
        """
        Delete all thumbnails for a disc.

        Args:
            disc_id: Disc ID

        Returns:
            True if deleted successfully
        """
        disc_dir = self.storage_path / disc_id

        if disc_dir.exists():
            try:
                shutil.rmtree(disc_dir)
                logger.info(f"Deleted thumbnails for disc {disc_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to delete thumbnails for {disc_id}: {e}")
                return False

        return True

    def get_disc_thumbnail_count(self, disc_id: str) -> int:
        """
        Get the number of thumbnails stored for a disc.

        Args:
            disc_id: Disc ID

        Returns:
            Number of thumbnail files
        """
        disc_dir = self.storage_path / disc_id
        if disc_dir.exists():
            return len(list(disc_dir.glob("*.jpg")))
        return 0

    def cleanup_old_thumbnails(self, max_age_hours: int = 24) -> int:
        """
        Clean up thumbnails older than max_age_hours.

        Args:
            max_age_hours: Maximum age in hours before cleanup

        Returns:
            Number of disc directories cleaned up
        """
        import time

        max_age_seconds = max_age_hours * 3600
        current_time = time.time()
        cleaned = 0

        for disc_dir in self.storage_path.iterdir():
            if disc_dir.is_dir():
                try:
                    # Check modification time of directory
                    mtime = disc_dir.stat().st_mtime
                    if current_time - mtime > max_age_seconds:
                        shutil.rmtree(disc_dir)
                        cleaned += 1
                        logger.info(f"Cleaned up old thumbnails: {disc_dir.name}")
                except Exception as e:
                    logger.error(f"Failed to clean up {disc_dir}: {e}")

        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} old thumbnail directories")

        return cleaned
