"""Discord webhook integration for notifications (S20)."""

import logging
from datetime import datetime
from typing import Optional

import httpx

from boz_server.core.config import settings

logger = logging.getLogger(__name__)


class DiscordClient:
    """Client for sending Discord webhook notifications.

    S20: Sends notifications for job completion, failures, and file organization.
    """

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._initialized = False

    async def start(self) -> None:
        """Initialize the Discord client."""
        if not settings.discord_enabled:
            logger.info("Discord notifications disabled")
            return

        if not settings.discord_webhook_url:
            logger.warning("Discord enabled but no webhook URL configured")
            return

        self._client = httpx.AsyncClient(timeout=10.0)
        self._initialized = True
        logger.info("Discord notifications enabled")

    async def stop(self) -> None:
        """Cleanup Discord client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def is_available(self) -> bool:
        """Check if Discord integration is available."""
        return self._initialized and self._client is not None

    async def _send_webhook(
        self,
        content: Optional[str] = None,
        embeds: Optional[list[dict]] = None,
    ) -> bool:
        """Send a message via Discord webhook.

        Args:
            content: Plain text message content
            embeds: List of embed objects

        Returns:
            True if message was sent successfully
        """
        if not self.is_available:
            return False

        payload = {}
        if content:
            payload["content"] = content
        if embeds:
            payload["embeds"] = embeds

        if not payload:
            return False

        try:
            response = await self._client.post(
                settings.discord_webhook_url,
                json=payload,
            )

            if response.status_code in (200, 204):
                logger.debug("Discord notification sent")
                return True
            else:
                logger.warning(f"Discord webhook failed: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Discord webhook error: {e}")
            return False

    async def notify_job_complete(
        self,
        job_id: str,
        output_name: str,
        job_type: str = "transcode",
        duration_seconds: Optional[float] = None,
    ) -> bool:
        """Notify that a job completed successfully.

        Args:
            job_id: Job identifier
            output_name: Name of the output file
            job_type: Type of job (rip/transcode)
            duration_seconds: How long the job took
        """
        if not settings.discord_notify_on_complete:
            return False

        duration_str = ""
        if duration_seconds:
            mins = int(duration_seconds // 60)
            secs = int(duration_seconds % 60)
            duration_str = f" in {mins}m {secs}s"

        embed = {
            "title": f"{job_type.title()} Complete",
            "description": f"**{output_name}**",
            "color": 0x00FF00,  # Green
            "fields": [
                {"name": "Job ID", "value": f"`{job_id[:8]}`", "inline": True},
            ],
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "Boz Ripper"},
        }

        if duration_str:
            embed["fields"].append(
                {"name": "Duration", "value": duration_str.strip(), "inline": True}
            )

        return await self._send_webhook(embeds=[embed])

    async def notify_job_failed(
        self,
        job_id: str,
        output_name: str,
        error: str,
        job_type: str = "transcode",
    ) -> bool:
        """Notify that a job failed.

        Args:
            job_id: Job identifier
            output_name: Name of the output file
            error: Error message
            job_type: Type of job (rip/transcode)
        """
        if not settings.discord_notify_on_failure:
            return False

        embed = {
            "title": f"{job_type.title()} Failed",
            "description": f"**{output_name}**",
            "color": 0xFF0000,  # Red
            "fields": [
                {"name": "Job ID", "value": f"`{job_id[:8]}`", "inline": True},
                {"name": "Error", "value": error[:500], "inline": False},
            ],
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "Boz Ripper"},
        }

        return await self._send_webhook(embeds=[embed])

    async def notify_file_organized(
        self,
        filename: str,
        destination: str,
        media_type: str = "unknown",
    ) -> bool:
        """Notify that a file was organized to NAS.

        Args:
            filename: Name of the file
            destination: Destination path on NAS
            media_type: Type of media (movie/tv)
        """
        if not settings.discord_notify_on_organized:
            return False

        # Choose icon based on media type
        icon = "\U0001F4FA" if media_type == "tv" else "\U0001F3AC"  # TV or Movie emoji

        embed = {
            "title": f"{icon} Added to Library",
            "description": f"**{filename}**",
            "color": 0x3498DB,  # Blue
            "fields": [
                {"name": "Type", "value": media_type.upper(), "inline": True},
                {"name": "Location", "value": f"`{destination}`", "inline": False},
            ],
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "Boz Ripper"},
        }

        return await self._send_webhook(embeds=[embed])

    async def notify_disc_detected(
        self,
        disc_name: str,
        disc_type: str,
        title_count: int,
        agent_name: str,
    ) -> bool:
        """Notify that a new disc was detected.

        Args:
            disc_name: Name of the disc
            disc_type: Type of disc (DVD/Blu-ray)
            title_count: Number of titles detected
            agent_name: Name of the agent that detected it
        """
        embed = {
            "title": "Disc Detected",
            "description": f"**{disc_name}**",
            "color": 0x9B59B6,  # Purple
            "fields": [
                {"name": "Type", "value": disc_type, "inline": True},
                {"name": "Titles", "value": str(title_count), "inline": True},
                {"name": "Agent", "value": agent_name, "inline": True},
            ],
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "Boz Ripper"},
        }

        return await self._send_webhook(embeds=[embed])

    def get_status(self) -> dict:
        """Get Discord integration status."""
        return {
            "enabled": settings.discord_enabled,
            "available": self.is_available,
            "notify_on_complete": settings.discord_notify_on_complete,
            "notify_on_failure": settings.discord_notify_on_failure,
            "notify_on_organized": settings.discord_notify_on_organized,
        }
