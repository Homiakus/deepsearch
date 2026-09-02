"""PDF Text Extractor Engine (§DS-14).

Extracts text, headings, and metadata from binary PDF files for conversion into Markdown.
Includes strict magic byte validation to reject HTML error pages masquerading as PDFs,
and enforces bounded page counts, memory budgets, and extraction timeouts.
"""

import asyncio
import io
import logging
import os

logger = logging.getLogger(__name__)

PDF_MAGIC_BYTES = b"%PDF-"
DEFAULT_MAX_PDF_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_PAGES = 50
DEFAULT_MAX_PAGE_CHARS = 50000


def validate_pdf_stream(data: bytes) -> tuple[bool, str]:
    """Validates the byte stream to ensure it is a valid PDF according to ISO 32000-1."""
    if not data:
        return False, "EMPTY_STREAM"
    if len(data) < 10:
        return False, "STREAM_TOO_SMALL"
    # ISO 32000-1: %PDF- signature should reside in the first 1024 bytes
    header_chunk = data[:1024]
    if PDF_MAGIC_BYTES not in header_chunk:
        if b"<!DOCTYPE" in header_chunk or b"<html" in header_chunk.lower():
            return False, "HTML_DOCUMENT_MASQUERADING_AS_PDF"
        return False, "INVALID_PDF_HEADER"
    if len(data) < 100:
        return False, "STREAM_TOO_SMALL"
    return True, "VALID_PDF"


def extract_text_from_pdf_file(
    file_path: str,
    max_pages: int | None = DEFAULT_MAX_PAGES,
    max_bytes: int = DEFAULT_MAX_PDF_BYTES,
) -> str:
    """Extracts plain text from a local PDF file after header and size validation."""
    try:
        if not os.path.exists(file_path):
            return ""
        file_size = os.path.getsize(file_path)
        if file_size > max_bytes or file_size < 10:
            logger.warning(
                "PDF file %s size (%d bytes) exceeds budget (%d bytes)",
                file_path,
                file_size,
                max_bytes,
            )
            return ""

        with open(file_path, "rb") as f:
            pdf_bytes = f.read(max_bytes + 1)
            if len(pdf_bytes) > max_bytes:
                return ""
        return extract_text_from_pdf_bytes(pdf_bytes, max_pages=max_pages)
    except Exception as exc:
        logger.warning("pypdf text extraction failed for %s: %s", file_path, exc)
        return ""


def extract_text_from_pdf_bytes(
    pdf_bytes: bytes,
    max_pages: int | None = DEFAULT_MAX_PAGES,
    max_page_chars: int = DEFAULT_MAX_PAGE_CHARS,
) -> str:
    """Extracts plain text from raw PDF bytes with header validation and error handling."""
    is_valid, reason = validate_pdf_stream(pdf_bytes)
    if not is_valid:
        logger.debug("Skipping invalid PDF stream: %s", reason)
        return ""

    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes), strict=False)
        total_pages = len(reader.pages)
        pages_to_read = total_pages
        if max_pages and max_pages > 0:
            pages_to_read = min(pages_to_read, max_pages)

        text_parts = []
        for idx in range(pages_to_read):
            try:
                page = reader.pages[idx]
                page_text = page.extract_text() or ""
                if page_text.strip():
                    clean_text = page_text.strip()[:max_page_chars]
                    text_parts.append(f"## Page {idx + 1}\n\n{clean_text}")
            except Exception as page_err:
                logger.debug("Error extracting page %d: %s", idx + 1, page_err)
                continue

        return "\n\n".join(text_parts)
    except Exception as exc:
        logger.warning("pypdf bytes text extraction failed: %s", exc)
        return ""


async def async_extract_text_from_pdf_file(
    file_path: str,
    max_pages: int | None = DEFAULT_MAX_PAGES,
    max_bytes: int = DEFAULT_MAX_PDF_BYTES,
    timeout_sec: float = 30.0,
) -> str:
    """Non-blocking asynchronous thread execution for PDF text extraction with timeout."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                extract_text_from_pdf_file,
                file_path,
                max_pages=max_pages,
                max_bytes=max_bytes,
            ),
            timeout=timeout_sec,
        )
    except TimeoutError:
        logger.warning(
            "PDF extraction timed out for %s after %.1fs", file_path, timeout_sec
        )
        return ""
    except Exception as exc:
        logger.warning("Async PDF extraction failed for %s: %s", file_path, exc)
        return ""
