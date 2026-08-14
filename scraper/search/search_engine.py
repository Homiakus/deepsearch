"""Text, Visual, and Hybrid Retrieval Search Engine (§41)."""

from typing import List
from pydantic import BaseModel


class SearchResultItem(BaseModel):
    id: str
    url: str
    title: str
    snippet: str
    score: float
    retrieval_type: str  # text | visual | hybrid


class SearchEngine:
    """Hybrid Retrieval Engine combining text vector search and visual screenshot retrieval (§41)."""

    def search_text(self, query: str, limit: int = 10) -> List[SearchResultItem]:
        return [
            SearchResultItem(
                id="doc_1",
                url="https://example.com/doc1",
                title="Sample Document 1",
                snippet=f"Matched query text: {query}",
                score=0.92,
                retrieval_type="text"
            )
        ]

    def search_visual(self, query: str, limit: int = 10) -> List[SearchResultItem]:
        return [
            SearchResultItem(
                id="visual_1",
                url="https://example.com/doc1#tile=2",
                title="Visual Diagram Match",
                snippet="Matched visual fragment diagram",
                score=0.88,
                retrieval_type="visual"
            )
        ]

    def search_hybrid(self, query: str, limit: int = 10) -> List[SearchResultItem]:
        text_results = self.search_text(query, limit=limit)
        visual_results = self.search_visual(query, limit=limit)

        # Merge and rerank (§41)
        combined = text_results + visual_results
        combined.sort(key=lambda r: r.score, reverse=True)
        return combined[:limit]
