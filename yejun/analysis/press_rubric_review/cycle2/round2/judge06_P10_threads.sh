#!/usr/bin/env bash
# P10 — R11 스레드: 스레드 환경변수(OMP_NUM_THREADS·PRESS_THREADS) 없이 train.py를 돌려 시간·manifest의 BLAS 스레드 수·결과 동일성을 본다.
# 한 명령 재현을 마친 사본(기본 P2 클론)에서, 결과는 임시 폴더에 쓴다. 비교용으로 PRESS_THREADS=8도 한 번.
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
SRC="${1:-$J06_BASE/P2_venv/clone}"; PYX="${PYX:-$J06_BASE/P2_venv/venv/bin/python}"
P="$J06_BASE/P10_threads"; rm -rf "$P"; mkdir -p "$P/logs"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_P10_threads.log"; : > "$SUMMARY"
echo "P10 시작 $(date '+%F %T') 원천=$SRC 파이썬=$PYX 코어=$(sysctl -n hw.ncpu)" | tee -a "$SUMMARY"
cd "$SRC/yejun"
NOVARS=(env -u OMP_NUM_THREADS -u PRESS_THREADS -u OPENBLAS_NUM_THREADS -u MKL_NUM_THREADS)
step P10a_train_novars "${NOVARS[@]}" "$PYX" press_guard/train.py --out "$P/out_novars" --artifacts "$P/art_novars"; tail_to_summary P10a_train_novars 1
step P10b_train_press8 "${NOVARS[@]}" PRESS_THREADS=8 "$PYX" press_guard/train.py --out "$P/out_p8" --artifacts "$P/art_p8"; tail_to_summary P10b_train_press8 1
"$PY" - "$P" "$REPO" "$COMMIT" >> "$SUMMARY" <<'PYEOF'
import hashlib, json, subprocess, sys
from pathlib import Path
P, repo, commit = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
show = lambda rel: json.loads(subprocess.run(["git", "-C", repo, "show", f"{commit}:yejun/press_guard/{rel}"], capture_output=True, check=True).stdout)
dig, man = show("outputs/expected/predictions_digest.json"), show("outputs/manifest.json")
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
for tag in ("novars", "p8"):
    m = json.loads((P / f"out_{tag}" / "manifest.json").read_text(encoding="utf-8"))
    blas = [(b.get("api"), b.get("version"), b.get("threads")) for b in (m["environment"].get("blas") or [])]
    print(f"---- {tag}: manifest BLAS {blas}, press_threads={m['environment'].get('press_threads')}, elapsed_s={m.get('elapsed_s')}")
    print("     저장 모델 동결 해시:", {n: sha(P / f"art_{tag}" / n) == h for n, h in man["artifacts"].items()})
    print("     행 단위 예측 동결 해시:", {n: sha(P / f"out_{tag}" / n) == d["sha256"] for n, d in dig.items()})
PYEOF
echo "P10 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
