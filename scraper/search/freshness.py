"""Freshness Scoring Engine (DS-SI19)."""

import time

from scraper.research.intent import FreshnessRequirement


def calculate_freshness_score(
    published_at: str | None,
    requirement: FreshnessRequirement = FreshnessRequirement.NONE,
) -> float:
    """Calculates freshness score according to research intent requirement."""
    if requirement == FreshnessRequirement.NONE:
        return 0.5  # Neutral freshness for timeless/historical facts

    if not published_at:
        return (
            0.4
            if requirement in (FreshnessRequirement.HIGH, FreshnessRequirement.REALTIME)
            else 0.5
        )

    # Try parsing publication year/date
    try:
        import re

        year_match = re.search(r"\b(19\d{2}|20\d{2})\b", str(published_at))
        if year_match:
            pub_year = int(year_match.group(0))
            cur_year = time.gmtime().tm_year
            age_years = max(0, cur_year - pub_year)

            if requirement == FreshnessRequirement.REALTIME:
                return 1.0 if age_years == 0 else max(0.1, 1.0 - 0.4 * age_years)
            elif requirement == FreshnessRequirement.HIGH:
                return max(0.2, 1.0 - 0.2 * age_years)
            elif requirement == FreshnessRequirement.MEDIUM:
                return max(0.3, 1.0 - 0.1 * age_years)
            else:
                return 0.6
    except Exception:
        pass

    return 0.5
