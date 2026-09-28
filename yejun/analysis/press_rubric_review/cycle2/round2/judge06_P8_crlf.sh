#!/usr/bin/env bash
# P8 — Windows용 Git 기본값(core.autocrlf=true)으로 받은 클론 모의: 커밋된 상태 그대로 계약·동결값 검사가 통과하는가.
# 제출은 ZIP(줄바꿈 변환 없음)이라 참고 항목이다. 커밋된 결과·기대값만 쓰므로 학습을 돌리지 않는다.
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/P8_crlf"; rm -rf "$P"; mkdir -p "$P/logs"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_P8_crlf.log"; : > "$SUMMARY"
echo "P8 시작 $(date '+%F %T') 기준=$COMMIT" | tee -a "$SUMMARY"
rm -rf "$P/clone"; git -c core.autocrlf=true clone -q "$REPO" "$P/clone"; cd "$P/clone"; git -c core.autocrlf=true -c advice.detachedHead=false checkout -q "$COMMIT"
echo "CRLF로 바뀐 파일 예: $(file yejun/analysis/press_selection/unified_comparison.csv | sed 's#.*: ##') / $(file yejun/press_guard/outputs/expected/metrics.csv | sed 's#.*: ##')" | tee -a "$SUMMARY"
for pkg in press_selection press_supervised press_advance press_evidence; do
  step P8_contract_$pkg env OMP_NUM_THREADS=1 "$PY" yejun/analysis/package_contract.py --package yejun/analysis/$pkg; tail_to_summary P8_contract_$pkg 4
done
step P8_supplement_verify env OMP_NUM_THREADS=1 "$PY" yejun/analysis/press_supplement/verify.py; tail_to_summary P8_supplement_verify 5
step P8_v2_expected_integrity env OMP_NUM_THREADS=1 "$PY" -c "import sys; sys.path.insert(0,'yejun/press_guard'); from pathlib import Path; import verify; b=verify.expected_integrity(Path('yejun/press_guard/outputs/expected')); print(len(b),'건', b[:3])"; tail_to_summary P8_v2_expected_integrity 3
# 비교: 같은 검사를 줄바꿈 변환 없는 클론에서
rm -rf "$P/clone_lf"; git -c core.autocrlf=false clone -q "$REPO" "$P/clone_lf"; cd "$P/clone_lf"; git -c advice.detachedHead=false checkout -q "$COMMIT"
step P8_lf_contract_press_selection env OMP_NUM_THREADS=1 "$PY" yejun/analysis/package_contract.py --package yejun/analysis/press_selection; tail_to_summary P8_lf_contract_press_selection 2
step P8_lf_v2_expected_integrity env OMP_NUM_THREADS=1 "$PY" -c "import sys; sys.path.insert(0,'yejun/press_guard'); from pathlib import Path; import verify; b=verify.expected_integrity(Path('yejun/press_guard/outputs/expected')); print(len(b),'건', b[:3])"; tail_to_summary P8_lf_v2_expected_integrity 3
echo "P8 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
