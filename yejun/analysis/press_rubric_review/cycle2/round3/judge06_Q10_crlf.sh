#!/usr/bin/env bash
# Q10 — Windows용 Git 기본값(core.autocrlf=true)으로 받은 클론 모의(R2-07 완료 기준).
#  a) 작업 트리 줄바꿈(git ls-files --eol), git status, 커밋된 v2 기대값 자체 무결성(verify.expected_integrity)
#  b) 커밋 상태 계약 검사: 원본은 주최 측 ZIP에서 배치(runtime.install_data), 저장 모델 4개는 저장소 작업 트리의 Git 제외 파일을
#     읽기 전용으로 복사(커밋 manifest 해시와 같음을 먼저 확인). 4개 분석 패키지 계약 + 보완 실험 verify
#  c) (인자 --reproduce일 때) 같은 클론에서 한 명령 재현(--data ZIP)
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
MODE="${1:-}"
P="$J06_BASE/Q10_crlf"; mkdir -p "$P/logs"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_Q10_crlf.log"
if [[ "$MODE" != "--reproduce" ]]; then
  : > "$SUMMARY"
  echo "Q10 시작 $(date '+%F %T') 기준=$COMMIT" | tee -a "$SUMMARY"
  rm -rf "$P/clone"; git -c core.autocrlf=true clone -q "$REPO" "$P/clone"; cd "$P/clone"
  git config core.autocrlf true; git -c advice.detachedHead=false checkout -q "$COMMIT"
  echo "autocrlf=$(git config core.autocrlf) HEAD=$(git rev-parse --short HEAD) / .gitattributes: $(head -2 yejun/.gitattributes | tail -1)" | tee -a "$SUMMARY"
  echo "작업 트리 CRLF 파일 수(yejun): $(git ls-files --eol yejun | awk '$2 ~ /crlf/' | wc -l | tr -d ' ') / 전체 $(git ls-files yejun | wc -l | tr -d ' ') · git status 변경 $(git status --short | wc -l | tr -d ' ')" | tee -a "$SUMMARY"
  echo "예: $(file yejun/analysis/press_selection/unified_comparison.csv | sed 's#.*: ##') / $(file yejun/press_guard/outputs/expected/metrics.csv | sed 's#.*: ##') / $(file yejun/press_guard/model.py | sed 's#.*: ##')" | tee -a "$SUMMARY"
  step Q10a_v2_expected_integrity env OMP_NUM_THREADS=1 "$PY" -c "import sys; sys.path.insert(0,'yejun/press_guard'); from pathlib import Path; import verify; b=verify.expected_integrity(Path('yejun/press_guard/outputs/expected')); print(len(b),'건', b[:3])"; tail_to_summary Q10a_v2_expected_integrity 3
  # 선행 파일 배치(원본 = 주최 측 ZIP, 저장 모델 = 커밋 manifest 해시와 같은 저장소 사본)
  step Q10b0_place_prereq env OMP_NUM_THREADS=1 "$PY" - "$ORG_ZIP" "$REPO" "$COMMIT" <<'PYEOF'
import hashlib, json, shutil, subprocess, sys
from pathlib import Path
sys.path.insert(0, "yejun/press_guard")
import runtime
from model import D
zip_path, repo, commit = sys.argv[1:4]
print(runtime.install_data(zip_path, D.PACKAGE_DIR, D.FILES, D.EXPECTED_SHA256, D.DATA_SUBDIR))
man = json.loads(subprocess.run(["git", "-C", repo, "show", f"{commit}:yejun/press_guard/outputs/manifest.json"], capture_output=True, check=True).stdout)
dst = Path("yejun/press_guard/artifacts"); dst.mkdir(parents=True, exist_ok=True)
for n, h in man["artifacts"].items():
    src = Path(repo) / "yejun/press_guard/artifacts" / n
    assert hashlib.sha256(src.read_bytes()).hexdigest() == h, n
    shutil.copy2(src, dst / n)
print("저장 모델 복사(커밋 manifest 해시 일치):", sorted(man["artifacts"]))
PYEOF
  tail_to_summary Q10b0_place_prereq 3
  for pkg in press_evidence press_supervised press_advance press_selection; do
    step Q10b_contract_$pkg env OMP_NUM_THREADS=1 "$PY" yejun/analysis/package_contract.py --package yejun/analysis/$pkg; tail_to_summary Q10b_contract_$pkg 4
  done
  step Q10b_supplement_verify env OMP_NUM_THREADS=1 "$PY" yejun/analysis/press_supplement/verify.py; tail_to_summary Q10b_supplement_verify 5
  echo "Q10 a·b 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
else
  cd "$P/clone"
  echo "Q10 c 시작 $(date '+%F %T')" | tee -a "$SUMMARY"
  step Q10c_reproduce env OMP_NUM_THREADS=1 "$PY" yejun/press_guard/reproduce.py --data "$ORG_ZIP"; tail_to_summary Q10c_reproduce 20
  summary_to_log yejun/press_guard/outputs/reproduce_summary.json
  bits_to_log "$P/clone"
  echo "재현 뒤 git status 변경 $(git status --short | wc -l | tr -d ' ')개: $(git status --short | head -5 | tr '\n' ' ')" | tee -a "$SUMMARY"
  echo "Q10 c 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
fi
