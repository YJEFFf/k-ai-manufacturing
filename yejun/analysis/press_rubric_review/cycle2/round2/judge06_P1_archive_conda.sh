#!/usr/bin/env bash
# P1 — git 없는 사본(git archive = ZIP을 푼 상태) + environment.yml로 만든 빈 conda 환경 + README 빠른 시작 두 줄 그대로.
# conda·pip 내려받기 캐시도 임시 폴더에 새로 잡는다(빈 환경에서 시작).
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/P1_archive"; rm -rf "$P"; mkdir -p "$P/logs" "$P/conda_pkgs" "$P/pip_cache" "$P/tmp"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_P1_archive_conda.log"; : > "$SUMMARY"
echo "P1 시작 $(date '+%F %T') 기준=$COMMIT" | tee -a "$SUMMARY"
make_archive "$P/copy"; cd "$P/copy"
echo "git 없는 사본: .git $( [[ -e .git ]] && echo 있음 || echo 없음 ), 원본 CSV $(ls yejun/press_submission/data 2>/dev/null | wc -l | tr -d ' ')개, git rev-parse: $(git rev-parse --is-inside-work-tree 2>&1 | head -1)" | tee -a "$SUMMARY"
export CONDA_PKGS_DIRS="$P/conda_pkgs" PIP_CACHE_DIR="$P/pip_cache" TMPDIR="$P/tmp"
# README 빠른 시작 1행: conda env create -f yejun/press_guard/environment.yml (이름 대신 임시 경로 -p)
# 내려받기 중 네트워크 끊김(IncompleteRead)은 팀 결함이 아니라 재시도한다(최대 3회, 매번 빈 환경에서)
for try in 1 2 3; do
  rm -rf "$P/env"
  step P1a_conda_env_create_try$try /opt/anaconda3/bin/conda env create -q -f yejun/press_guard/environment.yml -p "$P/env" && { tail_to_summary P1a_conda_env_create_try$try 6; break; }
  tail_to_summary P1a_conda_env_create_try$try 4
done
EPY="$P/env/bin/python"
{ echo "---- 환경: $("$EPY" --version 2>&1)"; "$EPY" -m pip freeze 2>&1; "$EPY" -c "import importlib.util as u; print('torch 설치 여부:', u.find_spec('torch') is not None)"; } >> "$SUMMARY"
# README 빠른 시작 2행 그대로(python = 활성화한 환경의 python)
step P1b_reproduce "$EPY" yejun/press_guard/reproduce.py --data "$ORG_ZIP"; tail_to_summary P1b_reproduce 20
summary_to_log yejun/press_guard/outputs/reproduce_summary.json
echo "P1 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
