"""One-command run of Q4's offline evaluation harness (ranking metrics,
beyond-accuracy metrics, slicing, bootstrap CIs).

Executes src/evaluation_harness.ipynb top-to-bottom; every cell's assertions
must pass or the run aborts. Requires data/processed/{ebnerd,mind}/ from Q1's
build_pipeline.py, Q2's bm25_retrieval.py, and Q3's embedding_retrieval.py.
See SPEC.md for the pipeline design.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NOTEBOOK = ROOT / "src" / "evaluation_harness.ipynb"


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
