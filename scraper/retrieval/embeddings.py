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

    def _pseudo_embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        for word in text.lower().split():
            h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dimension
            vec[idx] += 1.0

        norm = sum(x * x for x in vec) ** 0.5
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    def embed_text_dense(self, text: str) -> list[float]:
        """Embeds single text string into a float vector."""
        batch = self.embed_texts_batch([text])
        return batch[0] if batch else self._pseudo_embed(text)

    def embed_texts_batch(self, texts: list[str]) -> list[list[float]]:
        """Embeds a batch of text strings into float vectors using SIMD batching."""
        if not texts:
            return []
        model = self._get_model()
        if model is not None:
            try:
                embeddings = list(model.embed(texts))
                return [emb.tolist() for emb in embeddings]
            except Exception as e:
                logger.warning("FastEmbed batch embed failed: %s", e)

        return [self._pseudo_embed(t) for t in texts]

    async def async_embed_texts_batch(self, texts: list[str]) -> list[list[float]]:
        """Non-blocking async wrapper for batch embedding execution."""
        import asyncio

        return await asyncio.to_thread(self.embed_texts_batch, texts)


embedding_engine = FastEmbedEngine()
