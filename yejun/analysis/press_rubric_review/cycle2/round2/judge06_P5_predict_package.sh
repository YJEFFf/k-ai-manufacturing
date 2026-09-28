#!/usr/bin/env bash
# P5 — 추론 전용(predict.py --split)과 패키지 목록(package_manifest.py) 검사. 인자: 한 명령 재현을 마친 사본의 루트(기본 P2 클론).
#  a) 끝난 실행에서 predict.py --split A/B → 학습 실행의 test_predictions와 SHA-256, 커밋된 동결 요약(predictions_digest.json) 대조
#  b) package_manifest.py 목록·블라인드 검사 → 목록 파일만 새 폴더에 복사(목록의 상대 경로 그대로, 루트에 yejun/ 없음)
#  c) 복사본: README 문자 그대로의 명령, 추론 전용(SHA-256 대 동봉본), 한 명령 재현(--keep-going)
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
SRC="${1:-$J06_BASE/P2_venv/clone}"
PYX="${PYX:-$PY}"
P="$J06_BASE/P5_package"; rm -rf "$P"; mkdir -p "$P/logs" "$P/x"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_P5_predict_package.log"; : > "$SUMMARY"
echo "P5 시작 $(date '+%F %T') 원천=$SRC 파이썬=$PYX" | tee -a "$SUMMARY"
cd "$SRC"
for s in A B; do
  step P5a_predict_split_$s env OMP_NUM_THREADS=1 "$PYX" yejun/press_guard/predict.py --split $s --out "$P/x/predict_split_$s.csv"; tail_to_summary P5a_predict_split_$s 2
done
"$PY" - "$SRC" "$P/x" "$REPO" "$COMMIT" >> "$SUMMARY" <<'PYEOF'
import hashlib, json, subprocess, sys
from pathlib import Path
src, x, repo, commit = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest() if Path(p).is_file() else None
digest = json.loads(subprocess.run(["git", "-C", repo, "show", f"{commit}:yejun/press_guard/outputs/expected/predictions_digest.json"], capture_output=True, check=True).stdout)
man = json.loads(subprocess.run(["git", "-C", repo, "show", f"{commit}:yejun/press_guard/outputs/manifest.json"], capture_output=True, check=True).stdout)
print("---- P5a 추론 전용 SHA-256 대조")
for s in "AB":
    name = f"test_predictions_{s}.csv"
    a, b = sha(x / f"predict_split_{s}.csv"), sha(src / "yejun/press_guard/outputs" / name)
    print(f"  {s}: predict={a[:16]} 학습실행={b[:16]} 커밋 동결요약={digest[name]['sha256'][:16]} 커밋 manifest={man['outputs'][name][:16]} → "
          f"{'모두 같음' if a == b == digest[name]['sha256'] == man['outputs'][name] else '다름'} ({digest[name]['rows']}행)")
PYEOF
step P5b_package_manifest env OMP_NUM_THREADS=1 "$PYX" yejun/press_guard/tools/package_manifest.py --out "$P/package_list.csv"; tail_to_summary P5b_package_manifest 14
step P5b2_package_manifest_zip env OMP_NUM_THREADS=1 "$PYX" yejun/press_guard/tools/package_manifest.py --zip; tail_to_summary P5b2_package_manifest_zip 2
# 목록대로 복사(목록의 경로는 yejun/ 기준 상대 경로)
"$PY" - "$SRC/yejun" "$P/pkg" "$P/package_list.csv" >> "$SUMMARY" <<'PYEOF'
import shutil, sys
from pathlib import Path
import pandas as pd
src, dst, lst = Path(sys.argv[1]), Path(sys.argv[2]), pd.read_csv(sys.argv[3])
for rel in lst.path:
    (dst / rel).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / rel, dst / rel)
print(f"---- P5 목록 복사: {len(lst)}개 파일 → pkg/ (그룹별 {lst.group.value_counts().to_dict()})")
top = sorted({r.split('/')[0] for r in lst.path})
print(f"     복사본 최상위: {top}; analysis 아래: {sorted({r.split('/')[1] for r in lst.path if r.startswith('analysis/')})}")
PYEOF
cd "$P/pkg"
# c1) README 빠른 시작 문자 그대로(yejun/ 접두)
step P5c1_readme_literal env OMP_NUM_THREADS=1 "$PYX" yejun/press_guard/reproduce.py; tail_to_summary P5c1_readme_literal 2
# c2) 추론 전용: 동봉 모델로 테스트 예측 파일을 다시 만들고 동봉본과 대조
for s in A B; do
  step P5c2_pkg_predict_$s env OMP_NUM_THREADS=1 "$PYX" press_guard/predict.py --split $s --out "$P/x/pkg_predict_$s.csv"; tail_to_summary P5c2_pkg_predict_$s 2
  echo "     SHA-256 동봉본 $(shasum -a 256 press_guard/outputs/test_predictions_$s.csv | cut -c1-16) / 재생성 $(shasum -a 256 "$P/x/pkg_predict_$s.csv" | cut -c1-16)" >> "$SUMMARY"
done
# c3) 한 명령 재현(경로만 복사본 구조에 맞춤), 실패해도 끝까지
step P5c3_pkg_reproduce env OMP_NUM_THREADS=1 "$PYX" press_guard/reproduce.py --keep-going; tail_to_summary P5c3_pkg_reproduce 25
summary_to_log press_guard/outputs/reproduce_summary.json
echo "P5 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
