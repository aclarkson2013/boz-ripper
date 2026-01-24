"""Thumbnail extraction service for disc preview verification."""

import asyncio
import base64
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import structlog

from boz_agent.core.config import ThumbnailConfig

logger = structlog.get_logger()

# Timeout for FFmpeg operations
FFMPEG_TIMEOUT = 30


def _get_subprocess_flags() -> dict:
    """Get platform-specific subprocess flags to prevent GUI popups."""
    if sys.platform == "win32":
        return {
            "creationflags": subprocess.CREATE_NO_WINDOW,
            "stdin": subprocess.DEVNULL,
        }
    return {"stdin": subprocess.DEVNULL}


@dataclass
class TitleThumbnails:
    """Thumbnails extracted from a single title."""

    title_index: int
    thumbnails: list[str]  # Base64-encoded JPEG images
    timestamps: list[int]  # Timestamps in seconds where thumbnails were extracted
    errors: list[str]  # Any errors during extraction


class ThumbnailExtractor:
    """Extracts thumbnail frames from disc titles using FFmpeg."""

    def __init__(self, config: ThumbnailConfig):
        self.config = config
        self._ffmpeg = config.ffmpeg_path
        self._temp_dir = Path(tempfile.gettempdir()) / "boz_thumbnails"

    def is_available(self) -> bool:
        """Check if FFmpeg is installed and accessible."""
        try:
            result = subprocess.run(
                [self._ffmpeg, "-version"],
                capture_output=True,
                timeout=5,
                **_get_subprocess_flags(),
            )
            return result.returncode == 0
        except Exception:
            return False

    async def extract_thumbnails(
        self,
        drive: str,
        title_index: int,
        duration_seconds: int,
        disc_type: str = "DVD",
    ) -> TitleThumbnails:
        """
        Extract thumbnails from a disc title.

        Args:
            drive: Drive letter (e.g., "D:")
            title_index: MakeMKV title index
            duration_seconds: Title duration in seconds
            disc_type: "DVD" or "Blu-ray"

        Returns:
            TitleThumbnails with extracted images
        """
        if not self.config.enabled:
            logger.debug("thumbnail_extraction_disabled")
            return TitleThumbnails(
                title_index=title_index,
                thumbnails=[],
                timestamps=[],
                errors=["Thumbnail extraction disabled"],
            )

        if not self.is_available():
            logger.warning("ffmpeg_not_available")
            return TitleThumbnails(
                title_index=title_index,
                thumbnails=[],
                timestamps=[],
                errors=["FFmpeg not available"],
            )

        # Calculate timestamps to extract
        timestamps = list(self.config.timestamps)
        if self.config.extract_midpoint:
            midpoint = duration_seconds // 2
            if midpoint not in timestamps and midpoint > 0:
                timestamps.append(midpoint)
        timestamps.sort()

        # Filter out timestamps that exceed duration
        timestamps = [t for t in timestamps if t < duration_seconds - 5]

        if not timestamps:
            # If all timestamps exceed duration, use 10% and 50% of duration
            timestamps = [
                max(5, duration_seconds // 10),
                max(10, duration_seconds // 2),
            ]

        logger.info(
            "extracting_thumbnails",
            drive=drive,
            title_index=title_index,
            disc_type=disc_type,
            timestamps=timestamps,
        )

        thumbnails = []
        extracted_timestamps = []
        errors = []

        # Try different input methods based on disc type
        input_path = self._get_input_path(drive, title_index, disc_type)

        for timestamp in timestamps:
            try:
                thumbnail_data = await self._extract_single_frame(
                    input_path, timestamp, title_index
                )
                if thumbnail_data:
                    thumbnails.append(thumbnail_data)
                    extracted_timestamps.append(timestamp)
                else:
                    errors.append(f"Failed to extract frame at {timestamp}s")
            except Exception as e:
                logger.warning(
                    "thumbnail_extraction_error",
                    timestamp=timestamp,
                    error=str(e),
                )
                errors.append(f"Error at {timestamp}s: {str(e)}")

        logger.info(
            "thumbnails_extracted",
            title_index=title_index,
            count=len(thumbnails),
            errors=len(errors),
        )

        return TitleThumbnails(
            title_index=title_index,
            thumbnails=thumbnails,
            timestamps=extracted_timestamps,
            errors=errors,
        )

    def _get_input_path(self, drive: str, title_index: int, disc_type: str) -> str:
        """
        Get the FFmpeg input path for the disc.

        Different strategies for DVDs vs Blu-rays:
        - DVD: Use VIDEO_TS folder with title selection
        - Blu-ray: Use bluray: protocol (requires libbluray)
        """
        drive_letter = drive.rstrip(":\\")

        if "blu" in disc_type.lower():
            # Blu-ray: use bluray protocol
            return f"bluray:{drive_letter}:"
        else:
            # DVD: use dvdnav or direct path
            # Try VIDEO_TS folder first
            video_ts = Path(f"{drive_letter}:\\VIDEO_TS")
            if video_ts.exists():
                return str(video_ts)
            # Fallback to drive directly
            return f"{drive_letter}:\\"

    async def _extract_single_frame(
        self,
        input_path: str,
        timestamp: int,
        title_index: int,
    ) -> Optional[str]:
        """
        Extract a single frame at the given timestamp.

        Returns:
            Base64-encoded JPEG image or None on failure
        """
        # Create temp file for output
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        output_file = self._temp_dir / f"thumb_{title_index}_{timestamp}.jpg"

        # Build FFmpeg command
        # Use -ss before -i for fast seeking
        cmd = [
            self._ffmpeg,
            "-ss", str(timestamp),
            "-i", input_path,
        ]

        # Add title selection for DVD/Blu-ray
        # Note: This depends on FFmpeg build having dvdnav/libbluray
        if "bluray:" in input_path:
            cmd.extend(["-playlist", str(title_index)])
        elif "VIDEO_TS" in input_path or input_path.endswith(":\\"):
            # For DVD, try to select title via map (may not work for all)
            cmd.extend(["-map", f"0:v:{title_index}" if title_index > 0 else "0:v:0"])

        # Output settings
        cmd.extend([
            "-frames:v", "1",
            "-q:v", str(self.config.quality),
            "-vf", f"scale={self.config.width}:-1",
            "-y",  # Overwrite output
            str(output_file),
        ])

        logger.debug("ffmpeg_command", cmd=" ".join(cmd))

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **_get_subprocess_flags(),
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.config.timeout,
                )
            except asyncio.TimeoutError:
                logger.warning("ffmpeg_timeout", timestamp=timestamp)
                process.kill()
                await process.wait()
                return None

            if process.returncode != 0:
                logger.debug(
                    "ffmpeg_failed",
                    returncode=process.returncode,
                    stderr=stderr.decode("utf-8", errors="replace")[:500],
                )
                # Try alternative method
                return await self._extract_frame_alternative(
                    input_path, timestamp, title_index, output_file
                )

            # Read and encode the thumbnail
            if output_file.exists():
                with open(output_file, "rb") as f:
                    image_data = f.read()
                # Clean up
                output_file.unlink()
                return base64.b64encode(image_data).decode("ascii")

            return None

        except Exception as e:
            logger.error("ffmpeg_exception", error=str(e))
            return None

    async def _extract_frame_alternative(
        self,
        input_path: str,
        timestamp: int,
        title_index: int,
        output_file: Path,
    ) -> Optional[str]:
        """
        Alternative frame extraction method using simpler FFmpeg options.

        This is a fallback when title selection doesn't work.
        """
        # Try without title selection - just grab the first video stream
        cmd = [
            self._ffmpeg,
            "-ss", str(timestamp),
            "-i", input_path,
            "-frames:v", "1",
            "-q:v", str(self.config.quality),
            "-vf", f"scale={self.config.width}:-1",
            "-y",
            str(output_file),
        ]

        logger.debug("ffmpeg_alternative_command", cmd=" ".join(cmd))

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **_get_subprocess_flags(),
            )

            try:
                await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.config.timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return None

            if output_file.exists():
                with open(output_file, "rb") as f:
                    image_data = f.read()
                output_file.unlink()
                return base64.b64encode(image_data).decode("ascii")

            return None

        except Exception:
            return None

    async def extract_all_titles(
        self,
        drive: str,
        titles: list[dict],
        disc_type: str = "DVD",
    ) -> list[TitleThumbnails]:
        """
        Extract thumbnails for all titles on a disc.

        Args:
            drive: Drive letter
            titles: List of title dicts with 'index' and 'duration_seconds'
            disc_type: "DVD" or "Blu-ray"

        Returns:
            List of TitleThumbnails for each title
        """
        results = []

        for title in titles:
            title_index = title.get("index", 0)
            duration = title.get("duration_seconds", 0)

            # Skip very short titles (likely menus or extras)
            if duration < 60:
                logger.debug(
                    "skipping_short_title",
                    title_index=title_index,
                    duration=duration,
                )
                results.append(
                    TitleThumbnails(
                        title_index=title_index,
                        thumbnails=[],
                        timestamps=[],
                        errors=["Title too short for thumbnails"],
                    )
                )
                continue

            thumbnails = await self.extract_thumbnails(
                drive, title_index, duration, disc_type
            )
            results.append(thumbnails)

        return results

    def cleanup(self) -> None:
        """Clean up temporary thumbnail files."""
        if self._temp_dir.exists():
            for file in self._temp_dir.glob("thumb_*.jpg"):
                try:
                    file.unlink()
                except Exception:
                    pass
