#!/usr/bin/env bash
# Phase F — README가 안내하는 E2 '--no-cache'(변환 캐시 없이) 실행이 보완 실험 verify를 통과하는가.
# 결과 CSV가 같아도 manifest config의 cache_used 값이 달라 '실행 설정 불일치'로 실패하는지 확인한다. Phase B 클론(학습 완료)을 쓴다.
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/F_e2_nocache"; rm -rf "$P"; mkdir -p "$P/logs" "$P/tmp"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_phaseF_e2_nocache.log"; : > "$SUMMARY"
B="$J06_BASE/B_readme/clone"; BY="$B/yejun"
echo "Phase F 시작 $(date '+%F %T') 클론=$(git -C "$B" rev-parse --short HEAD)" | tee -a "$SUMMARY"
mkdir -p "$BY/analysis/press_external/data"; cp "$UCI_ZIP" "$BY/analysis/press_external/data/"
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
cd "$BY/analysis/press_supplement"
step F01_e2_nocache env TMPDIR="$P/tmp/" "$PY" uci_v2.py --out "$P/e2_nocache" --no-cache; tail_to_summary F01_e2_nocache 3
step F02_verify_nocache_run "$PY" verify.py --out "$P/e2_nocache" --experiments E2; tail_to_summary F02_verify_nocache_run 6
{ echo "---- F03 결과 CSV만 동결값과 바이트 비교"; for f in e2_uci_metrics.csv e2_uci_strata.csv e2_uci_component_diagnostic_posthoc.csv e2_uci_comparison.csv; do
    if cmp -s "$P/e2_nocache/$f" "expected/$f"; then echo "$f 바이트 동일"; else echo "$f 다름"; fi; done
  echo "---- manifest config 비교"; "$PY" -c "import json,sys; a=json.load(open('$P/e2_nocache/e2_manifest.json',encoding='utf-8'))['config']; b=json.load(open('expected/e2_manifest.json',encoding='utf-8'))['config']; print('재실행:', a); print('동결  :', b)"; } >> "$SUMMARY" 2>&1
echo "Phase F 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
