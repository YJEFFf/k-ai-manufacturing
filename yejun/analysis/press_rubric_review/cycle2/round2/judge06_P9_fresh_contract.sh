#!/usr/bin/env bash
# P9 — 갓 받은 사본(학습 전)에서 분석 패키지 계약 검사를 단독으로 부르면 어떻게 되는가(P8의 press_selection 실패 원인 확인).
# 커밋된 결과·기대값만 있고 press_guard/artifacts(Git 제외)는 아직 없다. 줄바꿈 변환 없는 새 클론.
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/P9_fresh"; rm -rf "$P"; mkdir -p "$P/logs"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_P9_fresh_contract.log"; : > "$SUMMARY"
echo "P9 시작 $(date '+%F %T') 기준=$COMMIT" | tee -a "$SUMMARY"
make_clone "$P/clone"; cd "$P/clone/yejun"
echo "press_guard/artifacts: $(ls press_guard/artifacts 2>&1 | head -1)" | tee -a "$SUMMARY"
for pkg in press_selection press_supervised press_evidence press_advance; do
  step P9_contract_$pkg env OMP_NUM_THREADS=1 "$PY" analysis/package_contract.py --package analysis/$pkg; tail_to_summary P9_contract_$pkg 12
done
step P9_pytest_contracts env OMP_NUM_THREADS=1 "$PY" -m pytest -q -p no:cacheprovider analysis/press_selection/test_contract.py analysis/press_supervised/test_contract.py; tail_to_summary P9_pytest_contracts 6
step P9_supp_verify env OMP_NUM_THREADS=1 "$PY" analysis/press_supplement/verify.py; tail_to_summary P9_supp_verify 6
echo "P9 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
