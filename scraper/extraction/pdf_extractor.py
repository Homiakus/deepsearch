"""PDF Text Extractor Engine.

Extracts text, headings, and metadata from binary PDF files for conversion into Markdown.
Includes strict magic byte validation to reject HTML error pages masquerading as PDFs.
"""

import io
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

PDF_MAGIC_BYTES = b"%PDF-"


def validate_pdf_stream(data: bytes) -> Tuple[bool, str]:
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


def extract_text_from_pdf_file(file_path: str, max_pages: Optional[int] = None) -> str:
    """Extracts plain text from a local PDF file after header validation."""
    try:
        with open(file_path, "rb") as f:
            pdf_bytes = f.read()
        return extract_text_from_pdf_bytes(pdf_bytes, max_pages=max_pages)
    except Exception as exc:
        logger.warning("pypdf text extraction failed for %s: %s", file_path, exc)
        return ""


def extract_text_from_pdf_bytes(
    pdf_bytes: bytes, max_pages: Optional[int] = None
) -> str:
    """Extracts plain text from raw PDF bytes with header validation and error handling."""
    is_valid, reason = validate_pdf_stream(pdf_bytes)
    if not is_valid:
        logger.debug("Skipping invalid PDF stream: %s", reason)
        return ""

    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes), strict=False)
        pages_to_read = len(reader.pages)
        if max_pages and max_pages > 0:
            pages_to_read = min(pages_to_read, max_pages)

        text_parts = []
        for idx in range(pages_to_read):
            try:
                page = reader.pages[idx]
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_parts.append(f"## Page {idx + 1}\n\n{page_text.strip()}")
            except Exception as page_err:
                logger.debug("Error extracting page %d: %s", idx + 1, page_err)
                continue

        return "\n\n".join(text_parts)
    except Exception as exc:
        logger.warning("pypdf bytes text extraction failed: %s", exc)
        return ""
