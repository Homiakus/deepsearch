"""Dense Embedding Engine (DS-SI38).

Provides batch dense embeddings with in-memory hashing cache and FastEmbed support.
"""

import hashlib
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class DenseEmbeddingEngine:
    def __init__(
        self, model_name: str = "BAAI/bge-small-en-v1.5", dimension: int = 384
    ):
        self.model_name = model_name
        self.dimension = dimension
        self._model = None
        self._initialized = False
        self._cache: Dict[str, List[float]] = {}

    def _get_model(self):
        if not self._initialized:
            import os

            if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("DEEPSEARCH_OFFLINE"):
                self._model = None
                self._initialized = True
                return None
            try:
                from fastembed import TextEmbedding

                self._model = TextEmbedding(model_name=self.model_name)
            except Exception as e:
                logger.warning("FastEmbed dense model initialization fallback: %s", e)
                self._model = None
            self._initialized = True
        return self._model

    def embed_query(self, query: str) -> List[float]:
        return self.embed_text(query)

    def embed_text(self, text: str) -> List[float]:
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if h in self._cache:
            return self._cache[h]

        model = self._get_model()
        if model is not None:
            try:
                vecs = list(model.embed([text]))
                v = vecs[0].tolist()
                self._cache[h] = v
                return v
            except Exception as e:
                logger.warning("FastEmbed error: %s", e)

        # Fallback deterministic pseudo-embedding
        vec = [0.0] * self.dimension
        for word in text.lower().split():
            idx = (
                int(hashlib.md5(word.encode("utf-8")).hexdigest()[:8], 16)
                % self.dimension
            )
            vec[idx] += 1.0

        norm = sum(x * x for x in vec) ** 0.5
        if norm > 0:
            vec = [x / norm for x in vec]

        self._cache[h] = vec
        return vec

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_text(t) for t in texts]


dense_embedder = DenseEmbeddingEngine()
