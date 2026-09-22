"""Run the fixed follow-up experiments with a caller-supplied original ZIP."""
from pathlib import Path
import argparse
import os
import subprocess
import sys


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--zip',required=True,help='Official task 5 ZIP; data are not bundled with the code')
    args=ap.parse_args()
    source=Path(args.zip).expanduser().resolve()
    if not source.is_file():raise FileNotFoundError(source)
    root=Path(__file__).resolve().parent
    env=dict(os.environ,OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1')
    jobs=[
        [sys.executable,str(root/'classifier_experiment.py'),'--zip',str(source)],
        [sys.executable,str(root/'window_experiment.py'),'--zip',str(source)],
        [sys.executable,str(root/'interval_policy_audit.py'),'--zip',str(source),'--output',str(root/'interval_results')],
        [sys.executable,str(root/'compare_policies.py'),'--interval-dir',str(root/'interval_results'),'--output',str(root/'comparison')],
    ]
    for command in jobs:subprocess.run(command,env=env,check=True)


if __name__=='__main__':main()
