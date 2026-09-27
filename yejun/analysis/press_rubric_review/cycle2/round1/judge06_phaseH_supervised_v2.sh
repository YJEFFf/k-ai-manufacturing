#!/usr/bin/env bash
# Phase H — 실행 도중 올라온 3ad2452(press_supervised v2만 변경)의 재실행 결정성. 새 클론에서 v2 저장 모델을 만든 뒤 run.py를 임시 폴더로 돌려 커밋 CSV와 바이트 비교한다.
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/H_supervised_v2"; rm -rf "$P"; mkdir -p "$P/logs"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_phaseH_supervised_v2.log"; : > "$SUMMARY"
C="$P/clone"; make_clone "$C"; cd "$C"
echo "Phase H 시작 $(date '+%F %T') 클론=$(git -C "$C" rev-parse --short HEAD)" | tee -a "$SUMMARY"
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
step H01_train "$PY" yejun/press_guard/train.py
step H02_supervised "$PY" yejun/analysis/press_supervised/run.py --out "$P/out"; tail_to_summary H02_supervised 2
{ echo "---- 커밋 CSV와 바이트 비교"; for f in random_rows.csv grouped_records.csv injection.csv; do
    if cmp -s "$P/out/$f" "yejun/analysis/press_supervised/$f"; then echo "$f 바이트 동일"; else echo "$f 다름"; fi; done; } >> "$SUMMARY"
echo "Phase H 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
