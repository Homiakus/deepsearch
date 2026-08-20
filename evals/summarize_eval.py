import glob
import json
import os
import zipfile

results = []
for zip_path in sorted(glob.glob("evals/results/*.zip")):
    with zipfile.ZipFile(zip_path) as z:
        manifest = json.loads(z.read("manifest.json").decode("utf-8"))

    meta = manifest.get("metadata", {})
    summary = manifest.get("summary", {})
    quality = manifest.get("quality_gate", {})
    q_summary = quality.get("summary", {})

    results.append(
        {
            "archive_name": os.path.basename(zip_path),
            "archive_size_mb": round(os.path.getsize(zip_path) / (1024 * 1024), 2),
            "query": meta.get("query"),
            "domain": meta.get("domain"),
            "accepted_documents": summary.get("total_documents", 0),
            "total_pdfs": summary.get("total_pdfs", 0),
            "total_rag_chunks": summary.get("total_rag_chunks", 0),
            "total_user_files": summary.get("total_user_files", 0),
            "total_media_files": summary.get("total_media_files", 0),
            "total_rejections": summary.get("total_rejections", 0),
            "independent_domains": q_summary.get("independent_domain_count", 0),
            "direct_evidence_count": q_summary.get("direct_evidence_count", 0),
            "direct_evidence_rate": q_summary.get("direct_evidence_rate", 0.0),
            "source_classes": q_summary.get("source_class_counts", {}),
            "quality_gate_status": quality.get("status", "UNKNOWN"),
        }
    )

print(json.dumps(results, indent=2, ensure_ascii=False))
with open(
    "evals/results/scientific_bulk_eval_summary.json", "w", encoding="utf-8"
) as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
