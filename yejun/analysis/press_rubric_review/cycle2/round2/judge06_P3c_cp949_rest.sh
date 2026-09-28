#!/usr/bin/env bash
# P3c — P3에서 reproduce --tests가 17단계(v1 시험)에서 멈춰 돌지 못한 18~23단계 시험을 같은 CP949·resource 차단 조건에서 따로 돌린다.
# 그리고 P3b8(v1 전체 결과 verify)은 결과 폴더에 동결 기대값을 두지 않은 평가관 실수라 기대값을 복사해 다시 돌린다.
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/P3_cp949"; LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_P3c_cp949_rest.log"; : > "$SUMMARY"
unset PYTHONUTF8 PYTHONIOENCODING
W=(env LC_ALL=ko_KR.CP949 LANG=ko_KR.CP949 PYTHONPATH="$P/nores" TMPDIR="$P/tmp")
echo "P3c 시작 $(date '+%F %T')" | tee -a "$SUMMARY"
cd "$P/clone/yejun"
for pkg in press_advance press_evidence press_selection press_supervised press_supplement; do
  step P3c_test_$pkg "${W[@]}" "$PY" -m pytest -q -p no:cacheprovider analysis/$pkg/test_contract.py; tail_to_summary P3c_test_$pkg 2
done
step P3c_test_web "${W[@]}" node press_guard/test_web.cjs; tail_to_summary P3c_test_web 2
step P3c_test_v1_deselect "${W[@]}" "$PY" -m pytest -q -p no:cacheprovider press_submission/tests -k "not test_clean_repro_propagates_failure_and_declares_scope"; tail_to_summary P3c_test_v1_deselect 2
cp -R press_submission/outputs/expected "$P/x/v1_out/expected"
step P3c_v1_verify_full_cp949 "${W[@]}" "$PY" press_submission/verify.py --out "$P/x/v1_out" --artifacts "$P/x/v1_art"; tail_to_summary P3c_v1_verify_full_cp949 3
{ echo "---- (CP949 출력을 UTF-8로 풀어 적음)"; iconv -f CP949 -t UTF-8 "$LOGS/P3c_v1_verify_full_cp949.out" | tail -2; iconv -f CP949 -t UTF-8 "$LOGS/P3c_test_v1_deselect.out" | tail -1; } >> "$SUMMARY"
echo "P3c 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
