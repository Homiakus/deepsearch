"""Unit tests for Hybrid Retrieval, Dense/Sparse Embeddings, Reranking & Diversity (DS-SI37 - DS-SI46)."""

import pytest
from scraper.search.embeddings.dense import dense_embedder
from scraper.search.embeddings.sparse import sparse_embedder
from scraper.search.retrieval.hybrid import RetrievalHit, weighted_reciprocal_rank_fusion
from scraper.search.rerank.cross_encoder import cross_encoder_reranker
from scraper.search.selection.diversity import diversity_selector


def test_dense_and_sparse_embeddings():
    text = "Qdrant HNSW vector indexing performance and payload filtering"
    d_vec = dense_embedder.embed_text(text)
    assert len(d_vec) == 384
    assert any(v != 0.0 for v in d_vec)

    s_vec = sparse_embedder.embed_sparse(text)
    assert len(s_vec.indices) > 0
    assert len(s_vec.indices) == len(s_vec.values)


def test_hybrid_fusion_and_reranking_pipeline():
    hit1 = RetrievalHit(
        id="h1", score=0.9, chunk_id="c1", document_id="d1", url="https://qdrant.tech/docs",
        title="Qdrant Indexing", text="Qdrant HNSW vector search indexing payload filter performance",
        authority_score=0.95
    )
    hit2 = RetrievalHit(
        id="h2", score=0.8, chunk_id="c2", document_id="d2", url="https://random.com/post",
        title="General Vector DBs", text="Overview of vector databases in production systems",
        authority_score=0.60
    )

    fused = weighted_reciprocal_rank_fusion(
        dense_hits=[hit1, hit2],
        sparse_hits=[hit1],
        w_dense=0.6,
        w_sparse=0.4,
    )

    assert len(fused) == 2
    assert fused[0].id == "h1"

    reranked = cross_encoder_reranker.rerank("Qdrant HNSW", fused, top_n=2)
    assert len(reranked) == 2
    assert reranked[0].fused_result.hit.id == "h1"

    diverse = diversity_selector.select_diverse(reranked, top_k=2)
    assert len(diverse) == 2
