"""Unit tests for legacy vector deprecation and epistemic transition (DS-41)."""

from scraper.storage.vector_store import VectorStoreManager


def test_vector_store_manager_deprecated_docstring():
    """Verify VectorStoreManager includes explicit deprecation notice."""
    doc = VectorStoreManager.__doc__
    assert doc is not None
    assert "[DEPRECATED: DS-41]" in doc
    assert "SncSinCore" in doc
