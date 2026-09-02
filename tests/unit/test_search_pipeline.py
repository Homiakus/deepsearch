"""Unit tests for DeepSearch Pipeline, Stages, Lifecycle, and Exporter (DS-12)."""

import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

from scraper.acquisition.engine import AdaptiveAcquisitionEngine, CapturedArtifact
from scraper.acquisition.page_classifier import PageIntelligence
from scraper.application.run_context import RunContext, RunContextOptions
from scraper.config import ExecutionMode
from scraper.pipeline.search_pipeline import (
    AcquisitionExtractionStage,
    DeepSearchPipeline,
    DeepSearchPipelineOptions,
    DiscoveryStage,
    ExportStage,
    MediaCollectionStage,
    PipelineWorkspace,
    ScheduleStage,
)
from scraper.storage.archive_exporter import ArchiveExporter, SearchRunMetadata


@pytest.fixture
def mock_acquisition_engine():
    engine = AdaptiveAcquisitionEngine()

    async def mock_acquire(
        url,
        canonical_url,
        mode=ExecutionMode.BALANCED,
        cached_content=None,
        take_screenshot=False,
    ):
        pi = PageIntelligence(
            content_type="text/html",
            static_score=0.9,
            js_dependency_score=0.1,
            content_quality=0.95,
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
            page_intelligence=pi,
        )

    engine.acquire_page = AsyncMock(side_effect=mock_acquire)
    return engine


@pytest.mark.asyncio
async def test_search_pipeline_execution(mock_acquisition_engine, tmp_path):
    output_dir = tmp_path / "research_test_out"
    output_archive = tmp_path / "research_test_out.zip"
    opts = DeepSearchPipelineOptions(
        query="artificial intelligence",
        domain="example.com",
        preferred_sources=["https://example.com/ai_overview"],
        depth=2,
        max_pages=3,
        mode=ExecutionMode.FAST,
        enable_media_archiving=False,
        output_dir_path=str(output_dir),
        output_archive_path=str(output_archive),
    )

    with patch(
        "scraper.discovery.providers.registry.ProviderRegistry.search_parallel",
        new_callable=AsyncMock,
    ) as mock_search:
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
async def test_search_pipeline_stages_and_workspace(mock_acquisition_engine, tmp_path):
    # Test Workspace lifecycle & fault injection
    out_target = tmp_path / "target_out"
    with PipelineWorkspace(output_dir_path=str(out_target)) as ws:
        t1 = ws.create_temp_dir(prefix="test1_")
        out = ws.resolve_output_dir()
        assert os.path.exists(t1) and os.path.exists(out)
    assert not os.path.exists(t1) and os.path.exists(str(out_target))

    # Test Discovery & Schedule Stage
    with patch(
        "scraper.discovery.providers.registry.ProviderRegistry.search_parallel",
        new_callable=AsyncMock,
    ) as mock_search:
        mock_search.return_value = []
        disc_out = await DiscoveryStage().execute(
            query="quantum computing", preferred_sources=["https://example.org/q1"]
        )
        assert len(disc_out.ranked_pool) >= 1
        sched_out = await ScheduleStage().execute(disc_out.ranked_pool)
        assert sched_out.enqueued_count >= 1

    # Test Acquisition, Media & Export Stages
    run_ctx = RunContext.create(
        RunContextOptions(run_id="r1", query="quantum computing", max_pages=1)
    )
    pdf_tmp = tmp_path / "pdf_tmp"
    pdf_tmp.mkdir()
    acq_out = await AcquisitionExtractionStage(
        acquisition_engine=mock_acquisition_engine
    ).execute(
        frontier=sched_out.frontier,
        intent=disc_out.intent,
        run_context=run_ctx,
        pdf_temp_dir=str(pdf_tmp),
        max_pages=1,
        enable_media_archiving=False,
    )
    assert len(acq_out.acquired_results) == 1

    media_out = await MediaCollectionStage().execute(
        query="quantum computing",
        enable_media_archiving=False,
        min_media_count=1,
        max_media_count=2,
        raw_image_candidates=[],
        downloaded_pdfs=[],
        media_temp_dir=str(tmp_path),
    )
    assert media_out.downloaded_media == []

    export_out = await ExportStage().execute(
        query="quantum computing",
        domain=None,
        preferred_sources=[],
        depth=1,
        max_pages=1,
        mode=ExecutionMode.BALANCED,
        acquired_results=acq_out.acquired_results,
        downloaded_pdfs=[],
        downloaded_media=[],
        rejections=[],
        media_rejections=[],
        output_dir=str(tmp_path / "export_test"),
        output_archive_path=None,
        min_media_count=1,
        max_media_count=2,
    )
    assert export_out.total_pages_processed == 1


