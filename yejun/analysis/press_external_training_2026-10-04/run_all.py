"""Rebuild source adapters, train all registered arms, and independently verify."""
import os
from pathlib import Path
import subprocess
import sys

here = Path(__file__).resolve().parent
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
for name in ("data.py", "run.py", "verify.py", "summarize.py"):
    subprocess.run([sys.executable, "-u", str(here/name)], check=True, env=env)
