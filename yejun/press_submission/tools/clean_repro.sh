#!/usr/bin/env bash
# 깨끗한 클론에서 재현 검사 — PLAN.md §9.6. 사용법: bash tools/clean_repro.sh [--with-lstm | --retrain-lstm]
#   --with-lstm   : LSTM 캐시를 복사해 1~5단계 실행(약 1분)
#   --retrain-lstm: 캐시 없이 LSTM을 처음부터 학습해 1~5단계 실행(약 30분). 검수 R6의 캐시 없는 재학습 확인
# 1) 저장소를 임시 폴더에 클론 2) 데이터·(선택) LSTM 캐시 복사 3) run_all 실행 4) verify.py로 동결 기대값과 비교
set -euo pipefail
PKG="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$PKG/../.." && pwd)"
TMP="$(mktemp -d)"
STEPS=3; WITH_LSTM=0; RETRAIN=0
case "${1:-}" in
  "") ;;
  --with-lstm) STEPS=5; WITH_LSTM=1 ;;
  --retrain-lstm) STEPS=5; RETRAIN=1 ;;
  *) echo "사용법: $0 [--with-lstm | --retrain-lstm]" >&2; exit 2 ;;
esac
git clone -q "$REPO" "$TMP/clone"
DEST="$TMP/clone/yejun/press_submission"
mkdir -p "$DEST/data" "$DEST/artifacts"
cp -R "$PKG/data/." "$DEST/data/"
[[ $WITH_LSTM -eq 1 && -d "$PKG/artifacts/lstm_cache" ]] && cp -R "$PKG/artifacts/lstm_cache" "$DEST/artifacts/"
cp -R "$PKG/outputs/expected" "$DEST/outputs_expected_from_source"
cd "$DEST"
rm -rf outputs && mkdir -p outputs   # 커밋된 산출물을 지우고 처음부터 다시 만든다
echo "== clone: $(git rev-parse --short HEAD) → run_all --steps $STEPS =="
RUN_ARGS=(--root . --out outputs --steps "$STEPS")
[[ $RETRAIN -eq 1 ]] && RUN_ARGS+=(--retrain-lstm)
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python3 run_all.py "${RUN_ARGS[@]}" > "$TMP/run.log" 2>&1 || { RUN_STATUS=$?; echo "run_all 실패(종료 코드 $RUN_STATUS), 로그: $TMP/run.log" >&2; tail -5 "$TMP/run.log"; exit "$RUN_STATUS"; }
mkdir -p outputs/expected
cp -R "$DEST/outputs_expected_from_source/." outputs/expected/
PYTHONDONTWRITEBYTECODE=1 python3 verify.py --out outputs --steps "$STEPS" | tail -n 45
echo "임시 폴더: $TMP (검사 후 삭제 가능)"
