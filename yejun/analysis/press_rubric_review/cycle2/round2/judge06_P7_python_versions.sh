#!/usr/bin/env bash
# P7 — 파이썬 판 주장 확인(README:14 "파이썬 3.10~3.12", runtime.py SUPPORTED=(3,10)~(3,12), requirements.txt 1행).
#  a) 3.13(uv)·3.14(homebrew)에서 reproduce.py가 안내를 내고 멈추는가
#  b) 3.10 새 가상환경에 requirements.txt가 설치되는가(uv, PyPI)
#  c) 3.11 새 가상환경(requirements-lock.txt) + git 없는 사본에서 한 명령 재현이 통과하고 결과가 3.12와 비트 단위로 같은가
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/P7_pyver"; rm -rf "$P"; mkdir -p "$P/logs" "$P/uvcache"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_P7_python_versions.log"; : > "$SUMMARY"
export UV_CACHE_DIR="$P/uvcache"
UV=/opt/anaconda3/bin/uv
echo "P7 시작 $(date '+%F %T') 기준=$COMMIT" | tee -a "$SUMMARY"
make_archive "$P/copy"; cd "$P/copy"
PY313=$($UV python find 3.13 2>/dev/null); PY314=/opt/homebrew/bin/python3.14
for v in "$PY313" "$PY314"; do
  n=$(basename "$v")
  step P7a_gate_$n "$v" yejun/press_guard/reproduce.py --data "$ORG_ZIP"; tail_to_summary P7a_gate_$n 3
done
step P7b0_uv_py310 $UV python install 3.10; tail_to_summary P7b0_uv_py310 2
step P7b1_venv310 $UV venv -q -p 3.10 "$P/venv310"; tail_to_summary P7b1_venv310 2
step P7b2_install310 $UV pip install -q -p "$P/venv310/bin/python" -r yejun/press_guard/requirements.txt; tail_to_summary P7b2_install310 6
step P7b3_install310_lock $UV pip install -q -p "$P/venv310/bin/python" -r yejun/press_guard/requirements-lock.txt; tail_to_summary P7b3_install310_lock 6
step P7c1_venv311 $UV venv -q -p 3.11 "$P/venv311"; tail_to_summary P7c1_venv311 2
step P7c2_install311_lock $UV pip install -q -p "$P/venv311/bin/python" -r yejun/press_guard/requirements-lock.txt; tail_to_summary P7c2_install311_lock 6
{ echo "---- 3.11 설치 목록"; $UV pip freeze -p "$P/venv311/bin/python" 2>&1 | tr '\n' ' '; echo; } >> "$SUMMARY"
step P7c3_reproduce311 "$P/venv311/bin/python" yejun/press_guard/reproduce.py --data "$ORG_ZIP"; tail_to_summary P7c3_reproduce311 20
summary_to_log yejun/press_guard/outputs/reproduce_summary.json
"$PY" - "$P/copy" "$REPO" "$COMMIT" >> "$SUMMARY" <<'PYEOF'
import hashlib, json, subprocess, sys
from pathlib import Path
root, repo, commit = Path(sys.argv[1]) / "yejun/press_guard", sys.argv[2], sys.argv[3]
show = lambda rel: json.loads(subprocess.run(["git", "-C", repo, "show", f"{commit}:yejun/press_guard/{rel}"], capture_output=True, check=True).stdout)
dig, man = show("outputs/expected/predictions_digest.json"), show("outputs/manifest.json")
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
print("---- 3.11 결과 대 커밋(3.12) 동결 해시")
print("  저장 모델·보정기:", {n: sha(root / "artifacts" / n) == h for n, h in man["artifacts"].items()})
print("  행 단위 예측:", {n: sha(root / "outputs" / n) == d["sha256"] for n, d in dig.items()})
PYEOF
echo "P7 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
