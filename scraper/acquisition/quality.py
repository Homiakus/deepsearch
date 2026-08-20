"""Acquisition Quality Evaluator (§4, DS-RB05).

Evaluates page quality beyond HTTP 200, detecting empty SPA shells, false-200 block pages,
and suggesting optimal backend escalation paths.
"""

import re
from typing import Dict, List, Optional
from scraper.acquisition.models import QualityReport


class AcquisitionQualityEvaluator:
    """Computes comprehensive quality score and escalation hints."""

    BLOCK_PATTERNS = [
        re.compile(r"cloudflare", re.I),
        re.compile(r"attention required", re.I),
        re.compile(r"access denied", re.I),
        re.compile(r"captcha", re.I),
        re.compile(r"datadome", re.I),
        re.compile(r"perimeterx", re.I),
        re.compile(r"security check", re.I),
        re.compile(r"please verify you are a human", re.I),
        re.compile(r"bot detection", re.I),
        re.compile(r"checking your browser before accessing", re.I),
    ]

    UNRENDERED_SPA_PATTERNS = [
        re.compile(r"<div\s+id=[\"']root[\"']\s*>\s*</div>", re.I),
        re.compile(r"<div\s+id=[\"']app[\"']\s*>\s*</div>", re.I),
        re.compile(r"<div\s+id=[\"']__next[\"']\s*>\s*</div>", re.I),
        re.compile(r"you need to enable javascript to run this app", re.I),
        re.compile(r"please enable javascript", re.I),
    ]

    def evaluate(
        self,
        url: str,
        status_code: int,
        headers: Dict[str, str],
        html_or_text: str,
        expected_min_text_chars: int = 100,
        expected_selectors: Optional[List[str]] = None,
    ) -> QualityReport:
        reasons: List[str] = []
        score = 1.0
        completeness = 1.0
        blocked = False
        likely_unrendered = False
        suggested_escalation: Optional[str] = None

        # 1. HTTP Status sanity
        if status_code >= 400:
            score -= 0.6
            completeness = 0.0
            reasons.append(f"HTTP error status: {status_code}")
            if status_code in (403, 429):
                blocked = True
                reasons.append("Rate limit or access forbidden")
                suggested_escalation = "chromium"

        # 2. Content Type Check
        content_type = headers.get("content-type", "").lower()
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            if "application/json" in content_type:
                # Could be structured API result or JSON error
                pass

        # 3. Block page detection
        text_sample = html_or_text[:10000]
        for pattern in self.BLOCK_PATTERNS:
            if pattern.search(text_sample):
                blocked = True
                score -= 0.5
                reasons.append(f"Block/Challenge pattern detected: {pattern.pattern}")
                suggested_escalation = "chromium"
                break

        # 4. Unrendered SPA shell detection
        for pattern in self.UNRENDERED_SPA_PATTERNS:
            if pattern.search(text_sample):
                likely_unrendered = True
                score -= 0.4
                completeness = min(completeness, 0.3)
                reasons.append("Empty SPA root or disabled JS message detected")
                if not suggested_escalation:
                    suggested_escalation = "servo"
                break

        # 5. Useful text content evaluation
        # Strip HTML tags
        clean_text = re.sub(r"<[^>]+>", " ", html_or_text)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()
        text_len = len(clean_text)

        if text_len < expected_min_text_chars:
            score -= 0.3
            completeness = min(
                completeness, max(0.1, text_len / max(expected_min_text_chars, 1))
            )
            reasons.append(
                f"Low useful text characters: {text_len} < {expected_min_text_chars}"
            )
            if not suggested_escalation and not blocked:
                suggested_escalation = "servo"

        # 6. Expected selectors check
        if expected_selectors:
            missing = [sel for sel in expected_selectors if sel not in html_or_text]
            if missing:
                completeness -= 0.2 * (len(missing) / len(expected_selectors))
                reasons.append(f"Missing expected selectors: {missing}")

        final_score = max(0.0, min(1.0, score))
        final_completeness = max(0.0, min(1.0, completeness))

        return QualityReport(
            score=round(final_score, 3),
            completeness=round(final_completeness, 3),
            blocked=blocked,
            likely_unrendered=likely_unrendered,
            reasons=reasons,
            suggested_escalation=suggested_escalation,
        )
