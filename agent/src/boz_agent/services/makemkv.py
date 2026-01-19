"""MakeMKV service for disc analysis and ripping."""

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import structlog

from boz_agent.core.config import MakeMKVConfig

logger = structlog.get_logger()


@dataclass
class Title:
    """Represents a title (movie/episode) on a disc."""

    index: int
    name: str
    duration_seconds: int
    size_bytes: int
    chapters: int = 0
    audio_tracks: list[dict] = field(default_factory=list)
    subtitle_tracks: list[dict] = field(default_factory=list)

    @property
    def duration_formatted(self) -> str:
        """Return duration as HH:MM:SS."""
        hours, remainder = divmod(self.duration_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    @property
    def size_formatted(self) -> str:
        """Return size in human-readable format."""
        for unit in ["B", "KB", "MB", "GB"]:
            if self.size_bytes < 1024:
                return f"{self.size_bytes:.1f} {unit}"
            self.size_bytes /= 1024
        return f"{self.size_bytes:.1f} TB"


@dataclass
class DiscAnalysis:
    """Result of analyzing a disc with MakeMKV."""

    disc_name: str
    disc_type: str  # "DVD" or "Blu-ray"
    drive: str
    titles: list[Title] = field(default_factory=list)
    raw_output: str = ""

    @property
    def main_feature(self) -> Optional[Title]:
        """Return the likely main feature (longest title)."""
        if not self.titles:
            return None
        return max(self.titles, key=lambda t: t.duration_seconds)


class MakeMKVService:
    """Interface to MakeMKV command-line tool."""

    def __init__(self, config: MakeMKVConfig):
        self.config = config
        self._executable = Path(config.executable)
        self._temp_dir = Path(config.temp_dir)

    def is_available(self) -> bool:
        """Check if MakeMKV is installed and accessible."""
        return self._executable.exists()

    async def analyze_disc(self, drive: str) -> DiscAnalysis:
        """Analyze a disc and return its contents.

        Args:
            drive: Drive letter (e.g., "D:")

        Returns:
            DiscAnalysis with all titles found on the disc
        """
        if not self.is_available():
            raise RuntimeError(f"MakeMKV not found at {self._executable}")

        logger.info("analyzing_disc", drive=drive)

        # Get disc index from drive letter
        disc_index = await self._get_disc_index(drive)

        # Run MakeMKV info command
        cmd = [
            str(self._executable),
            "-r",  # Robot mode (parseable output)
            "info",
            f"disc:{disc_index}",
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()
        output = stdout.decode("utf-8", errors="replace")

        if process.returncode != 0:
            logger.error(
                "makemkv_analysis_failed",
                drive=drive,
                returncode=process.returncode,
                stderr=stderr.decode("utf-8", errors="replace"),
            )
            raise RuntimeError(f"MakeMKV analysis failed: {stderr.decode()}")

        # Parse the output
        analysis = self._parse_info_output(output, drive)
        logger.info(
            "disc_analyzed",
            drive=drive,
            disc_name=analysis.disc_name,
            title_count=len(analysis.titles),
        )

        return analysis

    async def rip_title(
        self,
        drive: str,
        title_index: int,
        output_dir: Optional[Path] = None,
        progress_callback: Optional[callable] = None,
    ) -> Path:
        """Rip a specific title from the disc.

        Args:
            drive: Drive letter
            title_index: Index of the title to rip
            output_dir: Directory for output file (uses temp_dir if not specified)
            progress_callback: Optional callback for progress updates

        Returns:
            Path to the ripped MKV file
        """
        if not self.is_available():
            raise RuntimeError(f"MakeMKV not found at {self._executable}")

        output_dir = output_dir or self._temp_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        disc_index = await self._get_disc_index(drive)

        logger.info(
            "ripping_title",
            drive=drive,
            title_index=title_index,
            output_dir=str(output_dir),
        )

        cmd = [
            str(self._executable),
            "-r",  # Robot mode
            "mkv",
            f"disc:{disc_index}",
            str(title_index),
            str(output_dir),
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        # Stream output for progress updates
        output_lines = []
        while True:
            line = await process.stdout.readline()
            if not line:
                break

            line_str = line.decode("utf-8", errors="replace").strip()
            output_lines.append(line_str)

            # Parse progress if callback provided
            if progress_callback and line_str.startswith("PRGV:"):
                progress = self._parse_progress(line_str)
                if progress is not None:
                    await progress_callback(progress)

        await process.wait()

        if process.returncode != 0:
            raise RuntimeError(f"MakeMKV rip failed with code {process.returncode}")

        # Find the output file
        mkv_files = list(output_dir.glob("*.mkv"))
        if not mkv_files:
            raise RuntimeError("No MKV file produced")

        # Return the most recently modified MKV
        output_file = max(mkv_files, key=lambda p: p.stat().st_mtime)
        logger.info("rip_completed", output_file=str(output_file))

        return output_file

    async def _get_disc_index(self, drive: str) -> int:
        """Get MakeMKV disc index from drive letter."""
        # MakeMKV uses disc indices, not drive letters
        # Run with --list-drives to map them
        # For simplicity, assume single drive = disc:0
        # TODO: Implement proper drive mapping
        return 0

    def _parse_info_output(self, output: str, drive: str) -> DiscAnalysis:
        """Parse MakeMKV robot-mode info output."""
        analysis = DiscAnalysis(
            disc_name="Unknown",
            disc_type="Unknown",
            drive=drive,
            raw_output=output,
        )

        titles: dict[int, Title] = {}
        current_title_idx = -1

        for line in output.splitlines():
            line = line.strip()

            # Disc info: CINFO:index,code,value
            if line.startswith("CINFO:"):
                parts = line[6:].split(",", 2)
                if len(parts) >= 3:
                    code = int(parts[1])
                    value = parts[2].strip('"')

                    if code == 2:  # Disc name
                        analysis.disc_name = value
                    elif code == 1:  # Disc type
                        analysis.disc_type = value

            # Title info: TINFO:title_index,code,value
            elif line.startswith("TINFO:"):
                parts = line[6:].split(",", 3)
                if len(parts) >= 4:
                    title_idx = int(parts[0])
                    code = int(parts[1])
                    value = parts[3].strip('"')

                    if title_idx not in titles:
                        titles[title_idx] = Title(
                            index=title_idx,
                            name=f"Title {title_idx}",
                            duration_seconds=0,
                            size_bytes=0,
                        )

                    title = titles[title_idx]

                    if code == 2:  # Title name
                        title.name = value
                    elif code == 9:  # Duration (HH:MM:SS)
                        title.duration_seconds = self._parse_duration(value)
                    elif code == 10:  # Size in bytes
                        title.size_bytes = int(value) if value.isdigit() else 0
                    elif code == 8:  # Chapter count
                        title.chapters = int(value) if value.isdigit() else 0

        # Filter titles by minimum length
        min_length = self.config.min_title_length
        analysis.titles = [
            t for t in titles.values() if t.duration_seconds >= min_length
        ]

        # Sort by index
        analysis.titles.sort(key=lambda t: t.index)

        return analysis

    def _parse_duration(self, duration_str: str) -> int:
        """Parse HH:MM:SS to seconds."""
        match = re.match(r"(\d+):(\d+):(\d+)", duration_str)
        if match:
            hours, minutes, seconds = map(int, match.groups())
            return hours * 3600 + minutes * 60 + seconds
        return 0

    def _parse_progress(self, line: str) -> Optional[float]:
        """Parse PRGV progress line."""
        # Format: PRGV:current,total,max
        match = re.match(r"PRGV:(\d+),(\d+),(\d+)", line)
        if match:
            current, total, max_val = map(int, match.groups())
            if max_val > 0:
                return (current / max_val) * 100
        return None
