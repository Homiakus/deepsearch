"""Unit tests for Chunking and Filtering Optimizations."""

import json
import os

from scraper.acquisition.engine import CapturedArtifact, PageIntelligence
from scraper.extraction.content_filter import ContentFilter
from scraper.extraction.engine import ExtractionResult
from scraper.research.intent import Entity, ResearchIntent
from scraper.search.chunking import StructureAwareChunker
from scraper.search.document_relevance import (
    DocumentRelevanceEvaluator,
    RelevanceTier,
)
from scraper.storage.archive_exporter import ArchiveExporter, SearchRunMetadata


def test_structure_aware_chunking_oversized_paragraph_splitting():
    """Verify that oversized single paragraphs are split across sentence boundaries."""
    chunker = StructureAwareChunker(target_words=30, min_words=10)

    # Long sentences in a single paragraph
    s1 = "Stereolithography additive manufacturing utilizes liquid photopolymer resin cross-linking under ultraviolet laser exposure with precise galvanometer positioning for industrial micro-fabrication."
    s2 = "The mechanical properties of 3D printed parts depend significantly on post-curing temperature, ultraviolet exposure duration, and the concentration of photoinitiators in the acrylic formulation."
    s3 = "Thermal post-treatment at eighty degrees Celsius for two hours substantially enhances tensile strength, glass transition temperature, and long-term dimensional stability in biomedical engineering applications."
    giant_paragraph = f"# Photopolymer Processing\n\n{s1} {s2} {s3}"

    chunks = chunker.chunk_markdown(
        giant_paragraph,
        document_id="doc_oversized",
        source_url="https://example.com/photopolymer",
        title="Processing Guide",
    )

    assert len(chunks) >= 2
    assert all("Photopolymer Processing" in c.heading_path for c in chunks)
    assert chunks[1].previous_chunk_id == chunks[0].chunk_id
    assert chunks[0].next_chunk_id == chunks[1].chunk_id
    assert all(c.token_estimate > 0 for c in chunks)


def test_structure_aware_chunking_overlap():
    """Verify overlap_words keeps context continuity across section chunks."""
    chunker = StructureAwareChunker(target_words=25, min_words=10, overlap_words=10)
    md = """# Section A

First detailed paragraph describing resin chemistry, photoinitiators, and ultraviolet reactivity parameters in precision additive manufacturing.

Second detailed paragraph describing exposure calibration, layer thickness measurement, and scanning speed optimization for functional prototypes.

Third detailed paragraph summarizing tensile precision, modulus enhancement, and tolerance limits in biomedical devices.
"""
    chunks = chunker.chunk_markdown(
        md, "doc_ov", "https://example.com/a", title="Guide A"
    )
    assert len(chunks) >= 2
    assert all("Section A" in c.heading_path for c in chunks)


def test_structure_aware_chunking_multilingual_token_estimate():
    """Verify token estimation accounts for Cyrillic and Latin text."""
    en_text = "Standard desktop stereolithography resin curing at 405nm."
    ru_text = "Исследование кинетики фотополимеризации олигомеров при ультрафиолетовом облучении."

    est_en = StructureAwareChunker.estimate_tokens(en_text)
    est_ru = StructureAwareChunker.estimate_tokens(ru_text)

    assert est_en >= len(en_text.split())
    assert est_ru >= len(ru_text.split())


