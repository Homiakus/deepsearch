"""Unit tests for DeepSearch Pipeline and Dual Archive Exporter."""

import os
import json
import zipfile
import tempfile
import pytest
from unittest.mock import AsyncMock, patch

from scraper.config import ExecutionMode
from scraper.acquisition.engine import CapturedArtifact, AdaptiveAcquisitionEngine
from scraper.acquisition.page_classifier import PageIntelligence
from scraper.pipeline.search_pipeline import DeepSearchPipeline, DeepSearchPipelineOptions
from scraper.storage.archive_exporter import ArchiveExporter, SearchRunMetadata


@pytest.fixture
def mock_acquisition_engine():
    engine = AdaptiveAcquisitionEngine()

    async def mock_acquire(url, canonical_url, mode=ExecutionMode.BALANCED, cached_content=None, take_screenshot=False):
        pi = PageIntelligence(
            content_type="text/html",
            static_score=0.9,
            js_dependency_score=0.1,
            content_quality=0.95
        )
        html_content = f"<html><body><h1>Title for {url}</h1><p>Sample content for research topic on artificial intelligence and neural algorithms.</p><a href='{url}/subpage'>Sublink</a></body></html>"
        return CapturedArtifact(
            url=url,
            canonical_url=canonical_url,
            strategy_used="L1_HTTP",
            status_code=200,
            content_type="text/html",
            raw_content=html_content.encode("utf-8"),
            text_content=html_content,
            page_intelligence=pi
        )

    engine.acquire_page = AsyncMock(side_effect=mock_acquire)
    return engine


@pytest.mark.asyncio
async def test_search_pipeline_execution(mock_acquisition_engine):
    opts = DeepSearchPipelineOptions(
        query="artificial intelligence",
        domain="example.com",
        preferred_sources=["https://example.com/ai_overview"],
        depth=2,
        max_pages=3,
        mode=ExecutionMode.FAST,
        enable_media_archiving=False,
    )

    with patch("scraper.discovery.providers.registry.ProviderRegistry.search_parallel", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = []
        pipeline = DeepSearchPipeline(acquisition_engine=mock_acquisition_engine)
        result = await pipeline.execute(opts)

        assert result.query == "artificial intelligence"
        assert result.total_pages_processed > 0
        assert result.total_rag_chunks > 0
        assert os.path.exists(result.dir_path)
        assert os.path.exists(os.path.join(result.dir_path, "manifest.json"))
        assert os.path.exists(os.path.join(result.dir_path, "files"))
        assert os.path.exists(os.path.join(result.dir_path, "rag"))


@pytest.mark.asyncio
async def test_archive_exporter_files_and_rag_structure(mock_acquisition_engine):
    meta = SearchRunMetadata(
        query="quantum physics",
        domain="physics.org",
        preferred_sources=["https://physics.org/quantum"],
        depth=1,
        max_pages=2
    )
    exporter = ArchiveExporter(metadata=meta)

    art = await mock_acquisition_engine.acquire_page("https://physics.org/quantum", "https://physics.org/quantum")
    from scraper.extraction.engine import ExtractionEngine
    ext = ExtractionEngine.extract_from_html(art.url, art.text_content)

    fake_media = [
        {
            "url": "https://example.com/quantum_diagram.png",
            "filename": "img_01_quantum_diagram.png",
            "file_path": os.path.join(tempfile.gettempdir(), "fake_img.png"),
            "size_bytes": 1024,
            "sha256": "abc123hash",
            "content_type": "image/png",
            "width": 800,
            "height": 600,
            "caption": "Quantum State Diagram",
            "relevance_score": 0.95
        }
    ]
    with open(fake_media[0]["file_path"], "wb") as f:
        f.write(b"PNG_FAKE_BYTES")

    with tempfile.TemporaryDirectory() as tmp_dir:
        dir_out = exporter.build_archive_structure([(art, ext)], output_dir=tmp_dir, media_files=fake_media)

        # 1. Verify files/
        files_folder = os.path.join(dir_out, "files")
        user_files = os.listdir(files_folder)
        assert len(user_files) == 1

        # 2. Verify media/
        media_folder = os.path.join(dir_out, "media")
        assert os.path.exists(media_folder)
        assert len(os.listdir(media_folder)) == 1

        # 3. Verify rag/
        rag_folder = os.path.join(dir_out, "rag")
        assert os.path.exists(os.path.join(rag_folder, "rag_chunks.jsonl"))
        assert os.path.exists(os.path.join(rag_folder, "rag_context.md"))
        assert os.path.exists(os.path.join(rag_folder, "rag_dataset.json"))
        assert os.path.exists(os.path.join(rag_folder, "vector_index.json"))
