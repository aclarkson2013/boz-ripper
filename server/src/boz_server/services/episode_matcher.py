"""Episode matching with confidence scoring."""

import logging
from typing import List, Optional

from ..models.disc import Title
from ..models.tv_show import TVEpisode, TVSeason

logger = logging.getLogger(__name__)


class EpisodeMatcher:
    """Matches disc titles to TV episodes with confidence scoring."""

    # Confidence thresholds
    HIGH_CONFIDENCE = 0.9  # Good match (duration within tolerance)
    MEDIUM_CONFIDENCE = 0.7  # Acceptable match (duration mismatch but sequential)
    LOW_CONFIDENCE = 0.5  # Uncertain match (significant duration mismatch)
    VERY_LOW_CONFIDENCE = 0.3  # Very uncertain (unknown episode)

    # Duration tolerance for matching (±20%)
    DURATION_TOLERANCE = 0.2

    def __init__(self):
        """Initialize episode matcher."""
        pass

    def match_episodes(
        self,
        titles: List[Title],
        tv_season: TVSeason,
    ) -> List[Title]:
        """
        Match disc titles to TV episodes sequentially.

        Args:
            titles: List of main (non-extra) titles from disc
            tv_season: TV season tracking object with episode metadata

        Returns:
            List of titles with episode info and confidence scores
        """
        if not titles or not tv_season.episodes:
            logger.warning("No titles or episodes to match")
            return titles

        logger.info(f"Matching {len(titles)} titles to episodes, starting from episode {tv_season.next_episode_number}")

        # Sort titles by duration (longest first) to ensure we process them in order
        sorted_titles = sorted(titles, key=lambda t: t.duration_seconds, reverse=True)

        # Get starting episode number
        current_episode_num = tv_season.next_episode_number

        for title in sorted_titles:
            episode = tv_season.get_episode(current_episode_num)

            if episode:
                # We have metadata for this episode
                title.episode_number = episode.episode_number
                title.episode_title = episode.episode_name

                # Calculate confidence based on duration match
                if episode.runtime:
                    expected_seconds = episode.runtime * 60
                    actual_seconds = title.duration_seconds

                    duration_diff = abs(actual_seconds - expected_seconds) / expected_seconds

                    if duration_diff <= self.DURATION_TOLERANCE:
                        # Duration matches well
                        title.confidence_score = self.HIGH_CONFIDENCE
                        logger.info(
                            f"Title {title.index} matched to episode {episode.episode_number} "
                            f"with high confidence (duration match: {duration_diff:.1%})"
                        )
                    elif duration_diff <= 0.5:
                        # Duration somewhat off but acceptable
                        title.confidence_score = self.MEDIUM_CONFIDENCE
                        logger.info(
                            f"Title {title.index} matched to episode {episode.episode_number} "
                            f"with medium confidence (duration diff: {duration_diff:.1%})"
                        )
                    else:
                        # Significant duration mismatch
                        title.confidence_score = self.LOW_CONFIDENCE
                        logger.warning(
                            f"Title {title.index} matched to episode {episode.episode_number} "
                            f"with low confidence (duration diff: {duration_diff:.1%})"
                        )
                else:
                    # No runtime metadata, assume medium confidence
                    title.confidence_score = self.MEDIUM_CONFIDENCE
                    logger.info(
                        f"Title {title.index} matched to episode {episode.episode_number} "
                        f"(no runtime metadata available)"
                    )

                # Mark episode as assigned
                tv_season.mark_episode_assigned(current_episode_num)
                current_episode_num += 1

            else:
                # No episode metadata available (beyond known episodes)
                title.episode_number = current_episode_num
                title.episode_title = f"Episode {current_episode_num}"
                title.confidence_score = self.VERY_LOW_CONFIDENCE
                logger.warning(
                    f"Title {title.index} assigned to episode {current_episode_num} "
                    f"with very low confidence (no metadata available)"
                )

                # Still increment and mark assigned
                tv_season.mark_episode_assigned(current_episode_num)
                current_episode_num += 1

        return sorted_titles

    @staticmethod
    def get_confidence_label(confidence: float) -> str:
        """
        Get human-readable label for confidence score.

        Args:
            confidence: Confidence score (0-1)

        Returns:
            Label like "High", "Medium", "Low"
        """
        if confidence >= EpisodeMatcher.HIGH_CONFIDENCE:
            return "High"
        elif confidence >= EpisodeMatcher.MEDIUM_CONFIDENCE:
            return "Medium"
        elif confidence >= EpisodeMatcher.LOW_CONFIDENCE:
            return "Low"
        else:
            return "Very Low"
