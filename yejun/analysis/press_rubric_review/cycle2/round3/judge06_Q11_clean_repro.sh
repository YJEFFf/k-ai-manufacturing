#!/usr/bin/env bash
# Q11 — README 검증 표(README:195)의 bash yejun/press_guard/tools/clean_repro.sh 를 git 없는 사본(ZIP을 푼 상태)에서 그대로 실행.
#       사본에는 대회 원본 CSV만 넣는다. 스크립트가 만드는 mktemp 폴더는 TMPDIR로 이 평가관의 임시 폴더 아래에 둔다.
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/Q11_clean_repro"; rm -rf "$P"; mkdir -p "$P/logs" "$P/tmp"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_Q11_clean_repro.log"; : > "$SUMMARY"
echo "Q11 시작 $(date '+%F %T') 기준=$COMMIT PY=$PY" | tee -a "$SUMMARY"
make_archive "$P/copy"; cd "$P/copy"
mkdir -p yejun/press_submission/data/3_소성가공_예지보전
cp "$RAW_DIR/press_data_normal.csv" "$RAW_DIR/outlier_data.csv" yejun/press_submission/data/3_소성가공_예지보전/
step Q11_clean_repro env TMPDIR="$P/tmp" PYTHON="$PY" OMP_NUM_THREADS=1 bash yejun/press_guard/tools/clean_repro.sh; tail_to_summary Q11_clean_repro 22
S=$(ls -d "$P"/tmp/tmp.*/clone/yejun/press_guard/outputs/reproduce_summary.json 2>/dev/null | head -1)
[[ -n "$S" ]] && summary_to_log "$S" && bits_to_log "$(dirname "$(dirname "$(dirname "$(dirname "$S")")")")"
echo "Q11 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
