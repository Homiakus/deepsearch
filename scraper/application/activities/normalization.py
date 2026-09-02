"""Normalization and deduplication activity (§4, DS-A09, DS-A14)."""

from typing import Any

from scraper.normalization.deduplicator import Deduplicator
from scraper.orchestration.protocol import ActivityResult, ResourceUsage


async def run_normalization_activity(input_data: dict[str, Any]) -> ActivityResult:
    """Deduplicates and normalizes extracted documents based on content hashes."""
    docs: list[dict[str, Any]] = input_data.get("extracted_docs", [])
    dedup = Deduplicator()

    normalized_docs = []
    seen_hashes = set()

    for doc in docs:
        text = doc.get("clean_markdown", "")
        if not text:
            continue

        hashes = dedup.compute_hashes(text)
        b3_hash = hashes.blake3_hash

        if b3_hash in seen_hashes:
            continue
        seen_hashes.add(b3_hash)

        doc_copy = dict(doc)
        doc_copy["blake3_hash"] = b3_hash
        doc_copy["simhash"] = hashes.simhash_64
        normalized_docs.append(doc_copy)

    return ActivityResult(
        data={
            "normalized_docs": normalized_docs,
            "total_normalized": len(normalized_docs),
            "duplicates_removed": len(docs) - len(normalized_docs),
        },
        usage=ResourceUsage(),
        quality={"unique_ratio": float(len(normalized_docs)) / max(len(docs), 1)},
    )
