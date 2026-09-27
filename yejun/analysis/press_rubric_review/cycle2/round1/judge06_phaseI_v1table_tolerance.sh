#!/usr/bin/env bash
# Phase I — v2 analyze가 v1 비교표(model_comparison_all.csv)를 허용오차가 아니라 바이트 일치로 요구하는지 확인한다(다른 기기에서 LSTM 재학습 시 전체 재생성 경로가 막히는지).
# Phase T 클론(v2 전체 실행 완료)의 v1 비교표에서 LSTM 행 값 하나의 마지막 자리만 바꾼 뒤 analyze를 별도 출력 폴더로 실행한다.
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/I_v1table"; rm -rf "$P"; mkdir -p "$P/logs"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_phaseI_v1table_tolerance.log"; : > "$SUMMARY"
T="$J06_BASE/T_timing/clone"; TY="$T/yejun"
echo "Phase I 시작 $(date '+%F %T') 클론=$(git -C "$T" rev-parse --short HEAD)" | tee -a "$SUMMARY"
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
TAB="$TY/press_submission/outputs/model_comparison_all.csv"; cp "$TAB" "$P/model_comparison_all.orig.csv"
"$PY" - "$TAB" >> "$SUMMARY" <<'EOF'
import sys, re
from pathlib import Path
p = Path(sys.argv[1]); lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
head = lines[0].rstrip("\n").split(",")
col = head.index("f1_all_rows")
for i, line in enumerate(lines[1:], 1):
    cells = line.rstrip("\n").split(",")
    if "lstm" in line.lower() and re.fullmatch(r"-?\d+\.\d{6,}", cells[col]):
        old = cells[col]; last = int(old[-1]); cells[col] = old[:-1] + str((last + 1) % 10)
        lines[i] = ",".join(cells) + "\n"; p.write_text("".join(lines), encoding="utf-8")
        print(f"변경: {i}행 {cells[1] if len(cells) > 1 else ''} f1_all_rows {old} → {cells[col]} (차이 약 {10**-(len(old.split('.')[1])):.0e})")
        break
EOF
cp -R "$TY/press_guard/outputs" "$P/out"; cp -R "$TY/press_guard/artifacts" "$P/art"
cd "$T"
step I01_analyze_tiny_change "$PY" yejun/press_guard/analyze.py --out "$P/out" --artifacts "$P/art"; tail_to_summary I01_analyze_tiny_change 2
cp "$P/model_comparison_all.orig.csv" "$TAB"
echo "Phase I 끝 $(date '+%F %T') (원래 표로 되돌림)" | tee -a "$SUMMARY"
