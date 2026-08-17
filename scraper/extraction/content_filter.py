"""Boilerplate, Navigation, and Spam/Thin Content Filter (DS-SI30, DS-SI31)."""

import re
from typing import Tuple
from pydantic import BaseModel


class ContentFilterResult(BaseModel):
    is_valid: bool = True
    main_text_ratio: float = 1.0
    link_density: float = 0.0
    is_spam: bool = False
    is_navigation_only: bool = False
    rejection_reason: str = ""


class ContentFilter:
    """Filters out navigation-heavy, advertising spam, and thin templated content."""

    @staticmethod
    def inspect_content(raw_text: str) -> ContentFilterResult:
        if not raw_text or len(raw_text.strip()) < 80:
            return ContentFilterResult(
                is_valid=False,
                main_text_ratio=0.0,
                rejection_reason="THIN_CONTENT_TOO_SHORT",
            )

        lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
        total_chars = sum(len(l) for l in lines)
        total_words = sum(len(l.split()) for l in lines)

        # 1. Link density in markdown (approx count of markdown links vs total words)
        link_matches = re.findall(r'\[([^\]]+)\]\([^\)]+\)', raw_text)
        link_words = sum(len(m.split()) for m in link_matches)
        link_density = link_words / max(total_words, 1)

        # If > 65% of words are links, it is likely a tag/directory page
        is_nav = link_density > 0.65

        # 2. Check for cookie/consent/boilerplate banner domination
        boilerplate_terms = ["cookie policy", "terms of use", "privacy policy", "all rights reserved", "accept all cookies", "согласие на обработку"]
        bp_count = sum(1 for bp in boilerplate_terms if bp in raw_text.lower())
        is_bp_dominated = bp_count >= 3 and len(raw_text) < 500

        # 3. Spam / repetitive templating
        unique_lines = set(lines)
        repetition_ratio = len(unique_lines) / max(len(lines), 1)
        is_spam = repetition_ratio < 0.35 and len(lines) > 10

        is_valid = not (is_nav or is_bp_dominated or is_spam)
        reason = ""
        if is_nav:
            reason = "NAVIGATION_DIRECTORY_PAGE"
        elif is_bp_dominated:
            reason = "BOILERPLATE_DOMINATED"
        elif is_spam:
            reason = "REPETITIVE_SPAM_TEMPLATE"

        return ContentFilterResult(
            is_valid=is_valid,
            main_text_ratio=1.0 - link_density,
            link_density=round(link_density, 3),
            is_spam=is_spam,
            is_navigation_only=is_nav,
            rejection_reason=reason,
        )


content_filter = ContentFilter()
