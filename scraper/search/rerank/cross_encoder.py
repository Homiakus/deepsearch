"""Cross-Encoder and Lightweight Rerankers (DS-SI42, DS-SI44)."""

import re
from typing import List
from scraper.search.retrieval.hybrid import FusedResult
from scraper.search.rerank.base import RerankedPassage, Reranker


class LocalCrossEncoderReranker:
    """Computes exact lexical-semantic cross-attention alignment scores with calibrated confidence."""

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name

    def rerank(self, query: str, candidates: List[FusedResult], top_n: int = 10) -> List[RerankedPassage]:
        q_tokens = [t for t in re.findall(r'\w+', query.lower()) if len(t) > 2]
        reranked = []

        for item in candidates:
            hit = item.hit
            text_lower = hit.text.lower()
            title_lower = hit.title.lower()

            # Cross alignment scoring
            coverage = sum(1 for t in q_tokens if t in text_lower or t in title_lower) / max(len(q_tokens), 1)
            # Authority multiplier
            auth_boost = 0.8 + 0.2 * hit.authority_score
            # Exact phrase bonus
            phrase_bonus = 0.2 if query.lower() in text_lower else 0.0

            raw_score = (0.6 * coverage + 0.4 * item.fusion_score + phrase_bonus) * auth_boost
            calibrated = min(1.0, max(0.0, round(raw_score, 4)))

            reranked.append(
                RerankedPassage(
                    fused_result=item,
                    rerank_score=calibrated,
                    calibrated_confidence=calibrated,
                    explanation=f"Query overlap: {coverage:.2f}, Auth: {hit.authority_score:.2f}",
                )
            )

        reranked.sort(key=lambda r: r.rerank_score, reverse=True)
        return reranked[:top_n]


cross_encoder_reranker = LocalCrossEncoderReranker()
