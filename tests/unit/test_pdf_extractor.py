import io
import pytest
from pypdf import PdfWriter
from scraper.extraction.pdf_extractor import (
    validate_pdf_stream,
    extract_text_from_pdf_file,
    async_extract_text_from_pdf_file,
)


def _create_minimal_pdf_bytes(page_count: int = 3) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=200, height=200)
    packet = io.BytesIO()
    writer.write(packet)
    return packet.getvalue()


def test_validate_pdf_stream_valid_and_invalid():
    pdf_bytes = _create_minimal_pdf_bytes(1)
    assert len(pdf_bytes) >= 100
    is_valid, reason = validate_pdf_stream(pdf_bytes)
    assert is_valid is True
    assert reason == "VALID_PDF"

    # Empty stream
    assert validate_pdf_stream(b"")[0] is False

    # HTML disguised as PDF
    html_data = (
        b"<!DOCTYPE html><html><body><h1>404 Not Found - Server Error</h1>"
        + b" " * 100
        + b"</body></html>"
    )
    is_valid, reason = validate_pdf_stream(html_data)
    assert is_valid is False
    assert reason == "HTML_DOCUMENT_MASQUERADING_AS_PDF"

    # Random binary noise
    noise = b"XYZ1234567890abcdefghijklmnopqrstuvwxyz" * 5
    assert validate_pdf_stream(noise)[0] is False


def test_extract_text_page_limit(tmp_path):
    pdf_bytes = _create_minimal_pdf_bytes(page_count=5)
    pdf_file = tmp_path / "test_multipage.pdf"
    pdf_file.write_bytes(pdf_bytes)

    # Valid run without errors
    text = extract_text_from_pdf_file(str(pdf_file), max_pages=2)
    assert isinstance(text, str)


def test_extract_text_file_size_limit(tmp_path):
    pdf_bytes = _create_minimal_pdf_bytes(page_count=2)
    pdf_file = tmp_path / "oversized.pdf"
    pdf_file.write_bytes(pdf_bytes)

    # Strict byte limit below file size
    text = extract_text_from_pdf_file(str(pdf_file), max_bytes=10)
    assert text == ""


@pytest.mark.asyncio
async def test_async_extract_text_with_timeout(tmp_path):
    pdf_bytes = _create_minimal_pdf_bytes(page_count=3)
    pdf_file = tmp_path / "async_doc.pdf"
    pdf_file.write_bytes(pdf_bytes)

    text = await async_extract_text_from_pdf_file(
        str(pdf_file), max_pages=2, timeout_sec=5.0
    )
    assert isinstance(text, str)
