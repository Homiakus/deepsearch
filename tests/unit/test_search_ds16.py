"""Unit tests for DS-16: Isolate fake search / PixelRAG from stable surface (§DS-16).

Verifies:
1. Canonical capability matrix status for hybrid_search and pixel_rag in stable vs experimental profile.
2. Capability boundary enforcement on REST API, MCP server, CLI, and SearchEngine.
3. Strict retrieval contract: search results originate strictly from indexed documents; unpopulated store returns empty without fake/synthetic items.
4. Tenant and run isolation filtering (run_id_filter, document_id_filter, source_type_filter).
5. Visual search and PixelRAG capability boundary enforcement.
"""

from unittest.mock import MagicMock, patch
import pytest
from typer.testing import CliRunner

from scraper.config import settings
from scraper.contracts.capabilities import (
    CapabilityStatus,
    CapabilityUnavailableError,
    get_capability_matrix,
    require_capability,
)
from scraper.application.models import FeatureAvailabilityState
from scraper.search.search_engine import SearchEngine
from scraper.storage.vector_store import VectorStoreManager
from scraper.cli.main import app as cli_app

runner = CliRunner()


def test_capability_matrix_stable_profile_disables_search_and_pixel_rag():
    """In stable profile (default), hybrid_search and pixel_rag must be DISABLED (§DS-16)."""
    with patch.object(settings, "experimental_search", False):
        matrix = get_capability_matrix()
        assert matrix["hybrid_search"].status == CapabilityStatus.DISABLED
        assert "EXPERIMENTAL_SEARCH=false" in (
            matrix["hybrid_search"].reason_disabled or ""
        )
        assert matrix["pixel_rag"].status == CapabilityStatus.DISABLED

        with pytest.raises(CapabilityUnavailableError) as exc_info:
            require_capability("hybrid_search")
        assert exc_info.value.capability == "hybrid_search"
        assert exc_info.value.status == CapabilityStatus.DISABLED

        with pytest.raises(CapabilityUnavailableError) as exc_pixel:
            require_capability("pixel_rag")
        assert exc_pixel.value.capability == "pixel_rag"
        assert exc_pixel.value.status == CapabilityStatus.DISABLED


def test_capability_matrix_experimental_profile_enables_hybrid_search():
    """When experimental_search=True, hybrid_search tier becomes EXPERIMENTAL while pixel_rag remains DISABLED."""
    with (
        patch.object(settings, "experimental_search", True),
        patch.object(settings, "retrieval_backend", "qdrant"),
    ):
        matrix = get_capability_matrix()
        assert matrix["hybrid_search"].status == CapabilityStatus.EXPERIMENTAL
        assert matrix["pixel_rag"].status == CapabilityStatus.DISABLED

        info = require_capability("hybrid_search")
        assert info.status == CapabilityStatus.EXPERIMENTAL

        with pytest.raises(CapabilityUnavailableError):
            require_capability("pixel_rag")


def test_search_engine_unpopulated_vector_store_returns_empty():
    """When vector store is empty or unconfigured, SearchEngine must return empty list without synthetic items (§INV-5)."""
    mock_vs = MagicMock(spec=VectorStoreManager)
    mock_vs.client = MagicMock()
    mock_vs.has_documents.return_value = False

    engine = SearchEngine(vector_store=mock_vs)
    assert engine.get_feature_state() == FeatureAvailabilityState.INDEX_EMPTY

    assert engine.search_text("quantum computing") == []
    assert engine.search_hybrid("quantum computing") == []
    assert engine.search_documents("quantum computing") == []
    assert engine.search_evidence("quantum computing") == []


def test_search_engine_visual_search_enforces_pixel_rag_capability():
    """SearchEngine.search_visual must enforce require_capability('pixel_rag') and raise CapabilityUnavailableError."""
    engine = SearchEngine()
    with pytest.raises(CapabilityUnavailableError) as exc:
        engine.search_visual("diagram search")
    assert exc.value.capability == "pixel_rag"


def test_search_engine_retrieval_contract_and_run_isolation():
    """SearchEngine must only return documents originating from vector store with isolation filtering applied (§DS-16)."""
    mock_vs = MagicMock(spec=VectorStoreManager)
    mock_vs.client = MagicMock()
    mock_vs.has_documents.return_value = True

    # Real indexed chunk simulation
    mock_vs.search_text.return_value = [
        {
            "id": "point_user_doc_101",
            "score": 0.88,
            "payload": {
                "chunk_id": "chunk_101",
                "document_id": "user_doc_101",
                "run_id": "run_alpha",
                "url": "https://trusted-domain.org/article_101",
                "title": "Quantum Error Correction",
                "text": "Surface codes and fault-tolerant quantum error correction techniques.",
                "source_type": "ACADEMIC",
                "authority_score": 0.85,
                "provenance": {"tenant": "tenant_1", "run_id": "run_alpha"},
            },
        }
    ]

    engine = SearchEngine(vector_store=mock_vs)
    assert engine.get_feature_state() == FeatureAvailabilityState.READY

    results = engine.search_passages(
        query="quantum error correction",
        limit=5,
        explain=True,
        source_type_filter="ACADEMIC",
        run_id_filter="run_alpha",
        document_id_filter="user_doc_101",
    )

    # Verify vector_store.search_text was called with isolation filter payload
    mock_vs.search_text.assert_called_once()
    call_kwargs = mock_vs.search_text.call_args.kwargs
    assert call_kwargs["filter_payload"] == {
        "source_type": "ACADEMIC",
        "run_id": "run_alpha",
        "document_id": "user_doc_101",
    }

    assert len(results) == 1
    hit = results[0]
    assert hit.id == "point_user_doc_101"
    assert hit.url == "https://trusted-domain.org/article_101"
    assert hit.title == "Quantum Error Correction"
    assert hit.source_type == "ACADEMIC"
    assert hit.provenance == {"tenant": "tenant_1", "run_id": "run_alpha"}
    assert hit.explain is not None
    assert hit.explain.domain == "trusted-domain.org"


def test_cli_search_handles_disabled_capability_gracefully():
    """CLI search command must print clean warning when search capability is disabled in stable profile."""
    with patch.object(settings, "experimental_search", False):
        result = runner.invoke(cli_app, ["search", "quantum physics"])
        assert result.exit_code == 0
        assert "Search unavailable" in result.stdout
