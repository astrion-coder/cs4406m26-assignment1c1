"""One-command run of Q2's BM25 lexical retrieval and recall@K evaluation.

Executes src/bm25_retrieval.ipynb top-to-bottom; every cell's assertions must
pass or the run aborts. Requires data/processed/{ebnerd,mind}/ from Q1's
build_pipeline.py. See SPEC.md for the pipeline design.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NOTEBOOK = ROOT / "src" / "bm25_retrieval.ipynb"


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
