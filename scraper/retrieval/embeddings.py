"""Local dense embedding engine based on FastEmbed (§10, DS-A27)."""

import hashlib
import logging

logger = logging.getLogger(__name__)


class FastEmbedEngine:
    """Provides local dense vector embeddings using fastembed with fallback."""

    def __init__(
        self, model_name: str = "BAAI/bge-small-en-v1.5", dimension: int = 384
    ):
        self.model_name = model_name
        self.dimension = dimension
        self._model = None
        self._initialized = False

    def _get_model(self):
        if not self._initialized:
            import os

            if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get(
                "DEEPSEARCH_OFFLINE"
            ):
                self._model = None
                self._initialized = True
                return None
            try:
                from fastembed import TextEmbedding

                self._model = TextEmbedding(model_name=self.model_name)
            except Exception as e:
                logger.warning("FastEmbed not initialized (will use fallback): %s", e)
                self._model = None
            self._initialized = True
        return self._model

    def embed_text_dense(self, text: str) -> list[float]:
        """Embeds single text string into a float vector."""
        model = self._get_model()
        if model is not None:
            try:
                embeddings = list(model.embed([text]))
                return embeddings[0].tolist()
            except Exception as e:
                logger.warning("FastEmbed embed failed: %s", e)

        # Fallback deterministic pseudo-embedding for offline/test environments
        vec = [0.0] * self.dimension
        for word in text.lower().split():
            h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dimension
            vec[idx] += 1.0

        # Normalize L2 norm
        norm = sum(x * x for x in vec) ** 0.5
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec


embedding_engine = FastEmbedEngine()
