"""Late-Interaction ColBERT-style MaxSim Reranker (DS-SI42)."""

from typing import List
from scraper.search.retrieval.hybrid import FusedResult
from scraper.search.rerank.base import RerankedPassage


class LateInteractionReranker:
    """ColBERT-style token-level MaxSim late interaction scoring."""

    def rerank(
        self, query: str, candidates: List[FusedResult], top_n: int = 10
    ) -> List[RerankedPassage]:
        q_words = query.lower().split()
        results = []

        for cand in candidates:
            doc_words = cand.hit.text.lower().split()
            if not q_words or not doc_words:
                max_sim = 0.0
            else:
                sims = []
                for qw in q_words:
                    max_w_sim = max(
                        (1.0 if qw == dw else (0.5 if qw in dw or dw in qw else 0.0))
                        for dw in doc_words[:100]
                    )
                    sims.append(max_w_sim)
                max_sim = sum(sims) / len(sims)

            final_score = round(0.5 * max_sim + 0.5 * cand.fusion_score, 4)
            results.append(
                RerankedPassage(
                    fused_result=cand,
                    rerank_score=final_score,
                    calibrated_confidence=final_score,
                    explanation=f"Token MaxSim: {max_sim:.3f}",
                )
            )

        results.sort(key=lambda r: r.rerank_score, reverse=True)
        return results[:top_n]


late_interaction_reranker = LateInteractionReranker()
