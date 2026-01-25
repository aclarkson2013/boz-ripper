"""Plex Media Server integration for library scanning."""

import asyncio
import logging
from typing import Optional

import httpx

from boz_server.core.config import settings

logger = logging.getLogger(__name__)


class PlexClient:
    """Client for Plex Media Server API.

    S19: Triggers library scans after files are organized to NAS.
    """

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._initialized = False

    async def start(self) -> None:
        """Initialize the Plex client."""
        if not settings.plex_enabled:
            logger.info("Plex integration disabled")
            return

        if not settings.plex_token:
            logger.warning("Plex enabled but no token configured - scans will be skipped")
            return

        self._client = httpx.AsyncClient(
            base_url=settings.plex_url,
            timeout=30.0,
            headers={
                "X-Plex-Token": settings.plex_token,
                "Accept": "application/json",
            },
        )

        # Test connection
        try:
            response = await self._client.get("/")
            if response.status_code == 200:
                logger.info(f"Plex connection successful: {settings.plex_url}")
                self._initialized = True
            else:
                logger.warning(f"Plex connection test failed: {response.status_code}")
        except Exception as e:
            logger.warning(f"Could not connect to Plex: {e}")

    async def stop(self) -> None:
        """Cleanup Plex client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def is_available(self) -> bool:
        """Check if Plex integration is available."""
        return self._initialized and self._client is not None

    async def scan_library(
        self,
        library_id: str,
        path: Optional[str] = None,
    ) -> bool:
        """Trigger a library scan.

        Args:
            library_id: Plex library section ID
            path: Optional specific path to scan (more efficient)

        Returns:
            True if scan was triggered successfully
        """
        if not self.is_available:
            logger.debug("Plex not available, skipping scan")
            return False

        try:
            # Build scan URL
            url = f"/library/sections/{library_id}/refresh"
            params = {}
            if path:
                params["path"] = path

            response = await self._client.get(url, params=params)

            if response.status_code == 200:
                logger.info(
                    f"Plex library scan triggered",
                    extra={
                        "library_id": library_id,
                        "path": path,
                    },
                )
                return True
            else:
                logger.warning(
                    f"Plex scan failed: {response.status_code} - {response.text}"
                )
                return False

        except Exception as e:
            logger.error(f"Plex scan error: {e}")
            return False

    async def scan_movie_library(self, path: Optional[str] = None) -> bool:
        """Trigger a scan of the Movies library.

        Args:
            path: Optional specific path to scan

        Returns:
            True if scan was triggered
        """
        if not settings.plex_movie_library_id:
            logger.debug("No movie library ID configured")
            return False

        return await self.scan_library(settings.plex_movie_library_id, path)

    async def scan_tv_library(self, path: Optional[str] = None) -> bool:
        """Trigger a scan of the TV Shows library.

        Args:
            path: Optional specific path to scan

        Returns:
            True if scan was triggered
        """
        if not settings.plex_tv_library_id:
            logger.debug("No TV library ID configured")
            return False

        return await self.scan_library(settings.plex_tv_library_id, path)

    async def get_libraries(self) -> list[dict]:
        """Get list of all Plex libraries.

        Useful for finding library section IDs during setup.

        Returns:
            List of library info dicts
        """
        if not self.is_available:
            return []

        try:
            response = await self._client.get("/library/sections")
            if response.status_code == 200:
                data = response.json()
                directories = data.get("MediaContainer", {}).get("Directory", [])
                libraries = []
                for d in directories:
                    libraries.append({
                        "id": d.get("key"),
                        "title": d.get("title"),
                        "type": d.get("type"),
                        "path": d.get("Location", [{}])[0].get("path") if d.get("Location") else None,
                    })
                return libraries
            return []
        except Exception as e:
            logger.error(f"Failed to get Plex libraries: {e}")
            return []

    def get_status(self) -> dict:
        """Get Plex integration status."""
        return {
            "enabled": settings.plex_enabled,
            "available": self.is_available,
            "url": settings.plex_url if settings.plex_enabled else None,
            "movie_library_id": settings.plex_movie_library_id,
            "tv_library_id": settings.plex_tv_library_id,
        }
