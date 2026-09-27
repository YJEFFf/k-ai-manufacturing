#!/usr/bin/env bash
# Phase E — 이식성 모의(다른 OS 자체는 이 기기에서 확인할 수 없어, 원인이 되는 조건만 재현한다).
#  E-a 한국어 Windows 기본 인코딩(cp949) 모의: macOS에서 LC_ALL=ko_KR.CP949 → 파이썬 기본 텍스트 인코딩이 CP949가 된다.
#  E-b Windows에 없는 표준 모듈 resource 모의: sitecustomize로 import를 막는다.
#  E-c OMP_NUM_THREADS 미설정(다중 스레드 BLAS 기본값)에서 v2 전체 경로와 동결값 일치 여부.
#  E-d 주최 측 데이터 ZIP을 그대로 푼 폴더를 --root로 줄 때.
#  E-e 새 분석 패키지(press_supervised, dcd300a) 재실행 결정성.
# Phase B의 클론(v2 전체 실행 완료 상태)을 읽어 쓰되, 결과는 모두 별도 임시 폴더에 쓴다.
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/E_portability"; rm -rf "$P"; mkdir -p "$P/logs"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_phaseE_portability.log"; : > "$SUMMARY"
B="$J06_BASE/B_readme/clone"; BY="$B/yejun"
[[ -f "$BY/press_guard/outputs/audit.json" ]] || { echo "Phase B 클론이 없다" | tee -a "$SUMMARY"; exit 2; }
echo "Phase E 시작 $(date '+%F %T') HEAD=$(git -C "$REPO" rev-parse HEAD) 클론=$(git -C "$B" rev-parse --short HEAD)" | tee -a "$SUMMARY"
export PYTHONDONTWRITEBYTECODE=1
CP=(env LC_ALL=ko_KR.CP949 LANG=ko_KR.CP949 OMP_NUM_THREADS=1)
"${CP[@]}" "$PY" -c "import locale,sys; print('E-a 기본 인코딩:', locale.getpreferredencoding(False), 'utf8_mode', sys.flags.utf8_mode)" >> "$SUMMARY"

# ---- E-a cp949
cd "$B"
step Ea01_cp949_v2_verify "${CP[@]}" "$PY" yejun/press_guard/verify.py; tail_to_summary Ea01_cp949_v2_verify 8
cp -R "$BY/press_guard/outputs" "$P/cp949_out"; cp -R "$BY/press_guard/artifacts" "$P/cp949_art"
step Ea02_cp949_v2_analyze "${CP[@]}" "$PY" yejun/press_guard/analyze.py --out "$P/cp949_out" --artifacts "$P/cp949_art"; tail_to_summary Ea02_cp949_v2_analyze 4
step Ea03_cp949_v2_train "${CP[@]}" "$PY" yejun/press_guard/train.py --out "$P/cp949_train_out" --artifacts "$P/cp949_train_art"; tail_to_summary Ea03_cp949_v2_train 2
step Ea04_cp949_supp_verify "${CP[@]}" "$PY" yejun/analysis/press_supplement/verify.py --experiments E3; tail_to_summary Ea04_cp949_supp_verify 4
step Ea05_cp949_serve_import "${CP[@]}" "$PY" -c "import sys; sys.path.insert(0,'yejun/press_guard'); import serve, json; from pathlib import Path; print(json.loads(Path('yejun/press_guard/outputs/audit.json').read_text())['all_ok'])"; tail_to_summary Ea05_cp949_serve_import 3
step Ea06_cp949_utf8mode_v2_verify "${CP[@]}" PYTHONUTF8=1 "$PY" yejun/press_guard/verify.py; tail_to_summary Ea06_cp949_utf8mode_v2_verify 2
step Ea07_cp949_v1_step2 "${CP[@]}" "$PY" yejun/press_submission/run_all.py --root yejun/press_submission --out "$P/cp949_v1_out" --artifacts "$P/cp949_v1_art" --steps 2 --no-baselines; tail_to_summary Ea07_cp949_v1_step2 2
# Ea05는 serve.py:93과 같은 읽기를 흉내 낸 한 줄이다. 웹 콘솔 /api/overview 처리 함수를 직접 부르는 확인(Ea08·Ea09)은 첫 실행 뒤 추가해 같은 클론에서 따로 돌렸다.
{ echo "---- Ea08 웹 콘솔 Console().overview() 직접 호출(CP949 모의)"
  (cd "$BY/press_guard" && "${CP[@]}" "$PY" -c "from serve import Console; o = Console().overview(); print('overview ok', o['audit'].get('all_ok'))" 2>&1 | tail -4 | iconv -f CP949 -t UTF-8 2>/dev/null || true)
  echo "---- Ea09 같은 호출(PYTHONUTF8=1)"
  (cd "$BY/press_guard" && "${CP[@]}" PYTHONUTF8=1 "$PY" -c "from serve import Console; o = Console().overview(); print('overview ok', o['audit'].get('all_ok'))" 2>&1 | tail -2); } >> "$SUMMARY"

