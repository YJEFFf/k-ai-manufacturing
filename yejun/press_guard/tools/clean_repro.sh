#!/usr/bin/env bash
# v2 깨끗한 사본 재현 — 사용법: bash yejun/press_guard/tools/clean_repro.sh [reproduce.py 인자...]
# 1) 저장소를 임시 폴더에 클론한다. git 저장소가 아니면(ZIP을 푼 사본) yejun/ 폴더를 복사한다.
# 2) 원본 데이터만 복사하고, 커밋된 산출물(press_guard outputs·artifacts)을 지운다. 동결 기대값(outputs/expected)은 남긴다.
# 3) 한 명령 재현(reproduce.py)을 그 사본에서 실행한다. 인자를 그대로 넘긴다(예: --full, --tests).
# 운영체제와 무관한 같은 절차는 python yejun/press_guard/reproduce.py 한 줄이다. 이 스크립트는 사본을 만드는 편의용이다.
set -euo pipefail
PKG="$(cd "$(dirname "$0")/.." && pwd)"
YEJUN="$(cd "$PKG/.." && pwd)"
REPO="$(cd "$YEJUN/.." && pwd)"
TMP="$(mktemp -d)"
PY="${PYTHON:-python3}"
if git -C "$REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git clone -q "$REPO" "$TMP/clone"
  echo "== clone: $(git -C "$TMP/clone" rev-parse --short HEAD) =="
else
  mkdir -p "$TMP/clone"
  cp -R "$YEJUN" "$TMP/clone/yejun"
  echo "== git 없는 사본: $YEJUN 복사 =="
fi
DEST="$TMP/clone/yejun"
[[ -d "$DEST/press_guard/outputs/expected" ]] || { echo "사본에 press_guard/outputs/expected가 없다. 동결 기대값을 먼저 커밋한다." >&2; exit 2; }
mkdir -p "$DEST/press_submission/data"
cp -R "$YEJUN/press_submission/data/." "$DEST/press_submission/data/"
# --full이면 LSTM 캐시가 있을 때 복사한다(없으면 처음부터 학습, 약 30분 더 걸린다).
if [[ " $* " == *" --full "* && -d "$YEJUN/press_submission/artifacts/lstm_cache" ]]; then
  mkdir -p "$DEST/press_submission/artifacts" && cp -R "$YEJUN/press_submission/artifacts/lstm_cache" "$DEST/press_submission/artifacts/"
fi
mv "$DEST/press_guard/outputs/expected" "$TMP/expected_keep"
rm -rf "$DEST/press_guard/outputs" "$DEST/press_guard/artifacts" && mkdir -p "$DEST/press_guard/outputs"
mv "$TMP/expected_keep" "$DEST/press_guard/outputs/expected"
export PYTHONDONTWRITEBYTECODE=1
"$PY" "$DEST/press_guard/reproduce.py" "$@"
echo "임시 폴더: $TMP (검사 후 삭제 가능)"
