#!/usr/bin/env bash
# 평가관 02 (cycle2/round3) — 학습 없이 저장 모델로 테스트 예측 파일을 다시 만든다(predict.py --split, README:78).
# - judge02_repro.sh가 만든 기준 커밋 사본(시스템 임시 폴더)에서 실행한다. 저장소 안에는 이 스크립트와 로그만 남는다.
# - 새 확률 열(file_prior, anomaly_probability_file_prior)까지 train.py 결과와 SHA-256이 같은지 본다.
# 실행(저장소 루트): bash yejun/analysis/press_rubric_review/cycle2/round3/judge02_predict_split.sh <사본 경로> 2>&1 | tee yejun/analysis/press_rubric_review/cycle2/round3/judge02_predict_split.log
set -euo pipefail
COPY="${1:?judge02_repro.sh 사본 경로}"
PY="${PY:-/opt/anaconda3/bin/python}"
OUT="$(mktemp -d "${TMPDIR:-/tmp}/judge02_c2r3_split.XXXXXX")"
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
cd "$COPY"
for S in A B; do
  START=$(date +%s)
  "$PY" yejun/press_guard/predict.py --split "$S" --out "$OUT/test_predictions_$S.csv"
  END=$(date +%s)
  echo "split $S: $((END-START))초"
  shasum -a 256 "$OUT/test_predictions_$S.csv" "yejun/press_guard/outputs/test_predictions_$S.csv" | sed "s#$OUT#<임시>#; s#$COPY#<사본>#"
done
"$PY" - "$OUT" "$COPY" <<'EOF'
import sys
import pandas as pd
out, copy = sys.argv[1], sys.argv[2]
for s in "AB":
    a = pd.read_csv(f"{out}/test_predictions_{s}.csv")
    b = pd.read_csv(f"{copy}/yejun/press_guard/outputs/test_predictions_{s}.csv")
    same = a.equals(b)
    print(s, "행", len(a), "열 같음", list(a.columns) == list(b.columns), "값 같음", same,
          "새 열", [c for c in ("file_prior", "anomaly_probability_file_prior") if c in a.columns])
EOF
