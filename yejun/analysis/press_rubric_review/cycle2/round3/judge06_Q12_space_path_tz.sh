#!/usr/bin/env bash
# Q12 — 평가위원 PC에서 흔한 조건: 공백·한글이 든 폴더 경로에 목록 사본을 두고, 시간대를 바꿔(TZ=America/Los_Angeles) 한 명령 재현.
#       목록은 Q5가 만든 package_list.csv(원천 Q2 클론). --data 없이(목록에 원본 CSV 포함) README 한 명령 형태로 실행한다.
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
SRC="${1:-$J06_BASE/Q2_venv/clone}"
LIST="${2:-$J06_BASE/Q5_package/package_list.csv}"
PYX="${PYX:-$J06_BASE/Q2_venv/venv/bin/python}"
P="$J06_BASE/Q12_space"; rm -rf "$P"; mkdir -p "$P/logs"
DEST="$P/평가 위원 폴더/제출 사본 (압축 해제)"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_Q12_space_path_tz.log"; : > "$SUMMARY"
echo "Q12 시작 $(date '+%F %T') 원천=$SRC 목록=$LIST 파이썬=$PYX" | tee -a "$SUMMARY"
"$PY" - "$SRC" "$DEST" "$LIST" >> "$SUMMARY" <<'PYEOF'
import shutil, sys
from pathlib import Path
import pandas as pd
src, dst, lst = Path(sys.argv[1]), Path(sys.argv[2]), pd.read_csv(sys.argv[3])
for rel in lst.path:
    (dst / rel).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / rel, dst / rel)
print(f"---- 목록 복사 {len(lst)}개 → {dst}")
PYEOF
cd "$DEST"
echo "현재 폴더: $(pwd)" >> "$SUMMARY"
step Q12_reproduce_space_tz env TZ=America/Los_Angeles OMP_NUM_THREADS=1 "$PYX" yejun/press_guard/reproduce.py; tail_to_summary Q12_reproduce_space_tz 20
summary_to_log yejun/press_guard/outputs/reproduce_summary.json
bits_to_log "$DEST"
echo "Q12 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
