"""Structure-Aware Hierarchical Chunking Engine (§9, DS-A25)."""

import hashlib
import re
import uuid
from typing import List, Optional
from pydantic import BaseModel, Field

from scraper.domain.document import Document


class TextChunk(BaseModel):
    chunk_id: str
    document_id: str
    source_url: str
    heading: Optional[str] = None
    section_path: List[str] = Field(default_factory=list)
    ordinal: int = 0
    text: str
    word_count: int = 0
    content_hash: str
    previous_chunk_id: Optional[str] = None
    next_chunk_id: Optional[str] = None


class StructureAwareChunker:
    """Chunks documents along headings, paragraphs, and table boundaries without arbitrary truncation."""

    def __init__(self, target_words: int = 250, min_words: int = 30):
        self.target_words = target_words
        self.min_words = min_words

    def chunk_document(self, document: Document) -> List[TextChunk]:
        """Creates linked chunks preserving section headings and document context."""
        raw_markdown = document.clean_markdown
        lines = raw_markdown.splitlines()

        chunks: List[TextChunk] = []
        current_heading = document.title
        current_path = [document.title]
        current_paragraphs: List[str] = []
        current_words = 0

        def _flush_chunk():
            nonlocal current_paragraphs, current_words
            if not current_paragraphs:
                return
            combined_text = "\n\n".join(current_paragraphs).strip()
            if len(combined_text) == 0:
                return

            c_id = f"chunk_{uuid.uuid4().hex[:12]}"
            c_hash = hashlib.sha256(combined_text.encode("utf-8")).hexdigest()

            chunk = TextChunk(
                chunk_id=c_id,
                document_id=document.id,
                source_url=document.source_url,
                heading=current_heading,
                section_path=list(current_path),
                ordinal=len(chunks),
                text=combined_text,
                word_count=len(combined_text.split()),
                content_hash=c_hash,
            )
            if chunks:
                chunk.previous_chunk_id = chunks[-1].chunk_id
                chunks[-1].next_chunk_id = chunk.chunk_id

            chunks.append(chunk)
            current_paragraphs = []
            current_words = 0

        for line in lines:
            # Heading boundary
            if line.startswith("#"):
                _flush_chunk()
                heading_text = line.lstrip("#").strip()
                current_heading = heading_text
                current_path = [document.title, heading_text]
                continue

            # Table boundary
            if line.strip().startswith("|") and line.strip().endswith("|"):
                current_paragraphs.append(line)
                current_words += len(line.split())
                continue

            if not line.strip():
                if current_words >= self.target_words:
                    _flush_chunk()
                continue

            current_paragraphs.append(line)
            current_words += len(line.split())
            if current_words >= self.target_words:
                _flush_chunk()

        _flush_chunk()
        return chunks


chunker = StructureAwareChunker()