def test_archive_exporter_preserves_heading_hierarchy_in_rag_chunks(tmp_path):
    """Verify that ArchiveExporter outputs heading_path and parent_section_id in RAG chunks."""
    metadata = SearchRunMetadata(query="SLA Resins", domain="materials.org")
    exporter = ArchiveExporter(metadata=metadata)

    artifact = CapturedArtifact(
        url="https://materials.org/sla",
        canonical_url="https://materials.org/sla",
        html_content="<html><body>SLA</body></html>",
        text_content="SLA",
        content_type="text/html",
        raw_content=b"<html><body>SLA</body></html>",
        status_code=200,
        strategy_used="H1_FAST_HTTP",
        page_intelligence=PageIntelligence(content_quality=0.9),
    )

    clean_md = """# SLA Photopolymers

General overview of stereolithography resins.

## Curing Kinetics

| Metric | Value |
| Wavelength | 405nm |
| Exposure | 2.5s |

### Mechanical Properties

Tensile strength exceeds 65 MPa after standard UV post-curing.
"""

    extraction = ExtractionResult(
        url="https://materials.org/sla",
        raw_markdown=clean_md,
        clean_markdown=clean_md,
        fit_markdown=clean_md,
        relevance_score=0.88,
        authority_score=0.90,
        source_type="ACADEMIC_JOURNAL",
    )

    out_dir = str(tmp_path / "run_out")
    built = exporter.build_archive_structure(
        [(artifact, extraction)], output_dir=out_dir
    )

    rag_chunks_file = os.path.join(built, "rag", "rag_chunks.jsonl")
    assert os.path.exists(rag_chunks_file)

    with open(rag_chunks_file, "r", encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f if line.strip()]

    assert len(chunks) >= 2
    assert any("SLA Photopolymers" in c.get("heading_path", []) for c in chunks)
    assert any("Curing Kinetics" in c.get("heading_path", []) for c in chunks)
    assert any("Mechanical Properties" in c.get("heading_path", []) for c in chunks)
    assert all("token_estimate" in c and c["token_estimate"] > 0 for c in chunks)


def test_document_relevance_evaluator_morphological_and_academic_markers():
    """Verify morphological matching and Russian research markers in DocumentRelevanceEvaluator."""
    intent = ResearchIntent(
        original_query="исследование фотополимеризации 405nm",
        normalized_query="исследование фотополимеризации 405nm",
        entities=[Entity(name="405nm", entity_type="OTHER_IDENTIFIER")],
    )

    # Text uses different grammatical cases: "фотополимеризация", "исследования"
    doc_text = """# Результаты исследования оптических свойств

В данной работе изучена фотополимеризация акрилатных мономеров под действием излучения с длиной волны 405nm.
Таблица 1 содержит измеренные значения кинетических констант и время гелеобразования.
doi: 10.1016/j.polymer.2025.1001
"""

    tier, quality = DocumentRelevanceEvaluator.evaluate(
        doc_text, "Оптические свойства смол", intent
    )

    assert tier in (RelevanceTier.HIGH, RelevanceTier.MEDIUM)
    assert quality.is_accepted is True
    assert quality.evidence_density >= 0.75


def test_content_filter_accepts_articles_with_extensive_bibliography():
    """Verify that scientific articles with large reference lists are not falsely rejected as navigation pages."""
    body_text = (
        """# Comprehensive Review of Photopolymerization Kinetics

Photopolymerization is a light-activated chain reaction that transforms liquid monomer formulations into solid cross-linked polymers.
In stereolithography and digital light processing additive manufacturing, the kinetics of photoinitiation, propagation, and termination determine the cure depth and resolution of 3D printed objects.
Dual-cure systems combining radical photopolymerization with thermal cationic polymerization have gained extensive traction in dental and aerospace manufacturing due to high mechanical modulus and low volumetric shrinkage.
Experimental evaluation demonstrates that increasing exposure irradiance from five to twenty milliwatts per square centimeter accelerates double-bond conversion without compromising thermal stability.
"""
        * 4
    )  # Generates ~400 words of dense continuous article body

    bibliography = "\n\n## References\n\n" + "\n".join(
        f"- [{i}] Author et al., Paper Title {i}, [Link](https://doi.org/10.1000/182{i})"
        for i in range(1, 40)
    )

    full_article = body_text + bibliography
    result = ContentFilter.inspect_content(full_article)

    assert result.is_valid is True
    assert result.is_navigation_only is False
    assert result.rejection_reason == ""
