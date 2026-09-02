"""Structure-Aware Hierarchical Chunking Engine (§9, DS-A25)."""

import hashlib
import uuid

from pydantic import BaseModel, Field

from scraper.domain.document import Document


class TextChunk(BaseModel):
    chunk_id: str
    document_id: str
    source_url: str
    heading: str | None = None
    section_path: list[str] = Field(default_factory=list)
    ordinal: int = 0
    text: str
    word_count: int = 0
    token_estimate: int = 0
    content_hash: str
    previous_chunk_id: str | None = None
    next_chunk_id: str | None = None


class StructureAwareChunker:
    """Chunks documents along headings, paragraphs, and table boundaries without arbitrary truncation."""

    def __init__(
        self,
        target_words: int = 250,
        min_words: int = 30,
        overlap_words: int = 0,
    ):
        self.target_words = target_words
        self.min_words = min_words
        self.overlap_words = overlap_words

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Multilingual token count estimation."""
        if not text:
            return 0
        words = len(text.split())
        chars = len(text)
        return max(int(words * 1.3), int(chars / 3.5), 1)

    def _split_oversized_text(self, text: str) -> list[str]:
        """Splits an oversized paragraph into sentence/word-bounded chunks (§FRAG-006)."""
        import re

        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        if not sentences:
            words = text.split()
            if len(words) <= self.target_words:
                return [text]
            return [
                " ".join(words[i : i + self.target_words])
                for i in range(0, len(words), self.target_words)
            ]

        sub_blocks = []
        cur_sentences = []
        cur_w = 0

        for s in sentences:
            s_words = s.split()
            if len(s_words) > self.target_words:
                if cur_sentences:
                    sub_blocks.append(" ".join(cur_sentences))
                    cur_sentences = []
                    cur_w = 0
                for i in range(0, len(s_words), self.target_words):
                    sub_blocks.append(" ".join(s_words[i : i + self.target_words]))
                continue

            sw = len(s_words)
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

    def chunk_document(self, document: Document) -> list[TextChunk]:
        """Creates linked chunks preserving section headings and document context."""
        raw_markdown = document.clean_markdown
        lines = raw_markdown.splitlines()

        chunks: list[TextChunk] = []
        current_heading = document.title
        current_path = [document.title] if document.title else []
        current_paragraphs: list[str] = []
        current_words = 0

        def _emit_chunk(block_text: str):
            nonlocal chunks
            c_id = f"chunk_{uuid.uuid4().hex[:12]}"
            c_hash = hashlib.sha256(
                block_text.encode("utf-8", errors="replace")
            ).hexdigest()
            w_count = len(block_text.split())
            t_est = self.estimate_tokens(block_text)

            chunk = TextChunk(
                chunk_id=c_id,
                document_id=document.id,
                source_url=document.source_url,
                heading=current_heading,
                section_path=list(current_path),
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

        def _flush_chunk(reset_overlap: bool = False):
            nonlocal current_paragraphs, current_words
            if not current_paragraphs:
                return
            combined_text = "\n\n".join(current_paragraphs).strip()
            if len(combined_text) == 0:
                current_paragraphs = []
                current_words = 0
                return

            is_table = combined_text.startswith("|") and combined_text.endswith("|")
            if current_words > self.target_words and not is_table:
                sub_blocks = self._split_oversized_text(combined_text)
                for sb in sub_blocks:
                    if sb.strip():
                        _emit_chunk(sb.strip())
            else:
                _emit_chunk(combined_text)

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
            # Heading boundary
            if line.startswith("#"):
                _flush_chunk(reset_overlap=True)
                heading_text = line.lstrip("#").strip()
                current_heading = heading_text
                current_path = (
                    [document.title, heading_text] if document.title else [heading_text]
                )
                continue

            # Table boundary
            if line.strip().startswith("|") and line.strip().endswith("|"):
                current_paragraphs.append(line)
                current_words += len(line.split())
                continue

            if not line.strip():
                if current_words >= self.target_words:
                    _flush_chunk(reset_overlap=False)
                continue

            current_paragraphs.append(line)
            current_words += len(line.split())
            if current_words >= self.target_words:
                _flush_chunk(reset_overlap=False)

        _flush_chunk(reset_overlap=True)
        return chunks


chunker = StructureAwareChunker()
