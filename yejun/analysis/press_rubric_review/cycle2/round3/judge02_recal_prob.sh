#!/usr/bin/env bash
# 평가관 02 (cycle2/round3) — 재보정 모델(recalibrate.py)에서 이상 확률 층이 어떻게 되는지 확인한다.
# - OPERATIONS.md 2단계는 "재보정 모델, α, 사전 비율 π를 정한다"고 적는다. 재보정은 이상 라벨을 쓰지 않으므로
#   라벨 보정기(probability_<이름>.json)가 생기지 않는다. 그때 예측 파일의 확률 열이 어떻게 되는지 본다.
# - 기준 커밋 코드만 git archive로 시스템 임시 폴더에 푼다. 저장소 안에는 이 스크립트와 로그만 남는다.
# 실행(저장소 루트): bash yejun/analysis/press_rubric_review/cycle2/round3/judge02_recal_prob.sh 2>&1 | tee yejun/analysis/press_rubric_review/cycle2/round3/judge02_recal_prob.log
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../../../.." && pwd)"
COMMIT="${COMMIT:-061fac8}"
PY="${PY:-/opt/anaconda3/bin/python}"
DATA="$REPO/yejun/press_submission/data/3_소성가공_예지보전"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/judge02_c2r3_recal.XXXXXX")"
echo "HEAD $(git -C "$REPO" rev-parse --short HEAD) · 기준 $(git -C "$REPO" rev-parse --short "$COMMIT") · 사본 <임시>"
git -C "$REPO" archive --format=tar "$COMMIT" yejun/press_guard yejun/press_submission | tar -x -C "$TMP"
mkdir -p "$TMP/yejun/press_submission/data"
ln -s "$DATA" "$TMP/yejun/press_submission/data/3_소성가공_예지보전"
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
cd "$TMP"
START=$(date +%s)
set +e
"$PY" yejun/press_guard/recalibrate.py --normal "$DATA/press_data_normal.csv" --out "$TMP/site/site.json" --save-failed 2>&1 | tail -3 | sed "s#$TMP#<임시>#g"
set -e
"$PY" yejun/press_guard/predict.py --model "$TMP/site/site.json" --input "$DATA/outlier_data.csv" --out "$TMP/site/pred_abnormal.csv" --prior 0.01 | sed "s#$TMP#<임시>#g"
END=$(date +%s)
echo "재보정+예측 $((END-START))초"
ls "$TMP/site" | sed 's/^/  파일: /'
"$PY" - "$TMP/site/pred_abnormal.csv" <<'EOF'
import sys
import pandas as pd
t = pd.read_csv(sys.argv[1])
cols = [c for c in ("likelihood_ratio", "anomaly_probability", "record_likelihood_ratio", "record_probability", "probability_prior") if c in t]
print("행", len(t), "경보 행", int(t.alarm.sum()))
for c in cols:
    print(f"  {c}: 결측 {int(t[c].isna().sum())}/{len(t)}", "" if t[c].isna().all() else f"(예: {t[c].dropna().iloc[0]})")
EOF