# ---- E-b resource 없음(Windows) 모의
mkdir -p "$P/nores"; printf 'import sys\nsys.modules["resource"] = None\n' > "$P/nores/sitecustomize.py"
step Eb01_nores_libs env PYTHONPATH="$P/nores" OMP_NUM_THREADS=1 "$PY" -c "import numpy, pandas, scipy, sklearn, matplotlib; import importlib; print('libs ok'); importlib.import_module('resource')"; tail_to_summary Eb01_nores_libs 3
step Eb02_nores_v2_train env PYTHONPATH="$P/nores" OMP_NUM_THREADS=1 "$PY" yejun/press_guard/train.py --out "$P/nores_out" --artifacts "$P/nores_art"; tail_to_summary Eb02_nores_v2_train 4
{ echo "---- Eb02 산출물(학습은 끝났는데 manifest가 남는가)"; ls "$P/nores_out" 2>&1; ls "$P/nores_art" 2>&1; } >> "$SUMMARY"

# ---- E-c OMP_NUM_THREADS 미설정
C="$P/clone_nomp"; make_clone "$C"; cd "$C"
NOMP=(env -u OMP_NUM_THREADS -u OPENBLAS_NUM_THREADS -u MKL_NUM_THREADS)
"${NOMP[@]}" "$PY" -c "import json,threadpoolctl,numpy; print('E-c BLAS:', json.dumps([{k:i.get(k) for k in ('internal_api','version','num_threads')} for i in threadpoolctl.threadpool_info()]))" >> "$SUMMARY"
mv yejun/press_guard/outputs/expected "$P/nomp_expected"; rm -rf yejun/press_guard/outputs yejun/press_guard/artifacts; mkdir -p yejun/press_guard/outputs
step Ec01_nomp_v1_step2 "${NOMP[@]}" "$PY" yejun/press_submission/run_all.py --root yejun/press_submission --out yejun/press_submission/outputs --steps 2 --no-baselines; tail_to_summary Ec01_nomp_v1_step2 1
step Ec02_nomp_train "${NOMP[@]}" "$PY" yejun/press_guard/train.py --rolling; tail_to_summary Ec02_nomp_train 1
step Ec03_nomp_analyze "${NOMP[@]}" "$PY" yejun/press_guard/analyze.py; tail_to_summary Ec03_nomp_analyze 1
step Ec04_nomp_audit "${NOMP[@]}" "$PY" yejun/press_guard/audit.py; tail_to_summary Ec04_nomp_audit 1
cp -R "$P/nomp_expected" yejun/press_guard/outputs/expected
step Ec05_nomp_verify "${NOMP[@]}" "$PY" yejun/press_guard/verify.py; tail_to_summary Ec05_nomp_verify 2

# ---- E-d 주최 측 ZIP을 그대로 푼 폴더
mkdir -p "$P/official_unzip"; (cd "$P/official_unzip" && unzip -q "$REPO/데이터셋/프레스_유압펌프_예지보전/Dataset_소성가공 예지보전 AI 데이터셋.zip")
{ echo "---- E-d 주최 측 ZIP 구조"; find "$P/official_unzip" -type f | sed "s#$P/##"; } >> "$SUMMARY"
cd "$B"
step Ed01_official_root_train env OMP_NUM_THREADS=1 "$PY" yejun/press_guard/train.py --root "$P/official_unzip" --out "$P/official_out" --artifacts "$P/official_art"; tail_to_summary Ed01_official_root_train 2

# ---- E-e press_supervised 재실행 결정성(커밋된 CSV와 비교는 judge06_check.py)
step Ee01_supervised_rerun env OMP_NUM_THREADS=1 "$PY" yejun/analysis/press_supervised/run.py --out "$P/supervised_out"; tail_to_summary Ee01_supervised_rerun 3
echo "Phase E 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
