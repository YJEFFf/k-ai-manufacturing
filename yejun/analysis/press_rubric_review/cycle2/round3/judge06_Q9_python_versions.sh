#!/usr/bin/env bash
# Q9 — 파이썬 판 주장(R2-03: README:14 "3.11~3.12", runtime.py SUPPORTED=(3,11)~(3,12), requirements.txt 1행, lock 1행 "3.11·3.12 ... 시험 통과").
#  a) 패키지 없는 3.10·3.13·3.14 인터프리터에서 reproduce.py가 설치 안내를 내고 멈추는가(추적 출력 없이)
#  b) 3.10에 requirements.txt·lock이 정말 설치되지 않는가(uv 해석만, --dry-run)
#  c) 3.11.15 새 가상환경 + pip install --no-deps -r requirements-lock.txt + git 없는 사본 + 한 명령 --tests (lock 1행 주장 확인)
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/Q9_pyver"; rm -rf "$P"; mkdir -p "$P/logs" "$P/uvcache" "$P/pip_cache"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_Q9_python_versions.log"; : > "$SUMMARY"
export UV_CACHE_DIR="$P/uvcache" PIP_CACHE_DIR="$P/pip_cache"
UV=/opt/anaconda3/bin/uv
PY310=/Users/heoyejun/.local/share/uv/python/cpython-3.10-macos-aarch64-none/bin/python3.10
PY311=/Users/heoyejun/.local/share/uv/python/cpython-3.11-macos-aarch64-none/bin/python3.11
PY313=/Users/heoyejun/.local/share/uv/python/cpython-3.13-macos-aarch64-none/bin/python3.13
PY314=/opt/homebrew/bin/python3.14
echo "Q9 시작 $(date '+%F %T') 기준=$COMMIT" | tee -a "$SUMMARY"
make_archive "$P/copy"; cd "$P/copy"
for v in "$PY310" "$PY313" "$PY314"; do
  n=$(basename "$v")
  step Q9a_gate_$n "$v" -I yejun/press_guard/reproduce.py --data "$ORG_ZIP"; tail_to_summary Q9a_gate_$n 4
  echo "     추적 출력(Traceback) 수: $(grep -c Traceback "$LOGS/Q9a_gate_$n.err")" >> "$SUMMARY"
done
step Q9b1_dryrun310_req $UV pip install --dry-run -q -p "$PY310" --no-cache -r yejun/press_guard/requirements.txt; tail_to_summary Q9b1_dryrun310_req 6
step Q9b2_dryrun310_lock $UV pip install --dry-run -q -p "$PY310" --no-cache -r yejun/press_guard/requirements-lock.txt; tail_to_summary Q9b2_dryrun310_lock 6
step Q9c1_venv311 "$PY311" -m venv "$P/venv311"; tail_to_summary Q9c1_venv311 2
step Q9c2_install311_lock_nodeps "$P/venv311/bin/python" -m pip install -q --no-deps -r yejun/press_guard/requirements-lock.txt; tail_to_summary Q9c2_install311_lock_nodeps 6
step Q9c3_pip_check311 "$P/venv311/bin/python" -m pip check; tail_to_summary Q9c3_pip_check311 4
{ echo "---- 3.11 설치 목록"; "$P/venv311/bin/python" -m pip freeze 2>&1 | tr '\n' ' '; echo; } >> "$SUMMARY"
step Q9c4_reproduce311_tests "$P/venv311/bin/python" yejun/press_guard/reproduce.py --data "$ORG_ZIP" --tests; tail_to_summary Q9c4_reproduce311_tests 30
summary_to_log yejun/press_guard/outputs/reproduce_summary.json
bits_to_log "$P/copy"
echo "Q9 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
