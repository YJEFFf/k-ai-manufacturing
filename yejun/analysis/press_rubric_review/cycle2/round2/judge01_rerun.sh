#!/usr/bin/env bash
# 평가관 01 사이클2 2회차 — press_evidence 진단 스크립트를 기준 커밋의 깨끗한 사본(시스템 임시 폴더)에서 다시 실행한다.
#   1) git archive로 기준 커밋의 yejun/를 꺼내고, Git에서 뺀 입력(원본 CSV 2개, 동결 모델 guard_A/B.json)만 복사한다.
#   2) 손대지 않은 사본에서 공용 검증 계약(package_contract.py)과 변조 검출 시험(test_contract.py)을 돌린다.
#   3) build_tables.py·build_diagnostics.py를 다시 실행하고, 표 33개·그림 5장·manifest를 커밋된 파일과 해시로 비교한다.
#   4) 재실행 결과로 계약을 다시 확인한다.
# 저장소에는 아무것도 쓰지 않는다(이 스크립트의 로그만 round2 폴더에 남는다).
#
#   bash yejun/analysis/press_rubric_review/cycle2/round2/judge01_rerun.sh <임시 폴더>
set -u
REPO="/Volumes/YJSSD/공모전/k-제조데이터"
REF="e9ed90f"
WORK="${1:?임시 폴더를 주세요}"
PY="/opt/anaconda3/bin/python"
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 MPLBACKEND=Agg
rm -rf "$WORK" && mkdir -p "$WORK"
cd "$WORK" || exit 2
git -C "$REPO" archive "$REF" yejun | tar -x -C "$WORK"
mkdir -p yejun/press_submission/data/3_소성가공_예지보전 yejun/press_guard/artifacts
cp "$REPO/yejun/press_submission/data/3_소성가공_예지보전/"*.csv yejun/press_submission/data/3_소성가공_예지보전/
cp "$REPO/yejun/press_guard/artifacts/guard_A.json" "$REPO/yejun/press_guard/artifacts/guard_B.json" yejun/press_guard/artifacts/
echo "== 입력 해시"
shasum -a 256 yejun/press_submission/data/3_소성가공_예지보전/*.csv yejun/press_guard/artifacts/guard_*.json

cd "$WORK/yejun" || exit 2
echo "== [1] 손대지 않은 사본: 공용 검증 계약"
t0=$(date +%s)
$PY analysis/package_contract.py --package analysis/press_evidence; echo "exit=$? ($(( $(date +%s) - t0 ))s)"
echo "== [2] 손대지 않은 사본: 변조 검출 시험"
t0=$(date +%s)
$PY -m pytest -q -p no:cacheprovider analysis/press_evidence/test_contract.py 2>&1 | tail -3; echo "($(( $(date +%s) - t0 ))s)"

echo "== [3] build_tables.py 재실행"
t0=$(date +%s)
$PY analysis/press_evidence/build_tables.py > "$WORK/build_tables.out" 2>&1; echo "exit=$? ($(( $(date +%s) - t0 ))s)"; tail -2 "$WORK/build_tables.out"
echo "== [4] build_diagnostics.py 재실행"
t0=$(date +%s)
$PY analysis/press_evidence/build_diagnostics.py > "$WORK/build_diag.out" 2>&1; echo "exit=$? ($(( $(date +%s) - t0 ))s)"; tail -2 "$WORK/build_diag.out"

echo "== [5] 재실행 산출물과 커밋 파일 해시 비교(표·그림·manifest)"
same=0; diff=0
for f in $(cd "$REPO/yejun/analysis/press_evidence" && git -C "$REPO" ls-files --full-name -- yejun/analysis/press_evidence | sed 's#^yejun/analysis/press_evidence/##' | grep -E '\.(csv|png|json)$' | grep -v '^expected/'); do
  a=$(shasum -a 256 "$REPO/yejun/analysis/press_evidence/$f" | cut -d' ' -f1)
  b=$(shasum -a 256 "$WORK/yejun/analysis/press_evidence/$f" | cut -d' ' -f1)
  if [ "$a" = "$b" ]; then same=$((same+1)); else diff=$((diff+1)); echo "  다름: $f"; fi
done
echo "  같음 $same, 다름 $diff"
echo "== [6] 재실행 뒤 공용 검증 계약"
$PY analysis/package_contract.py --package analysis/press_evidence; echo "exit=$?"
echo "== [7] 사본에 __pycache__가 생겼는가(0이어야 한다)"
find "$WORK/yejun" -name __pycache__ | wc -l
