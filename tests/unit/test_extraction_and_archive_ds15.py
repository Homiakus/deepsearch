"""Hermetic unit tests for DS-15: Table Extraction, Markdown sanitation, and Archive format integrity."""

import hashlib
import json
import os
import tempfile
import zipfile

from scraper.acquisition.engine import CapturedArtifact
from scraper.acquisition.page_classifier import PageIntelligence
from scraper.extraction.engine import (
    ExtractionEngine,
    ExtractionResult,
    FieldProvenance,
)
from scraper.extraction.table_extractor import extract_tables_from_html, TableData
from scraper.storage.archive_exporter import ArchiveExporter, SearchRunMetadata


def test_mutable_defaults_isolation():
    """Verify ExtractionResult and TableData have isolated default collections."""
    r1 = ExtractionResult(
        url="https://example.com/1", raw_markdown="", clean_markdown="", fit_markdown=""
    )
    r2 = ExtractionResult(
        url="https://example.com/2", raw_markdown="", clean_markdown="", fit_markdown=""
    )

    r1.extracted_records["test_key"] = FieldProvenance(
        value="val", source_url="https://example.com/1"
    )
    r1.tables.append(TableData(table_index=0, headers=["h1"], rows=[["v1"]]))

    assert "test_key" not in r2.extracted_records
    assert len(r2.tables) == 0


def test_table_extractor_rowspan_colspan_and_unequal_rows():
    """Verify table extractor handles rowspan, colspan, and irregular row lengths accurately."""
    html = """
    <table>
        <thead>
            <tr>
                <th rowspan="2">Header MultiRow</th>
                <th colspan="2">Header MultiCol</th>
            </tr>
            <tr>
                <th>SubCol 1</th>
                <th>SubCol 2</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td rowspan="2">SpanRowVal</td>
                <td>Cell R1C2</td>
                <td>Cell R1C3</td>
            </tr>
            <tr>
                <td>Cell R2C2</td>
                <td>Cell R2C3</td>
            </tr>
            <tr>
                <td colspan="2">WideCell</td>
                <!-- Missing 3rd cell in this row to test unequal row padding -->
            </tr>
        </tbody>
    </table>
    """
    tables = extract_tables_from_html(html)
    assert len(tables) == 1
    t = tables[0]

    # Check headers
    assert len(t.headers) == 3

    # Check rows dimensions and content
    assert len(t.rows) == 3
    # Row 0: SpanRowVal, Cell R1C2, Cell R1C3
    assert t.rows[0] == ["SpanRowVal", "Cell R1C2", "Cell R1C3"]
    # Row 1: SpanRowVal (from rowspan), Cell R2C2, Cell R2C3
    assert t.rows[1] == ["SpanRowVal", "Cell R2C2", "Cell R2C3"]
    # Row 2: WideCell, WideCell (from colspan), "" (padded)
    assert t.rows[2] == ["WideCell", "WideCell", ""]


def test_table_extractor_escapes_pipes_and_newlines_in_markdown():
    """Verify pipes and newlines are sanitized in Markdown table output."""
    html = """
    <table>
        <tr>
            <th>Name | Symbol</th>
            <th>Description</th>
        </tr>
        <tr>
            <td>Pipe | Inside | Cell</td>
            <td>Line 1
Line 2
Line 3</td>
        </tr>
    </table>
    """
    tables = extract_tables_from_html(html)
    assert len(tables) == 1
    t = tables[0]

    # Markdown table lines must not have unescaped internal pipes breaking the column count
    for line in t.markdown.splitlines():
        # Every line starts and ends with '|'
        assert line.startswith("| ")
        assert line.endswith(" |")
        # Check that newlines were converted so each table row is a single line
        assert "\n" not in line.strip()

    # The pipe in cell content must be escaped
    assert r"\|" in t.markdown


def test_table_extractor_adversarial_malformed_and_unicode():
    """Verify table extraction against malformed HTML, extreme/negative attributes, and rich Unicode."""
    malformed_html = """
    <div>Some text before table</div>
    <table>
        <tr>
            <td colspan="-10" rowspan="abc">First Cell</td>
            <td><a href="https://example.com"><b>Bold Link</b></a> and <code>code()</code></td>
            <td>Unicode: 🔬 🧬 \u0627\u0644\u0639\u0631\u0628\u064a\u0629 中文</td>
        </tr>
        <tr>
            <td>Second Row Only One Cell</td>
        </tr>
    </table>
    <table></table>
    <table><tr></tr></table>
    """
    tables = extract_tables_from_html(malformed_html)
    assert len(tables) == 1  # Only the table with actual cells produces TableData
    t = tables[0]
    assert len(t.headers) == 3
    assert t.headers == ["col_1", "col_2", "col_3"]
    assert len(t.rows) == 2
    assert "Bold Link and code()" in t.rows[0][1]
    assert "🔬 🧬" in t.rows[0][2]
    assert t.rows[1] == ["Second Row Only One Cell", "", ""]


