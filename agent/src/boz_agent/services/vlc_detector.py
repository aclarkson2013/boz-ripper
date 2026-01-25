"""VLC Media Player detection service."""

import subprocess
import winreg
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger()


@dataclass
class VLCInfo:
    """VLC installation information."""

    installed: bool
    path: Optional[str] = None
    version: Optional[str] = None


def detect_vlc() -> VLCInfo:
    """Detect VLC Media Player installation.

    Checks:
    1. Windows registry for VLC installation
    2. Common installation paths
    3. Gets version via --version flag

    Returns:
        VLCInfo with installation details
    """
    vlc_path = _find_vlc_path()

    if not vlc_path:
        logger.debug("vlc_not_found")
        return VLCInfo(installed=False)

    # Get version
    version = _get_vlc_version(vlc_path)

    logger.info(
        "vlc_detected",
        path=vlc_path,
        version=version,
    )

    return VLCInfo(
        installed=True,
        path=vlc_path,
        version=version,
    )


def _find_vlc_path() -> Optional[str]:
    """Find VLC executable path.

    Checks registry first, then common paths.

    Returns:
        Path to vlc.exe or None if not found
    """
    # Try registry first (most reliable)
    registry_path = _check_registry()
    if registry_path:
        return registry_path

    # Check common installation paths
    common_paths = [
        Path(r"C:\Program Files\VideoLAN\VLC\vlc.exe"),
        Path(r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"),
        Path.home() / "AppData" / "Local" / "Programs" / "VideoLAN" / "VLC" / "vlc.exe",
    ]

    for path in common_paths:
        if path.exists():
            return str(path)

    return None


def _check_registry() -> Optional[str]:
    """Check Windows registry for VLC installation.

    Returns:
        Path to vlc.exe or None if not found
    """
    registry_keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\VideoLAN\VLC"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\VideoLAN\VLC"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\VideoLAN\VLC"),
    ]

    for hkey, subkey in registry_keys:
        try:
            with winreg.OpenKey(hkey, subkey) as key:
                install_dir, _ = winreg.QueryValueEx(key, "InstallDir")
                vlc_exe = Path(install_dir) / "vlc.exe"
                if vlc_exe.exists():
                    return str(vlc_exe)
        except (FileNotFoundError, OSError):
            continue

    return None


def _get_vlc_version(vlc_path: str) -> Optional[str]:
    """Get VLC version by running vlc --version.

    Args:
        vlc_path: Path to vlc.exe

    Returns:
        Version string or None if unable to determine
    """
    try:
        result = subprocess.run(
            [vlc_path, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        # VLC outputs version on first line like: "VLC media player 3.0.18 Vetinari"
        output = result.stdout or result.stderr
        if output:
            first_line = output.strip().split("\n")[0]
            # Extract version number
            parts = first_line.split()
            for i, part in enumerate(parts):
                if part == "player" and i + 1 < len(parts):
                    return parts[i + 1]

        return None

    except (subprocess.SubprocessError, OSError) as e:
        logger.debug("vlc_version_check_failed", error=str(e))
        return None
