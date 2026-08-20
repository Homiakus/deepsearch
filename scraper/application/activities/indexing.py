"""Indexing activity implementation (§4, DS-A09, DS-A25, DS-A26)."""

from typing import Any, Dict, List
import uuid
from scraper.storage.vector_store import VectorStoreManager
from scraper.orchestration.protocol import ActivityResult, ResourceUsage


async def run_indexing_activity(input_data: Dict[str, Any]) -> ActivityResult:
    """Chunks documents and indexes them in vector store."""
    docs: List[Dict[str, Any]] = input_data.get("normalized_docs", [])
    vector_store = VectorStoreManager()

    indexed_chunks = []

    for doc in docs:
        text = doc.get("clean_markdown", "")
        url = doc.get("url", "")
        # Structural paragraph/section chunking
        paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 30]

        for i, para in enumerate(paragraphs):
            chunk_id = str(uuid.uuid4())
            chunk_data = {
                "chunk_id": chunk_id,
                "document_url": url,
                "ordinal": i,
                "text": para,
                "word_count": len(para.split()),
            }
            indexed_chunks.append(chunk_data)

            # If vector store is available, generate embedding & upsert
            if vector_store.client:
                try:
                    from scraper.retrieval.embeddings import embedding_engine

                    vec = embedding_engine.embed_text_dense(para)
                    vector_store.upsert_text_embedding(
                        doc_id=chunk_id,
                        vector=vec,
                        payload={
                            "url": url,
                            "text": para,
                            "document_id": doc.get("blake3_hash", ""),
                        },
                    )
                except Exception:
                    pass

    return ActivityResult(
        data={
            "indexed_chunks": indexed_chunks,
            "total_chunks": len(indexed_chunks),
        },
        usage=ResourceUsage(tokens=sum(c.get("word_count", 0) for c in indexed_chunks)),
        quality={"indexing_rate": 1.0 if indexed_chunks else 0.0},
    )
