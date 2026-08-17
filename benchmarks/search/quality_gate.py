"""Offline quality-gate runner for an exported DeepSearch report.

Usage:
    python -m benchmarks.search.quality_gate path/to/source_quality_report.json
"""

import argparse
import json
from pathlib import Path

from benchmarks.search.metrics import evaluate_quality_gate_report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    result = evaluate_quality_gate_report(report)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
