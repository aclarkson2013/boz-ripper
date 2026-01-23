"""TV show detection from disc names."""

import re
from typing import Optional, Tuple


class TVShowDetector:
    """Detects TV shows from disc names using pattern matching."""

    # Pattern: "Show Name S01" or "Show Name Season 1"
    SEASON_PATTERNS = [
        r"^(.+?)\s+S(?:eason\s*)?(\d{1,2})(?:\s|$)",  # "Breaking Bad S01" or "Breaking Bad Season 1"
        r"^(.+?)\s+(?:Season|Series)\s*(\d{1,2})(?:\s|$)",  # "Breaking Bad Season 1"
        r"^(.+?)\s+-\s+S(?:eason\s*)?(\d{1,2})(?:\s|$)",  # "Breaking Bad - S01"
        r"^(.+?)\s+-\s+(?:Season|Series)\s*(\d{1,2})(?:\s|$)",  # "Breaking Bad - Season 1"
    ]

    # Pattern: "Show Name Disc 1" (implies TV show if multiple discs expected)
    DISC_PATTERNS = [
        r"^(.+?)\s+(?:Disc|Disk|D)(?:\s*)?(\d{1,2})(?:\s|$)",  # "Show Name Disc 1"
        r"^(.+?)\s+-\s+(?:Disc|Disk|D)(?:\s*)?(\d{1,2})(?:\s|$)",  # "Show Name - Disc 1"
    ]

    # Additional TV show indicators
    TV_KEYWORDS = [
        "complete series",
        "complete season",
        "the complete",
        "episodes",
        "collection",
    ]

    @staticmethod
    def detect(disc_name: str, enable_ambiguous_search: bool = True) -> Tuple[bool, Optional[str], Optional[int]]:
        """
        Detect if disc is a TV show and extract metadata.

        Args:
            disc_name: Name of the disc
            enable_ambiguous_search: If True, ambiguous names will be flagged for TheTVDB search

        Returns:
            Tuple of (is_tv_show, show_name, season_number)
        """
        import logging
        logger = logging.getLogger(__name__)

        if not disc_name:
            logger.debug("TV detection: Empty disc name")
            return False, None, None

        disc_name_normalized = disc_name.strip()
        logger.info(f"TV detection: Analyzing disc name: '{disc_name_normalized}'")

        # Try season patterns first
        for pattern in TVShowDetector.SEASON_PATTERNS:
            match = re.search(pattern, disc_name_normalized, re.IGNORECASE)
            if match:
                show_name = match.group(1).strip()
                season_number = int(match.group(2))
                logger.info(f"TV detection: Matched season pattern - Show: '{show_name}', Season: {season_number}")
                return True, show_name, season_number

        # Try disc patterns (likely TV show if labeled as disc)
        for pattern in TVShowDetector.DISC_PATTERNS:
            match = re.search(pattern, disc_name_normalized, re.IGNORECASE)
            if match:
                show_name = match.group(1).strip()
                # Disc pattern doesn't give season, assume Season 1
                logger.info(f"TV detection: Matched disc pattern - Show: '{show_name}', Season: 1 (assumed)")
                return True, show_name, 1

        # Check for TV show keywords
        disc_name_lower = disc_name_normalized.lower()
        for keyword in TVShowDetector.TV_KEYWORDS:
            if keyword in disc_name_lower:
                # Extract show name by removing the keyword
                show_name = disc_name_lower.replace(keyword, "").strip()
                show_name = show_name.split("-")[0].strip()  # Remove trailing parts
                if show_name:
                    # Restore proper capitalization
                    show_name = disc_name_normalized.split(keyword)[0].strip()
                    show_name = show_name.split("-")[0].strip()
                    logger.info(f"TV detection: Matched keyword '{keyword}' - Show: '{show_name}', Season: 1 (assumed)")
                    return True, show_name, 1

        # Fallback: Check if disc name is short/ambiguous and could be a TV show
        # This allows TheTVDB search for names like "OFFICE", "FRIENDS", etc.
        if enable_ambiguous_search:
            # Short names (1-3 words) without clear movie indicators might be TV shows
            words = disc_name_normalized.split()
            movie_indicators = ["(19", "(20", "blu-ray", "dvd", "edition"]
            has_movie_indicator = any(indicator in disc_name_lower for indicator in movie_indicators)

            if 1 <= len(words) <= 3 and not has_movie_indicator:
                logger.info(f"TV detection: Ambiguous name detected, will search TheTVDB - Show: '{disc_name_normalized}', Season: 1 (assumed)")
                return True, disc_name_normalized, 1

        logger.info(f"TV detection: No TV show patterns matched for '{disc_name_normalized}'")
        return False, None, None

    @staticmethod
    def normalize_show_name(show_name: str) -> str:
        """
        Normalize show name for consistent matching.

        Args:
            show_name: Raw show name

        Returns:
            Normalized show name
        """
        # Remove common suffixes
        normalized = show_name.strip()
        normalized = re.sub(r"\s*-\s*$", "", normalized)  # Trailing dash
        normalized = re.sub(r"\s*:\s*$", "", normalized)  # Trailing colon
        normalized = re.sub(r"\s+", " ", normalized)  # Multiple spaces
        return normalized.strip()
