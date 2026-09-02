"""Unit tests for Hybrid Retrieval, Dense/Sparse Embeddings, Reranking & Diversity (DS-SI37 - DS-SI46)."""

from scraper.search.embeddings.dense import dense_embedder
from scraper.search.embeddings.sparse import sparse_embedder
from scraper.search.rerank.cross_encoder import cross_encoder_reranker
from scraper.search.retrieval.hybrid import (
    RetrievalHit,
    weighted_reciprocal_rank_fusion,
)
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
        id="h1",
        score=0.9,
        chunk_id="c1",
        document_id="d1",
        url="https://qdrant.tech/docs",
        title="Qdrant Indexing",
        text="Qdrant HNSW vector search indexing payload filter performance",
        authority_score=0.95,
    )
    hit2 = RetrievalHit(
        id="h2",
        score=0.8,
        chunk_id="c2",
        document_id="d2",
        url="https://random.com/post",
        title="General Vector DBs",
        text="Overview of vector databases in production systems",
        authority_score=0.60,
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


def test_scientific_information_density_rerank():
    # Hit A has high empirical evidence (p-value, 95% CI, sample size, AUROC)
    hit_empirical = RetrievalHit(
        id="h_emp",
        score=0.85,
        chunk_id="c_emp",
        document_id="d_emp",
        url="https://nature.com/articles/s41591-023-02401-x",
        title="Colorectal Cancer ctDNA Detection",
        text="In a prospective cohort of n=1420 patients, sensitivity was 92.4% (95% CI: 88.1-95.6%, p<0.001) with AUROC of 0.96.",
        authority_score=0.98,
    )
    # Hit B has vague promotional description without concrete empirical findings
    hit_vague = RetrievalHit(
        id="h_vague",
        score=0.85,
        chunk_id="c_vague",
        document_id="d_vague",
        url="https://genericblog.com/ctdna",
        title="Liquid Biopsy News",
        text="Liquid biopsy is an amazing new breakthrough in oncology that doctors are excited about.",
        authority_score=0.60,
    )

    fused = weighted_reciprocal_rank_fusion(
        dense_hits=[hit_vague, hit_empirical],
        sparse_hits=[hit_vague, hit_empirical],
    )
    reranked = cross_encoder_reranker.rerank(
        "liquid biopsy ctDNA colorectal cancer", fused, top_n=2
    )
    assert reranked[0].fused_result.hit.id == "h_emp"
    assert "Density" in reranked[0].explanation
