"""Unit tests for Document model and StructureAwareChunker (DS-A24, DS-A25)."""

import pytest
from scraper.domain.document import Document, DocumentProvenance
from scraper.retrieval.chunking import StructureAwareChunker


def test_structure_aware_chunking_preserves_headings():
    markdown = """# Introduction to Quantum Physics

Quantum physics explores the behavior of matter and energy at the subatomic level.

## Superposition Principle

In quantum mechanics, particles can exist in a linear combination of multiple states simultaneously until measured.
This property is foundational for quantum computing algorithms like Shor's and Grover's algorithms.

| Feature | Classical | Quantum |
| --- | --- | --- |
| Bits | 0 or 1 | Superposition |
"""
    doc = Document(
        id="doc_q1",
        source_url="https://example.com/quantum",
        canonical_url="https://example.com/quantum",
        title="Quantum Physics Overview",
        clean_markdown=markdown,
        provenance=DocumentProvenance(
            content_hash="abc123hash",
            fetch_strategy="HTTP",
            status_code=200,
        ),
    )

    chunker = StructureAwareChunker(target_words=30)
    chunks = chunker.chunk_document(doc)

    assert len(chunks) >= 2
    assert chunks[0].heading in ("Introduction to Quantum Physics", "Quantum Physics Overview")
    assert chunks[1].heading == "Superposition Principle"
    assert chunks[1].previous_chunk_id == chunks[0].chunk_id
    assert chunks[0].next_chunk_id == chunks[1].chunk_id
