"""Extras and bonus content detection."""

import logging
import statistics
from typing import List

from ..models.disc import Title

logger = logging.getLogger(__name__)


class ExtrasFilter:
    """Detects extras and bonus content using duration and keyword analysis."""

    # Keywords that indicate bonus content
    EXTRA_KEYWORDS = [
        "bonus",
        "extra",
        "behind",
        "making of",
        "blooper",
        "deleted scene",
        "gag reel",
        "interview",
        "featurette",
        "commentary",
        "trailer",
        "preview",
        "commercial",
        "promo",
    ]

    def __init__(
        self,
        min_duration_seconds: int = 600,  # 10 minutes
        duration_variance_threshold: float = 0.4,  # 40%
    ):
        """
        Initialize extras filter.

        Args:
            min_duration_seconds: Titles shorter than this are likely extras
            duration_variance_threshold: Titles with duration >X% different from median are likely extras
        """
        self.min_duration_seconds = min_duration_seconds
        self.duration_variance_threshold = duration_variance_threshold

    def filter_extras(self, titles: List[Title]) -> List[Title]:
        """
        Mark titles that are likely extras.

        Args:
            titles: List of titles to analyze

        Returns:
            List of titles with is_extra flag updated
        """
        if not titles:
            return titles

        logger.info(f"Analyzing {len(titles)} titles for extras")

        # Step 1: Check duration threshold
        for title in titles:
            if title.duration_seconds < self.min_duration_seconds:
                title.is_extra = True
                logger.debug(f"Title {title.index} marked as extra (short duration: {title.duration_formatted})")

        # Step 2: Check for keyword matches in title names
        for title in titles:
            title_lower = title.name.lower()
            for keyword in self.EXTRA_KEYWORDS:
                if keyword in title_lower:
                    title.is_extra = True
                    logger.debug(f"Title {title.index} marked as extra (keyword: '{keyword}')")
                    break

        # Step 3: Check duration variance from median (for remaining non-extra titles)
        non_extra_titles = [t for t in titles if not t.is_extra]
        if len(non_extra_titles) >= 3:
            durations = [t.duration_seconds for t in non_extra_titles]
            median_duration = statistics.median(durations)

            for title in non_extra_titles:
                variance = abs(title.duration_seconds - median_duration) / median_duration
                if variance > self.duration_variance_threshold:
                    title.is_extra = True
                    logger.debug(
                        f"Title {title.index} marked as extra (duration variance: {variance:.2%} from median)"
                    )

        extras_count = sum(1 for t in titles if t.is_extra)
        logger.info(f"Identified {extras_count} extras out of {len(titles)} titles")

        return titles

    def get_main_titles(self, titles: List[Title]) -> List[Title]:
        """
        Get only main content titles (non-extras).

        Args:
            titles: List of titles

        Returns:
            List of non-extra titles sorted by duration (longest first)
        """
        main_titles = [t for t in titles if not t.is_extra]
        main_titles.sort(key=lambda t: t.duration_seconds, reverse=True)
        return main_titles

    def get_extras(self, titles: List[Title]) -> List[Title]:
        """
        Get only extra titles.

        Args:
            titles: List of titles

        Returns:
            List of extra titles
        """
        return [t for t in titles if t.is_extra]
