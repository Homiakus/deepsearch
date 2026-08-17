"""Structure-Aware Hierarchical Chunking (DS-SI65, DS-SI66).

Splits documents along headings, paragraphs, and tables, maintaining parent heading paths
and contextual relationships for parent-child retrieval.
"""

import hashlib
import re
import uuid
from typing import List, Optional
from pydantic import BaseModel, Field


class StructuredChunk(BaseModel):
    chunk_id: str = Field(default_factory=lambda: f"chk_{uuid.uuid4().hex[:10]}")
    document_id: str
    source_url: str
    canonical_url: str = ""
    domain: str = ""
    title: str = ""
    heading_path: List[str] = Field(default_factory=list)
    parent_section_id: Optional[str] = None
    ordinal: int = 0
    text: str
    word_count: int = 0
    content_hash: str = ""
    previous_chunk_id: Optional[str] = None
    next_chunk_id: Optional[str] = None


class StructureAwareChunker:
    """Chunks structured markdown text preserving heading hierarchy and table structures."""

    def __init__(self, target_words: int = 200, min_words: int = 25):
        self.target_words = target_words
        self.min_words = min_words

    def chunk_markdown(
        self,
        markdown_text: str,
        document_id: str,
        source_url: str,
        title: str = "",
    ) -> List[StructuredChunk]:
        if not markdown_text:
            return []

        lines = markdown_text.splitlines()
        chunks: List[StructuredChunk] = []

        current_heading_path: List[str] = [title] if title else []
        current_paragraphs: List[str] = []
        current_words = 0
        section_id = f"sec_{uuid.uuid4().hex[:8]}"

        import urllib.parse
        domain = urllib.parse.urlparse(source_url).netloc.lower() if "//" in source_url else ""

        def _flush():
            nonlocal current_paragraphs, current_words
            if not current_paragraphs:
                return

            block = "\n\n".join(current_paragraphs).strip()
            if not block:
                return

            c_hash = hashlib.sha256(block.encode("utf-8")).hexdigest()
            chunk = StructuredChunk(
                document_id=document_id,
                source_url=source_url,
                canonical_url=source_url,
                domain=domain,
                title=title,
                heading_path=list(current_heading_path),
                parent_section_id=section_id,
                ordinal=len(chunks),
                text=block,
                word_count=len(block.split()),
                content_hash=c_hash,
            )

            if chunks:
                chunk.previous_chunk_id = chunks[-1].chunk_id
                chunks[-1].next_chunk_id = chunk.chunk_id

            chunks.append(chunk)
            current_paragraphs = []
            current_words = 0

        for line in lines:
            line_str = line.strip()
            if line_str.startswith("#"):
                _flush()
                h_level = len(line_str) - len(line_str.lstrip("#"))
                h_text = line_str.lstrip("#").strip()
                section_id = f"sec_{uuid.uuid4().hex[:8]}"

                # Adjust heading path depth
                if len(current_heading_path) > h_level:
                    current_heading_path = current_heading_path[:h_level]
                current_heading_path.append(h_text)
                continue

            # Table preservation
            if line_str.startswith("|") and line_str.endswith("|"):
                current_paragraphs.append(line)
                current_words += len(line.split())
                continue

            if not line_str:
                if current_words >= self.target_words:
                    _flush()
                continue

            current_paragraphs.append(line)
            current_words += len(line.split())
            if current_words >= self.target_words:
                _flush()

        _flush()
        return chunks


structure_chunker = StructureAwareChunker()
