"""OMDb API client for fetching movie metadata."""

import logging
import re
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class MovieMetadata:
    """Movie metadata from OMDb."""

    title: str
    year: int
    imdb_id: str
    plot: Optional[str] = None
    director: Optional[str] = None
    runtime_minutes: Optional[int] = None
    genre: Optional[str] = None
    poster_url: Optional[str] = None
    imdb_rating: Optional[float] = None
    confidence: float = 1.0  # Search confidence (1.0 = exact match)


class OMDbClient:
    """Client for OMDb API (Open Movie Database)."""

    BASE_URL = "https://www.omdbapi.com"

    def __init__(self, api_key: str):
        """
        Initialize OMDb client.

        Args:
            api_key: OMDb API key
        """
        self.api_key = api_key
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def search_movie(self, title: str, year: Optional[int] = None) -> Optional[MovieMetadata]:
        """
        Search for a movie by title.

        Args:
            title: Movie title to search for
            year: Optional release year to narrow search

        Returns:
            MovieMetadata if found, None otherwise
        """
        logger.info(f"Searching OMDb for movie: {title}" + (f" ({year})" if year else ""))

        # Clean up the title for searching
        search_title = self._clean_search_title(title)

        try:
            # First try exact search with title (and year if provided)
            params = {
                "apikey": self.api_key,
                "t": search_title,
                "type": "movie",
            }
            if year:
                params["y"] = str(year)

            response = await self._client.get(self.BASE_URL, params=params)

            if response.status_code != 200:
                logger.error(f"OMDb request failed: {response.status_code}")
                return None

            data = response.json()

            if data.get("Response") == "True":
                movie = self._parse_movie_response(data)
                movie.confidence = self._calculate_confidence(title, movie.title, year, movie.year)
                logger.info(f"Found movie: {movie.title} ({movie.year}) - confidence: {movie.confidence:.2f}")
                return movie

            # If exact search fails, try search API for multiple results
            logger.debug(f"Exact search failed, trying search API for: {search_title}")
            return await self._search_multiple(search_title, year, title)

        except Exception as e:
            logger.error(f"Error searching for movie '{title}': {e}")
            return None

    async def _search_multiple(
        self, search_title: str, year: Optional[int], original_title: str
    ) -> Optional[MovieMetadata]:
        """
        Search using OMDb search API for multiple results.

        Args:
            search_title: Cleaned search title
            year: Optional release year
            original_title: Original title from disc for confidence calculation

        Returns:
            Best matching MovieMetadata or None
        """
        params = {
            "apikey": self.api_key,
            "s": search_title,
            "type": "movie",
        }
        if year:
            params["y"] = str(year)

        response = await self._client.get(self.BASE_URL, params=params)

        if response.status_code != 200:
            return None

        data = response.json()

        if data.get("Response") != "True" or not data.get("Search"):
            logger.debug(f"No search results found for: {search_title}")
            return None

        # Find best match from results
        best_match = None
        best_confidence = 0.0

        for result in data["Search"][:5]:  # Check top 5 results
            result_year = int(result.get("Year", "0").split("-")[0]) if result.get("Year") else 0
            confidence = self._calculate_confidence(
                original_title, result.get("Title", ""), year, result_year
            )

            if confidence > best_confidence:
                best_confidence = confidence
                best_match = result

        if best_match and best_confidence >= 0.5:  # Minimum 50% confidence
            # Fetch full details for the best match
            full_movie = await self.get_movie_by_id(best_match["imdbID"])
            if full_movie:
                full_movie.confidence = best_confidence
                return full_movie

        return None

    async def get_movie_by_id(self, imdb_id: str) -> Optional[MovieMetadata]:
        """
        Get movie by IMDb ID.

        Args:
            imdb_id: IMDb ID (e.g., "tt0111161")

        Returns:
            MovieMetadata if found, None otherwise
        """
        logger.debug(f"Fetching movie by IMDb ID: {imdb_id}")

        try:
            params = {
                "apikey": self.api_key,
                "i": imdb_id,
                "type": "movie",
            }

            response = await self._client.get(self.BASE_URL, params=params)

            if response.status_code != 200:
                logger.error(f"OMDb request failed: {response.status_code}")
                return None

            data = response.json()

            if data.get("Response") == "True":
                return self._parse_movie_response(data)

            return None

        except Exception as e:
            logger.error(f"Error fetching movie by ID '{imdb_id}': {e}")
            return None

    def _parse_movie_response(self, data: dict) -> MovieMetadata:
        """Parse OMDb API response into MovieMetadata."""
        # Parse runtime (e.g., "142 min" -> 142)
        runtime = None
        if data.get("Runtime") and data["Runtime"] != "N/A":
            match = re.match(r"(\d+)", data["Runtime"])
            if match:
                runtime = int(match.group(1))

        # Parse year
        year_str = data.get("Year", "0")
        # Handle year ranges like "2008-2013" (take first year)
        year = int(year_str.split("-")[0]) if year_str and year_str != "N/A" else 0

        # Parse IMDb rating
        rating = None
        if data.get("imdbRating") and data["imdbRating"] != "N/A":
            try:
                rating = float(data["imdbRating"])
            except ValueError:
                pass

        return MovieMetadata(
            title=data.get("Title", "Unknown"),
            year=year,
            imdb_id=data.get("imdbID", ""),
            plot=data.get("Plot") if data.get("Plot") != "N/A" else None,
            director=data.get("Director") if data.get("Director") != "N/A" else None,
            runtime_minutes=runtime,
            genre=data.get("Genre") if data.get("Genre") != "N/A" else None,
            poster_url=data.get("Poster") if data.get("Poster") != "N/A" else None,
            imdb_rating=rating,
        )

    def _clean_search_title(self, title: str) -> str:
        """
        Clean disc name for movie searching.

        Removes common disc artifacts like:
        - Underscores and extra punctuation
        - Year in parentheses (we'll add it separately)
        - Common disc suffixes (DISC1, DVD, etc.)
        - Studio codes

        Args:
            title: Raw disc name

        Returns:
            Cleaned title for searching
        """
        cleaned = title

        # Replace underscores with spaces
        cleaned = cleaned.replace("_", " ")

        # Remove disc/DVD/Blu-ray indicators
        cleaned = re.sub(r"\b(DISC|DISK|DVD|BD|BLURAY|BLU-RAY)\s*\d*\b", "", cleaned, flags=re.IGNORECASE)

        # Remove edition indicators
        cleaned = re.sub(
            r"\b(EXTENDED|UNRATED|DIRECTORS?\s*CUT|SPECIAL\s*EDITION|COLLECTORS?\s*EDITION|ANNIVERSARY|REMASTERED)\b",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

        # Remove year in parentheses (we'll use it separately if provided)
        cleaned = re.sub(r"\(\d{4}\)", "", cleaned)

        # Remove trailing numbers that might be disc numbers
        cleaned = re.sub(r"\s+\d+$", "", cleaned)

        # Remove common studio codes at beginning
        cleaned = re.sub(r"^[A-Z]{2,4}[-_]", "", cleaned)

        # Clean up multiple spaces
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        return cleaned

    def _calculate_confidence(
        self,
        search_title: str,
        result_title: str,
        search_year: Optional[int],
        result_year: int,
    ) -> float:
        """
        Calculate confidence score for a search result.

        Args:
            search_title: Original search title
            result_title: Title from search result
            search_year: Year we searched for (if any)
            result_year: Year from result

        Returns:
            Confidence score between 0 and 1
        """
        # Normalize titles for comparison
        search_normalized = self._normalize_for_comparison(search_title)
        result_normalized = self._normalize_for_comparison(result_title)

        # Calculate title similarity
        title_similarity = self._string_similarity(search_normalized, result_normalized)

        # Year matching bonus/penalty
        year_factor = 1.0
        if search_year and result_year:
            year_diff = abs(search_year - result_year)
            if year_diff == 0:
                year_factor = 1.1  # Bonus for exact year match
            elif year_diff == 1:
                year_factor = 1.0  # Off by one is OK
            elif year_diff <= 3:
                year_factor = 0.9  # Slight penalty
            else:
                year_factor = 0.7  # Larger penalty for wrong year

        confidence = min(1.0, title_similarity * year_factor)
        return confidence

    def _normalize_for_comparison(self, title: str) -> str:
        """Normalize title for comparison."""
        normalized = title.lower()
        # Remove common articles
        normalized = re.sub(r"^(the|a|an)\s+", "", normalized)
        # Remove non-alphanumeric characters
        normalized = re.sub(r"[^a-z0-9\s]", "", normalized)
        # Collapse whitespace
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _string_similarity(self, s1: str, s2: str) -> float:
        """
        Calculate similarity between two strings using a simple algorithm.

        Returns value between 0 and 1.
        """
        if not s1 or not s2:
            return 0.0

        if s1 == s2:
            return 1.0

        # Check if one contains the other
        if s1 in s2 or s2 in s1:
            shorter = min(len(s1), len(s2))
            longer = max(len(s1), len(s2))
            return shorter / longer

        # Word overlap
        words1 = set(s1.split())
        words2 = set(s2.split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        return len(intersection) / len(union)
