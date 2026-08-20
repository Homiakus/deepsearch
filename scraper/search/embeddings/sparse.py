"""Sparse Lexical Representation Engine (DS-SI39).

Generates sparse vector representations (indices and values) for exact token,
identifier, standard, and technical symbol matching in hybrid search.
"""

import hashlib
import re
from typing import Dict, List
from pydantic import BaseModel, Field


class SparseVector(BaseModel):
    indices: List[int] = Field(default_factory=list)
    values: List[float] = Field(default_factory=list)


class SparseEmbeddingEngine:
    """Computes BM25/TF-IDF-like hashed term frequencies for exact match sparse indexing."""

    def __init__(self, vocab_space: int = 100000):
        self.vocab_space = vocab_space

    def embed_sparse(self, text: str) -> SparseVector:
        tokens = re.findall(r"[a-zA-Z0-9_.-]+", text.lower())
        if not tokens:
            return SparseVector()

        # Token frequencies
        counts: Dict[str, int] = {}
        for t in tokens:
            if len(t) > 1:
                counts[t] = counts.get(t, 0) + 1

        sparse_map: Dict[int, float] = {}
        for token, count in counts.items():
            # Stable token index hash
            idx = (
                int(hashlib.md5(token.encode("utf-8")).hexdigest()[:8], 16)
                % self.vocab_space
            )
            # TF score with log saturation
            val = 1.0 + (count - 1) * 0.2
            # Extra weight for technical identifiers (uppercase / underscores / dots)
            if (
                "_" in token
                or "-" in token
                or "." in token
                or any(c.isdigit() for c in token)
            ):
                val *= 1.5
            sparse_map[idx] = max(sparse_map.get(idx, 0.0), round(val, 3))

        indices = sorted(sparse_map.keys())
        values = [sparse_map[idx] for idx in indices]

        return SparseVector(indices=indices, values=values)


sparse_embedder = SparseEmbeddingEngine()
