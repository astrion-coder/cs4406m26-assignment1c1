"""One-command run of Q3's semantic (embedding) retrieval and recall@K evaluation.

Executes src/embedding_retrieval.ipynb top-to-bottom; every cell's assertions
must pass or the run aborts. Requires data/processed/{ebnerd,mind}/ from Q1's
build_pipeline.py, Q2's bm25_retrieval.py, and article_embeddings.parquet per
dataset (computed on Kaggle -- see src/compute_embeddings_kaggle.ipynb).
See SPEC.md for the pipeline design.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NOTEBOOK = ROOT / "src" / "embedding_retrieval.ipynb"


def main() -> int:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "jupyter",
            "nbconvert",
            "--to",
            "notebook",
            "--execute",
            "--inplace",
            str(NOTEBOOK),
        ],
        cwd=ROOT,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