@pytest.mark.asyncio
async def test_pipeline_cancellation_semantics(mock_acquisition_engine):
    run_ctx = RunContext.create(
        RunContextOptions(run_id="cancel_run", query="cancellation test", max_pages=5)
    )
    run_ctx.cancel()
    opts = DeepSearchPipelineOptions(
        query="cancellation test",
        preferred_sources=["https://example.com/seed1"],
        max_pages=3,
    )
    with patch(
        "scraper.discovery.providers.registry.ProviderRegistry.search_parallel",
        new_callable=AsyncMock,
    ) as mock_search:
        mock_search.return_value = []
        pipeline = DeepSearchPipeline(acquisition_engine=mock_acquisition_engine)
        with pytest.raises(asyncio.CancelledError):
            await pipeline.execute(opts, run_context=run_ctx)


@pytest.mark.asyncio
async def test_archive_exporter_files_and_rag_structure(mock_acquisition_engine):
    meta = SearchRunMetadata(
        query="quantum physics",
        domain="physics.org",
        preferred_sources=["https://physics.org/quantum"],
        depth=1,
        max_pages=2,
    )
    exporter = ArchiveExporter(metadata=meta)

    art = await mock_acquisition_engine.acquire_page(
        "https://physics.org/quantum", "https://physics.org/quantum"
    )
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
            "relevance_score": 0.95,
        }
    ]
    with open(fake_media[0]["file_path"], "wb") as f:
        f.write(b"PNG_FAKE_BYTES")

    with tempfile.TemporaryDirectory() as tmp_dir:
        dir_out = exporter.build_archive_structure(
            [(art, ext)], output_dir=tmp_dir, media_files=fake_media
        )

        files_folder = os.path.join(dir_out, "files")
        user_files = os.listdir(files_folder)
        assert len(user_files) == 1

        media_folder = os.path.join(dir_out, "media")
        assert os.path.exists(media_folder)
        assert len(os.listdir(media_folder)) == 1

        rag_folder = os.path.join(dir_out, "rag")
        assert os.path.exists(os.path.join(rag_folder, "rag_chunks.jsonl"))
        assert os.path.exists(os.path.join(rag_folder, "dataset.jsonl"))
        assert os.path.exists(os.path.join(rag_folder, "rag_context.md"))
        assert not os.path.exists(os.path.join(rag_folder, "vector_index.json"))


def test_archive_chunk_hard_limit():
    """FRAG-006: Chunker must enforce target word bounds even on single oversized paragraphs."""
    from scraper.domain.document import Document, DocumentProvenance
    from scraper.retrieval.chunking import StructureAwareChunker

    chunker = StructureAwareChunker(target_words=250)
    oversized_text = "word " * 251
    doc = Document(
        id="doc_test",
        title="Oversized Document",
        source_url="https://example.com/oversized",
        canonical_url="https://example.com/oversized",
        clean_markdown=oversized_text,
        provenance=DocumentProvenance(content_hash="mock_hash"),
    )
    chunks = chunker.chunk_document(doc)
    assert len(chunks) >= 2
    for c in chunks:
        assert c.word_count <= 250


