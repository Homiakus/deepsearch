"""Unit tests for Media Finder and Downloader Modules (§DS-14)."""

import os
import io
import pytest
import httpx
from scraper.discovery.media_finder import (
    extract_document_links,
    extract_relevant_images,
    extract_image_candidates,
)
from scraper.acquisition.media_downloader import (
    sanitize_media_filename,
    download_media_file,
)


def test_extract_document_links():
    html = """
    <html>
        <body>
            <a href="/papers/study_2024.pdf">Download PDF</a>
            <a href="https://arxiv.org/pdf/2401.12345">ArXiv PDF</a>
            <a href="/data/dataset.csv">CSV Data</a>
            <a href="https://example.com/about">About Page</a>
        </body>
    </html>
    """
    base_url = "https://example.com"
    docs = extract_document_links(html, base_url)

    assert len(docs) == 3
    assert any(d.endswith(".pdf") for d in docs)
    assert any("arxiv.org/pdf" in d for d in docs)
    assert any(d.endswith(".csv") for d in docs)


def test_extract_relevant_images():
    html = """
    <html>
        <body>
            <img src="/img/logo.png" alt="Company Logo" class="site-logo" width="50" height="50">
            <img src="https://example.com/figures/hair_follicle_diagram.jpg" alt="Hair Follicle Anagen Phase Diagram" width="800" height="600">
            <img src="/charts/clinical_trial_results.png" title="JAK Inhibitor Response Chart" width="600" height="400">
        </body>
    </html>
    """
    base_url = "https://example.com"
    images = extract_relevant_images(html, base_url)

    assert len(images) == 2
    assert images[0]["url"] == "https://example.com/figures/hair_follicle_diagram.jpg"
    assert "Diagram" in images[0]["caption"]
    assert images[1]["url"] == "https://example.com/charts/clinical_trial_results.png"


def test_extract_image_candidates_includes_license_and_author():
    html = """
    <html>
        <body>
            <figure>
                <img src="https://example.com/fig1.png" alt="Quantum Circuit Diagram" width="500" height="400">
                <figcaption>Circuit overview</figcaption>
            </figure>
        </body>
    </html>
    """
    candidates = extract_image_candidates(html, "https://example.com/paper")
    assert len(candidates) == 1
    assert candidates[0]["license"] == "UNKNOWN_LICENSE"
    assert candidates[0]["author"] == "UNKNOWN_AUTHOR"
    assert candidates[0]["source_domain"] == "example.com"


def test_sanitize_media_filename():
    fn1 = sanitize_media_filename(
        "https://arxiv.org/pdf/2401.12345.pdf", prefix="doc_001"
    )
    assert fn1.startswith("doc_001")
    assert fn1.endswith(".pdf")

    fn2 = sanitize_media_filename(
        "https://example.com/images/figure1.jpg?token=123", prefix="img"
    )
    assert fn2.startswith("img")
    assert fn2.endswith(".jpg")


def test_distinct_urls_have_distinct_targets():
    """FRAG-008: Distinct URLs sharing the same base filename must yield distinct target filenames."""
    url1 = "https://example1.com/reports/annual_report.pdf"
    url2 = "https://example2.com/files/annual_report.pdf"
    fn1 = sanitize_media_filename(url1, prefix="doc")
    fn2 = sanitize_media_filename(url2, prefix="doc")
    assert fn1 != fn2


@pytest.mark.asyncio
async def test_download_media_file_rejects_ssrf(tmp_path):
    target_dir = tmp_path / "downloads"
    res = await download_media_file(
        url="http://127.0.0.1:8000/secret.pdf",
        output_dir=str(target_dir),
    )
    assert res is None
    assert not target_dir.exists() or len(list(target_dir.glob("*.pdf"))) == 0


@pytest.mark.asyncio
async def test_download_media_file_streaming_success(tmp_path, monkeypatch):
    from PIL import Image

    target_dir = tmp_path / "media_out"
    img_bytes_io = io.BytesIO()
    image = Image.new("RGB", (200, 150), color="blue")
    image.save(img_bytes_io, format="PNG")
    valid_png_bytes = img_bytes_io.getvalue()

    class MockStreamCtx:
        async def __aenter__(self):
            class Resp:
                status_code = 200
                headers = {
                    "content-type": "image/png",
                    "content-length": str(len(valid_png_bytes)),
                }

                async def aiter_bytes(self, chunk_size=65536):
                    yield valid_png_bytes

            return Resp()

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        def stream(self, method, url, **kw):
            return MockStreamCtx()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)

    result = await download_media_file(
        url="https://example.com/image.png",
        output_dir=str(target_dir),
        filename_prefix="img_01",
        caption="Example Image",
        license="CC-BY-4.0",
        author="Alice",
    )

    assert result is not None
    assert result["license"] == "CC-BY-4.0"
    assert result["author"] == "Alice"
    assert result["width"] == 200
    assert result["height"] == 150
    assert result["size_bytes"] == len(valid_png_bytes)
    assert os.path.exists(result["file_path"])
    # Verify no lingering temp files
    assert not any(f.name.startswith(".ds_dl_") for f in target_dir.iterdir())


@pytest.mark.asyncio
async def test_download_media_file_oversized_aborts_and_cleans_up(
    tmp_path, monkeypatch
):
    target_dir = tmp_path / "oversized_out"

    class MockStreamCtx:
        async def __aenter__(self):
            class Resp:
                status_code = 200
                headers = {"content-type": "application/pdf"}

                async def aiter_bytes(self, chunk_size=65536):
                    for _ in range(10):
                        yield b"%PDF-" + b"0" * 2000

            return Resp()

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        def stream(self, method, url, **kw):
            return MockStreamCtx()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)

    result = await download_media_file(
        url="https://example.com/huge.pdf",
        output_dir=str(target_dir),
        max_bytes=1000,  # smaller than stream
    )

    assert result is None
    # Verify target file not created and temporary file cleaned up
    assert not target_dir.exists() or len(list(target_dir.glob("*"))) == 0


@pytest.mark.asyncio
async def test_download_media_file_rejects_fake_mime_html(tmp_path, monkeypatch):
    target_dir = tmp_path / "fake_mime_out"
    html_error = (
        b"<!DOCTYPE html><html><body><h1>403 Forbidden - Cloudflare</h1></body></html>"
    )

    class MockStreamCtx:
        async def __aenter__(self):
            class Resp:
                status_code = 200
                headers = {"content-type": "application/pdf"}

                async def aiter_bytes(self, chunk_size=65536):
                    yield html_error

            return Resp()

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        def stream(self, method, url, **kw):
            return MockStreamCtx()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)

    result = await download_media_file(
        url="https://example.com/fake.pdf",
        output_dir=str(target_dir),
        filename_prefix="doc",
    )

    assert result is None
    assert not target_dir.exists() or len(list(target_dir.glob("*"))) == 0
