import json
import os
import tempfile

from scraper.acquisition.engine import CapturedArtifact
from scraper.acquisition.page_classifier import PageIntelligence
from scraper.extraction.engine import ExtractionEngine
from scraper.storage.archive_exporter import ArchiveExporter, SearchRunMetadata


def test_archive_uses_full_text_and_exports_relevance_provenance():
    html = "<html><head><title>Evidence document</title></head><body><h1>Evidence</h1><p>Abstract evidence text.</p></body></html>"
    artifact = CapturedArtifact(
        url="https://example.org/article",
        canonical_url="https://example.org/article",
        strategy_used="L1_HTTP",
        status_code=200,
        content_type="text/html",
        raw_content=html.encode(),
        text_content=html,
        page_intelligence=PageIntelligence(content_quality=0.95),
    )
    extraction = ExtractionEngine.extract_from_html(artifact.url, html)
    extraction.abstract_markdown = extraction.clean_markdown
    extraction.full_text_markdown = (
        "## Page 1\n\nFull PDF evidence with measurable result."
    )
    extraction.source_type = "PRIMARY_RESEARCH"
    extraction.authority_score = 0.9
    extraction.relevance_score = 0.88
    extraction.published_at = "2025"

    with tempfile.TemporaryDirectory() as output_dir:
        built = ArchiveExporter(
            SearchRunMetadata(query="evidence")
        ).build_archive_structure([(artifact, extraction)], output_dir=output_dir)
        with open(
            os.path.join(built, "rag", "rag_chunks.jsonl"), encoding="utf-8"
        ) as f:
            chunk = json.loads(f.readline())
        assert "Full PDF evidence" in chunk["text"]
        assert chunk["relevance_score"] == 0.88
        assert chunk["provenance"]["full_text"] is True
