#!/usr/bin/env bash
# Q6b — 갓 받은 사본(학습 전, 원본·저장 모델 없음)에서 분석 패키지 계약·보완 실험 verify를 단독으로 부를 때(R2-06 완료 기준):
#       안내 한 줄 + 종료 코드 2 + 추적 출력 없음인가. 옵션(--rerun·--freeze·--strict)과 원본만 있는 부분 상태도 본다.
#       마지막으로 팀 시험(test_contract.py)을 같은 상태에서 돌려 본다(참고).
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/Q6b_prereq"; rm -rf "$P"; mkdir -p "$P/logs"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_Q6b_prereq.log"; : > "$SUMMARY"
echo "Q6b 시작 $(date '+%F %T') 기준=$COMMIT" | tee -a "$SUMMARY"
make_clone "$P/clone"; cd "$P/clone/yejun"
echo "원본 CSV: $(ls press_submission/data 2>&1 | head -1) / press_guard/artifacts: $(ls press_guard/artifacts 2>&1 | head -1)" | tee -a "$SUMMARY"
judge() {   # judge <이름>: 종료 코드·stderr 줄 수·Traceback 여부·첫 줄
  local n="$1"
  local rc; rc=$(grep -E "^STEP $n " "$SUMMARY" | tail -1 | sed -E 's/.* rc=([0-9]+) .*/\1/')
  local errl; errl=$(grep -v -E '^[[:space:]]*[0-9.]+[[:space:]]+real[[:space:]]|^[[:space:]]*[0-9]+[[:space:]]+[a-z][a-z ()-]*$' "$LOGS/$n.err" | grep -v '^[[:space:]]*$')
  echo "     판정 $n: rc=$rc · stderr $(echo "$errl" | grep -c .)줄 · stdout $(grep -c . "$LOGS/$n.out")줄 · Traceback $(grep -c Traceback "$LOGS/$n.err") · 첫 줄: $(echo "$errl" | head -1 | cut -c1-220)" >> "$SUMMARY"
}
for pkg in press_evidence press_supervised press_advance press_selection; do
  step Q6b_contract_$pkg env OMP_NUM_THREADS=1 "$PY" analysis/package_contract.py --package analysis/$pkg; judge Q6b_contract_$pkg
done
step Q6b_contract_rerun env OMP_NUM_THREADS=1 "$PY" analysis/package_contract.py --package analysis/press_selection --rerun; judge Q6b_contract_rerun
step Q6b_contract_freeze env OMP_NUM_THREADS=1 "$PY" analysis/package_contract.py --package analysis/press_supervised --freeze; judge Q6b_contract_freeze
echo "     동결 거부 뒤 press_supervised/expected 변경: $(cd "$P/clone" && git status --short yejun/analysis/press_supervised | wc -l | tr -d ' ')개" >> "$SUMMARY"
step Q6b_supp_verify env OMP_NUM_THREADS=1 "$PY" analysis/press_supplement/verify.py; judge Q6b_supp_verify
step Q6b_supp_strict env OMP_NUM_THREADS=1 "$PY" analysis/press_supplement/verify.py --strict; judge Q6b_supp_strict
step Q6b_supp_rerun env OMP_NUM_THREADS=1 "$PY" analysis/press_supplement/verify.py --rerun E3; judge Q6b_supp_rerun
# 저장소 루트에서 부르는 경우(README 한 명령과 같은 위치)
( cd "$P/clone" && step Q6b_contract_from_root env OMP_NUM_THREADS=1 "$PY" yejun/analysis/package_contract.py --package yejun/analysis/press_evidence ); judge Q6b_contract_from_root
# 부분 상태: 원본만 배치(저장 모델 없음)
step Q6b0_place_data env OMP_NUM_THREADS=1 "$PY" -c "import sys; sys.path.insert(0,'press_guard'); import runtime; from model import D; print(runtime.install_data(sys.argv[1], D.PACKAGE_DIR, D.FILES, D.EXPECTED_SHA256, D.DATA_SUBDIR))" "$ORG_ZIP"
step Q6b_partial_contract env OMP_NUM_THREADS=1 "$PY" analysis/package_contract.py --package analysis/press_selection; judge Q6b_partial_contract
step Q6b_partial_supp env OMP_NUM_THREADS=1 "$PY" analysis/press_supplement/verify.py; judge Q6b_partial_supp
# 팀 시험(참고): 원본만 있고 저장 모델이 없는 상태
for t in press_evidence press_supervised press_advance press_selection press_supplement; do
  step Q6b_pytest_$t env OMP_NUM_THREADS=1 "$PY" -m pytest -q -p no:cacheprovider analysis/$t/test_contract.py; tail_to_summary Q6b_pytest_$t 3
done
echo "Q6b 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
