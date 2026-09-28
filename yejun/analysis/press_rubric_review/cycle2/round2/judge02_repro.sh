#!/usr/bin/env bash
# 평가관 02 (cycle2/round2) — 팀의 한 명령 재현(reproduce.py --tests)을 기준 커밋 사본에서 실행한다.
# - 커밋 코드만 git archive로 시스템 임시 폴더에 푼다(작업 트리 미사용). 원본 CSV 두 개만 심볼릭 링크로 둔다.
# - 저장소 안에는 이 스크립트와 로그(judge02_repro.log)만 남는다.
# 실행(저장소 루트): bash yejun/analysis/press_rubric_review/cycle2/round2/judge02_repro.sh 2>&1 | tee yejun/analysis/press_rubric_review/cycle2/round2/judge02_repro.log
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../../../.." && pwd)"
COMMIT="${COMMIT:-e9ed90f}"
PY="${PY:-/opt/anaconda3/bin/python}"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/judge02_c2r2_repro.XXXXXX")"
echo "HEAD $(git -C "$REPO" rev-parse HEAD) · 기준 $(git -C "$REPO" rev-parse "$COMMIT") · 사본 $TMP"
git -C "$REPO" archive --format=tar "$COMMIT" yejun | tar -x -C "$TMP"
mkdir -p "$TMP/yejun/press_submission/data"
ln -s "$REPO/데이터셋/프레스_유압펌프_예지보전/data/3_소성가공_예지보전" "$TMP/yejun/press_submission/data/3_소성가공_예지보전"
shasum -a 256 "$TMP/yejun/press_submission/data/3_소성가공_예지보전/"*.csv
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
START=$(date +%s)
set +e
( cd "$TMP" && "$PY" yejun/press_guard/reproduce.py --tests )
RC=$?
set -e
END=$(date +%s)
echo "reproduce.py --tests 종료 코드 $RC · $((END-START))초"
echo "--- reproduce_summary.json"
cat "$TMP/yejun/press_guard/outputs/reproduce_summary.json" || true
echo "--- 테스트 예측 파일 열·F1 확인"
"$PY" - "$TMP" <<'EOF'
import sys, pandas as pd, numpy as np
root = sys.argv[1]
for sid in "AB":
    t = pd.read_csv(f"{root}/yejun/press_guard/outputs/test_predictions_{sid}.csv")
    tp = int(((t.alarm == 1) & (t.label == 1)).sum()); fp = int(((t.alarm == 1) & (t.label == 0)).sum()); fn = int(((t.alarm == 0) & (t.label == 1)).sum())
    cols = [c for c in ("likelihood_ratio", "anomaly_probability", "record_likelihood_ratio", "record_probability", "probability_prior", "probability_source") if c in t]
    print(sid, "rows", len(t), "TP/FP/FN", tp, fp, fn, "F1", round(2 * tp / (2 * tp + fp + fn), 6), "prob cols", cols,
          "prob null", int(t.anomaly_probability.isna().sum()), "sources", t.groupby("subset").probability_source.unique().to_dict())
EOF
echo "사본 위치: $TMP"
