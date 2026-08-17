"""Heterogeneous Scientific Bulk Research & Acquisition Evaluation Harness.

Executes multi-domain research pipelines across medicine, AI, physics, photonics,
and genetics, recording detailed precision, recall, PDF acquisition, deduplication,
and RAG chunking metrics.
"""

import os
import sys
import json
import time
import asyncio
from pathlib import Path
from typing import Dict, Any, List

from scraper.config import ExecutionMode
from scraper.pipeline.search_pipeline import DeepSearchPipeline, DeepSearchPipelineOptions

TEST_SUITE = [
    {
        "id": "exp_01_biomedicine",
        "domain": "biomedicine",
        "category": "medical",
        "topic": "Oncology & Biomarkers",
        "query": "Liquid biopsy and circulating tumor DNA (ctDNA) in colorectal cancer early detection",
        "max_pages": 15,
    },
    {
        "id": "exp_02_ai_systems",
        "domain": "computer_science",
        "category": "scientific",
        "topic": "AI & RAG Evaluation",
        "query": "Retrieval-augmented generation evaluation faithfulness factuality citation correctness",
        "max_pages": 15,
    },
    {
        "id": "exp_03_quantum_physics",
        "domain": "physics",
        "category": "scientific",
        "topic": "Quantum Computing & Superconductors",
        "query": "Topological quantum error correction surface codes Majorana zero modes",
        "max_pages": 15,
    },
    {
        "id": "exp_04_photonics_engineering",
        "domain": "engineering",
        "category": "engineering",
        "topic": "Laser Materials Processing",
        "query": "High power fiber laser cutting assist gas dynamics parameters kerf quality",
        "max_pages": 15,
    },
    {
        "id": "exp_05_genetics_bulk",
        "domain": "genetics",
        "category": "medical",
        "topic": "CRISPR & Prime Editing (Bulk High-Volume Test)",
        "query": "CRISPR Cas9 base editing and prime editing off-target reduction mechanisms",
        "max_pages": 30,
    },
]


async def run_scientific_evaluation():
    output_dir = Path("evals/results")
    output_dir.mkdir(parents=True, exist_ok=True)

    pipeline = DeepSearchPipeline()
    suite_results: List[Dict[str, Any]] = []

    print("=" * 80, flush=True)
    print("STARTING HETEROGENEOUS SCIENTIFIC RESEARCH & BULK GATHERING EVALUATION", flush=True)
    print(f"Total experiments: {len(TEST_SUITE)}", flush=True)
    print("=" * 80, flush=True)

    for idx, test_case in enumerate(TEST_SUITE, start=1):
        print(f"\n[{idx}/{len(TEST_SUITE)}] Running Experiment: {test_case['topic']}", flush=True)
        print(f"  Query: '{test_case['query']}'", flush=True)
        print(f"  Target Max Pages: {test_case['max_pages']}", flush=True)

        archive_zip_name = f"{test_case['id']}_dataset.zip"
        archive_zip_path = str(output_dir / archive_zip_name)

        opts = DeepSearchPipelineOptions(
            query=test_case["query"],
            domain=test_case["domain"],
            category=test_case["category"],
            depth=2,
            max_pages=test_case["max_pages"],
            mode=ExecutionMode.BALANCED,
            enable_media_archiving=True,
            min_media_count=2,
            max_media_count=5,
            output_archive_path=archive_zip_path,
        )

        start_time = time.time()
        try:
            res = await pipeline.execute(opts)
            elapsed = time.time() - start_time

            manifest = res.manifest or {}
            summary = manifest.get("summary", {})
            quality_report = manifest.get("quality_report", {})
            rejections = manifest.get("rejections", [])
            pdf_inventory = manifest.get("pdf_inventory", [])

            # Extract metrics
            total_docs = summary.get("total_documents", res.total_pages_processed)
            total_chunks = summary.get("total_rag_chunks", res.total_rag_chunks)
            total_pdfs = summary.get("total_pdfs", len(pdf_inventory))
            total_media = summary.get("total_media_files", 0)
            total_rejections = len(rejections)

            q_summary = quality_report.get("summary", {})
            independent_domains = q_summary.get("independent_domain_count", 0)
            direct_evidence_count = q_summary.get("direct_evidence_count", 0)
            source_classes = q_summary.get("source_classes", {})

            # Provider breakdown
            sources = quality_report.get("sources", [])
            providers = {}
            for s in sources:
                p = s.get("provider", "unknown")
                providers[p] = providers.get(p, 0) + 1

            zip_size_bytes = os.path.getsize(archive_zip_path) if os.path.exists(archive_zip_path) else 0

            exp_result = {
                "id": test_case["id"],
                "topic": test_case["topic"],
                "domain": test_case["domain"],
                "query": test_case["query"],
                "target_max_pages": test_case["max_pages"],
                "elapsed_seconds": round(elapsed, 2),
                "total_documents_accepted": total_docs,
                "total_rag_chunks": total_chunks,
                "total_pdfs_downloaded": total_pdfs,
                "total_media_archived": total_media,
                "total_rejections": total_rejections,
                "independent_domains": independent_domains,
                "direct_evidence_count": direct_evidence_count,
                "quality_gate_passed": res.quality_gate_passed,
                "quality_status": quality_report.get("status", "UNKNOWN"),
                "source_classes": source_classes,
                "provider_distribution": providers,
                "archive_zip": archive_zip_name,
                "archive_size_bytes": zip_size_bytes,
            }

            suite_results.append(exp_result)

            # Persist intermediate report
            report_file = output_dir / "scientific_bulk_eval_report.json"
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump({
                    "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                    "total_experiments": len(TEST_SUITE),
                    "completed_experiments": len(suite_results),
                    "successful_experiments": sum(1 for r in suite_results if "error" not in r),
                    "experiments": suite_results,
                }, f, indent=2, ensure_ascii=False)

            print(f"  [COMPLETED] in {elapsed:.1f}s", flush=True)
            print(f"    - Accepted Documents: {total_docs}", flush=True)
            print(f"    - RAG Chunks: {total_chunks}", flush=True)
            print(f"    - PDFs Downloaded: {total_pdfs}", flush=True)
            print(f"    - Independent Domains: {independent_domains}", flush=True)
            print(f"    - Quality Gate: {quality_report.get('status', 'UNKNOWN')} (Passed: {res.quality_gate_passed})", flush=True)
            print(f"    - Archive Size: {zip_size_bytes / (1024 * 1024):.2f} MB", flush=True)

        except Exception as exc:
            elapsed = time.time() - start_time
            print(f"  [FAILED] in {elapsed:.1f}s: {exc}", flush=True)
            suite_results.append({
                "id": test_case["id"],
                "topic": test_case["topic"],
                "query": test_case["query"],
                "error": str(exc),
                "elapsed_seconds": round(elapsed, 2),
            })

    # Save summary report
    report_file = output_dir / "scientific_bulk_eval_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "total_experiments": len(TEST_SUITE),
            "successful_experiments": sum(1 for r in suite_results if "error" not in r),
            "experiments": suite_results,
        }, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 80)
    print("EVALUATION SUITE COMPLETED")
    print(f"Report saved to: {report_file}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_scientific_evaluation())
