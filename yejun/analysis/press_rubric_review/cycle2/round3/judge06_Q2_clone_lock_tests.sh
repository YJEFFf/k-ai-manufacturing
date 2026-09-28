#!/usr/bin/env bash
# Q2 — 새 git 클론 + torch 없는 새 가상환경(python.org 3.12.8, pip install --no-deps -r requirements-lock.txt = R2-08 완료 기준)
#      + 주최 측 ZIP을 현재 폴더에 두고 README 빠른 시작 3행을 문자 그대로 + --tests.
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/Q2_venv"; rm -rf "$P"; mkdir -p "$P/logs" "$P/pip_cache"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_Q2_clone_lock_tests.log"; : > "$SUMMARY"
BASEPY=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12
export PIP_CACHE_DIR="$P/pip_cache"
echo "Q2 시작 $(date '+%F %T') 기준=$COMMIT 기본 파이썬=$($BASEPY --version)" | tee -a "$SUMMARY"
make_clone "$P/clone"; cd "$P/clone"
cp "$ORG_ZIP" "./$ZIP_NAME"
step Q2a_venv_create "$BASEPY" -m venv "$P/venv"
step Q2b_pip_install_lock_nodeps "$P/venv/bin/python" -m pip install -q --no-deps -r yejun/press_guard/requirements-lock.txt; tail_to_summary Q2b_pip_install_lock_nodeps 5
step Q2b2_pip_check "$P/venv/bin/python" -m pip check; tail_to_summary Q2b2_pip_check 5
"$P/venv/bin/python" -m pip freeze > "$P/pip_freeze.txt"
{ echo "---- 설치 목록(pip freeze)"; tr '\n' ' ' < "$P/pip_freeze.txt"; echo; } >> "$SUMMARY"
"$P/venv/bin/python" -c "import importlib.util as u; print('torch 설치 여부:', u.find_spec('torch') is not None, '| cloudpickle:', u.find_spec('cloudpickle') is not None)" | tee -a "$SUMMARY"
# README 빠른 시작 3행 그대로(python = 가상환경의 python), 끝에 --tests
step Q2c_reproduce_tests "$P/venv/bin/python" yejun/press_guard/reproduce.py --data "$ZIP_NAME" --tests; tail_to_summary Q2c_reproduce_tests 34
summary_to_log yejun/press_guard/outputs/reproduce_summary.json
bits_to_log "$P/clone"
echo "Q2 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
