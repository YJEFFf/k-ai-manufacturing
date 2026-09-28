#!/usr/bin/env bash
# Q1 — git 없는 사본(git archive = ZIP을 푼 상태) + environment.yml로 만든 빈 conda 환경 + 대회 원본 CSV 2개만 표준 위치에 넣고
#      README 한 명령(python yejun/press_guard/reproduce.py, --data 없음)을 그대로 실행. conda·pip 내려받기 캐시도 임시 폴더에 새로 잡는다.
#      끝난 뒤 같은 사본(git 없음)에서 package_manifest.py 목록을 계산해 git 클론 기준 목록(Q5)과 비교할 수 있게 남긴다.
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/Q1_archive"; rm -rf "$P"; mkdir -p "$P/logs" "$P/conda_pkgs" "$P/pip_cache" "$P/tmp"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_Q1_archive_conda.log"; : > "$SUMMARY"
echo "Q1 시작 $(date '+%F %T') 기준=$COMMIT" | tee -a "$SUMMARY"
make_archive "$P/copy"; cd "$P/copy"
mkdir -p yejun/press_submission/data/3_소성가공_예지보전
cp "$RAW_DIR/press_data_normal.csv" "$RAW_DIR/outlier_data.csv" yejun/press_submission/data/3_소성가공_예지보전/
echo "git 없는 사본: .git $( [[ -e .git ]] && echo 있음 || echo 없음 ), git rev-parse: $(git rev-parse --is-inside-work-tree 2>&1 | head -1)" | tee -a "$SUMMARY"
echo "넣은 원본: $(ls yejun/press_submission/data/3_소성가공_예지보전 | tr '\n' ' ') / press_guard/artifacts $(ls yejun/press_guard/artifacts 2>/dev/null | wc -l | tr -d ' ')개 / v1 artifacts $(ls yejun/press_submission/artifacts 2>/dev/null | wc -l | tr -d ' ')개" | tee -a "$SUMMARY"
export CONDA_PKGS_DIRS="$P/conda_pkgs" PIP_CACHE_DIR="$P/pip_cache" TMPDIR="$P/tmp"
# README 빠른 시작 1행: conda env create -f yejun/press_guard/environment.yml (이름 대신 임시 경로 -p). 네트워크 끊김은 재시도(최대 3회)
for try in 1 2 3; do
  rm -rf "$P/env"
  step Q1a_conda_env_create_try$try /opt/anaconda3/bin/conda env create -q -f yejun/press_guard/environment.yml -p "$P/env" && { tail_to_summary Q1a_conda_env_create_try$try 6; break; }
  tail_to_summary Q1a_conda_env_create_try$try 4
done
EPY="$P/env/bin/python"
{ echo "---- 환경: $("$EPY" --version 2>&1)"; "$EPY" -m pip freeze 2>&1 | tr '\n' ' '; echo; "$EPY" -m pip check 2>&1 | tail -3; "$EPY" -c "import importlib.util as u; print('torch 설치 여부:', u.find_spec('torch') is not None)"; } >> "$SUMMARY"
# README 빠른 시작 3행에서 --data만 뺀 형태(README:25 "원본 두 CSV가 이미 있으면 --data는 필요 없다")
step Q1b_reproduce "$EPY" yejun/press_guard/reproduce.py; tail_to_summary Q1b_reproduce 20
summary_to_log yejun/press_guard/outputs/reproduce_summary.json
bits_to_log "$P/copy"
# git 없는 사본에서 목록 도구(폴더를 훑는 경로)
step Q1c_package_manifest_nogit "$EPY" yejun/press_guard/tools/package_manifest.py --out "$P/package_list_nogit.csv"; tail_to_summary Q1c_package_manifest_nogit 16
echo "Q1 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
