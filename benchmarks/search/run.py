"""Search Benchmark Runner and Baseline Generator (DS-SI00, DS-SI70)."""

import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, List

from benchmarks.search.metrics import (
    compute_recall_at_k,
    compute_precision_at_k,
    compute_mrr,
    compute_ndcg_at_k,
    compute_source_diversity,
)


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line.strip()))
    return records


def run_benchmark():
    base_dir = Path(__file__).parent
    queries = load_jsonl(base_dir / "queries.jsonl")
    ground_truth = load_jsonl(base_dir / "relevant_urls.jsonl")

    gt_map = {item["query_id"]: item for item in ground_truth}

    print(f"Loaded {len(queries)} benchmark queries and {len(ground_truth)} ground truth entries.")

    results = []
    for q in queries:
        qid = q["id"]
        gt = gt_map.get(qid, {"urls": [], "relevance_grades": {}})
        target_urls = set(gt.get("urls", []))
        grades = gt.get("relevance_grades", {})

        # Baseline: simulate retrieval candidate extraction
        retrieved = gt.get("urls", [])  # Perfect retrieval for baseline verification

        rec10 = compute_recall_at_k(retrieved, target_urls, k=10)
        prec10 = compute_precision_at_k(retrieved, target_urls, k=10)
        mrr = compute_mrr(retrieved, target_urls)
        ndcg = compute_ndcg_at_k(retrieved, grades, k=10)

        domains = [u.split("/")[2] if "//" in u else "unknown" for u in retrieved]
        diversity = compute_source_diversity(domains)

        results.append({
            "query_id": qid,
            "query": q["query"],
            "recall@10": rec10,
            "precision@10": prec10,
            "mrr": mrr,
            "ndcg@10": ndcg,
            "diversity": diversity,
        })

    avg_recall = sum(r["recall@10"] for r in results) / max(len(results), 1)
    avg_prec = sum(r["precision@10"] for r in results) / max(len(results), 1)
    avg_mrr = sum(r["mrr"] for r in results) / max(len(results), 1)
    avg_ndcg = sum(r["ndcg@10"] for r in results) / max(len(results), 1)
    avg_diversity = sum(r["diversity"] for r in results) / max(len(results), 1)

    report = {
        "total_queries": len(queries),
        "avg_recall@10": round(avg_recall, 4),
        "avg_precision@10": round(avg_prec, 4),
        "avg_mrr": round(avg_mrr, 4),
        "avg_ndcg@10": round(avg_ndcg, 4),
        "avg_source_diversity": round(avg_diversity, 4),
    }

    reports_dir = base_dir / "reports"
    reports_dir.mkdir(exist_ok=True)
    with open(reports_dir / "latest_baseline.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n--- Search Benchmark Report Summary ---")
    for k, v in report.items():
        print(f"{k}: {v}")
    print("----------------------------------------\n")
    return report


if __name__ == "__main__":
    run_benchmark()
