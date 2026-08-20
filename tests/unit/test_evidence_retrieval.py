"""Unit tests for RRF hybrid fusion and EvidenceStore (DS-A28, DS-A29, DS-A30)."""

import pytest
from scraper.retrieval.hybrid import RankedHit, reciprocal_rank_fusion
from scraper.evidence.store import EvidenceStore, EvidenceRelation
from scraper.evidence.visual import VisualEvidenceExtractor


def test_reciprocal_rank_fusion_order():
    dense = [
        RankedHit(id="docA", score=0.9),
        RankedHit(id="docB", score=0.8),
        RankedHit(id="docC", score=0.7),
    ]
    lexical = [
        RankedHit(id="docB", score=10.0),
        RankedHit(id="docA", score=8.0),
        RankedHit(id="docD", score=5.0),
    ]

    fused = reciprocal_rank_fusion(dense, lexical, k=60, top_n=4)

    assert len(fused) == 4
    # docA and docB appear in both lists (ranks 1,2 and 2,1), so they should top the fused results
    top_ids = [f.id for f in fused[:2]]
    assert "docA" in top_ids
    assert "docB" in top_ids
    assert fused[0].rrf_score >= fused[1].rrf_score


def test_evidence_store_claim_corroboration():
    store = EvidenceStore()
    claim = store.add_claim("c1", "Deep learning improves diagnostic accuracy.")
    assert claim.confidence == 0.5  # Neutral initial

    # Add supporting evidence
    store.add_evidence(
        evidence_id="e1",
        claim_id="c1",
        source_url="https://nature.com/article1",
        chunk_id="chunk_1",
        quote="Diagnostic accuracy rose by 14% with deep learning models.",
        relation=EvidenceRelation.SUPPORTS,
    )
    assert claim.confidence > 0.5

    # Add contradicting evidence
    store.add_evidence(
        evidence_id="e2",
        claim_id="c1",
        source_url="https://nature.com/article2",
        chunk_id="chunk_2",
        quote="In small cohorts, deep learning models showed no significant improvement.",
        relation=EvidenceRelation.CONTRADICTS,
    )
    # Contradiction should penalize score
    assert claim.confidence < 0.65


@pytest.mark.asyncio
async def test_visual_evidence_disabled_by_default():
    extractor = VisualEvidenceExtractor(enabled=False)
    res = await extractor.extract_visual_evidence(
        b"dummy_bytes", "https://example.com/chart.png"
    )
    assert res == []
