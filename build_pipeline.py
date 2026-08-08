"""One-command rebuild of the Q1 feature store from raw files.

Executes src/build_pipeline.ipynb top-to-bottom; every cell's assertions must
pass or the rebuild aborts. See SPEC.md for the pipeline design.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NOTEBOOK = ROOT / "src" / "build_pipeline.ipynb"


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
