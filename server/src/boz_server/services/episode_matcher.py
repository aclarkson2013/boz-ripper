"""Episode matching with confidence scoring."""

import logging
from typing import List, Optional

from ..models.disc import Title
from ..models.tv_show import TVEpisode, TVSeason

logger = logging.getLogger(__name__)


class EpisodeMatcher:
    """Matches disc titles to TV episodes with confidence scoring."""

    # Confidence thresholds
    HIGH_CONFIDENCE = 0.95  # Excellent match (within 10% or 2 minutes)
    MEDIUM_CONFIDENCE = 0.70  # Good match (within 20% or 5 minutes)
    LOW_CONFIDENCE = 0.40  # Uncertain match (>20% difference)
    VERY_LOW_CONFIDENCE = 0.30  # Very uncertain (no metadata or major mismatch)

    def __init__(self):
        """Initialize episode matcher."""
        pass

    def match_episodes(
        self,
        titles: List[Title],
        tv_season: TVSeason,
        starting_episode: Optional[int] = None,
    ) -> List[Title]:
        """
        Match disc titles to TV episodes using disc order (sequential matching).

        DVDs typically have episodes in sequential order by title index.
        This method:
        1. Sorts titles by index (disc order)
        2. Matches sequentially starting from specified episode
        3. Validates duration against TheTVDB metadata
        4. Assigns confidence scores based on duration match quality

        Args:
            titles: List of main (non-extra) titles from disc
            tv_season: TV season tracking object with episode metadata
            starting_episode: Episode number to start from (overrides auto-continuation)

        Returns:
            List of titles with episode info and confidence scores
        """
        if not titles:
            logger.warning("No titles to match")
            return titles

        # Determine starting episode number
        if starting_episode is not None:
            current_episode_num = starting_episode
            logger.info(f"Matching {len(titles)} titles to episodes, starting from episode {starting_episode} (user-specified)")
        else:
            current_episode_num = tv_season.next_episode_number
            logger.info(f"Matching {len(titles)} titles to episodes, starting from episode {current_episode_num} (auto-continue)")

        logger.info("Using sequential matching strategy (disc order)")

        # Sort titles by index to respect disc order
        sorted_titles = sorted(titles, key=lambda t: t.index)
        logger.info(f"Titles sorted by index: {[t.index for t in sorted_titles]}")

        # Try sequential matching
        validation_results = []

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
                    duration_diff_seconds = abs(actual_seconds - expected_seconds)
                    duration_diff_percent = duration_diff_seconds / expected_seconds if expected_seconds > 0 else 1.0

                    # NEW CONFIDENCE CALCULATION per user requirements:
                    # High (95%): Within 10% or 2 minutes (whichever is MORE permissive)
                    # Medium (70%): Within 20% or 5 minutes (whichever is MORE permissive)
                    # Low (40%): More than 20% but less than 50%
                    # Very Low (30%): More than 50%

                    if duration_diff_seconds <= 120 or duration_diff_percent <= 0.10:
                        # Within 2 minutes OR within 10% - high confidence
                        title.confidence_score = self.HIGH_CONFIDENCE
                        validation_results.append(True)
                        logger.info(
                            f"✓ Title {title.index} → S{episode.season_number:02d}E{episode.episode_number:02d}: {episode.episode_name} "
                            f"(duration match: ±{duration_diff_seconds}s, {duration_diff_percent:.1%})"
                        )
                    elif duration_diff_seconds <= 300 or duration_diff_percent <= 0.20:
                        # Within 5 minutes OR within 20% - medium confidence
                        title.confidence_score = self.MEDIUM_CONFIDENCE
                        validation_results.append(True)
                        logger.info(
                            f"~ Title {title.index} → S{episode.season_number:02d}E{episode.episode_number:02d}: {episode.episode_name} "
                            f"(duration acceptable: ±{duration_diff_seconds}s, {duration_diff_percent:.1%})"
                        )
                    elif duration_diff_percent <= 0.50:
                        # Within 50% - low confidence
                        title.confidence_score = self.LOW_CONFIDENCE
                        validation_results.append(False)
                        logger.warning(
                            f"⚠ Title {title.index} → S{episode.season_number:02d}E{episode.episode_number:02d}: {episode.episode_name} "
                            f"(duration mismatch: ±{duration_diff_seconds}s, {duration_diff_percent:.1%})"
                        )
                    else:
                        # Significant mismatch - very low confidence
                        title.confidence_score = self.VERY_LOW_CONFIDENCE
                        validation_results.append(False)
                        logger.warning(
                            f"✗ Title {title.index} → S{episode.season_number:02d}E{episode.episode_number:02d}: {episode.episode_name} "
                            f"(significant duration mismatch: ±{duration_diff_seconds}s, {duration_diff_percent:.1%})"
                        )
                else:
                    # No runtime metadata, assume low confidence
                    title.confidence_score = self.LOW_CONFIDENCE
                    validation_results.append(False)
                    logger.info(
                        f"? Title {title.index} → S{episode.season_number:02d}E{episode.episode_number:02d}: {episode.episode_name} "
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
                validation_results.append(False)
                logger.warning(
                    f"? Title {title.index} → Episode {current_episode_num} "
                    f"(no metadata available - beyond known episodes)"
                )

                # Still increment and mark assigned
                tv_season.mark_episode_assigned(current_episode_num)
                current_episode_num += 1

        # Log validation summary
        if validation_results:
            valid_count = sum(validation_results)
            total_count = len(validation_results)
            validation_rate = (valid_count / total_count) * 100
            logger.info(
                f"Sequential matching validation: {valid_count}/{total_count} titles validated ({validation_rate:.0f}%)"
            )

            if validation_rate < 50:
                logger.warning(
                    f"⚠ Low validation rate ({validation_rate:.0f}%) - episodes may be mismatched. "
                    f"Please review season/episode numbers in preview page!"
                )
            elif validation_rate < 80:
                logger.info(
                    f"Sequential matching looks acceptable ({validation_rate:.0f}% validated). "
                    f"Review low-confidence matches in preview page."
                )
            else:
                logger.info(f"✓ Sequential matching looks good ({validation_rate:.0f}% validated)")

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

    @staticmethod
    def get_confidence_symbol(confidence: float) -> str:
        """
        Get validation symbol for confidence score.

        Args:
            confidence: Confidence score (0-1)

        Returns:
            Symbol like "✓", "~", "⚠", "✗"
        """
        if confidence >= EpisodeMatcher.HIGH_CONFIDENCE:
            return "✓"
        elif confidence >= EpisodeMatcher.MEDIUM_CONFIDENCE:
            return "~"
        elif confidence >= EpisodeMatcher.LOW_CONFIDENCE:
            return "⚠"
        else:
            return "✗"
