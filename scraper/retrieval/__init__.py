"""Retrieval module."""

from scraper.retrieval.chunking import StructureAwareChunker, TextChunk, chunker
from scraper.retrieval.embeddings import FastEmbedEngine, embedding_engine
from scraper.retrieval.hybrid import RankedHit, ScoredResult, reciprocal_rank_fusion

__all__ = [
    "FastEmbedEngine",
    "RankedHit",
    "ScoredResult",
    "StructureAwareChunker",
    "TextChunk",
    "chunker",
    "embedding_engine",
    "reciprocal_rank_fusion",
]
