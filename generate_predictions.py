"""One-command generation of Q5's Codabench submission files for MIND
(`codabench.org/competitions/13967`) and EB-NeRD/RecSys 2024
(`codabench.org/competitions/2469`).

Executes src/generate_predictions.ipynb top-to-bottom; every cell's
assertions must pass or the run aborts. Requires data/processed/{ebnerd,mind}/
from Q1's build_pipeline.py, and Q3's article_embeddings.parquet for both
datasets. Writes submissions/{ebnerd,mind}/*.zip. See SPEC.md Q5 for the
submission format (MIND confirmed; EB-NeRD inferred, not yet directly
confirmed) and README.md for the upload steps.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NOTEBOOK = ROOT / "src" / "generate_predictions.ipynb"


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
