#!/usr/bin/env bash
# v2 깨끗한 클론 재현 — 사용법: bash yejun/press_guard/tools/clean_repro.sh
# 1) 저장소를 임시 폴더에 클론 2) 원본 데이터만 복사 3) v1 2단계(행별 예측 재생성, 캐시 없음) 4) train.py --rolling → analyze.py → audit.py
# 5) verify.py로 클론에 커밋된 동결 기대값과 비교. 실행 실패는 즉시 전파한다. 약 1분.
set -euo pipefail
PKG="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$PKG/../.." && pwd)"
TMP="$(mktemp -d)"
PY="${PYTHON:-python3}"
git clone -q "$REPO" "$TMP/clone"
DEST="$TMP/clone/yejun"
[[ -d "$DEST/press_guard/outputs/expected" ]] || { echo "클론에 press_guard/outputs/expected가 없다. 동결 기대값을 먼저 커밋한다." >&2; exit 2; }
mkdir -p "$DEST/press_submission/data"
cp -R "$PKG/../press_submission/data/." "$DEST/press_submission/data/"
mv "$DEST/press_guard/outputs/expected" "$TMP/expected_from_clone"
rm -rf "$DEST/press_guard/outputs" "$DEST/press_guard/artifacts" && mkdir -p "$DEST/press_guard/outputs"
echo "== clone: $(git -C "$TMP/clone" rev-parse --short HEAD) =="
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
run() { echo "-- $*"; "$PY" "$@" > "$TMP/last.log" 2>&1 || { s=$?; echo "실패(종료 코드 $s): $*" >&2; tail -8 "$TMP/last.log"; exit "$s"; }; }
run "$DEST/press_submission/run_all.py" --root "$DEST/press_submission" --out "$DEST/press_submission/outputs" --steps 2 --no-baselines
run "$DEST/press_guard/train.py" --rolling
run "$DEST/press_guard/analyze.py"
run "$DEST/press_guard/audit.py"
mkdir -p "$DEST/press_guard/outputs/expected"
cp -R "$TMP/expected_from_clone/." "$DEST/press_guard/outputs/expected/"
"$PY" "$DEST/press_guard/verify.py" --out "$DEST/press_guard/outputs" | tail -n 20
echo "임시 폴더: $TMP (검사 후 삭제 가능)"
