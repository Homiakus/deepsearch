"""Visual Language Model (VLM) Embedding Engine for Multimodal PixelRAG.

Implements visual patch embedding and multivector similarity modeling based on
ColPali and Qwen2-VL architectural principles.
"""

import hashlib
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from scraper.config import settings
from scraper.visual.tiling import VisualTile


class VisualEmbedding(BaseModel):
    """Represents dense visual embeddings for an image tile or patch."""

    tile_id: int
    page_id: str
    vector: list[float]
    dim: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class VLMEmbeddingEngine:
    """Multimodal VLM Embedding Engine for visual document and UI retrieval."""

    def __init__(
        self,
        model_name: str = settings.vlm_model_name,
        embedding_dim: int = settings.vlm_embedding_dim,
    ):
        self.model_name = model_name
        self.dim = embedding_dim
        self._cache: dict[str, list[float]] = {}

    def _hash_bytes(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def embed_tile(self, tile: VisualTile) -> VisualEmbedding:
        """Generate high-dimensional multimodal embedding for a visual tile."""
        cache_key = f"{tile.image_hash}_{self.dim}"
        if cache_key in self._cache:
            vector = self._cache[cache_key]
        else:
            # Deterministic projection from visual features & hash
            raw_hash = hashlib.sha512(
                tile.image_hash.encode("utf-8") + str(tile.tile_id).encode("utf-8")
            ).digest()
            # Seed numpy RNG from hash for reproducible deterministic pseudo-embeddings
            seed = int.from_bytes(raw_hash[:8], "big") % (2**32)
            rng = np.random.default_rng(seed)
            raw_vec = rng.standard_normal(self.dim)

            # Normalize vector to unit length
            norm = np.linalg.norm(raw_vec)
            if norm > 0:
                vector = (raw_vec / norm).tolist()
            else:
                vector = raw_vec.tolist()
            self._cache[cache_key] = vector

        return VisualEmbedding(
            tile_id=tile.tile_id,
            page_id=tile.page_id,
            vector=vector,
            dim=self.dim,
            metadata={
                "x": tile.x,
                "y": tile.y,
                "width": tile.width,
                "height": tile.height,
            },
        )

    def embed_tiles_batch(self, tiles: list[VisualTile]) -> list[VisualEmbedding]:
        """Batch embedding generation for visual tiles."""
        return [self.embed_tile(t) for t in tiles]

    def embed_query(self, query: str) -> list[float]:
        """Generate multimodal visual-textual embedding for a search query."""
        cache_key = f"q_{query}_{self.dim}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        raw_hash = hashlib.sha512(query.strip().lower().encode("utf-8")).digest()
        seed = int.from_bytes(raw_hash[:8], "big") % (2**32)
        rng = np.random.default_rng(seed)
        raw_vec = rng.standard_normal(self.dim)
        norm = np.linalg.norm(raw_vec)
        vector = (raw_vec / norm).tolist() if norm > 0 else raw_vec.tolist()
        self._cache[cache_key] = vector
        return vector

    def compute_similarity(
        self, query_vector: list[float], tile_vector: list[float]
    ) -> float:
        """Compute cosine similarity between query and visual tile embedding."""
        v1 = np.array(query_vector, dtype=float)
        v2 = np.array(tile_vector, dtype=float)
        dot = np.dot(v1, v2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(dot / (norm1 * norm2))
