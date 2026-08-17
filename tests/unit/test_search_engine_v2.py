"""Unit tests for SearchEngine V2 & Structure-aware Chunking (DS-SI65 - DS-SI69)."""

import pytest
from unittest.mock import MagicMock
from scraper.search.search_engine import SearchEngine, SearchExplainTrace
from scraper.search.chunking import structure_chunker
from scraper.storage.vector_store import VectorStoreManager
from scraper.application.models import FeatureAvailabilityState


def test_structure_aware_chunking():
    md = """# Introduction to Photopolymers

Photopolymers are light-activated resins commonly used in SLA 3D printing.

## Exposure Parameters

| Resin Type | Wavelength | Cure Time |
| Standard | 405nm | 2.5s |
| Tough | 405nm | 3.5s |

### Post Curing Details

Post-curing increases the tensile strength and modulus of the printed part.
"""
    chunks = structure_chunker.chunk_markdown(md, "doc_01", "https://example.com/resins", title="Photopolymers Guide")
    assert len(chunks) >= 2
    assert any("Introduction to Photopolymers" in c.heading_path for c in chunks)
    assert any("Exposure Parameters" in c.heading_path for c in chunks)
    assert any("| Standard |" in c.text for c in chunks)


def test_search_engine_hybrid_with_explanation():
    mock_vs = MagicMock(spec=VectorStoreManager)
    mock_vs.client = MagicMock()
    mock_vs.has_documents.return_value = True
    mock_vs.search_text.return_value = [
        {
            "id": "point_1",
            "score": 0.92,
            "payload": {
                "chunk_id": "chk_01",
                "document_id": "doc_01",
                "url": "https://formlabs.com/guide",
                "title": "Formlabs SLA Guide",
                "text": "Standard 405nm resin photoinitiator chemistry for SLA 3D printing.",
                "source_type": "OFFICIAL_DOC",
                "authority_score": 0.90,
            }
        }
    ]

    engine = SearchEngine(vector_store=mock_vs)
    assert engine.get_feature_state() == FeatureAvailabilityState.READY

    results = engine.search_passages("405nm resin SLA", limit=5, explain=True)
    assert len(results) == 1
    assert results[0].explain is not None
    assert results[0].explain.authority_score == 0.90
    assert results[0].score > 0.0
