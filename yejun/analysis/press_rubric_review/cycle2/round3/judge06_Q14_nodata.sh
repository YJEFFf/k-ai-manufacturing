#!/usr/bin/env bash
# Q14 — 원본 CSV 없이 README 한 명령(--data 없음)과 없는 --data 경로를 줄 때 안내·종료 코드·추적 출력(git 없는 사본). 결과: judge06_Q14_nodata.log
# 2026-09-28 검수 때 같은 명령을 한 줄로 실행했다.
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P=$J06_BASE/Q14_nodata; rm -rf $P; mkdir -p $P
make_archive $P/copy; cd $P/copy
{ echo "Q14 — 원본 없이 README 한 명령(--data 없음), 잘못된 --data 경로 $(date '+%F %T')"
  OMP_NUM_THREADS=1 $PY yejun/press_guard/reproduce.py > $P/a.out 2> $P/a.err
  echo "  a) 원본 없음: rc=$? · stderr $(grep -c . $P/a.err)줄 · Traceback $(grep -c Traceback $P/a.err) · $(head -2 $P/a.err | tr '\n' ' ' | cut -c1-230)"
  OMP_NUM_THREADS=1 $PY yejun/press_guard/reproduce.py --data "없는파일.zip" > $P/b.out 2> $P/b.err
  echo "  b) 없는 --data: rc=$? · Traceback $(grep -c Traceback $P/b.err) · $(head -1 $P/b.err | cut -c1-200)"
  echo "  단계 실행 여부: reproduce_logs $(ls yejun/press_guard/outputs/reproduce_logs 2>/dev/null | wc -l | tr -d ' ')개"
} | tee $OUTDIR/judge06_Q14_nodata.log
rm -rf $P