def test_archive_manifest_schema_and_no_fake_vector_index():
    """Verify manifest schema_version, run_status, accurate checksums, and vector_index absence without embeddings."""
    metadata = SearchRunMetadata(
        query="table extraction and archive verification",
        domain="example.org",
        run_status="COMPLETED",
        warnings=["Non-fatal parse notice"],
        errors=[],
    )
    exporter = ArchiveExporter(metadata=metadata)

    html_content = (
        "<html><body><h1>Doc 1</h1><p>Sample scientific evidence.</p></body></html>"
    )
    artifact = CapturedArtifact(
        url="https://example.org/study",
        canonical_url="https://example.org/study",
        strategy_used="L1_HTTP",
        status_code=200,
        content_type="text/html",
        raw_content=html_content.encode("utf-8"),
        text_content=html_content,
        page_intelligence=PageIntelligence(content_quality=0.9),
    )
    extraction = ExtractionEngine.extract_from_html(artifact.url, html_content)
    extraction.clean_markdown = "Sample scientific evidence."
    extraction.relevance_score = 0.95

    with tempfile.TemporaryDirectory() as tmp_dir:
        built_dir = exporter.build_archive_structure(
            results=[(artifact, extraction)],
            output_dir=tmp_dir,
            warnings=["Archive warning"],
            errors=[],
        )

        # 1. Manifest verification
        manifest_path = os.path.join(built_dir, "manifest.json")
        assert os.path.exists(manifest_path)
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        assert manifest["schema_version"] == "2.0.0"
        assert manifest["deepsearch_version"] == "1.0.0"
        assert manifest["run_status"] == "COMPLETED"
        assert "Archive warning" in manifest["warnings"]
        assert manifest["summary"]["total_documents"] == 1
        assert manifest["summary"]["total_user_files"] == len(manifest["inventory"])

        # 2. Inventory checksums and sizes match actual files
        for item in manifest["inventory"]:
            rel_path = item["file_path"]
            full_path = os.path.join(built_dir, rel_path)
            assert os.path.exists(full_path)
            actual_size = os.path.getsize(full_path)
            assert item["size_bytes"] == actual_size
            with open(full_path, "rb") as bf:
                actual_sha = hashlib.sha256(bf.read()).hexdigest()
            assert item["sha256"] == actual_sha

        # 3. Vector index must NOT exist when no vectors/embeddings were generated
        vector_index_path = os.path.join(built_dir, "rag", "vector_index.json")
        assert not os.path.exists(vector_index_path), (
            "Fictitious vector_index.json must not be created without real embeddings!"
        )

        # 4. Pack ZIP and test reproducibility & readability
        zip_path = os.path.join(tmp_dir, "archive.zip")
        exporter.pack_zip_archive(built_dir, zip_path)
        assert os.path.exists(zip_path)
        with zipfile.ZipFile(zip_path, "r") as zf:
            namelist = zf.namelist()
            assert "manifest.json" in namelist
            assert "files/doc_001_example_org.md" in namelist
            assert "rag/rag_chunks.jsonl" in namelist
            assert "rag/vector_index.json" not in namelist


def test_archive_creates_vector_index_only_when_real_embeddings_provided():
    """Verify vector_index.json is created when actual embeddings data is passed."""
    metadata = SearchRunMetadata(query="real vector test", domain="vectors.org")
    exporter = ArchiveExporter(metadata=metadata)

    html_content = "<html><body><h1>Vector Document</h1><p>Content</p></body></html>"
    artifact = CapturedArtifact(
        url="https://vectors.org/v1",
        canonical_url="https://vectors.org/v1",
        strategy_used="L1_HTTP",
        status_code=200,
        content_type="text/html",
        raw_content=html_content.encode("utf-8"),
        text_content=html_content,
        page_intelligence=PageIntelligence(content_quality=0.9),
    )
    extraction = ExtractionEngine.extract_from_html(artifact.url, html_content)

    real_vector_index = {
        "total_vectors": 1,
        "dimensions": 384,
        "metric": "cosine",
        "vectors": [
            {
                "id": "doc_001_vectors_org_c001",
                "embedding": [0.12, 0.34, -0.56],
                "payload": {"source_url": "https://vectors.org/v1", "text": "Content"},
            }
        ],
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
        built_dir = exporter.build_archive_structure(
            results=[(artifact, extraction)],
            output_dir=tmp_dir,
            vector_index=real_vector_index,
            include_rag_dataset_json=True,
        )

        vector_index_path = os.path.join(built_dir, "rag", "vector_index.json")
        assert os.path.exists(vector_index_path)
        with open(vector_index_path, "r", encoding="utf-8") as f:
            v_data = json.load(f)
        assert v_data["dimensions"] == 384
        assert len(v_data["vectors"]) == 1
        assert v_data["vectors"][0]["embedding"] == [0.12, 0.34, -0.56]

        rag_dataset_path = os.path.join(built_dir, "rag", "rag_dataset.json")
        assert os.path.exists(rag_dataset_path)
