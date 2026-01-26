"""MakeMKV service for disc analysis and ripping."""

import asyncio
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import structlog

from boz_agent.core.config import MakeMKVConfig

logger = structlog.get_logger()

# Timeout constants
DISC_INDEX_TIMEOUT = 30  # seconds to get disc index
ANALYZE_TIMEOUT = 300  # seconds to analyze disc (some discs with copy protection take longer)
ANALYZE_RETRIES = 3  # number of retry attempts for disc analysis
ANALYZE_RETRY_DELAY = 5  # seconds to wait between retries
RIP_TIMEOUT = 7200  # 2 hours max for ripping
RIP_STALL_TIMEOUT = 300  # 5 minutes with no output = stalled


def _get_subprocess_flags() -> dict:
    """Get platform-specific subprocess flags to prevent GUI popups."""
    if sys.platform == "win32":
        return {
            "creationflags": subprocess.CREATE_NO_WINDOW,
            "stdin": subprocess.DEVNULL,
        }
    return {"stdin": subprocess.DEVNULL}


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

        last_error = None
        for attempt in range(1, ANALYZE_RETRIES + 1):
            try:
                analysis = await self._analyze_disc_attempt(drive, attempt)
                return analysis
            except RuntimeError as e:
                last_error = e
                if attempt < ANALYZE_RETRIES:
                    logger.warning(
                        "analyze_disc_retry",
                        drive=drive,
                        attempt=attempt,
                        max_attempts=ANALYZE_RETRIES,
                        error=str(e),
                    )
                    await asyncio.sleep(ANALYZE_RETRY_DELAY)
                else:
                    logger.error(
                        "analyze_disc_all_retries_failed",
                        drive=drive,
                        attempts=ANALYZE_RETRIES,
                    )

        raise last_error

    async def _analyze_disc_attempt(self, drive: str, attempt: int = 1) -> "DiscAnalysis":
        """Single attempt to analyze a disc."""
        # Get disc index from drive letter
        disc_index = await self._get_disc_index(drive)

        # Run MakeMKV info command
        cmd = [
            str(self._executable),
            "-r",  # Robot mode (parseable output)
            "--noscan",  # Don't scan for other devices
            "info",
            f"disc:{disc_index}",
        ]

        logger.debug("analyze_disc_cmd", cmd=" ".join(cmd), attempt=attempt)
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **_get_subprocess_flags(),
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=ANALYZE_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.error("analyze_disc_timeout", drive=drive, timeout=ANALYZE_TIMEOUT, attempt=attempt)
            process.kill()
            await process.wait()
            raise RuntimeError(f"MakeMKV analysis timed out after {ANALYZE_TIMEOUT}s")

        output = stdout.decode("utf-8", errors="replace")

        if process.returncode != 0:
            logger.error(
                "makemkv_analysis_failed",
                drive=drive,
                returncode=process.returncode,
                stderr=stderr.decode("utf-8", errors="replace"),
                attempt=attempt,
            )
            raise RuntimeError(f"MakeMKV analysis failed: {stderr.decode()}")

        # Parse the output
        analysis = self._parse_info_output(output, drive)
        logger.info(
            "disc_analyzed",
            drive=drive,
            disc_name=analysis.disc_name,
            title_count=len(analysis.titles),
            attempt=attempt,
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

        # NOTE: Don't clean up existing MKV files here!
        # Previous versions deleted all .mkv files to avoid overwrite prompts,
        # but this would delete files that were ripped but not yet transcoded.
        # MakeMKV will handle overwrites itself or use unique filenames.

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
            "--noscan",  # Don't scan for other devices
            "--progress=-same",  # Output progress to stdout
            "mkv",
            f"disc:{disc_index}",
            str(title_index),
            str(output_dir),
        ]

        logger.debug("makemkv_command", cmd=" ".join(cmd))

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            **_get_subprocess_flags(),
        )

        logger.debug("makemkv_started", pid=process.pid)

        # Stream output for progress updates with stall detection
        output_lines = []
        last_progress_log = 0
        lines_received = 0
        stall_detected = False

        while True:
            try:
                # Wait for output with timeout to detect stalls
                line = await asyncio.wait_for(
                    process.stdout.readline(),
                    timeout=RIP_STALL_TIMEOUT
                )
            except asyncio.TimeoutError:
                logger.error(
                    "makemkv_stall_detected",
                    pid=process.pid,
                    timeout=RIP_STALL_TIMEOUT,
                    lines_received=lines_received,
                )
                stall_detected = True
                # Kill the hung process
                process.kill()
                await process.wait()
                break

            if not line:
                logger.debug("makemkv_stdout_closed", lines_received=lines_received)
                break

            lines_received += 1

            line_str = line.decode("utf-8", errors="replace").strip()
            output_lines.append(line_str)

            # Log all output for debugging
            if line_str.startswith("PRGV:"):
                progress = self._parse_progress(line_str)
                if progress is not None:
                    # Log every 10%
                    if int(progress / 10) > last_progress_log:
                        last_progress_log = int(progress / 10)
                        logger.info("rip_progress", progress=f"{progress:.1f}%")
                    if progress_callback:
                        await progress_callback(progress)
            elif line_str.startswith("MSG:"):
                logger.debug("makemkv_msg", msg=line_str)
            elif line_str.startswith("PRGT:") or line_str.startswith("PRGC:"):
                logger.debug("makemkv_status", status=line_str)
            elif line_str:
                # Log any other non-empty output
                logger.debug("makemkv_output", line=line_str)

        if stall_detected:
            raise RuntimeError(f"MakeMKV stalled - no output for {RIP_STALL_TIMEOUT} seconds")

        await process.wait()
        logger.debug("makemkv_finished", returncode=process.returncode)

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
        """Get MakeMKV disc index from drive letter.

        MakeMKV uses disc indices (0, 1, 2...) not drive letters.
        We query MakeMKV to find which index corresponds to the drive.
        """
        # Run MakeMKV info with an invalid disc to get drive list
        cmd = [
            str(self._executable),
            "-r",
            "--noscan",  # Don't scan for other devices
            "info",
            "disc:9999",  # Invalid index triggers drive listing
        ]

        try:
            logger.debug("getting_disc_index", drive=drive, cmd=" ".join(cmd))
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **_get_subprocess_flags(),
            )

            try:
                stdout, _ = await asyncio.wait_for(
                    process.communicate(),
                    timeout=DISC_INDEX_TIMEOUT
                )
            except asyncio.TimeoutError:
                logger.error("disc_index_timeout", drive=drive, timeout=DISC_INDEX_TIMEOUT)
                process.kill()
                await process.wait()
                return 0

            output = stdout.decode("utf-8", errors="replace")
            logger.debug("disc_index_output", output_lines=len(output.splitlines()))

            # Parse DRV lines to find the drive matching our drive letter
            # Format: DRV:index,visible,flags,drive_num,"drive_name","disc_name","drive_path"
            # Example: DRV:0,2,999,1,"BD-RE HL-DT-ST BD-RE BH16NS40","OFFICE","I:"
            drive_letter = drive.rstrip(":").upper()

            # First pass: look for exact drive letter match
            for line in output.splitlines():
                if line.startswith("DRV:"):
                    # Check if this line contains our drive letter (e.g., "I:")
                    if f'"{drive_letter}:"' in line.upper() or f",{drive_letter}:" in line.upper():
                        parts = line[4:].split(",")
                        if len(parts) >= 1:
                            idx = int(parts[0])
                            logger.debug("found_drive_by_letter", index=idx, drive=drive, info=line)
                            return idx

            # Second pass: look for first drive with a disc inserted (has disc name)
            for line in output.splitlines():
                if line.startswith("DRV:"):
                    parts = line[4:].split(",")
                    if len(parts) >= 6:
                        idx = int(parts[0])
                        visible = int(parts[1]) if parts[1].isdigit() else 0
                        # parts[5] is disc_name - check if it's non-empty (not just "")
                        disc_name = parts[5].strip('"')
                        if visible > 0 and disc_name:
                            logger.debug("found_drive_with_disc", index=idx, disc_name=disc_name, info=line)
                            return idx

            # Fallback: return 0 if no disc found
            logger.warning("disc_index_not_found", drive=drive, defaulting_to=0)
            return 0

        except Exception as e:
            logger.warning("disc_index_detection_failed", error=str(e), defaulting_to=0)
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
        """Parse PRGV progress line.

        MakeMKV outputs: PRGV:current,total,max
        - current: progress within current operation
        - total: overall progress for this title
        - max: maximum value (usually 65536)

        We use 'total' for overall title progress.
        """
        # Format: PRGV:current,total,max
        match = re.match(r"PRGV:(\d+),(\d+),(\d+)", line)
        if match:
            current, total, max_val = map(int, match.groups())
            if max_val > 0:
                # Use 'total' for overall progress (not 'current' which is per-operation)
                return (total / max_val) * 100
        return None
