#!/usr/bin/env bash
# 깨끗한 클론에서 재현 검사 — PLAN.md §9.6. 사용법: bash tools/clean_repro.sh [--with-lstm]
# 1) 저장소를 임시 폴더에 클론 2) 데이터·(선택) LSTM 캐시 복사 3) run_all 실행 4) verify.py로 동결 기대값과 비교
set -euo pipefail
PKG="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$PKG/../.." && pwd)"
TMP="$(mktemp -d)"
STEPS=3; WITH_LSTM=0
[[ "${1:-}" == "--with-lstm" ]] && { STEPS=5; WITH_LSTM=1; }
git clone -q "$REPO" "$TMP/clone"
DEST="$TMP/clone/yejun/press_submission"
mkdir -p "$DEST/data" "$DEST/artifacts"
cp -R "$PKG/data/." "$DEST/data/"
[[ $WITH_LSTM -eq 1 && -d "$PKG/artifacts/lstm_cache" ]] && cp -R "$PKG/artifacts/lstm_cache" "$DEST/artifacts/"
cp -R "$PKG/outputs/expected" "$DEST/outputs_expected_from_source" 2>/dev/null || true
cd "$DEST"
echo "== clone: $(git rev-parse --short HEAD) → run_all --steps $STEPS =="
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python3 run_all.py --root . --out outputs --steps "$STEPS" > "$TMP/run.log" 2>&1
mkdir -p outputs/expected && cp -R "$DEST/outputs_expected_from_source/." outputs/expected/ 2>/dev/null || true
PYTHONDONTWRITEBYTECODE=1 python3 verify.py --out outputs | tail -n 25
echo "임시 폴더: $TMP (검사 후 삭제 가능)"
