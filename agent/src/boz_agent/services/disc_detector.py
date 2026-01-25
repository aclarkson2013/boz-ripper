"""Disc detection service for Windows - non-blocking."""

import asyncio
import ctypes
import os
import string
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes
from typing import Callable, Optional

import structlog

from boz_agent.core.config import DiscDetectionConfig

logger = structlog.get_logger()

# Thread pool for blocking I/O operations
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="disc_detector")

# Windows constants for disc ejection
GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
IOCTL_STORAGE_EJECT_MEDIA = 0x2D4808


class DiscDetector:
    """Monitors optical drives for disc insertion/ejection events.

    Uses non-blocking polling with thread pool to avoid blocking the event loop.
    """

    def __init__(
        self,
        config: DiscDetectionConfig,
        on_disc_inserted: Optional[Callable] = None,
        on_disc_ejected: Optional[Callable] = None,
    ):
        self.config = config
        self.on_disc_inserted = on_disc_inserted
        self.on_disc_ejected = on_disc_ejected

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._known_discs: dict[str, dict] = {}

    async def start(self) -> None:
        """Start monitoring for disc events."""
        if self._running:
            return

        self._running = True
        logger.info("disc_detector_starting")

        # Get drives from config or discover them
        if self.config.drives:
            drives = self.config.drives
        else:
            drives = await self._discover_drives_async()

        logger.info("optical_drives_found", drives=drives)

        # Start the monitoring loop
        self._task = asyncio.create_task(self._monitor_loop(drives))
        logger.info("disc_monitor_started", drives=drives)

    async def stop(self) -> None:
        """Stop monitoring for disc events."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("disc_detector_stopped")

    async def _discover_drives_async(self) -> list[str]:
        """Discover optical drives without blocking."""
        loop = asyncio.get_event_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(_executor, self._discover_drives_sync),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            logger.warning("drive_discovery_timeout")
            return ["I:"]  # Fallback to I: drive

    def _discover_drives_sync(self) -> list[str]:
        """Discover optical drives (runs in thread)."""
        drives = []
        DRIVE_CDROM = 5

        for letter in string.ascii_uppercase:
            try:
                drive_path = f"{letter}:\\"
                drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive_path)
                if drive_type == DRIVE_CDROM:
                    drives.append(f"{letter}:")
                    logger.debug("optical_drive_found", drive=f"{letter}:")
            except Exception:
                pass

        return drives if drives else ["I:"]  # Fallback

    async def _monitor_loop(self, drives: list[str]) -> None:
        """Main monitoring loop - non-blocking."""
        while self._running:
            try:
                for drive in drives:
                    # Run disc check in thread with timeout
                    disc_info = await self._check_drive_async(drive)
                    await self._handle_disc_change(drive, disc_info)

                await asyncio.sleep(self.config.poll_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("monitor_loop_error", error=str(e))
                await asyncio.sleep(self.config.poll_interval)

    async def _check_drive_async(self, drive: str) -> Optional[dict]:
        """Check drive for disc - runs in thread with timeout."""
        loop = asyncio.get_event_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(_executor, self._get_disc_info_sync, drive),
                timeout=5.0  # 5 second timeout per drive
            )
        except asyncio.TimeoutError:
            logger.debug("disc_check_timeout", drive=drive)
            return None
        except Exception as e:
            logger.debug("disc_check_error", drive=drive, error=str(e))
            return None

    async def _handle_disc_change(self, drive: str, disc_info: Optional[dict]) -> None:
        """Handle disc insertion/ejection."""
        previously_had_disc = drive in self._known_discs

        if disc_info and not previously_had_disc:
            # Disc was inserted
            self._known_discs[drive] = disc_info
            logger.info("disc_inserted", drive=drive, disc_info=disc_info)
            if self.on_disc_inserted:
                try:
                    await self.on_disc_inserted(drive, disc_info)
                except Exception as e:
                    logger.error("disc_inserted_callback_error", error=str(e))

        elif not disc_info and previously_had_disc:
            # Disc was ejected
            del self._known_discs[drive]
            logger.info("disc_ejected", drive=drive)
            if self.on_disc_ejected:
                try:
                    await self.on_disc_ejected(drive)
                except Exception as e:
                    logger.error("disc_ejected_callback_error", error=str(e))

    def _get_disc_info_sync(self, drive: str) -> Optional[dict]:
        """Get disc info - simple and fast (runs in thread).

        Uses os.path.exists and os.listdir for quick detection,
        then ctypes for volume name if disc is present.
        """
        drive_path = f"{drive}\\"

        try:
            # Quick check - can we access the drive?
            if not os.path.exists(drive_path):
                return None

            # Try to list the drive - this confirms disc is readable
            try:
                os.listdir(drive_path)
            except (OSError, PermissionError):
                return None

            # Disc is present - get volume info
            volume_name = "Unknown"
            file_system = "Unknown"

            try:
                volume_name_buf = ctypes.create_unicode_buffer(261)
                file_system_buf = ctypes.create_unicode_buffer(261)
                serial = ctypes.c_ulong()
                max_len = ctypes.c_ulong()
                flags = ctypes.c_ulong()

                result = ctypes.windll.kernel32.GetVolumeInformationW(
                    drive_path,
                    volume_name_buf, 261,
                    ctypes.byref(serial),
                    ctypes.byref(max_len),
                    ctypes.byref(flags),
                    file_system_buf, 261
                )

                if result:
                    volume_name = volume_name_buf.value or "Unknown"
                    file_system = file_system_buf.value or "Unknown"
            except Exception:
                pass  # Use defaults

            # Determine media type
            media_type = "DVD" if file_system == "UDF" else "CD"
            if "BD" in volume_name.upper() or "BLU" in volume_name.upper():
                media_type = "Blu-ray"

            return {
                "drive": drive,
                "name": volume_name,
                "media_type": media_type,
                "file_system": file_system,
            }

        except Exception as e:
            return None

    def get_current_discs(self) -> dict[str, dict]:
        """Get currently detected discs."""
        return self._known_discs.copy()

    async def eject_disc(self, drive: str) -> bool:
        """A18: Eject a disc from the specified drive.

        Args:
            drive: Drive letter (e.g., "I:" or "I")

        Returns:
            True if eject succeeded, False otherwise
        """
        # Normalize drive letter
        drive_letter = drive.rstrip(":\\").upper()

        logger.info("ejecting_disc", drive=drive_letter)

        loop = asyncio.get_event_loop()
        try:
            success = await asyncio.wait_for(
                loop.run_in_executor(_executor, self._eject_disc_sync, drive_letter),
                timeout=10.0,
            )
            if success:
                logger.info("disc_ejected_successfully", drive=drive_letter)
                # Remove from known discs immediately
                if f"{drive_letter}:" in self._known_discs:
                    del self._known_discs[f"{drive_letter}:"]
            else:
                logger.warning("disc_eject_failed", drive=drive_letter)
            return success
        except asyncio.TimeoutError:
            logger.error("disc_eject_timeout", drive=drive_letter)
            return False
        except Exception as e:
            logger.error("disc_eject_error", drive=drive_letter, error=str(e))
            return False

    def _eject_disc_sync(self, drive_letter: str) -> bool:
        """Eject disc using Windows DeviceIoControl (runs in thread).

        Args:
            drive_letter: Single letter drive (e.g., "I")

        Returns:
            True if eject succeeded
        """
        # Build device path for the drive
        device_path = f"\\\\.\\{drive_letter}:"

        try:
            # Open the drive device
            handle = ctypes.windll.kernel32.CreateFileW(
                device_path,
                GENERIC_READ,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None,
                OPEN_EXISTING,
                0,
                None,
            )

            if handle == -1 or handle == wintypes.HANDLE(-1).value:
                logger.warning("eject_open_drive_failed", drive=drive_letter)
                return False

            try:
                # Send eject command
                bytes_returned = wintypes.DWORD()
                result = ctypes.windll.kernel32.DeviceIoControl(
                    handle,
                    IOCTL_STORAGE_EJECT_MEDIA,
                    None,
                    0,
                    None,
                    0,
                    ctypes.byref(bytes_returned),
                    None,
                )

                return bool(result)

            finally:
                # Close handle
                ctypes.windll.kernel32.CloseHandle(handle)

        except Exception as e:
            logger.error("eject_exception", drive=drive_letter, error=str(e))
            return False
