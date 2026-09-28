#!/usr/bin/env bash
# 평가관 01 사이클2 3회차 — press_evidence 진단 스크립트를 기준 커밋의 깨끗한 사본(시스템 임시 폴더)에서 다시 실행한다.
#   1) git archive로 기준 커밋의 yejun/를 꺼내고, Git에서 뺀 입력(원본 CSV 2개, 동결 모델 guard_A/B.json)만 복사한다.
#   2) 손대지 않은 사본에서 공용 검증 계약(package_contract.py)과 변조 검출 시험(test_contract.py)을 돌린다.
#   3) build_tables.py·build_diagnostics.py를 다시 실행하고, 표 37개·그림 5장·manifest를 커밋된 파일과 해시로 비교한다.
#   4) 재실행 결과로 계약을 다시 확인한다. 2회차에 더한 표 4개는 따로 적는다.
# 저장소에는 아무것도 쓰지 않는다(이 스크립트의 로그만 round3 폴더에 남는다).
#
#   bash yejun/analysis/press_rubric_review/cycle2/round3/judge01_rerun.sh <임시 폴더> > .../round3/judge01_rerun.log 2>&1
set -u
REPO="/Volumes/YJSSD/공모전/k-제조데이터"
REF="061fac8"
WORK="${1:?임시 폴더를 주세요}"
PY="/opt/anaconda3/bin/python"
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 MPLBACKEND=Agg
T_ALL=$(date +%s)
echo "== 기준 커밋 $(git -C "$REPO" rev-parse "$REF")"
rm -rf "$WORK" && mkdir -p "$WORK"
cd "$WORK" || exit 2
git -C "$REPO" archive "$REF" yejun | tar -x -C "$WORK"
mkdir -p yejun/press_submission/data/3_소성가공_예지보전 yejun/press_guard/artifacts
cp "$REPO/yejun/press_submission/data/3_소성가공_예지보전/"*.csv yejun/press_submission/data/3_소성가공_예지보전/
cp "$REPO/yejun/press_guard/artifacts/guard_A.json" "$REPO/yejun/press_guard/artifacts/guard_B.json" yejun/press_guard/artifacts/
echo "== 입력 해시(diagnostics_manifest의 input_hashes·artifacts와 같아야 한다)"
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
for f in $(git -C "$REPO" ls-tree -r --name-only "$REF" -- yejun/analysis/press_evidence | sed 's#^yejun/analysis/press_evidence/##' | grep -E '\.(csv|png|json)$' | grep -v '^expected/' | grep -v '^contract.json$'); do
  a=$(git -C "$REPO" show "$REF:yejun/analysis/press_evidence/$f" | shasum -a 256 | cut -d' ' -f1)
  b=$(shasum -a 256 "$WORK/yejun/analysis/press_evidence/$f" | cut -d' ' -f1)
  if [ "$a" = "$b" ]; then same=$((same+1)); else diff=$((diff+1)); echo "  다름: $f"; fi
done
echo "  같음 $same, 다름 $diff"
echo "== [5b] 2회차에 더한 표 4개와 정정된 표·그림(바이트 비교)"
for f in operating_states.csv operating_states_summary.csv split_state_composition.csv normal_alarms_by_state.csv production_unit_evidence.csv sensor_relations.csv decision_table_diagnosis_v2.csv observability.csv failure_mode_map.csv figures/fig_d2a_timeline.png figures/fig_d2c_raw_examples.png figures/fig_d2d_relations.png; do
  a=$(git -C "$REPO" show "$REF:yejun/analysis/press_evidence/$f" | shasum -a 256 | cut -d' ' -f1)
  b=$(shasum -a 256 "$WORK/yejun/analysis/press_evidence/$f" | cut -d' ' -f1)
  if [ "$a" = "$b" ]; then echo "  같음: $f"; else echo "  다름: $f"; fi
done
echo "== [5c] manifest 차이(elapsed_s 외 키가 다르면 안 된다)"
for m in manifest.json diagnostics_manifest.json; do
  $PY - "$REPO" "$REF" "$WORK/yejun/analysis/press_evidence/$m" "$m" <<'EOF'
import json, subprocess, sys
repo, ref, new_path, name = sys.argv[1:5]
old = json.loads(subprocess.run(["git", "-C", repo, "show", f"{ref}:yejun/analysis/press_evidence/{name}"], capture_output=True, text=True, check=True).stdout)
new = json.load(open(new_path, encoding="utf-8"))
def flat(d, p=""):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(flat(v, f"{p}{k}."))
        else:
            out[f"{p}{k}"] = v
    return out
fo, fn = flat(old), flat(new)
keys = sorted(k for k in set(fo) | set(fn) if fo.get(k) != fn.get(k))
print(f"  {name}: 다른 키 {keys}")
EOF
done
echo "== [6] 재실행 뒤 공용 검증 계약"
$PY analysis/package_contract.py --package analysis/press_evidence; echo "exit=$?"
echo "== [7] 사본에 __pycache__가 생겼는가(0이어야 한다)"
find "$WORK/yejun" -name __pycache__ | wc -l
echo "== 전체 $(( $(date +%s) - T_ALL ))초"
