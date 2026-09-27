#!/usr/bin/env bash
# Phase B — 평가자가 press_guard/README.md만 보고 따라 하는 경로.
# 새 클론 + 원본 CSV 2개(README 안내 위치). README '최종 모델 패키지' 명령을 순서대로 실행한 뒤,
# 막히면 clean_repro.sh가 몰래 하는 선행 단계(v1 2단계)를 보충해 다시 실행한다.
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/B_readme"; rm -rf "$P"; mkdir -p "$P/logs"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_phaseB_readme_path.log"; : > "$SUMMARY"
echo "Phase B 시작 $(date '+%F %T') HEAD=$(git -C "$REPO" rev-parse HEAD)" | tee -a "$SUMMARY"
C="$P/clone"; make_clone "$C"
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
cd "$C"    # README: 저장소 루트에서 실행
# (1) press_guard/README.md '최종 모델 패키지로서의 산출물' 블록 그대로
step B01_train "$PY" yejun/press_guard/train.py --rolling; tail_to_summary B01_train 3
step B02_analyze "$PY" yejun/press_guard/analyze.py; tail_to_summary B02_analyze 4
step B03_audit "$PY" yejun/press_guard/audit.py; tail_to_summary B03_audit 4
step B04_verify "$PY" yejun/press_guard/verify.py; tail_to_summary B04_verify 6
# (2) 선행 단계 보충: clean_repro.sh 22행과 같은 v1 2단계(행별 예측 재생성)
step B05_v1_step2 "$PY" yejun/press_submission/run_all.py --root yejun/press_submission --out yejun/press_submission/outputs --steps 2 --no-baselines; tail_to_summary B05_v1_step2 3
step B06_analyze "$PY" yejun/press_guard/analyze.py; tail_to_summary B06_analyze 3
step B07_audit "$PY" yejun/press_guard/audit.py; tail_to_summary B07_audit 2
step B08_verify "$PY" yejun/press_guard/verify.py; tail_to_summary B08_verify 3
# (3) README '실행' 블록의 추론 예시(저장 모델만 사용)
step B09_predict "$PY" yejun/press_guard/predict.py --model yejun/press_guard/artifacts/guard_A.json --input yejun/press_submission/data/3_소성가공_예지보전/outlier_data.csv --out "$P/press_predictions.csv" --cases "$P/press_cases.csv" --chunk 128; tail_to_summary B09_predict 2
# (4) 테스트 데이터 예측 파일 존재·행 수
{ echo "---- 행별 예측 파일(train.py 산출, Git 제외)"; for f in "$C"/yejun/press_guard/outputs/predictions_*.csv; do printf '%s rows=%s\n' "$(basename "$f")" "$(($(wc -l < "$f")-1))"; done; } >> "$SUMMARY"
echo "Phase B 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
