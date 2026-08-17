"""Hybrid Retrieval with Weighted Reciprocal Rank Fusion (DS-SI40, DS-SI41)."""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


class RetrievalHit(BaseModel):
    id: str
    score: float
    chunk_id: str
    document_id: str
    url: str
    title: str
    text: str
    source_type: str = "UNKNOWN"
    authority_score: float = 0.5
    goal_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FusedResult(BaseModel):
    id: str
    fusion_score: float
    dense_rank: Optional[int] = None
    sparse_rank: Optional[int] = None
    hit: RetrievalHit


def weighted_reciprocal_rank_fusion(
    dense_hits: List[RetrievalHit],
    sparse_hits: List[RetrievalHit],
    w_dense: float = 0.6,
    w_sparse: float = 0.4,
    k: int = 60,
    top_n: int = 20,
    metadata_filter: Optional[Dict[str, Any]] = None,
) -> List[FusedResult]:
    """Combines dense semantic and sparse lexical retrieval rankings using Weighted RRF."""
    scores: Dict[str, float] = {}
    dense_ranks: Dict[str, int] = {}
    sparse_ranks: Dict[str, int] = {}
    hits_map: Dict[str, RetrievalHit] = {}

    # Dense branch
    for rank, hit in enumerate(dense_hits, start=1):
        if _matches_filter(hit, metadata_filter):
            dense_ranks[hit.id] = rank
            scores[hit.id] = scores.get(hit.id, 0.0) + w_dense * (1.0 / (k + rank))
            hits_map[hit.id] = hit

    # Sparse branch
    for rank, hit in enumerate(sparse_hits, start=1):
        if _matches_filter(hit, metadata_filter):
            sparse_ranks[hit.id] = rank
            scores[hit.id] = scores.get(hit.id, 0.0) + w_sparse * (1.0 / (k + rank))
            if hit.id not in hits_map:
                hits_map[hit.id] = hit

    # Sort descending by score, resolve ties by id
    sorted_keys = sorted(scores.keys(), key=lambda hid: (-round(scores[hid], 6), hid))

    fused = []
    for hid in sorted_keys[:top_n]:
        fused.append(
            FusedResult(
                id=hid,
                fusion_score=round(scores[hid], 6),
                dense_rank=dense_ranks.get(hid),
                sparse_rank=sparse_ranks.get(hid),
                hit=hits_map[hid],
            )
        )

    return fused


def _matches_filter(hit: RetrievalHit, metadata_filter: Optional[Dict[str, Any]]) -> bool:
    if not metadata_filter:
        return True
    for k, v in metadata_filter.items():
        if k == "source_type" and hit.source_type != v:
            return False
        if k == "goal_id" and v not in hit.goal_ids:
            return False
        if k == "domain" and v not in hit.url:
            return False
    return True
