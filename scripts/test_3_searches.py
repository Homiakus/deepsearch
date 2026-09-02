"""Script to test DeepSearch platform on 3 distinct research search topics."""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper.application.models import ResearchRequest, RunLifecycleState
from scraper.application.service import get_deepsearch_service
from scraper.config import ExecutionMode


async def run_single_search(
    service, query: str, category: str, max_pages: int = 5, depth: int = 2
) -> dict:
    print(f"\n{'=' * 70}")
    print(f"[*] STARTING SEARCH: '{query}'")
    print(f"[*] Category: {category} | Max Pages: {max_pages} | Depth: {depth}")
    print(f"{'=' * 70}")

    output_zip = f"test_run_{category}.zip"
    req = ResearchRequest(
        query=query,
        depth=depth,
        max_pages=max_pages,
        mode=ExecutionMode.BALANCED,
        min_media_count=2,
        max_media_count=8,
        enable_media_archiving=True,
        output_archive_path=output_zip,
    )

    start_time = time.time()
    handle = await service.start_research(req)
    print(f"[+] Run ID assigned: {handle.run_id}")

    last_processed = -1
    while True:
        await asyncio.sleep(0.5)
        st = await service.research_status(handle.run_id)
        if st.pages_processed != last_processed:
            print(
                f"    -> Progress: {st.pages_processed}/{max_pages} pages processed (progress: {st.progress * 100:.0f}%, status: {st.status.value})"
            )
            last_processed = st.pages_processed

        if st.status in (
            RunLifecycleState.COMPLETED,
            RunLifecycleState.FAILED,
            RunLifecycleState.CANCELLED,
            RunLifecycleState.BUDGET_EXHAUSTED,
            RunLifecycleState.INSUFFICIENT_EVIDENCE,
        ):
            break

    elapsed = time.time() - start_time
    result = await service.research_result(handle.run_id)

    zip_size_kb = 0
    if result and result.archive_path and os.path.exists(result.archive_path):
        zip_size_kb = os.path.getsize(result.archive_path) / 1024.0

    gate_passed = (
        result.manifest.get("quality_gate_passed", False)
        if result and result.manifest
        else (result.status == RunLifecycleState.COMPLETED if result else False)
    )

    report = {
        "query": query,
        "category": category,
        "status": result.status.value if result else st.status.value,
        "elapsed_sec": round(elapsed, 2),
        "pages_processed": result.total_pages_processed
        if result
        else st.pages_processed,
        "rag_chunks": result.total_rag_chunks if result else 0,
        "quality_gate_passed": gate_passed,
        "archive_path": result.archive_path if result else None,
        "archive_size_kb": round(zip_size_kb, 1),
        "manifest_summary": {
            "title": result.manifest.get("query") if result else query,
            "total_files": len(result.manifest.get("files", [])) if result else 0,
            "total_rag_docs": len(result.manifest.get("rag_documents", []))
            if result
            else 0,
            "total_media": len(result.manifest.get("media", [])) if result else 0,
        }
        if result
        else {},
        "warnings": result.warnings if result else [],
        "errors": result.errors if result else st.errors,
    }

    print(
        f"[+] COMPLETED in {elapsed:.2f}s | Status: {report['status']} | Pages: {report['pages_processed']} | Chunks: {report['rag_chunks']} | Archive: {zip_size_kb:.1f} KB"
    )
    return report


async def main():
    service = get_deepsearch_service()

    searches = [
        {
            "query": "Attention Is All You Need Transformer Architecture",
            "category": "ai_transformers",
            "max_pages": 5,
            "depth": 2,
        },
        {
            "query": "PostgreSQL vs SQLite database architecture concurrency locking",
            "category": "databases_concurrency",
            "max_pages": 5,
            "depth": 2,
        },
        {
            "query": "Quantum Computing error correction surface codes",
            "category": "quantum_error_correction",
            "max_pages": 5,
            "depth": 2,
        },
    ]

    all_reports = []
    for s in searches:
        rep = await run_single_search(
            service=service,
            query=s["query"],
            category=s["category"],
            max_pages=s["max_pages"],
            depth=s["depth"],
        )
        all_reports.append(rep)

    print("\n" + "=" * 80)
    print("FINAL 3-SEARCH BENCHMARK SUMMARY")
    print("=" * 80)
    print(json.dumps(all_reports, indent=2, ensure_ascii=False))

    with open("3_searches_report.json", "w", encoding="utf-8") as f:
        json.dump(all_reports, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    asyncio.run(main())
