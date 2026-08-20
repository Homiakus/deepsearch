"""Unit tests for DeepSearch defect elimination and core enhancements.

Covers:
1. Unicode surrogate and malformed character sanitization.
2. PDF stream magic byte validation and pseudo-PDF guard.
3. Adaptive Quality Gate evaluation with warning dispatch.
4. PDF Figure Extractor capabilities.
5. Dual-format archive export with HuggingFace/LlamaIndex dataset.jsonl.
"""

import json
from pathlib import Path


from scraper.acquisition.engine import CapturedArtifact
from scraper.acquisition.page_classifier import PageIntelligence
from scraper.extraction.engine import ExtractionResult
from scraper.extraction.pdf_extractor import (
    extract_text_from_pdf_bytes,
    validate_pdf_stream,
)
from scraper.normalization.text import recursive_sanitize, sanitize_unicode_string
from scraper.search.quality_report import (
    SourceQualityEvaluator,
    SourceQualityRequirements,
)
from scraper.storage.archive_exporter import ArchiveExporter, SearchRunMetadata
from scraper.visual.pdf_figure_extractor import PDFFigureExtractor


def test_surrogate_sanitization():
    """Verifies removal of invalid Unicode surrogates, null bytes, and control characters."""
    raw_corrupt = "Paper Title: \ud800\udfff Valid Text \x00 NullByte \x07 Bell"
    clean = sanitize_unicode_string(raw_corrupt)
    assert "\x00" not in clean
    assert "\x07" not in clean
    assert clean.encode(
        "utf-8"
    )  # Must encode to utf-8 without throwing UnicodeEncodeError
    assert "Valid Text" in clean


def test_recursive_sanitize():
    """Verifies recursive sanitization across complex nested data structures."""
    corrupt_data = {
        "title": "Title with \x00 null byte",
        "nested": [
            {"chunk": "Text 😀 and \ud800 corrupt surrogate with \x00"},
            ("tuple_val \x01", 123),
        ],
        "number": 42,
    }
    cleaned = recursive_sanitize(corrupt_data)
    assert cleaned["title"] == "Title with  null byte"
    assert "Text 😀 and" in cleaned["nested"][0]["chunk"]
    assert "\x00" not in cleaned["nested"][0]["chunk"]
    assert cleaned["nested"][1][0] == "tuple_val"
    assert cleaned["number"] == 42
    # Verify json.dumps roundtrip succeeds cleanly
    dumped = json.dumps(cleaned, ensure_ascii=False)
    assert dumped is not None


def test_pdf_magic_bytes_validation():
    """Verifies that HTML error/block pages masquerading as PDF are rejected."""
    html_bytes = (
        b"<!DOCTYPE html><html><body>Access Denied 403 Cloudflare</body></html>"
    )
    is_valid, reason = validate_pdf_stream(html_bytes)
    assert is_valid is False
    assert reason == "HTML_DOCUMENT_MASQUERADING_AS_PDF"
    assert extract_text_from_pdf_bytes(html_bytes) == ""

    empty_stream = b""
    is_valid, reason = validate_pdf_stream(empty_stream)
    assert is_valid is False
    assert reason == "EMPTY_STREAM"

    short_stream = b"hello"
    is_valid, reason = validate_pdf_stream(short_stream)
    assert is_valid is False
    assert reason == "STREAM_TOO_SMALL"

    valid_stream = b"%PDF-1.4\n" + b"x" * 120
    is_valid, reason = validate_pdf_stream(valid_stream)
    assert is_valid is True
    assert reason == "VALID_PDF"


