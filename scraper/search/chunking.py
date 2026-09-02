"""Structure-Aware Hierarchical Chunking (DS-SI65, DS-SI66).

Splits documents along headings, paragraphs, and tables, maintaining parent heading paths
and contextual relationships for parent-child retrieval.
"""

import hashlib
import uuid

from pydantic import BaseModel, Field


class StructuredChunk(BaseModel):
    chunk_id: str = Field(default_factory=lambda: f"chk_{uuid.uuid4().hex[:10]}")
    document_id: str
    source_url: str
    canonical_url: str = ""
    domain: str = ""
    title: str = ""
    heading_path: list[str] = Field(default_factory=list)
    parent_section_id: str | None = None
    ordinal: int = 0
    text: str
    word_count: int = 0
    token_estimate: int = 0
    content_hash: str = ""
    previous_chunk_id: str | None = None
    next_chunk_id: str | None = None


class StructureAwareChunker:
    """Chunks structured markdown text preserving heading hierarchy and table structures."""

    def __init__(
        self,
        target_words: int = 200,
        min_words: int = 25,
        overlap_words: int = 0,
    ):
        self.target_words = target_words
        self.min_words = min_words
        self.overlap_words = overlap_words

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Multilingual token count estimation (BPE safe for Latin, Cyrillic, CJK, and code)."""
        if not text:
            return 0
        words = len(text.split())
        chars = len(text)
        return max(int(words * 1.3), int(chars / 3.5), 1)

    def _split_oversized_text(self, text: str) -> list[str]:
        """Splits an oversized paragraph into sentence-bounded chunks."""
        import re

        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        if not sentences:
            return [text]

        sub_blocks = []
        cur_sentences = []
        cur_w = 0

        for s in sentences:
            sw = len(s.split())
            if cur_w + sw > self.target_words and cur_sentences:
                sub_blocks.append(" ".join(cur_sentences))
                cur_sentences = [s]
                cur_w = sw
            else:
                cur_sentences.append(s)
                cur_w += sw

        if cur_sentences:
            sub_blocks.append(" ".join(cur_sentences))

        return sub_blocks or [text]

    def chunk_markdown(
        self,
        markdown_text: str,
        document_id: str,
        source_url: str,
        title: str = "",
    ) -> list[StructuredChunk]:
        if not markdown_text:
            return []

        lines = markdown_text.splitlines()
        chunks: list[StructuredChunk] = []

        current_heading_path: list[str] = [title] if title else []
        current_paragraphs: list[str] = []
        current_words = 0
        section_id = f"sec_{uuid.uuid4().hex[:8]}"

        import urllib.parse

        domain = (
            urllib.parse.urlparse(source_url).netloc.lower()
            if "//" in source_url
            else ""
        )

        def _emit_chunk(block_text: str):
            nonlocal chunks
            c_hash = hashlib.sha256(
                block_text.encode("utf-8", errors="replace")
            ).hexdigest()
            w_count = len(block_text.split())
            t_est = self.estimate_tokens(block_text)

            chunk = StructuredChunk(
                document_id=document_id,
                source_url=source_url,
                canonical_url=source_url,
                domain=domain,
                title=title,
                heading_path=list(current_heading_path),
                parent_section_id=section_id,
                ordinal=len(chunks),
                text=block_text,
                word_count=w_count,
                token_estimate=t_est,
                content_hash=c_hash,
            )

            if chunks:
                chunk.previous_chunk_id = chunks[-1].chunk_id
                chunks[-1].next_chunk_id = chunk.chunk_id

            chunks.append(chunk)

        def _flush(reset_overlap: bool = False):
            nonlocal current_paragraphs, current_words
            if not current_paragraphs:
                return

            block = "\n\n".join(current_paragraphs).strip()
            if not block:
                current_paragraphs = []
                current_words = 0
                return

            # Check if block exceeds target_words and has multiple sentences (and not a markdown table)
            is_table = block.startswith("|") and block.endswith("|")
            if current_words > self.target_words and not is_table:
                sub_blocks = self._split_oversized_text(block)
                if len(sub_blocks) > 1:
                    for sb in sub_blocks:
                        if sb.strip():
                            _emit_chunk(sb.strip())
                else:
                    _emit_chunk(block)
            else:
                _emit_chunk(block)

            # Handle overlap if within the same section
            if not reset_overlap and self.overlap_words > 0 and current_paragraphs:
                last_p = current_paragraphs[-1]
                p_words = len(last_p.split())
                if p_words <= self.overlap_words:
                    current_paragraphs = [last_p]
                    current_words = p_words
                else:
                    words = last_p.split()
                    overlap_tail = " ".join(words[-self.overlap_words :])
                    current_paragraphs = [overlap_tail]
                    current_words = len(overlap_tail.split())
            else:
                current_paragraphs = []
                current_words = 0

        for line in lines:
            line_str = line.strip()
            if line_str.startswith("#"):
                _flush(reset_overlap=True)
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
                    _flush(reset_overlap=False)
                continue

            current_paragraphs.append(line)
            current_words += len(line.split())
            if current_words >= self.target_words:
                _flush(reset_overlap=False)

        _flush(reset_overlap=True)
        return chunks


structure_chunker = StructureAwareChunker()
