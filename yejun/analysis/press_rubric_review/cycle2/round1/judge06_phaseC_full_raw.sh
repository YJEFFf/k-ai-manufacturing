#!/usr/bin/env bash
# Phase C — 원본 CSV만으로 전체 재생성. 커밋된 중간 산출물·LSTM 캐시·학습 상태 없이
# v1 전체(1~5단계, LSTM 처음부터) → 후보 비교(press_advance) → v2 학습·분석·audit·verify → 진단 보강 표 → 보완 실험 verify·재실행(E1~E3) → 테스트 → 추론 전용.
# 실패해도 다음 단계를 계속 실행해 전체 상태를 기록한다.
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/C_full_raw"; rm -rf "$P"; mkdir -p "$P/logs"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_phaseC_full_raw.log"; : > "$SUMMARY"
echo "Phase C 시작 $(date '+%F %T') HEAD=$(git -C "$REPO" rev-parse HEAD) python=$("$PY" -c 'import sys;print(sys.version.split()[0])') 임시=$P" | tee -a "$SUMMARY"
C="$P/clone"; make_clone "$C"; Y="$C/yejun"
mkdir -p "$Y/analysis/press_external/data"; cp "$UCI_ZIP" "$Y/analysis/press_external/data/"
# 비교용: 실행 전 커밋 상태 보관
mkdir -p "$P/committed"
cp -R "$Y/analysis/press_advance" "$P/committed/press_advance"
cp -R "$Y/analysis/press_evidence" "$P/committed/press_evidence"
cp -R "$Y/analysis/press_supplement" "$P/committed/press_supplement"
cp -R "$Y/press_guard/outputs" "$P/committed/press_guard_outputs"
cp -R "$Y/press_submission/outputs" "$P/committed/press_submission_outputs"
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1

# 1) v1 전체: 커밋 산출물·기대값을 치우고 처음부터(LSTM 캐시 없음 → 처음부터 학습)
mv "$Y/press_submission/outputs/expected" "$P/v1_expected"
rm -rf "$Y/press_submission/outputs" "$Y/press_submission/artifacts"; mkdir -p "$Y/press_submission/outputs"
cd "$Y/press_submission"
step C01_v1_run_all_full "$PY" run_all.py --root . --out outputs; tail_to_summary C01_v1_run_all_full 8
cp -R "$P/v1_expected" "$Y/press_submission/outputs/expected"
step C02_v1_verify "$PY" verify.py --out outputs; tail_to_summary C02_v1_verify 6

# 2) v2 후보 고정 비교(press_advance) 재실행
cd "$C"
step C03_advance "$PY" yejun/analysis/press_advance/run_experiment.py; tail_to_summary C03_advance 4

# 3) v2: 커밋 산출물·기대값을 치우고 학습→분석→audit, 기대값을 되돌려 verify
mv "$Y/press_guard/outputs/expected" "$P/v2_expected"
rm -rf "$Y/press_guard/outputs" "$Y/press_guard/artifacts"; mkdir -p "$Y/press_guard/outputs"
step C04_v2_train "$PY" yejun/press_guard/train.py --rolling; tail_to_summary C04_v2_train 4
step C05_v2_analyze "$PY" yejun/press_guard/analyze.py; tail_to_summary C05_v2_analyze 4
step C06_v2_audit "$PY" yejun/press_guard/audit.py; tail_to_summary C06_v2_audit 3
cp -R "$P/v2_expected" "$Y/press_guard/outputs/expected"
step C07_v2_verify "$PY" yejun/press_guard/verify.py; tail_to_summary C07_v2_verify 3

# 4) 진단 보강 표
step C08_evidence "$PY" yejun/analysis/press_evidence/build_tables.py; tail_to_summary C08_evidence 3

# 5) 보완 실험: 커밋 결과 무결성·기대값(재학습 모델 해시 포함) → 새 임시 폴더(캐시 없음)에서 E1~E3 재실행
cd "$Y/analysis/press_supplement"
step C09_supp_verify "$PY" verify.py; tail_to_summary C09_supp_verify 6
mkdir -p "$P/tmpdir_rerun"
step C10_supp_rerun env TMPDIR="$P/tmpdir_rerun/" "$PY" verify.py --rerun E1,E2,E3; tail_to_summary C10_supp_rerun 8
step C11_supp_figures "$PY" figures.py; tail_to_summary C11_supp_figures 3

# 6) 테스트(전체 실행 뒤 클론 안)
cd "$Y"
step C12_pytest_v2 "$PY" -m pytest -q -p no:cacheprovider press_guard/test_guard.py press_guard/test_serve.py press_guard/test_analyze.py press_guard/test_review_regressions.py press_guard/test_recalibrate.py --basetemp "$P/pt_v2"; tail_to_summary C12_pytest_v2 3
step C13_pytest_v1 "$PY" -m pytest -q -p no:cacheprovider press_submission/tests --basetemp "$P/pt_v1"; tail_to_summary C13_pytest_v1 3
step C14_pytest_supp "$PY" -m pytest -q -p no:cacheprovider analysis/press_supplement/test_contract.py --basetemp "$P/pt_supp"; tail_to_summary C14_pytest_supp 3
step C15_node_web node press_guard/test_web.cjs; tail_to_summary C15_node_web 2

# 7) 추론 전용(README 예시): 새로 학습한 저장 모델로 이상 CSV 순차 추론
step C16_predict_cli "$PY" press_guard/predict.py --model press_guard/artifacts/guard_A.json --input press_submission/data/3_소성가공_예지보전/outlier_data.csv --out "$P/predict_cli_A_abnormal.csv" --cases "$P/predict_cli_A_cases.csv" --chunk 128; tail_to_summary C16_predict_cli 2
echo "Phase C 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
