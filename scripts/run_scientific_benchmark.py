"""Scientific Search Benchmark & System Evaluation (§DS-SI, §DS-04).

Runs 3 representative scientific queries across distinct scientific domains:
1. Biomedical / Genetics: CRISPR-Cas9 gene editing
2. Computer Science / AI: Transformer attention architecture
3. Quantum Physics: Quantum error correction surface codes
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Ensure UTF-8 output encoding for Windows consoles
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper.application.models import ResearchRequest, RunLifecycleState  # noqa: E402
from scraper.application.service import get_deepsearch_service  # noqa: E402
from scraper.config import ExecutionMode  # noqa: E402


async def test_scientific_search(
    service,
    query: str,
    category: str,
    domain: str = None,
    max_pages: int = 5,
    depth: int = 2,
) -> dict:
    print(f"\n{'=' * 75}")
    print(f"🔬 TESTING SCIENTIFIC SEARCH: '{query}'")
    print(f"📌 Domain/Category: {category} | Max Pages: {max_pages} | Depth: {depth}")
    print(f"{'=' * 75}")

    output_zip = f"scientific_run_{category}.zip"
    req = ResearchRequest(
        query=query,
        category=category,
        domain=domain,
        depth=depth,
        max_pages=max_pages,
        mode=ExecutionMode.BALANCED,
        min_media_count=1,
        max_media_count=5,
        enable_media_archiving=True,
        output_archive_path=output_zip,
        auto_discover=True,
    )

    start_time = time.time()
    handle = await service.start_research(req)
    print(f"[+] Run ID: {handle.run_id}")

    last_processed = -1
    last_node = ""
    while True:
        await asyncio.sleep(0.5)
        st = await service.research_status(handle.run_id)

        if st.current_node != last_node or st.pages_processed != last_processed:
            print(
                f"    [Step: {st.current_node}] Progress: {st.progress * 100:.0f}% | Pages processed: {st.pages_processed}/{max_pages} (status: {st.status.value})"
            )
            last_node = st.current_node
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

    zip_size_kb = 0.0
    if result and result.archive_path and os.path.exists(result.archive_path):
        zip_size_kb = os.path.getsize(result.archive_path) / 1024.0

    manifest = result.manifest if result else {}
    files_list = manifest.get("files", [])
    rag_docs = manifest.get("rag_documents", [])
    media_list = manifest.get("media", [])
    quality_summary = manifest.get("quality_report", {})
    sources_summary = manifest.get("sources", [])

    report = {
        "query": query,
        "category": category,
        "run_id": handle.run_id,
        "status": result.status.value if result else st.status.value,
        "elapsed_sec": round(elapsed, 2),
        "pages_processed": result.total_pages_processed
        if result
        else st.pages_processed,
        "rag_chunks": result.total_rag_chunks if result else 0,
        "archive_path": result.archive_path if result else None,
        "archive_size_kb": round(zip_size_kb, 1),
        "manifest_details": {
            "total_files": len(files_list),
            "total_rag_docs": len(rag_docs),
            "total_media": len(media_list),
            "top_sources": [
                {
                    "title": s.get("title"),
                    "url": s.get("url"),
                    "provider": s.get("provider"),
                }
                for s in sources_summary[:3]
            ],
            "sample_media": [
                {"caption": m.get("caption"), "url": m.get("url")}
                for m in media_list[:2]
            ],
        },
        "quality_gate": {
            "passed": manifest.get("quality_gate_passed", False)
            or (result.status == RunLifecycleState.COMPLETED if result else False),
            "report": quality_summary,
        },
        "warnings": result.warnings if result else [],
        "errors": result.errors if result else st.errors,
    }

    print(f"\n✅ Result for '{category}':")
    print(f"   - Status: {report['status']}")
    print(f"   - Duration: {elapsed:.2f}s")
    print(f"   - Pages Processed: {report['pages_processed']}")
    print(f"   - RAG Chunks: {report['rag_chunks']}")
    print(f"   - Files in Archive: {len(files_list)}")
    print(f"   - Media/Figures: {len(media_list)}")
    print(f"   - Archive Size: {zip_size_kb:.1f} KB")
    print(f"   - Archive Path: {report['archive_path']}")
    return report


async def main():
    service = get_deepsearch_service()

    test_queries = [
        {
            "query": "CRISPR Cas9 gene editing mechanism in immunotherapy",
            "category": "science",
            "max_pages": 4,
            "depth": 2,
        },
        {
            "query": "Transformer self-attention architecture neural networks",
            "category": "science",
            "max_pages": 4,
            "depth": 2,
        },
        {
            "query": "Quantum error correction surface codes fault tolerance",
            "category": "science",
            "max_pages": 4,
            "depth": 2,
        },
    ]

    all_reports = []
    for tq in test_queries:
        rep = await test_scientific_search(
            service=service,
            query=tq["query"],
            category=tq["category"],
            max_pages=tq["max_pages"],
            depth=tq["depth"],
        )
        all_reports.append(rep)

    await service.close()

    summary_file = "scientific_3_searches_report.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(all_reports, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 80)
    print("📊 3-SEARCH SCIENTIFIC BENCHMARK COMPLETED")
    print(f"Report written to {summary_file}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
