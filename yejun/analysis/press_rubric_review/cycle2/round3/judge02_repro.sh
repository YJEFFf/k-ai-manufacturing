#!/usr/bin/env bash
# 평가관 02 (cycle2/round3) — 팀의 한 명령 재현(reproduce.py --tests)을 기준 커밋 사본에서 실행한다.
# - 커밋 코드만 git archive로 시스템 임시 폴더에 푼다(작업 트리 미사용). 원본 CSV 두 개만 심볼릭 링크로 둔다.
# - 저장소 안에는 이 스크립트와 로그(judge02_repro.log)만 남는다.
# 실행(저장소 루트): bash yejun/analysis/press_rubric_review/cycle2/round3/judge02_repro.sh 2>&1 | tee yejun/analysis/press_rubric_review/cycle2/round3/judge02_repro.log
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../../../.." && pwd)"
COMMIT="${COMMIT:-061fac8}"
PY="${PY:-/opt/anaconda3/bin/python}"
DATA="$REPO/yejun/press_submission/data/3_소성가공_예지보전"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/judge02_c2r3_repro.XXXXXX")"
echo "HEAD $(git -C "$REPO" rev-parse HEAD) · 기준 $(git -C "$REPO" rev-parse "$COMMIT") · 사본 $TMP"
git -C "$REPO" archive --format=tar "$COMMIT" yejun | tar -x -C "$TMP"
mkdir -p "$TMP/yejun/press_submission/data"
ln -s "$DATA" "$TMP/yejun/press_submission/data/3_소성가공_예지보전"
shasum -a 256 "$TMP/yejun/press_submission/data/3_소성가공_예지보전/"*.csv
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
START=$(date +%s)
set +e
( cd "$TMP" && "$PY" yejun/press_guard/reproduce.py --tests )
RC=$?
set -e
END=$(date +%s)
echo "reproduce.py --tests 종료 코드 $RC · $((END-START))초"
echo "--- reproduce_summary.json(단계·종료 코드·시간)"
"$PY" - "$TMP" <<'EOF'
import json, sys
s = json.load(open(f"{sys.argv[1]}/yejun/press_guard/outputs/reproduce_summary.json", encoding="utf-8"))
steps = s.get("steps", [])
print("단계", len(steps), "실패", sum(1 for x in steps if x.get("returncode") != 0), "합계 초", round(sum(x.get("seconds", 0) for x in steps), 1))
for x in steps:
    print(f"  {x.get('returncode')} {x.get('seconds', 0):7.1f}s {x.get('step')} | {str(x.get('last_line', ''))[:150]}")
EOF
echo "--- 테스트 예측 파일 열·F1·확률 열 확인"
"$PY" - "$TMP" <<'EOF'
import hashlib, json, sys
import numpy as np, pandas as pd
root = sys.argv[1]
dig = json.load(open(f"{root}/yejun/press_guard/outputs/expected/predictions_digest.json", encoding="utf-8"))
for sid in "AB":
    p = f"{root}/yejun/press_guard/outputs/test_predictions_{sid}.csv"
    t = pd.read_csv(p)
    tp = int(((t.alarm == 1) & (t.label == 1)).sum()); fp = int(((t.alarm == 1) & (t.label == 0)).sum()); fn = int(((t.alarm == 0) & (t.label == 1)).sum())
    cols = [c for c in t.columns if "prob" in c or "likelihood" in c or "prior" in c]
    sha = hashlib.sha256(open(p, "rb").read()).hexdigest()
    ab = t[t.label.eq(1)]
    print(sid, "rows", len(t), "TP/FP/FN", tp, fp, fn, "F1", round(2 * tp / (2 * tp + fp + fn), 6), "prob cols", cols,
          "file_prior", sorted(t.file_prior.unique().tolist()) if "file_prior" in t else None,
          "abnormal LR at cap", int(np.isclose(ab.likelihood_ratio, ab.likelihood_ratio.max()).sum()), "sha256", sha[:16])
    ent = dig.get(f"test_predictions_{sid}.csv") or {}
    print("   digest sha256", str(ent.get("sha256", ""))[:16], "같음" if ent.get("sha256") == sha else "다름(허용오차 비교는 verify 단계)")
EOF
echo "사본 위치: $TMP"
