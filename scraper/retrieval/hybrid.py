"""Hybrid Retrieval with Reciprocal Rank Fusion (RRF) (§10, DS-A28)."""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


class RankedHit(BaseModel):
    id: str
    score: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ScoredResult(BaseModel):
    id: str
    rrf_score: float
    dense_rank: Optional[int] = None
    lexical_rank: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


def reciprocal_rank_fusion(
    dense_hits: List[RankedHit],
    lexical_hits: List[RankedHit],
    k: int = 60,
    top_n: int = 20,
) -> List[ScoredResult]:
    """Combines dense and lexical search results using Reciprocal Rank Fusion.

    RRF_score(d) = sum( 1 / (k + rank_i(d)) ) for each ranking i.
    """
    scores: Dict[str, float] = {}
    dense_ranks: Dict[str, int] = {}
    lexical_ranks: Dict[str, int] = {}
    metadata_map: Dict[str, Dict[str, Any]] = {}

    for rank, hit in enumerate(dense_hits, start=1):
        dense_ranks[hit.id] = rank
        scores[hit.id] = scores.get(hit.id, 0.0) + (1.0 / (k + rank))
        metadata_map[hit.id] = hit.metadata

    for rank, hit in enumerate(lexical_hits, start=1):
        lexical_ranks[hit.id] = rank
        scores[hit.id] = scores.get(hit.id, 0.0) + (1.0 / (k + rank))
        if hit.id not in metadata_map:
            metadata_map[hit.id] = hit.metadata

    # Deterministic sorting by score descending, then by id ascending to resolve ties
    sorted_items = sorted(scores.items(), key=lambda item: (-round(item[1], 6), item[0]))

    results = []
    for doc_id, score in sorted_items[:top_n]:
        results.append(
            ScoredResult(
                id=doc_id,
                rrf_score=round(score, 6),
                dense_rank=dense_ranks.get(doc_id),
                lexical_rank=lexical_ranks.get(doc_id),
                metadata=metadata_map.get(doc_id, {}),
            )
        )

    return results
