#!/usr/bin/env bash
# P2 — torch 없는 새 가상환경(python.org 3.12, press_guard/requirements.txt만 설치) + 새 git 클론 + README 한 명령(--data ZIP) + --tests.
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/P2_venv"; rm -rf "$P"; mkdir -p "$P/logs"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_P2_venv_notorch.log"; : > "$SUMMARY"
BASEPY=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12
echo "P2 시작 $(date '+%F %T') 기준=$COMMIT 기본 파이썬=$($BASEPY --version)" | tee -a "$SUMMARY"
make_clone "$P/clone"; cd "$P/clone"
step P2a_venv_create "$BASEPY" -m venv "$P/venv"
step P2b_pip_install "$P/venv/bin/python" -m pip install -q -r yejun/press_guard/requirements.txt; tail_to_summary P2b_pip_install 5
"$P/venv/bin/python" -m pip freeze > "$P/pip_freeze.txt"
{ echo "---- 설치 목록(pip freeze)"; cat "$P/pip_freeze.txt"; } >> "$SUMMARY"
"$P/venv/bin/python" -c "import importlib.util as u; print('torch 설치 여부:', u.find_spec('torch') is not None)" | tee -a "$SUMMARY"
# README 빠른 시작 두 번째 줄 그대로(파이썬만 가상환경의 것), 끝에 --tests
step P2c_reproduce_tests "$P/venv/bin/python" yejun/press_guard/reproduce.py --data "$ORG_ZIP" --tests; tail_to_summary P2c_reproduce_tests 30
summary_to_log yejun/press_guard/outputs/reproduce_summary.json
echo "P2 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
