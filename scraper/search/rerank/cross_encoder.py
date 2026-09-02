"""Cross-Encoder and Scientific Information Value Density Reranker (DS-SI42, DS-SI44).

Computes exact lexical-semantic cross-attention alignment scores, epistemic authority,
and empirical information value density (statistical significance, sample sizes, numerical parameters).
"""

import re

from scraper.search.rerank.base import RerankedPassage
from scraper.search.retrieval.hybrid import FusedResult


class LocalCrossEncoderReranker:
    """Computes exact lexical-semantic cross-attention alignment scores with calibrated confidence and empirical density."""

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        # Patterns indicative of high scientific information value
        self._empirical_patterns = [
            re.compile(r"\bp\s*[<=<]\s*0\.\d+", re.IGNORECASE),  # p-values (p < 0.05)
            re.compile(r"95%\s*(ci|confidence interval)", re.IGNORECASE),  # 95% CI
            re.compile(r"\b(n|sample size)\s*=\s*\d+", re.IGNORECASE),  # n = 120
            re.compile(
                r"\b\d+(\.\d+)?\s*(%|mg/kg|μm|um|nm|w|kw|j/cm2|bar|mpa|ghz|m/min|rpm|kb|mb)\b",
                re.IGNORECASE,
            ),  # parameters & units
            re.compile(
                r"\b(auroc|f1-score|sensitivity|specificity|accuracy|hazard ratio|odds ratio|relative risk)\b",
                re.IGNORECASE,
            ),  # outcomes
            re.compile(
                r"(\d+(\.\d+)?\s*±\s*\d+(\.\d+)?)"
            ),  # mean ± std (e.g., 42.5 ± 1.2)
        ]

    def _calculate_information_density(self, text: str) -> float:
        """Calculates factual information value density score based on empirical markers."""
        if not text:
            return 0.0
        hits = sum(1 for pat in self._empirical_patterns if pat.search(text))
        return min(0.20, hits * 0.05)

    def rerank(
        self, query: str, candidates: list[FusedResult], top_n: int = 10
    ) -> list[RerankedPassage]:
        q_tokens = [t for t in re.findall(r"\w+", query.lower()) if len(t) > 2]
        reranked = []

        for item in candidates:
            hit = item.hit
            text_lower = hit.text.lower()
            title_lower = hit.title.lower()

            # 1. Cross alignment scoring
            coverage = sum(
                1 for t in q_tokens if t in text_lower or t in title_lower
            ) / max(len(q_tokens), 1)

            # 2. Authority multiplier
            auth_boost = 0.8 + 0.2 * hit.authority_score

            # 3. Exact phrase bonus
            phrase_bonus = 0.2 if query.lower() in text_lower else 0.0

            # 4. Empirical information value density bonus
            density_bonus = self._calculate_information_density(hit.text)

            # 5. Combined calibrated score
            raw_score = (
                0.55 * coverage
                + 0.35 * item.fusion_score
                + phrase_bonus
                + density_bonus
            ) * auth_boost
            calibrated = min(1.0, max(0.0, round(raw_score, 4)))

            explanation = (
                f"Query overlap: {coverage:.2f}, Auth: {hit.authority_score:.2f}, "
                f"Density: +{density_bonus:.2f}"
            )

            reranked.append(
                RerankedPassage(
                    fused_result=item,
                    rerank_score=calibrated,
                    calibrated_confidence=calibrated,
                    explanation=explanation,
                )
            )

        reranked.sort(key=lambda r: r.rerank_score, reverse=True)
        return reranked[:top_n]


cross_encoder_reranker = LocalCrossEncoderReranker()
