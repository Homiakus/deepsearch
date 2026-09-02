"""Qdrant Vector Store Integration (§42, DS-A03, DS-A26)."""

import logging
from typing import Any

from scraper.config import settings

logger = logging.getLogger(__name__)

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        FieldCondition,
        Filter,
        MatchValue,
        PointStruct,
        VectorParams,
    )

    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False


class VectorStoreManager:
    """[DEPRECATED: DS-41] Legacy Qdrant vector database collection manager.

    Superceded by SncSinCore Epistemic Memory for deterministic evidence subgraphs.
    Retained for backward compatibility with experimental dense vector plugins.
    """

    DEFAULT_COLLECTION = "deepsearch_chunks"

    def __init__(self, url: str | None = None, collection_name: str | None = None):
        logger.debug(
            "Initializing legacy VectorStoreManager (superceded by SncSinCore Epistemic Memory)"
        )
        self.url = url or settings.qdrant_url
        self.collection_name = collection_name or self.DEFAULT_COLLECTION
        self.client: QdrantClient | None = None
        if QDRANT_AVAILABLE and self.url:
            try:
                self.client = QdrantClient(url=self.url, timeout=3.0)
            except Exception as e:
                logger.warning("Failed to initialize QdrantClient: %s", e)
                self.client = None

    def is_healthy(self) -> bool:
        if not self.client:
            return False
        try:
            self.client.get_collections()
            return True
        except Exception:
            return False

    def ensure_collection(
        self, vector_size: int = 384, distance: str = "Cosine"
    ) -> bool:
        """Create collection if it does not exist with appropriate vector dimensions."""
        if not self.client:
            return False
        try:
            collections = [c.name for c in self.client.get_collections().collections]
            if self.collection_name not in collections:
                dist = Distance.COSINE if distance == "Cosine" else Distance.DOT
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=vector_size, distance=dist),
                )
            return True
        except Exception as e:
            logger.error("Error creating collection %s: %s", self.collection_name, e)
            return False

    def has_documents(self) -> bool:
        if not self.client:
            return False
        try:
            info = self.client.get_collection(self.collection_name)
            return (info.points_count or 0) > 0
        except Exception:
            return False

    def upsert_text_embedding(
        self, doc_id: str, vector: list[float], payload: dict[str, Any]
    ) -> bool:
        return self.upsert_text_embeddings_batch([(doc_id, vector, payload)])

    def upsert_text_embeddings_batch(
        self, records: list[tuple[str, list[float], dict[str, Any]]]
    ) -> bool:
        """Batch upsert multiple text embedding points in a single Qdrant request."""
        if not self.client or not records:
            return False
        try:
            vector_size = len(records[0][1])
            self.ensure_collection(vector_size=vector_size)
            points = [
                PointStruct(id=doc_id, vector=vector, payload=payload)
                for doc_id, vector, payload in records
            ]
            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
            )
            return True
        except Exception as e:
            logger.error("Failed to batch upsert %d points: %s", len(records), e)
            return False

    def search_text(
        self,
        vector: list[float],
        top_k: int = 5,
        filter_payload: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not self.client or not self.has_documents():
            return []
        try:
            query_filter = None
            if filter_payload and QDRANT_AVAILABLE:
                conditions = [
                    FieldCondition(key=k, match=MatchValue(value=v))
                    for k, v in filter_payload.items()
                    if v is not None
                ]
                if conditions:
                    query_filter = Filter(must=conditions)

            search_kwargs: dict[str, Any] = {
                "collection_name": self.collection_name,
                "query_vector": vector,
                "limit": top_k,
            }
            if query_filter is not None:
                search_kwargs["query_filter"] = query_filter

            results = self.client.search(**search_kwargs)
            return [
                {
                    "id": hit.id,
                    "score": hit.score,
                    "payload": hit.payload or {},
                }
                for hit in results
            ]
        except Exception as e:
            logger.error("Failed to search vector store: %s", e)
            return []

    def search_text_by_query(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Search text by query using FastEmbed dense vector representation."""
        if not self.client or not self.has_documents():
            return []
        try:
            from scraper.retrieval.embeddings import embedding_engine

            vector = embedding_engine.embed_query_dense(query)
            return self.search_text(vector=vector, top_k=top_k)
        except Exception as e:
            logger.warning("Error generating query embedding: %s", e)
            return []

    def delete_by_document(self, document_id: str) -> bool:
        """Delete all points belonging to a specific document."""
        if not self.client:
            return False
        try:
            from qdrant_client.models import FieldCondition, MatchValue

            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="document_id", match=MatchValue(value=document_id)
                        )
                    ]
                ),
            )
            return True
        except Exception as e:
            logger.error("Failed to delete points for document %s: %s", document_id, e)
            return False
