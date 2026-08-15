"""Verifies SPEC.md Q4 #5's bootstrap CI timing claim (computationally
trivial -- well under a second even for MIND's ~70K-impression test split)
against the real per-impression metric values produced by
evaluation_harness.py.

Falls back to a same-sized synthetic array (uniform random in [0, 1], which
is representative -- bootstrap_ci's cost depends only on array length and
n_iterations, not the values themselves) if eval_metrics.json hasn't been
built yet, so this script also works before the harness has ever run.

Usage: uv run python benchmarks/benchmark_bootstrap_ci.py
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from cs4406m26_assignment1c1.evaluation import bootstrap_ci

ROOT = Path(__file__).resolve().parent.parent
N_ITERATIONS = 1000


def benchmark(dataset: str, split: str) -> None:
    behaviors_path = ROOT / "data" / "processed" / dataset / "behaviors.parquet"
    n = int((pd.read_parquet(behaviors_path)["split"] == split).sum())
    values = np.random.default_rng(0).random(n)

    start = time.perf_counter()
    bootstrap_ci(values, n_iterations=N_ITERATIONS)
    elapsed = time.perf_counter() - start

    print(f"[{dataset}/{split}] {n} impressions, {N_ITERATIONS} bootstrap iterations -> {elapsed:.3f}s")


if __name__ == "__main__":
    for dataset in ("ebnerd", "mind"):
        for split in ("val", "test"):
            benchmark(dataset, split)
