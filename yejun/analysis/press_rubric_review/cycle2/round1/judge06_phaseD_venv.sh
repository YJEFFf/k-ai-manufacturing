#!/usr/bin/env bash
# Phase D — 새 가상환경. (1) 다른 파이썬 빌드(python.org 3.12.8)로 빈 venv → requirements.txt만 설치 → 새 클론에서 v2 전체 경로·테스트
# (2) torch 없이 설치한 venv에서 최종 모델 경로가 되는지(의존성 결합 확인) (3) 파이썬 3.14·3.13에서 고정 의존성 설치 가능 여부(설치하지 않고 해석만)
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/D_venv"; rm -rf "$P"; mkdir -p "$P/logs"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_phaseD_venv.log"; : > "$SUMMARY"
PY312=/usr/local/bin/python3.12; PY314=/opt/homebrew/bin/python3.14; UV=/opt/anaconda3/bin/uv
echo "Phase D 시작 $(date '+%F %T') HEAD=$(git -C "$REPO" rev-parse HEAD) base=$("$PY312" -c 'import sys;print(sys.version.split()[0], sys.executable)')" | tee -a "$SUMMARY"
C="$P/clone"; make_clone "$C"; Y="$C/yejun"
REQ="$Y/press_submission/requirements.txt"

# (1) python.org 3.12.8 빈 venv
"$PY312" -m venv "$P/venv312"; V="$P/venv312/bin/python"
step D01_pip_install "$V" -m pip install --disable-pip-version-check -r "$REQ"; tail_to_summary D01_pip_install 3
"$V" -m pip freeze > "$P/logs/pip_freeze_venv312.txt"; cp "$P/logs/pip_freeze_venv312.txt" "$OUTDIR/judge06_venv312_pip_freeze.txt"
"$V" -c "import json,sys,threadpoolctl; print(json.dumps(dict(python=sys.version.split()[0], executable=sys.executable, blas=[{k:i.get(k) for k in ('internal_api','version','num_threads','filepath')} for i in threadpoolctl.threadpool_info()]), ensure_ascii=False))" >> "$SUMMARY" 2>&1
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
cd "$C"
mv "$Y/press_guard/outputs/expected" "$P/v2_expected"
rm -rf "$Y/press_guard/outputs" "$Y/press_guard/artifacts"; mkdir -p "$Y/press_guard/outputs"
step D02_v1_step2 "$V" yejun/press_submission/run_all.py --root yejun/press_submission --out yejun/press_submission/outputs --steps 2 --no-baselines; tail_to_summary D02_v1_step2 2
step D03_train "$V" yejun/press_guard/train.py --rolling; tail_to_summary D03_train 2
step D04_analyze "$V" yejun/press_guard/analyze.py; tail_to_summary D04_analyze 2
step D05_audit "$V" yejun/press_guard/audit.py; tail_to_summary D05_audit 1
cp -R "$P/v2_expected" "$Y/press_guard/outputs/expected"
step D06_verify "$V" yejun/press_guard/verify.py; tail_to_summary D06_verify 2
cd "$Y"
step D07_pytest_v2 "$V" -m pytest -q -p no:cacheprovider press_guard/test_guard.py press_guard/test_serve.py press_guard/test_analyze.py press_guard/test_review_regressions.py press_guard/test_recalibrate.py --basetemp "$P/pt_v2"; tail_to_summary D07_pytest_v2 3
step D08_pytest_v1 "$V" -m pytest -q -p no:cacheprovider press_submission/tests --basetemp "$P/pt_v1"; tail_to_summary D08_pytest_v1 3
step D09_pytest_supp "$V" -m pytest -q -p no:cacheprovider analysis/press_supplement/test_contract.py --basetemp "$P/pt_supp"; tail_to_summary D09_pytest_supp 3

# (2) torch 없는 venv: 최종 모델(v2)은 torch를 쓰지 않지만 선행 단계 run_all.py가 torch를 최상단에서 import한다
"$PY312" -m venv "$P/venv_notorch"; VN="$P/venv_notorch/bin/python"
grep -v -i '^torch' "$REQ" > "$P/req_notorch.txt"
step D10_pip_notorch "$VN" -m pip install --disable-pip-version-check -r "$P/req_notorch.txt"; tail_to_summary D10_pip_notorch 2
C2="$P/clone_notorch"; make_clone "$C2"; cd "$C2"
step D11_notorch_v1_step2 "$VN" yejun/press_submission/run_all.py --root yejun/press_submission --out yejun/press_submission/outputs --steps 2 --no-baselines; tail_to_summary D11_notorch_v1_step2 3
step D12_notorch_train "$VN" yejun/press_guard/train.py --rolling; tail_to_summary D12_notorch_train 2

# (3) 다른 파이썬 버전에서 고정 의존성 설치 가능 여부(바이너리 휠만, 실제 설치 없이 해석)
"$PY314" -m venv "$P/venv314"
step D13_py314_dryrun "$P/venv314/bin/python" -m pip install --disable-pip-version-check --dry-run --only-binary=:all: -r "$REQ"; tail_to_summary D13_py314_dryrun 6
for pv in 3.11 3.12 3.13; do
  step "D14_uv_resolve_mac_py${pv}" "$UV" pip compile "$REQ" --python-version "$pv" --python-platform aarch64-apple-darwin --only-binary :all: --no-header -q; tail_to_summary "D14_uv_resolve_mac_py${pv}" 4
done
step D15_uv_resolve_win_py312 "$UV" pip compile "$REQ" --python-version 3.12 --python-platform x86_64-pc-windows-msvc --only-binary :all: --no-header -q; tail_to_summary D15_uv_resolve_win_py312 4
step D16_uv_resolve_linux_py312 "$UV" pip compile "$REQ" --python-version 3.12 --python-platform x86_64-manylinux_2_28 --only-binary :all: --no-header -q; tail_to_summary D16_uv_resolve_linux_py312 4
{ echo "---- 리눅스 x86_64 해석 결과의 nvidia·triton 패키지 수: $(grep -c -E '^(nvidia-|triton)' "$LOGS/D16_uv_resolve_linux_py312.out")"; } >> "$SUMMARY"
echo "Phase D 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
