"""PDF Text Extractor Engine.

Extracts text, headings, and metadata from binary PDF files for conversion into Markdown.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def extract_text_from_pdf_file(file_path: str) -> str:
    """Extracts plain text from a local PDF file."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        text_parts = []
        for idx, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text()
            if page_text and page_text.strip():
                text_parts.append(f"## Page {idx}\n\n" + page_text.strip())
        return "\n\n".join(text_parts)
    except Exception as exc:
        logger.warning("pypdf text extraction failed for %s: %s", file_path, exc)
        return ""


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extracts plain text from raw PDF bytes."""
    try:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text_parts = []
        for idx, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text()
            if page_text and page_text.strip():
                text_parts.append(f"## Page {idx}\n\n" + page_text.strip())
        return "\n\n".join(text_parts)
    except Exception as exc:
        logger.warning("pypdf bytes text extraction failed: %s", exc)
        return ""
