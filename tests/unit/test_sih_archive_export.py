"""Unit tests for SIH extraction and archive export (DS-39)."""

import json
import tempfile
import zipfile
from pathlib import Path

from scraper.acquisition.engine import CapturedArtifact, PageIntelligence
from scraper.extraction.engine import ExtractionResult
from scraper.storage.archive_exporter import ArchiveExporter, SearchRunMetadata


def test_archive_exporter_generates_sih_corpus():
    """Verify that build_archive_structure and pack_zip_archive include sih/sih_corpus.json."""
    metadata = SearchRunMetadata(
        query="CRDT and Distributed Consensus",
        domain="tech",
    )
    exporter = ArchiveExporter(metadata)

    artifact = CapturedArtifact(
        url="https://distributed-systems.net/crdt",
        canonical_url="https://distributed-systems.net/crdt",
        status_code=200,
        content_type="text/html",
        raw_content=b"<html><body><h1>Conflict-free Replicated Data Types</h1><p>CRDTs enable state-based and operation-based deterministic replication.</p></body></html>",
        text_content="<html><body><h1>Conflict-free Replicated Data Types</h1><p>CRDTs enable state-based and operation-based deterministic replication.</p></body></html>",
        page_intelligence=PageIntelligence(
            content_quality=0.9,
            static_score=0.8,
        ),
        strategy_used="HTTP",
    )

    extraction = ExtractionResult(
        url=artifact.url,
        title="Conflict-free Replicated Data Types",
        raw_markdown="# Conflict-free Replicated Data Types\n\nCRDTs enable state-based and operation-based deterministic replication.",
        clean_markdown="# Conflict-free Replicated Data Types\n\nCRDTs enable state-based and operation-based deterministic replication.",
        fit_markdown="CRDTs enable state-based and operation-based deterministic replication.",
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_folder = Path(tmp_dir) / "export_dir"
        exporter.build_archive_structure(
            results=[(artifact, extraction)],
            output_dir=str(out_folder),
        )

        sih_corpus_file = out_folder / "sih" / "sih_corpus.json"
        assert sih_corpus_file.exists()

        data = json.loads(sih_corpus_file.read_text(encoding="utf-8"))
        assert data["version"] == "v1.0"
        assert len(data["nodes"]) >= 2
        assert len(data["edges"]) >= 1

        # Check node types
        kinds = [n["kind"] for n in data["nodes"]]
        assert "document" in kinds

        manifest_file = out_folder / "manifest.json"
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        assert manifest["summary"]["total_sih_nodes"] >= 2

        # Test ZIP packaging
        zip_path = Path(tmp_dir) / "test_archive.zip"
        exporter.pack_zip_archive(str(out_folder), str(zip_path))
        assert zip_path.exists()

        with zipfile.ZipFile(zip_path, "r") as z:
            names = z.namelist()
            assert "sih/sih_corpus.json" in names
            assert "manifest.json" in names
