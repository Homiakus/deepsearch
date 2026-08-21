"""Execution Script for 3 Heterogeneous Searches to profile and audit DeepSearch performance.
"""

import os
os.environ["DEEPSEARCH_OFFLINE"] = "1"
import json
import time
import asyncio
from pathlib import Path
from typing import Dict, Any, List

from scraper.config import ExecutionMode
from scraper.pipeline.search_pipeline import (
    DeepSearchPipeline,
    DeepSearchPipelineOptions,
)

SEARCH_SCENARIOS = [
    {
        "id": "search_1_medical_rus",
        "name": "1. Медицина: Ингибиторы JAK при алопеции (RU)",
        "query": "Клинические испытания ингибиторов JAK тофацитиниб барицитиниб при гнездной алопеции",
        "category": "medical",
        "max_pages": 8,
        "depth": 2,
    },
    {
        "id": "search_2_materials_en",
        "name": "2. Материаловедение: Solid-State Battery Electrolytes (EN)",
        "query": "Solid-state lithium metal batteries solid electrolyte interphase dendritic degradation impedance",
        "category": "materials_science",
        "max_pages": 8,
        "depth": 2,
    },
    {
        "id": "search_3_ai_tech",
        "name": "3. AI / Computer Science: RAG HNSW Reranking (EN)",
        "query": "Retrieval augmented generation HNSW vector search latency reranking evaluation",
        "category": "computer_science",
        "max_pages": 8,
        "depth": 2,
    },
]


async def run_benchmark():
    pipeline = DeepSearchPipeline()
    results = []
    
    print("=" * 80)
    print("STARTING 3-SEARCH PERFORMANCE AUDIT & BOTTLENECK PROFILING")
    print("=" * 80)
    
    for scenario in SEARCH_SCENARIOS:
        print(f"\n>>> Running Scenario: {scenario['name']}")
        print(f"    Query: '{scenario['query']}'")
        print(f"    Target pages: {scenario['max_pages']}, Depth: {scenario['depth']}")
        
        t0 = time.time()
        opts = DeepSearchPipelineOptions(
            query=scenario["query"],
            max_pages=scenario["max_pages"],
            depth=scenario["depth"],
            mode=ExecutionMode.BALANCED,
            enable_media_archiving=True,
            min_media_count=3,
            max_media_count=10,
        )
        
        try:
            res = await pipeline.execute(opts)
            elapsed = time.time() - t0
            
            manifest_data = res.manifest or {}
            archive_files = manifest_data.get("files", [])
            pdfs = [f for f in archive_files if f.get("type") == "pdf" or f.get("url", "").endswith(".pdf")]
            media = [f for f in archive_files if f.get("type") == "image"]
            
            summary = {
                "id": scenario["id"],
                "name": scenario["name"],
                "query": scenario["query"],
                "elapsed_sec": round(elapsed, 2),
                "pages_crawled": res.total_pages_processed,
                "rag_chunks": res.total_rag_chunks,
                "quality_gate_passed": res.quality_gate_passed,
                "dir_path": res.dir_path,
                "archive_path": res.archive_path,
                "total_media_files": len(media),
                "total_pdfs": len(pdfs),
                "unique_domains": manifest_data.get("summary", {}).get("total_unique_domains", 0),
                "average_relevance": manifest_data.get("quality_report", {}).get("average_relevance", 0.0),
            }
            
            results.append(summary)
            print(f"    [OK] Completed in {elapsed:.2f}s | Pages: {res.total_pages_processed} | Chunks: {res.total_rag_chunks} | Quality Gate: {res.quality_gate_passed}")
            
        except Exception as exc:
            elapsed = time.time() - t0
            print(f"    [FAIL] Error in scenario {scenario['id']}: {exc}")
            results.append({
                "id": scenario["id"],
                "name": scenario["name"],
                "error": str(exc),
                "elapsed_sec": round(elapsed, 2),
            })
            
    print("\n" + "=" * 80)
    print("AUDIT RESULTS SUMMARY:")
    print("=" * 80)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    
    # Save results to json
    out_file = Path("evals/audit_3_searches_results.json")
    out_file.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved benchmark results to {out_file}")


if __name__ == "__main__":
    asyncio.run(run_benchmark())