@pytest.mark.asyncio
async def test_single_failure_is_not_empty_success(tmp_path):
    """FRAG-011: When all acquisition attempts fail, pipeline must report failure rather than empty success."""
    failing_engine = AdaptiveAcquisitionEngine()
    failing_engine.acquire_page = AsyncMock(
        side_effect=TimeoutError("Connection timed out")
    )

    pipeline = DeepSearchPipeline(acquisition_engine=failing_engine)
    opts = DeepSearchPipelineOptions(
        query="laser optics",
        preferred_sources=["https://example.com/timeout"],
        output_dir_path=str(tmp_path / "out"),
        max_pages=1,
    )
    result = await pipeline.execute(opts)
    assert result.total_pages_processed == 0
    assert result.quality_gate_passed is False
    assert len(result.manifest.get("rejections", [])) >= 1


@pytest.mark.asyncio
async def test_fault_matrix_partial_degradation_and_rejections(tmp_path):
    """FRAG-DEPENDENCY/FRAG-RECOVERY: Faults across sources yield graceful partial results without empty success."""
    import httpx

    output_dir = tmp_path / "partial_out"

    async def mock_faulty_acquire(url, canonical_url, **kwargs):
        if "ok" in url:
            html = "<html><body><h1>Fault Injection Test Page</h1><p>Comprehensive article discussing fault injection test methodology, resilience patterns, and degradation verification in distributed web scrapers.</p></body></html>"
            return CapturedArtifact(
                url=url,
                canonical_url=canonical_url,
                strategy_used="L1_HTTP",
                status_code=200,
                content_type="text/html",
                raw_content=html.encode("utf-8"),
                text_content=html,
                page_intelligence=PageIntelligence(
                    content_type="text/html",
                    static_score=0.9,
                    js_dependency_score=0.1,
                    content_quality=0.95,
                ),
            )
        elif "dns_failure" in url:
            raise httpx.ConnectError("DNS name resolution failed")
        elif "timeout" in url:
            raise httpx.ReadTimeout("Socket read timed out")
        elif "malformed" in url:
            raise ValueError("Malformed byte sequence in chunked transfer")
        raise RuntimeError("Unexpected failure")

    engine = AdaptiveAcquisitionEngine()
    engine.acquire_page = AsyncMock(side_effect=mock_faulty_acquire)

    opts = DeepSearchPipelineOptions(
        query="fault injection test",
        preferred_sources=[
            "https://example.com/ok_source",
            "https://example.com/dns_failure",
            "https://example.com/timeout",
            "https://example.com/malformed",
        ],
        output_dir_path=str(output_dir),
        max_pages=4,
        enable_media_archiving=False,
    )

    with patch(
        "scraper.discovery.providers.registry.ProviderRegistry.search_parallel",
        new_callable=AsyncMock,
    ) as mock_search:
        mock_search.return_value = []
        pipeline = DeepSearchPipeline(acquisition_engine=engine)
        result = await pipeline.execute(opts)

    # 1 page succeeded, 3 failed
    assert result.total_pages_processed == 1
    assert os.path.exists(result.dir_path)
    # Manifest lists rejections with failure reasons
    rejections = result.manifest.get("rejections", [])
    assert len(rejections) == 3
    rejection_urls = [r.get("url") for r in rejections]
    assert "https://example.com/dns_failure" in rejection_urls
    assert "https://example.com/timeout" in rejection_urls
    assert "https://example.com/malformed" in rejection_urls

    # Files folder only contains the succeeded page
    files_dir = os.path.join(result.dir_path, "files")
    assert len(os.listdir(files_dir)) == 1


@pytest.mark.asyncio
async def test_fault_injection_workspace_cleans_up_on_failure(tmp_path):
    """FRAG-RECOVERY: Workspace does not leak temporary directories or files on pipeline failure."""
    out_target = tmp_path / "workspace_fail_out"
    created_temp_dirs = []

    try:
        with PipelineWorkspace(output_dir_path=str(out_target)) as ws:
            t1 = ws.create_temp_dir(prefix="stage1_")
            t2 = ws.create_temp_dir(prefix="stage2_")
            created_temp_dirs.extend([t1, t2])
            assert os.path.exists(t1) and os.path.exists(t2)
            # Simulate fatal pipeline error
            raise RuntimeError("Fatal unhandled worker failure")
    except RuntimeError:
        pass

    # Verify all temporary directories were safely cleaned up
    for t_dir in created_temp_dirs:
        assert not os.path.exists(t_dir), f"Temp dir {t_dir} leaked!"
