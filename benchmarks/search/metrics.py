"""Search and Ranking Evaluation Metrics (§DS-SI00, §DS-SI70, §DS-SI71, §DS-SI72)."""

import math
from typing import List, Dict, Set, Any


def compute_recall_at_k(
    retrieved: List[str], ground_truth: Set[str], k: int = 10
) -> float:
    """Computes Recall@K: fraction of relevant URLs found in top-K."""
    if not ground_truth:
        return 1.0
    top_k = set(retrieved[:k])
    found = top_k.intersection(ground_truth)
    return len(found) / len(ground_truth)


def compute_precision_at_k(
    retrieved: List[str], ground_truth: Set[str], k: int = 10
) -> float:
    """Computes Precision@K: fraction of top-K results that are relevant."""
    if k <= 0:
        return 0.0
    top_k = set(retrieved[:k])
    found = top_k.intersection(ground_truth)
    return len(found) / min(k, len(retrieved) if retrieved else 1)


def compute_mrr(retrieved: List[str], ground_truth: Set[str]) -> float:
    """Computes Mean Reciprocal Rank (MRR) for first relevant hit."""
    for rank, url in enumerate(retrieved, start=1):
        if url in ground_truth:
            return 1.0 / rank
    return 0.0


def compute_ndcg_at_k(
    retrieved: List[str], relevance_grades: Dict[str, float], k: int = 10
) -> float:
    """Computes Normalized Discounted Cumulative Gain (nDCG@K)."""
    dcg = 0.0
    for rank, url in enumerate(retrieved[:k], start=1):
        rel = relevance_grades.get(url, 0.0)
        dcg += (2.0**rel - 1.0) / math.log2(rank + 1.0)

    # Ideal DCG
    ideal_rels = sorted(relevance_grades.values(), reverse=True)[:k]
    idcg = 0.0
    for rank, rel in enumerate(ideal_rels, start=1):
        idcg += (2.0**rel - 1.0) / math.log2(rank + 1.0)

    if idcg <= 0.0:
        return 1.0 if dcg == 0.0 else 0.0
    return dcg / idcg


def compute_source_diversity(domains: List[str]) -> float:
    """Computes normalized Shannon entropy of retrieved source domains."""
    if not domains:
        return 0.0
    total = len(domains)
    counts = {}
    for d in domains:
        counts[d] = counts.get(d, 0) + 1

    entropy = 0.0
    for cnt in counts.values():
        p = cnt / total
        entropy -= p * math.log2(p)

    max_entropy = math.log2(len(counts)) if len(counts) > 1 else 1.0
    return entropy / max_entropy if max_entropy > 0 else 1.0


def compute_near_duplicate_ratio(
    fingerprints: List[int], hamming_thresh: int = 3
) -> float:
    """Computes ratio of near-duplicate items in a set of SimHash fingerprints."""
    if len(fingerprints) <= 1:
        return 0.0
    duplicates = 0
    seen = []
    for fp in fingerprints:
        is_dup = False
        for s in seen:
            # Hamming distance
            dist = bin(fp ^ s).count("1")
            if dist <= hamming_thresh:
                is_dup = True
                break
        if is_dup:
            duplicates += 1
        else:
            seen.append(fp)
    return duplicates / len(fingerprints)


def compute_source_chunk_concentration(source_chunk_counts: Dict[str, int]) -> float:
    """Largest fraction of chunks contributed by a single source."""
    total = sum(source_chunk_counts.values())
    return max(source_chunk_counts.values(), default=0) / max(total, 1)


def compute_direct_evidence_rate(sources: List[Dict[str, Any]]) -> float:
    if not sources:
        return 0.0
    return sum(bool(source.get("direct_evidence")) for source in sources) / len(sources)


def evaluate_quality_gate_report(
    report: Dict[str, Any],
    min_direct_evidence_rate: float = 0.80,
    max_block_page_rate: float = 0.0,
) -> Dict[str, Any]:
    """Evaluate the run-level source quality contract from an exported report."""
    summary = report.get("summary", {})
    accepted = int(summary.get("accepted_source_count", 0))
    rejected = int(summary.get("rejected_candidate_count", 0))
    total = accepted + rejected
    block_rejections = sum(
        1
        for item in report.get("rejections", [])
        if str(item.get("document_type", "")).upper()
        in {"BLOCK_PAGE", "LOGIN", "JS_SHELL", "ERROR_PAGE"}
        or "BLOCK" in str(item.get("reason_code", "")).upper()
    )
    direct_rate = float(
        summary.get(
            "direct_evidence_rate",
            compute_direct_evidence_rate(report.get("sources", [])),
        )
    )
    block_rate = block_rejections / max(total, 1)
    checks = {
        "direct_evidence_rate": direct_rate >= min_direct_evidence_rate,
        "block_page_rate": block_rate <= max_block_page_rate,
        "report_status": report.get("status") == "SUFFICIENT_EVIDENCE",
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "metrics": {
            "direct_evidence_rate": round(direct_rate, 3),
            "block_page_rate": round(block_rate, 3),
            "accepted_sources": accepted,
            "rejected_candidates": rejected,
        },
    }
