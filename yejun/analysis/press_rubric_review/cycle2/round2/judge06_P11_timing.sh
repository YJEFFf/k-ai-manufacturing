#!/usr/bin/env bash
# P11 — README 실측 시간(15단계 572초) 확인: 다른 평가관 실행이 줄어든 뒤, git 없는 사본 + 팀과 같은 anaconda 파이썬으로 한 번 더 잰다.
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/P11_timing"; rm -rf "$P"; mkdir -p "$P/logs"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_P11_timing.log"; : > "$SUMMARY"
echo "P11 시작 $(date '+%F %T') 기준=$COMMIT 동시 실행: $(pgrep -fl 'reproduce.py' | grep -v P11 | wc -l | tr -d ' ')개" | tee -a "$SUMMARY"
make_archive "$P/copy"; cd "$P/copy"
step P11_reproduce env OMP_NUM_THREADS=1 "$PY" yejun/press_guard/reproduce.py --data "$ORG_ZIP"; tail_to_summary P11_reproduce 3
summary_to_log yejun/press_guard/outputs/reproduce_summary.json
echo "P11 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
