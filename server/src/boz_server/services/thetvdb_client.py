"""TheTVDB API client for fetching TV show metadata."""

import logging
from typing import Optional
from datetime import datetime, timedelta

import httpx

from ..models.tv_show import TVEpisode

logger = logging.getLogger(__name__)


class TheTVDBClient:
    """Client for TheTVDB v4 API."""

    BASE_URL = "https://api4.thetvdb.com/v4"
    TOKEN_EXPIRY_BUFFER = timedelta(hours=1)  # Refresh token 1 hour before expiry

    def __init__(self, api_key: str):
        """
        Initialize TheTVDB client.

        Args:
            api_key: TheTVDB v4 API key
        """
        self.api_key = api_key
        self._token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def _get_token(self) -> str:
        """
        Get or refresh authentication token.

        Returns:
            JWT token for API requests

        Raises:
            Exception: If authentication fails
        """
        # Check if token is still valid
        if self._token and self._token_expires_at:
            if datetime.utcnow() < self._token_expires_at - self.TOKEN_EXPIRY_BUFFER:
                return self._token

        # Authenticate to get new token
        logger.info("Authenticating with TheTVDB API")
        response = await self._client.post(
            f"{self.BASE_URL}/login",
            json={"apikey": self.api_key},
        )

        if response.status_code != 200:
            logger.error(f"TheTVDB authentication failed: {response.status_code} {response.text}")
            raise Exception(f"TheTVDB authentication failed: {response.status_code}")

        data = response.json()
        self._token = data["data"]["token"]

        # TheTVDB tokens typically last 30 days
        self._token_expires_at = datetime.utcnow() + timedelta(days=29)

        logger.info("Successfully authenticated with TheTVDB")
        return self._token

    async def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """
        Make authenticated request to TheTVDB API.

        Args:
            method: HTTP method
            endpoint: API endpoint (without base URL)
            **kwargs: Additional arguments for httpx request

        Returns:
            Response JSON data

        Raises:
            Exception: If request fails
        """
        token = await self._get_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"

        response = await self._client.request(
            method,
            f"{self.BASE_URL}/{endpoint}",
            headers=headers,
            **kwargs,
        )

        if response.status_code != 200:
            logger.error(f"TheTVDB request failed: {method} {endpoint} -> {response.status_code}")
            raise Exception(f"TheTVDB request failed: {response.status_code}")

        return response.json()

    async def search_series(self, name: str) -> Optional[int]:
        """
        Search for a TV series by name.

        Args:
            name: Show name to search for

        Returns:
            Series ID if found, None otherwise
        """
        logger.info(f"Searching TheTVDB for series: {name}")

        try:
            data = await self._request("GET", "search", params={"query": name, "type": "series"})

            if not data.get("data"):
                logger.warning(f"No results found for series: {name}")
                return None

            # Return first result (most relevant)
            series = data["data"][0]
            series_id = series.get("tvdb_id")

            if series_id:
                logger.info(f"Found series '{series.get('name')}' with ID: {series_id}")
                return int(series_id)

            return None

        except Exception as e:
            logger.error(f"Error searching for series '{name}': {e}")
            return None

    async def get_season_episodes(self, series_id: int, season_number: int) -> list[TVEpisode]:
        """
        Get all episodes for a specific season.

        Args:
            series_id: TheTVDB series ID
            season_number: Season number

        Returns:
            List of episodes for the season
        """
        logger.info(f"Fetching episodes for series {series_id}, season {season_number}")

        try:
            # Get extended series info with episodes
            data = await self._request("GET", f"series/{series_id}/episodes/default")

            if not data.get("data") or "episodes" not in data["data"]:
                logger.warning(f"No episodes found for series {series_id}")
                return []

            # Filter episodes for the requested season
            episodes = []
            for episode_data in data["data"]["episodes"]:
                if episode_data.get("seasonNumber") == season_number:
                    episode = TVEpisode(
                        episode_number=episode_data.get("number", 0),
                        episode_name=episode_data.get("name", "Unknown Episode"),
                        season_number=season_number,
                        runtime=episode_data.get("runtime"),
                        overview=episode_data.get("overview"),
                    )
                    episodes.append(episode)

            # Sort by episode number
            episodes.sort(key=lambda e: e.episode_number)

            logger.info(f"Found {len(episodes)} episodes for season {season_number}")
            return episodes

        except Exception as e:
            logger.error(f"Error fetching episodes for series {series_id}, season {season_number}: {e}")
            return []
