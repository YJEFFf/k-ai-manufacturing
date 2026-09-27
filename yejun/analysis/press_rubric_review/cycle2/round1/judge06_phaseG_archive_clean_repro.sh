#!/usr/bin/env bash
# Phase G — ZIP을 푼 것과 같은 git 없는 사본(git archive)에서 press_guard/tools/clean_repro.sh가 도는가.
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/G_archive"; rm -rf "$P"; mkdir -p "$P/copy"
SUMMARY="$OUTDIR/judge06_phaseG_archive_clean_repro.log"; : > "$SUMMARY"
COMMIT="${COMMIT:-dcd300a}"
git -C "$REPO" archive "$COMMIT" yejun/press_guard yejun/press_submission yejun/analysis/press_advance | tar -x -C "$P/copy"
mkdir -p "$P/copy/yejun/press_submission/data/3_소성가공_예지보전"
cp "$SRC_DATA/press_data_normal.csv" "$SRC_DATA/outlier_data.csv" "$P/copy/yejun/press_submission/data/3_소성가공_예지보전/"
echo "Phase G $(date '+%F %T') git archive $COMMIT → git 없는 사본에서 clean_repro.sh 실행" >> "$SUMMARY"
before=$(ls -d /var/folders/*/*/T/tmp.* 2>/dev/null | sort)
(cd "$P" && PYTHON="$PY" bash copy/yejun/press_guard/tools/clean_repro.sh) >> "$SUMMARY" 2>&1
echo "rc=$?" >> "$SUMMARY"
# 스크립트가 만든 빈 임시 폴더(mktemp -d)는 지운다
for t in $(comm -13 <(echo "$before") <(ls -d /var/folders/*/*/T/tmp.* 2>/dev/null | sort)); do rmdir "$t" 2>/dev/null && echo "정리: $t" >> "$SUMMARY"; done
