#!/usr/bin/env bash
# Phase T — 부하가 적을 때 v2 경로 단계별 소요 시간(README 표기와 대조). 새 클론 하나에서 순서대로 한 번 실행한다.
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/T_timing"; rm -rf "$P"; mkdir -p "$P/logs"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_phaseT_timing.log"; : > "$SUMMARY"
echo "Phase T 시작 $(date '+%F %T') loadavg=$(sysctl -n vm.loadavg) 동시 실행: Phase C의 LSTM 학습(1코어)" | tee -a "$SUMMARY"
C="$P/clone"; make_clone "$C"; cd "$C"
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
step T01_v1_step2 "$PY" yejun/press_submission/run_all.py --root yejun/press_submission --out yejun/press_submission/outputs --steps 2 --no-baselines
step T02_train "$PY" yejun/press_guard/train.py --rolling
step T03_analyze "$PY" yejun/press_guard/analyze.py
step T04_audit "$PY" yejun/press_guard/audit.py
step T05_verify "$PY" yejun/press_guard/verify.py; tail_to_summary T05_verify 1
echo "Phase T 끝 $(date '+%F %T') loadavg=$(sysctl -n vm.loadavg)" | tee -a "$SUMMARY"
