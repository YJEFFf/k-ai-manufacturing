#!/usr/bin/env bash
# 컨테이너 안에서 실행: 평가자가 README 빠른 시작대로 하는 절차(pip + 한 명령 재현 + 시험)
set -uo pipefail
cd /work
echo "== platform: $(uname -m) $(uname -s) $(cat /etc/os-release | grep PRETTY_NAME)"
python --version
t0=$(date +%s)
pip install --no-cache-dir -q -r yejun/press_guard/requirements.txt 2>&1 | tail -3
echo "== pip done ($(( $(date +%s) - t0 ))s)"
pip freeze | grep -i -E "numpy|pandas|scikit|scipy|matplotlib|threadpoolctl|pytest"
python - <<'PY'
import numpy as np, platform
print("machine", platform.machine(), platform.platform())
try:
    from threadpoolctl import threadpool_info
    for i in threadpool_info():
        print("blas", i.get("internal_api"), i.get("version"), i.get("architecture"), i.get("num_threads"))
except Exception as e:
    print("threadpoolctl", e)
PY
t1=$(date +%s)
OMP_NUM_THREADS=1 python yejun/press_guard/reproduce.py --tests
rc=$?
echo "== reproduce exit $rc ($(( $(date +%s) - t1 ))s)"
exit $rc
