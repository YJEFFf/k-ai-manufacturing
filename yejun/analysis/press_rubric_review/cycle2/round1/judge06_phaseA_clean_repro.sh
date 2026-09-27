#!/usr/bin/env bash
# Phase A — 저장소에 들어 있는 새 클론 재현 스크립트를 그대로 실행한다(v2, v1 --with-lstm).
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/A_clean_repro"; rm -rf "$P"; mkdir -p "$P/logs" "$P/tmp"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_phaseA_clean_repro.log"; : > "$SUMMARY"
echo "Phase A 시작 $(date '+%F %T') HEAD=$(git -C "$REPO" rev-parse HEAD)" | tee -a "$SUMMARY"
cd "$P"
step A01_v2_clean_repro env TMPDIR="$P/tmp/" PYTHON="$PY" bash "$REPO/yejun/press_guard/tools/clean_repro.sh"; tail_to_summary A01_v2_clean_repro 25
step A02_v1_clean_repro_with_lstm env TMPDIR="$P/tmp/" PATH="/opt/anaconda3/bin:$PATH" bash "$REPO/yejun/press_submission/tools/clean_repro.sh" --with-lstm; tail_to_summary A02_v1_clean_repro_with_lstm 45
# 스크립트가 남긴 임시 클론은 확인 뒤 지운다(각 스크립트 안내: 검사 후 삭제 가능).
# macOS mktemp -d는 TMPDIR 대신 사용자 임시 폴더(/var/folders/...)를 쓰므로 출력의 '임시 폴더:' 경로를 지운다.
for t in $(grep -h "^임시 폴더: " "$LOGS"/A0*.out | sed -E 's/^임시 폴더: ([^ ]+).*/\1/'); do
  case "$t" in /var/folders/*|/private/var/folders/*|/tmp/*|/private/tmp/*) du -sh "$t" >> "$SUMMARY"; rm -rf "$t" ;; esac
done
rm -rf "$P/tmp"
echo "Phase A 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
