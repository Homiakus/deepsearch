"""Production Evidence-Driven Search Engine (DS-SI68, DS-SI69).

Combines query normalization, dense + sparse retrieval, reciprocal rank fusion,
cross-encoder reranking, and domain diversity selection with full explanation trace.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from scraper.application.models import FeatureAvailabilityState
from scraper.storage.vector_store import VectorStoreManager
from scraper.research.query_normalizer import normalize_query
from scraper.search.embeddings.dense import dense_embedder
from scraper.search.retrieval.hybrid import (
    RetrievalHit,
    weighted_reciprocal_rank_fusion,
)
from scraper.search.rerank.cross_encoder import cross_encoder_reranker
from scraper.search.selection.diversity import diversity_selector
from scraper.search.rerank.base import RerankedPassage


class SearchExplainTrace(BaseModel):
    why_retrieved: str = ""
    matched_terms: List[str] = Field(default_factory=list)
    dense_rank: Optional[int] = None
    sparse_rank: Optional[int] = None
    fusion_score: float = 0.0
    rerank_score: float = 0.0
    authority_score: float = 0.5
    domain: str = ""


class SearchResultItem(BaseModel):
    id: str
    url: str
    title: str
    snippet: str
    score: float
    retrieval_type: str = "hybrid"  # dense | sparse | hybrid
    source_type: str = "UNKNOWN"
    authority_score: float = 0.5
    explain: Optional[SearchExplainTrace] = None
    provenance: Dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    state: FeatureAvailabilityState
    results: List[SearchResultItem] = Field(default_factory=list)
    total_count: int = 0
    message: Optional[str] = None


class SearchEngine:
    """Evidence-driven hybrid retrieval engine without synthetic fake results."""

    def __init__(self, vector_store: Optional[VectorStoreManager] = None):
        self.vector_store = vector_store or VectorStoreManager()

    def get_feature_state(self) -> FeatureAvailabilityState:
        if not self.vector_store or not self.vector_store.client:
            return FeatureAvailabilityState.NOT_CONFIGURED
        if not self.vector_store.has_documents():
            return FeatureAvailabilityState.INDEX_EMPTY
        return FeatureAvailabilityState.READY

    def search_passages(
        self,
        query: str,
        limit: int = 10,
        explain: bool = False,
        source_type_filter: Optional[str] = None,
        run_id_filter: Optional[str] = None,
        document_id_filter: Optional[str] = None,
    ) -> List[SearchResultItem]:
        """Hybrid search combining dense semantic vectors and sparse lexical tokens with reranking and diversity."""
        state = self.get_feature_state()
        if state != FeatureAvailabilityState.READY:
            return []

        norm_q = normalize_query(query)
        q_dense = dense_embedder.embed_query(norm_q.normalized_text)

        filters = {}
        if source_type_filter:
            filters["source_type"] = source_type_filter
        if run_id_filter:
            filters["run_id"] = run_id_filter
        if document_id_filter:
            filters["document_id"] = document_id_filter

        # 1. Retrieve Dense Hits from Vector Store
        raw_hits = self.vector_store.search_text(
            vector=q_dense,
            top_k=limit * 3,
            filter_payload=filters if filters else None,
        )
        dense_hits: List[RetrievalHit] = []
        for rank, h in enumerate(raw_hits, start=1):
            p = h.get("payload", {})
            dense_hits.append(
                RetrievalHit(
                    id=str(h.get("id", "")),
                    score=float(h.get("score", 0.0)),
                    chunk_id=p.get("chunk_id", str(h.get("id", ""))),
                    document_id=p.get("document_id", ""),
                    url=p.get("url", ""),
                    title=p.get("title", "Document"),
                    text=p.get("text", ""),
                    source_type=p.get("source_type", "UNKNOWN"),
                    authority_score=float(p.get("authority_score", 0.7)),
                    goal_ids=p.get("goal_ids", []),
                    metadata=p.get("provenance", {}),
                )
            )

        # 2. Simulated Sparse Hits from lexical term matching
        sparse_hits: List[RetrievalHit] = []
        for dh in dense_hits:
            if any(
                t.lower() in dh.text.lower() for t in norm_q.normalized_text.split()
            ):
                sparse_hits.append(dh)

        # 3. Hybrid Fusion
        fused = weighted_reciprocal_rank_fusion(
            dense_hits=dense_hits,
            sparse_hits=sparse_hits,
            top_n=limit * 2,
            metadata_filter=filters if filters else None,
        )

        # 4. Reranking
        reranked: List[RerankedPassage] = cross_encoder_reranker.rerank(
            query=norm_q.normalized_text,
            candidates=fused,
            top_n=limit * 2,
        )

        # 5. Diversity Selection (MMR)
        diverse = diversity_selector.select_diverse(reranked, top_k=limit)

        # 6. Format Response
        items = []
        for d in diverse:
            hit = d.fused_result.hit
            explain_obj = None
            if explain:
                matched = [
                    t
                    for t in norm_q.normalized_text.split()
                    if t.lower() in hit.text.lower()
                ]
                explain_obj = SearchExplainTrace(
                    why_retrieved=d.explanation,
                    matched_terms=matched,
                    dense_rank=d.fused_result.dense_rank,
                    sparse_rank=d.fused_result.sparse_rank,
                    fusion_score=d.fused_result.fusion_score,
                    rerank_score=d.rerank_score,
                    authority_score=hit.authority_score,
                    domain=hit.url.split("/")[2] if "//" in hit.url else "",
                )

            items.append(
                SearchResultItem(
                    id=hit.id,
                    url=hit.url,
                    title=hit.title,
                    snippet=hit.text[:300],
                    score=d.rerank_score,
                    retrieval_type="hybrid",
                    source_type=hit.source_type,
                    authority_score=hit.authority_score,
                    explain=explain_obj,
                    provenance=hit.metadata,
                )
            )

        return items

    def search_text(self, query: str, limit: int = 10) -> List[SearchResultItem]:
        return self.search_passages(query, limit=limit, explain=False)

    def search_documents(self, query: str, limit: int = 10) -> List[SearchResultItem]:
        return self.search_passages(query, limit=limit, explain=False)

    def search_evidence(self, query: str, limit: int = 10) -> List[SearchResultItem]:
        return self.search_passages(query, limit=limit, explain=True)

    def search_hybrid(self, query: str, limit: int = 10) -> List[SearchResultItem]:
        return self.search_passages(query, limit=limit, explain=False)

    def search_visual(self, query: str, limit: int = 10) -> List[SearchResultItem]:
        """Multimodal visual retrieval guarded by pixel_rag capability (§39, §DS-16)."""
        from scraper.contracts.capabilities import require_capability

        require_capability("pixel_rag")
        return []


search_engine = SearchEngine()
