"""Qdrant Vector Store Integration (§42, DS-A03, DS-A26)."""

import logging
from typing import List, Dict, Any, Optional
from scraper.config import settings

logger = logging.getLogger(__name__)

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct, Filter

    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False


class VectorStoreManager:
    """Manages Qdrant vector database collections for text and visual multivectors (§42)."""

    DEFAULT_COLLECTION = "deepsearch_chunks"

    def __init__(
        self, url: Optional[str] = None, collection_name: Optional[str] = None
    ):
        self.url = url or settings.qdrant_url
        self.collection_name = collection_name or self.DEFAULT_COLLECTION
        self.client: Optional[QdrantClient] = None
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
        self, doc_id: str, vector: List[float], payload: Dict[str, Any]
    ) -> bool:
        if not self.client:
            return False
        try:
            self.ensure_collection(vector_size=len(vector))
            self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    PointStruct(
                        id=doc_id,
                        vector=vector,
                        payload=payload,
                    )
                ],
            )
            return True
        except Exception as e:
            logger.error("Failed to upsert point %s: %s", doc_id, e)
            return False

    def search_text(
        self,
        vector: List[float],
        top_k: int = 5,
        filter_payload: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        if not self.client or not self.has_documents():
            return []
        try:
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=vector,
                limit=top_k,
            )
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

    def search_text_by_query(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
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
