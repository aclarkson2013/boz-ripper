"""VLC Media Player launcher service."""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger()


@dataclass
class LaunchResult:
    """Result of launching VLC."""

    success: bool
    error: Optional[str] = None
    pid: Optional[int] = None


def launch_vlc(
    vlc_path: str,
    file_path: str,
    fullscreen: bool = True,
) -> LaunchResult:
    """Launch VLC to preview a video file.

    Launches VLC as a detached process so it doesn't block the agent.

    Args:
        vlc_path: Path to vlc.exe
        file_path: Path to the video file to play
        fullscreen: Whether to start in fullscreen mode

    Returns:
        LaunchResult with success status and optional error
    """
    # Validate VLC exists
    if not Path(vlc_path).exists():
        logger.error("vlc_not_found", path=vlc_path)
        return LaunchResult(
            success=False,
            error=f"VLC not found at: {vlc_path}",
        )

    # Validate file exists
    if not Path(file_path).exists():
        logger.error("file_not_found", path=file_path)
        return LaunchResult(
            success=False,
            error=f"File not found: {file_path}",
        )

    # Build VLC command
    cmd = [vlc_path]

    if fullscreen:
        cmd.append("--fullscreen")

    # Add the file to play
    cmd.append(file_path)

    try:
        logger.info(
            "vlc_launching",
            vlc_path=vlc_path,
            file_path=file_path,
            fullscreen=fullscreen,
            command=cmd,
        )

        # Launch VLC as a normal process (not detached) so it shows on screen
        # Using shell=False and no special creation flags for better compatibility
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )

        logger.info(
            "vlc_launched",
            file=file_path,
            fullscreen=fullscreen,
            pid=process.pid,
        )

        return LaunchResult(
            success=True,
            pid=process.pid,
        )

    except (subprocess.SubprocessError, OSError) as e:
        logger.error("vlc_launch_failed", error=str(e))
        return LaunchResult(
            success=False,
            error=str(e),
        )