def test_adaptive_quality_gate_passes_high_evidence_without_formal_review():
    """Verifies that high-evidence multi-domain corpora pass in adaptive mode with warning."""
    evaluator = SourceQualityEvaluator()

    def _make_article(
        idx: int, domain: str
    ) -> tuple[CapturedArtifact, ExtractionResult]:
        url = f"https://{domain}/article/{idx}"
        artifact = CapturedArtifact(
            url=url,
            canonical_url=url,
            strategy_used="L1_HTTP",
            status_code=200,
            content_type="text/html",
            raw_content=b"ok",
            text_content="content",
            page_intelligence=PageIntelligence(),
        )
        extraction = ExtractionResult(
            url=url,
            raw_markdown="evidence",
            clean_markdown="research paper evidence " * 50,
            fit_markdown="research paper evidence " * 50,
            source_id=url,
            source_title=f"Clinical Study #{idx}",
            provider="test",
            source_type="PRIMARY_RESEARCH",
            authority_score=0.9,
            relevance_score=0.85,
        )
        return artifact, extraction

    results = [
        _make_article(1, "nature.com"),
        _make_article(2, "nature.com"),
        _make_article(3, "thelancet.com"),
        _make_article(4, "nejm.org"),
    ]

    report = evaluator.evaluate(
        results,
        requirements=SourceQualityRequirements(
            min_independent_domains=2,
            min_direct_evidence=3,
            min_review_or_benchmark=1,
            adaptive_mode=True,
        ),
    )

    assert report["passed"] is True
    assert report["status"] == "SUFFICIENT_EVIDENCE"
    assert "NO_FORMAL_REVIEW_DETECTED_BUT_HIGH_DIRECT_EVIDENCE" in report["warnings"]
    assert "MIN_REVIEW_OR_BENCHMARK" not in report["missing_requirements"]


def test_pdf_figure_extractor_handles_missing_file(tmp_path: Path):
    """Verifies that non-existent PDF file gracefully returns empty figure list."""
    extractor = PDFFigureExtractor()
    figs = extractor.extract_figures_from_pdf(
        str(tmp_path / "non_existent.pdf"),
        str(tmp_path / "media"),
        "doc_123",
    )
    assert figs == []


def test_archive_exporter_generates_dataset_jsonl(tmp_path: Path):
    """Verifies ArchiveExporter creates rag/dataset.jsonl and sanitizes output correctly."""
    metadata = SearchRunMetadata(
        query="Immunotherapy biomarker evaluation",
        domain="Medicine",
    )
    exporter = ArchiveExporter(metadata)

    artifact = CapturedArtifact(
        url="https://nature.com/articles/123",
        canonical_url="https://nature.com/articles/123",
        strategy_used="L1_HTTP",
        status_code=200,
        content_type="text/html",
        raw_content=b"ok",
        text_content="content",
        page_intelligence=PageIntelligence(),
    )
    extraction = ExtractionResult(
        url="https://nature.com/articles/123",
        raw_markdown="raw",
        clean_markdown="Sample body \ud800 corrupt surrogate and text",
        fit_markdown="Sample body \ud800 corrupt surrogate and text",
        source_id="nature_123",
        source_title="Biomarker Discovery in Oncology \x00",
        provider="nature",
        source_type="PRIMARY_RESEARCH",
        authority_score=0.95,
        relevance_score=0.9,
    )

    out_dir = tmp_path / "archive_out"
    exporter.build_archive_structure(
        results=[(artifact, extraction)],
        output_dir=str(out_dir),
    )

    # 1. Check dataset.jsonl existence and format
    dataset_jsonl = out_dir / "rag" / "dataset.jsonl"
    assert dataset_jsonl.exists()

    lines = dataset_jsonl.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) >= 1
    record = json.loads(lines[0])
    assert "id" in record
    assert "text" in record
    assert "metadata" in record
    assert record["metadata"]["query"] == "Immunotherapy biomarker evaluation"
    assert record["metadata"]["source_url"] == "https://nature.com/articles/123"

    # 2. Check manifest.json sanitization
    manifest_path = out_dir / "manifest.json"
    assert manifest_path.exists()
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_data["summary"]["total_documents"] == 1
    assert manifest_data["summary"]["total_rag_chunks"] >= 1
