#!/usr/bin/env bash
# Q13 — README:21 실측 시간(git 없는 사본에 주최 측 ZIP만 준 경우 572초) 재측정. 다른 실행이 거의 끝나 부하가 낮을 때 한 번.
#       git archive 사본 + 현재 폴더에 ZIP + README 빠른 시작 3행 그대로(anaconda 3.12.2). 단계별 시간과 부하를 남긴다.
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/Q13_timing"; rm -rf "$P"; mkdir -p "$P/logs"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_Q13_timing.log"; : > "$SUMMARY"
echo "Q13 시작 $(date '+%F %T') 기준=$COMMIT PY=$PY 부하=$(sysctl -n vm.loadavg)" | tee -a "$SUMMARY"
make_archive "$P/copy"; cd "$P/copy"; cp "$ORG_ZIP" "./$ZIP_NAME"
( while true; do echo "$(date +%T) $(sysctl -n vm.loadavg)"; sleep 30; done ) > "$P/load.log" 2>&1 &
LP=$!
step Q13_reproduce_timing "$PY" yejun/press_guard/reproduce.py --data "$ZIP_NAME"; tail_to_summary Q13_reproduce_timing 4
kill $LP 2>/dev/null
summary_to_log yejun/press_guard/outputs/reproduce_summary.json
bits_to_log "$P/copy"
awk '{gsub(/[{}]/,""); s+=$2; n++; if ($2>m) m=$2} END {printf "---- 실행 중 1분 부하 평균: 평균 %.1f · 최대 %.1f (30초 간격 %d회)\n", s/n, m, n}' "$P/load.log" >> "$SUMMARY"
echo "Q13 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
