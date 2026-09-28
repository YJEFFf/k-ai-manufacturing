#!/usr/bin/env bash
# P4 — 새 git 클론에서 --full(v1 1~5단계 LSTM 처음부터, 후보 비교, E1~E3 재실행) 한 번.
# 원본은 주최 측 ZIP(--data)으로만 준다. 보완 E2용 UCI ZIP(Git 제외 외부 자료)은 복사해 넣는다. TMPDIR을 새로 잡아 E2 10 Hz 캐시도 없이 시작한다.
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/P4_full"; rm -rf "$P"; mkdir -p "$P/logs" "$P/tmp"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_P4_full.log"; : > "$SUMMARY"
echo "P4 시작 $(date '+%F %T') 저장소 HEAD=$(git -C "$REPO" rev-parse --short HEAD) 기준=$COMMIT PY=$PY" | tee -a "$SUMMARY"
make_clone "$P/clone"; cd "$P/clone"
echo "클론 HEAD=$(git rev-parse --short HEAD); LSTM 캐시 $(ls yejun/press_submission/artifacts 2>/dev/null | wc -l | tr -d ' ')개 파일; 원본 CSV $(ls yejun/press_submission/data 2>/dev/null | wc -l | tr -d ' ')개" | tee -a "$SUMMARY"
mkdir -p yejun/analysis/press_external/data && cp "$UCI_ZIP" yejun/analysis/press_external/data/
export TMPDIR="$P/tmp"
step P4_full_reproduce env OMP_NUM_THREADS=1 "$PY" yejun/press_guard/reproduce.py --full --data "$ORG_ZIP"; tail_to_summary P4_full_reproduce 40
summary_to_log yejun/press_guard/outputs/reproduce_summary.json
echo "P4 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
