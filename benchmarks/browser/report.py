"""Browser Acquisition Benchmark Report Generator (DS-RB00)."""

import statistics
from typing import Any


def generate_benchmark_report(results: list[dict[str, Any]]) -> str:
    if not results:
        return "No benchmark results available."

    total = len(results)
    successful = [r for r in results if r.get("success")]
    success_rate = (len(successful) / total) * 100.0

    latencies = [r["elapsed_ms"] for r in results if r.get("elapsed_ms")]
    avg_latency = statistics.mean(latencies) if latencies else 0.0
    p95_latency = (
        statistics.quantiles(latencies, n=20)[18]
        if len(latencies) >= 20
        else avg_latency
    )

    qualities = [r["quality_score"] for r in results if "quality_score" in r]
    avg_quality = statistics.mean(qualities) if qualities else 0.0

    lines = [
        "# DeepSearch Acquisition Baseline Report",
        "",
        f"- **Total URLs Evaluated:** {total}",
        f"- **Success Rate:** {success_rate:.1f}% ({len(successful)}/{total})",
        f"- **Average Latency:** {avg_latency:.1f} ms",
        f"- **P95 Latency:** {p95_latency:.1f} ms",
        f"- **Mean Quality Score:** {avg_quality:.2f}",
        "",
        "| URL | Status | Elapsed (ms) | Content (bytes) | Text (chars) | Quality |",
        "|---|---|---|---|---|---|",
    ]

    for r in results:
        lines.append(
            f"| {r['url']} | {r['status_code']} | {r['elapsed_ms']:.1f} | {r['content_bytes']} | {r['useful_text_chars']} | {r['quality_score']:.2f} |"
        )

    return "\n".join(lines)
