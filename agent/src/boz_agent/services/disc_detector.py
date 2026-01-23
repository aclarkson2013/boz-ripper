"""Disc detection service for Windows using WMI."""

import asyncio
from typing import Callable, Optional

import structlog

from boz_agent.core.config import DiscDetectionConfig

logger = structlog.get_logger()


class DiscDetector:
    """Monitors optical drives for disc insertion/ejection events.

    On Windows, uses WMI to receive real-time events when discs are
    inserted or ejected. Falls back to polling if WMI is unavailable.
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

        # Discover optical drives (synchronous WMI call)
        drives = self._discover_drives()
        logger.info("optical_drives_found", drives=drives)

        # Start the monitoring loop
        self._task = asyncio.create_task(self._monitor_loop(drives))

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

    def _discover_drives(self) -> list[str]:
        """Discover optical drives on the system.

        Returns:
            List of drive letters (e.g., ["D:", "E:"])
        """
        if self.config.drives:
            return self.config.drives

        # Use WMI to find optical drives (synchronous)
        return self._wmi_discover_drives()

    def _wmi_discover_drives(self) -> list[str]:
        """Use WMI to discover optical drives."""
        try:
            import wmi

            c = wmi.WMI()
            drives = []

            for drive in c.Win32_CDROMDrive():
                drive_letter = drive.Drive
                if drive_letter:
                    drives.append(drive_letter)
                    logger.debug(
                        "optical_drive_found",
                        drive=drive_letter,
                        name=drive.Name,
                    )

            return drives

        except ImportError:
            logger.warning("wmi_not_available", msg="Falling back to manual config")
            return []
        except Exception as e:
            logger.error("wmi_discovery_failed", error=str(e))
            return []

    async def _monitor_loop(self, drives: list[str]) -> None:
        """Main monitoring loop."""
        logger.info("disc_monitor_started", drives=drives)

        while self._running:
            try:
                for drive in drives:
                    await self._check_drive(drive)

                await asyncio.sleep(self.config.poll_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("monitor_loop_error", error=str(e))
                await asyncio.sleep(self.config.poll_interval)

    async def _check_drive(self, drive: str) -> None:
        """Check a single drive for disc presence."""
        disc_info = self._get_disc_info(drive)

        previously_had_disc = drive in self._known_discs

        if disc_info and not previously_had_disc:
            # Disc was inserted
            self._known_discs[drive] = disc_info
            if self.on_disc_inserted:
                await self.on_disc_inserted(drive, disc_info)

        elif not disc_info and previously_had_disc:
            # Disc was ejected
            del self._known_discs[drive]
            if self.on_disc_ejected:
                await self.on_disc_ejected(drive)

    def _get_disc_info(self, drive: str) -> Optional[dict]:
        """Get information about a disc in the drive.

        Uses ctypes to check drive status without WMI (faster and more reliable).

        Returns:
            Dict with disc info if present, None if no disc
        """
        import ctypes
        import os

        # Ensure drive has proper format (e.g., "I:" -> "I:\\")
        drive_path = drive if drive.endswith("\\") else f"{drive}\\"

        try:
            # Check drive type - should be DRIVE_CDROM (5)
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive_path)
            if drive_type != 5:  # Not a CD-ROM drive
                return None

            # Try to get volume information - this will fail if no disc
            volume_name_buf = ctypes.create_unicode_buffer(261)
            serial_number = ctypes.c_ulong()
            max_component_length = ctypes.c_ulong()
            file_system_flags = ctypes.c_ulong()
            file_system_name_buf = ctypes.create_unicode_buffer(261)

            result = ctypes.windll.kernel32.GetVolumeInformationW(
                drive_path,
                volume_name_buf,
                261,
                ctypes.byref(serial_number),
                ctypes.byref(max_component_length),
                ctypes.byref(file_system_flags),
                file_system_name_buf,
                261,
            )

            if result:
                volume_name = volume_name_buf.value or "Unknown"
                file_system = file_system_name_buf.value or "Unknown"

                # Determine media type from file system
                media_type = "DVD" if file_system == "UDF" else "CD"
                if "BD" in volume_name.upper() or "BLU" in volume_name.upper():
                    media_type = "Blu-ray"

                logger.debug("disc_detected", drive=drive, name=volume_name, fs=file_system)
                return {
                    "drive": drive,
                    "name": volume_name,
                    "media_type": media_type,
                    "file_system": file_system,
                }

            return None

        except Exception as e:
            logger.debug("disc_check_failed", drive=drive, error=str(e))
            return None

    def get_current_discs(self) -> dict[str, dict]:
        """Get currently detected discs."""
        return self._known_discs.copy()
