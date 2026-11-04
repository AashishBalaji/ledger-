#!/usr/bin/env python3
"""Compare a fresh pytest-benchmark JSON run against the committed baseline
and fail (non-zero exit) if any benchmark's median time regresses beyond
the allowed threshold. This is what turns "we have a benchmark suite" into
an actual CI gate rather than a number nobody looks at.

Usage:
    python scripts/compare_benchmarks.py <current.json> <baseline.json> [--threshold 0.5]
"""
from __future__ import annotations

import argparse
import json
import sys


def load_medians(path: str) -> dict[str, float]:
    with open(path) as f:
        data = json.load(f)
    return {b["name"]: b["stats"]["median"] for b in data["benchmarks"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("current")
    parser.add_argument("baseline")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="allowed fractional regression before failing, e.g. 0.5 = 50%% slower is a failure",
    )
    args = parser.parse_args()

    current = load_medians(args.current)
    baseline = load_medians(args.baseline)

    regressions: list[str] = []
    new_benchmarks: list[str] = []

    for name, current_median in current.items():
        if name not in baseline:
            new_benchmarks.append(name)
            continue

        baseline_median = baseline[name]
        if baseline_median <= 0:
            continue

        pct_change = (current_median - baseline_median) / baseline_median
        marker = "REGRESSION" if pct_change > args.threshold else "ok"
        print(
            f"[{marker}] {name}: baseline={baseline_median * 1e6:.1f}us "
            f"current={current_median * 1e6:.1f}us change={pct_change:+.1%}"
        )
        if pct_change > args.threshold:
            regressions.append(name)

    if new_benchmarks:
        print(f"\nNew benchmarks with no baseline (not checked): {', '.join(new_benchmarks)}")

    if regressions:
        print(
            f"\nFAIL: {len(regressions)} benchmark(s) regressed beyond "
            f"{args.threshold:.0%}: {', '.join(regressions)}"
        )
        return 1

    print("\nAll benchmarks within threshold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
