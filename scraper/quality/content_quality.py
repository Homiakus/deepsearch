"""Multi-signal content quality evaluator (§52, DS-A19)."""

import re
from typing import Optional
from scraper.quality.models import ContentQualityReport, QualityDecision


class ContentQualityEvaluator:
    """Evaluates text density, boilerplate, shell/challenge markers, and completeness."""

    CHALLENGE_PATTERNS = [
        r"please enable javascript",
        r"checking your browser",
        r"cloudflare",
        r"ddos-guard",
        r"access denied",
        r"captcha",
        r"verify you are human",
        r"security check",
    ]

    def evaluate_text(
        self, text: str, raw_html: Optional[str] = None
    ) -> ContentQualityReport:
        if not text or len(text.strip()) == 0:
            return ContentQualityReport(
                decision=QualityDecision.ESCALATE,
                overall_score=0.0,
                text_density=0.0,
                boilerplate_ratio=1.0,
                is_challenge_or_shell=True,
                details={"reason": "Empty content"},
            )

        text_lower = text.lower()
        # Challenge / shell detection
        for pat in self.CHALLENGE_PATTERNS:
            if re.search(pat, text_lower):
                return ContentQualityReport(
                    decision=QualityDecision.ESCALATE,
                    overall_score=0.1,
                    text_density=0.1,
                    is_challenge_or_shell=True,
                    details={"challenge_detected": pat},
                )

        word_count = len(text.split())
        raw_len = len(raw_html) if raw_html else len(text)
        text_density = min(1.0, len(text) / max(raw_len, 1))

        # Very short text (< 40 words) with large raw HTML indicates boilerplate / shell
        if word_count < 30 and raw_len > 1500:
            return ContentQualityReport(
                decision=QualityDecision.ESCALATE,
                overall_score=0.25,
                text_density=text_density,
                boilerplate_ratio=0.8,
                details={"reason": "Low word count relative to DOM size"},
            )

        if word_count < 10:
            return ContentQualityReport(
                decision=QualityDecision.DISCARD,
                overall_score=0.1,
                text_density=text_density,
                details={"reason": "Insufficient content"},
            )

        # Standard accepted content
        score = min(1.0, 0.4 + 0.6 * min(1.0, word_count / 300.0))
        return ContentQualityReport(
            decision=QualityDecision.ACCEPT,
            overall_score=round(score, 3),
            text_density=round(text_density, 3),
            boilerplate_ratio=0.1,
            is_challenge_or_shell=False,
            details={"word_count": word_count},
        )


quality_evaluator = ContentQualityEvaluator()
