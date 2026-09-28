#!/usr/bin/env bash
# Q4·Q5 — 추론 전용(predict.py --split)과 제출 목록(package_manifest.py) 검사(R2-01 완료 기준). 인자: 한 명령 재현을 마친 클론 루트(기본 Q2).
#  Q4) 끝난 실행에서 predict.py --split A/B → 학습 실행의 test_predictions, 커밋 동결 요약(predictions_digest.json), 커밋 manifest와 SHA-256 대조
#  Q5a) package_manifest.py 목록·블라인드 검사(팀 도구 그대로)
#  Q5b) package_manifest.py --copy-test <빈 임시 폴더> (팀 도구가 목록만 복사해 reproduce.py 실행)
#  Q5c) 평가관이 목록대로 따로 복사한 사본: 추론 전용 SHA-256(동봉본 대조) → 절대 경로 검사(실행 전) → ZIP을 현재 폴더에 두고
#       README 빠른 시작 3행을 README에서 읽어 zsh로 문자 그대로 실행 + --tests → 절대 경로 검사(실행 후) → 문서 링크 검사
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
SRC="${1:-$J06_BASE/Q2_venv/clone}"
PYX="${PYX:-$J06_BASE/Q2_venv/venv/bin/python}"
P="$J06_BASE/Q5_package"; rm -rf "$P"; mkdir -p "$P/logs" "$P/x"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_Q5_package.log"; : > "$SUMMARY"
echo "Q5 시작 $(date '+%F %T') 원천=$SRC 파이썬=$PYX($("$PYX" --version 2>&1))" | tee -a "$SUMMARY"
cd "$SRC"
for s in A B; do
  step Q4_predict_split_$s env OMP_NUM_THREADS=1 "$PYX" yejun/press_guard/predict.py --split $s --out "$P/x/predict_split_$s.csv"; tail_to_summary Q4_predict_split_$s 2
done
"$PY" - "$SRC" "$P/x" "$REPO" "$COMMIT" >> "$SUMMARY" <<'PYEOF'
import hashlib, json, subprocess, sys
from pathlib import Path
src, x, repo, commit = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest() if Path(p).is_file() else None
digest = json.loads(subprocess.run(["git", "-C", repo, "show", f"{commit}:yejun/press_guard/outputs/expected/predictions_digest.json"], capture_output=True, check=True).stdout)
man = json.loads(subprocess.run(["git", "-C", repo, "show", f"{commit}:yejun/press_guard/outputs/manifest.json"], capture_output=True, check=True).stdout)
print("---- Q4 추론 전용 SHA-256 대조")
for s in "AB":
    name = f"test_predictions_{s}.csv"
    a, b = sha(x / f"predict_split_{s}.csv"), sha(src / "yejun/press_guard/outputs" / name)
    print(f"  {s}: predict={a[:16]} 학습실행={b[:16]} 커밋 동결요약={digest[name]['sha256'][:16]} 커밋 manifest={man['outputs'][name][:16]} → "
          f"{'모두 같음' if a == b == digest[name]['sha256'] == man['outputs'][name] else '다름'} ({digest[name]['rows']}행)")
PYEOF
# Q5a 목록·블라인드 검사
step Q5a_package_manifest env OMP_NUM_THREADS=1 "$PYX" yejun/press_guard/tools/package_manifest.py --out "$P/package_list.csv"; tail_to_summary Q5a_package_manifest 16
step Q5a2_zip_refused env OMP_NUM_THREADS=1 "$PYX" yejun/press_guard/tools/package_manifest.py --zip; tail_to_summary Q5a2_zip_refused 2
# Q5b 팀 도구의 복사 시험(빈 임시 폴더)
mkdir -p "$P/copytest"
step Q5b_copy_test env OMP_NUM_THREADS=1 "$PYX" yejun/press_guard/tools/package_manifest.py --copy-test "$P/copytest"; tail_to_summary Q5b_copy_test 24
[[ -f "$P/copytest/yejun/press_guard/outputs/reproduce_summary.json" ]] && summary_to_log "$P/copytest/yejun/press_guard/outputs/reproduce_summary.json"
bits_to_log "$P/copytest"
# Q5c 평가관이 따로 만든 목록 사본(목록의 경로 그대로: yejun/...)
"$PY" - "$SRC" "$P/pkg" "$P/package_list.csv" >> "$SUMMARY" <<'PYEOF'
import shutil, sys
from pathlib import Path
import pandas as pd
src, dst, lst = Path(sys.argv[1]), Path(sys.argv[2]), pd.read_csv(sys.argv[3])
for rel in lst.path:
    (dst / rel).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / rel, dst / rel)
print(f"---- Q5c 목록 복사: {len(lst)}개 파일 → pkg/ (묶음별 {lst.group.value_counts().to_dict()}) · {lst.bytes.sum() / 2**20:.1f} MB")
print(f"     최상위: {sorted({r.split('/')[0] for r in lst.path})}")
PYEOF
cd "$P/pkg"
for s in A B; do
  step Q5c1_pkg_predict_$s env OMP_NUM_THREADS=1 "$PYX" yejun/press_guard/predict.py --split $s --out "$P/x/pkg_predict_$s.csv"; tail_to_summary Q5c1_pkg_predict_$s 2
  echo "     SHA-256 동봉본 $(shasum -a 256 yejun/press_guard/outputs/test_predictions_$s.csv | cut -c1-16) / 목록 사본 재생성 $(shasum -a 256 "$P/x/pkg_predict_$s.csv" | cut -c1-16)" >> "$SUMMARY"
done
( cd "$OUTDIR" && "$PY" judge06_Q7_abs_paths.py pkg_before_run "$P/pkg" ) >> "$SUMMARY" 2>&1
cp "$ORG_ZIP" "./$ZIP_NAME"
LINE=$(sed -n '/^```bash/,/^```/p' yejun/press_guard/README.md | grep -m1 '^python yejun/press_guard/reproduce.py' | sed 's/[[:space:]]*#.*$//')
echo "---- README 빠른 시작 3행(주석 제거): $LINE" >> "$SUMMARY"
step Q5c2_readme_literal_tests env OMP_NUM_THREADS=1 PATH="$(dirname "$PYX"):$PATH" zsh -c "$LINE --tests"; tail_to_summary Q5c2_readme_literal_tests 30
summary_to_log yejun/press_guard/outputs/reproduce_summary.json
bits_to_log "$P/pkg"
( cd "$OUTDIR" && "$PY" judge06_Q7_abs_paths.py pkg_after_run "$P/pkg" ) >> "$SUMMARY" 2>&1
( cd "$OUTDIR" && "$PY" judge06_Q5_docs.py "$P/package_list.csv" "$P/pkg" ) >> "$SUMMARY" 2>&1
echo "Q5 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
