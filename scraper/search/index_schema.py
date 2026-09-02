"""Qdrant Collection Schema and Index Payload Definition (DS-SI37)."""

from pydantic import BaseModel, Field


class IndexedChunkPayload(BaseModel):
    chunk_id: str
    document_id: str
    source_id: str
    url: str
    canonical_url: str
    domain: str
    title: str
    heading_path: list[str] = Field(default_factory=list)
    text: str
    language: str = "en"
    published_at: str | None = None
    source_type: str = "UNKNOWN"
    authority_score: float = 0.5
    goal_ids: list[str] = Field(default_factory=list)
    content_hash: str = ""
    near_dup_cluster: int = 0
    token_count: int = 0


DEFAULT_DENSE_VECTOR_SIZE = 384
DEFAULT_SPARSE_VECTOR_NAME = "sparse"
DEFAULT_COLLECTION_NAME = "deepsearch_chunks_v2"
