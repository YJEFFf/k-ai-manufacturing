#!/usr/bin/env bash
# 평가관 06(코드·재현성) 2주기 1회차 공용 함수. 저장소 안에는 이 폴더의 judge06_* 기록만 쓴다.
# 클론·가상환경·실행 산출물은 모두 시스템 임시 폴더($J06_BASE)에 둔다.
REPO="/Volumes/YJSSD/공모전/k-제조데이터"
OUTDIR="$REPO/yejun/analysis/press_rubric_review/cycle2/round1"
J06_BASE="${J06_BASE:-/private/tmp/claude-501/-Volumes-YJSSD-----k------/69347b62-83f2-47fa-8d8d-9aa723b0597a/scratchpad/judge06}"
PY="${PY:-/opt/anaconda3/bin/python}"
SRC_DATA="$REPO/데이터셋/프레스_유압펌프_예지보전/data/3_소성가공_예지보전"
UCI_ZIP="$REPO/yejun/analysis/press_external/data/hydraulic.zip"
mkdir -p "$J06_BASE"

# 새 클론 + 대회 원본 CSV 2개만 복사(학습 상태·행별 예측·LSTM 캐시는 복사하지 않는다)
make_clone() {
  local dest="$1"
  rm -rf "$dest"
  git clone -q "$REPO" "$dest"
  mkdir -p "$dest/yejun/press_submission/data/3_소성가공_예지보전"
  cp "$SRC_DATA/press_data_normal.csv" "$SRC_DATA/outlier_data.csv" "$dest/yejun/press_submission/data/3_소성가공_예지보전/"
}

# step <이름> <명령...> : 종료 코드·경과 시간·최대 메모리를 요약 파일($SUMMARY)에 한 줄로 남긴다. 표준출력/오류는 $LOGS/<이름>.out/.err
step() {
  local name="$1"; shift
  local t0 t1 rc rss
  t0=$(date +%s)
  /usr/bin/time -l "$@" > "$LOGS/$name.out" 2> "$LOGS/$name.err"
  rc=$?
  t1=$(date +%s)
  rss=$(grep "maximum resident set size" "$LOGS/$name.err" | awk '{printf "%.0f", $1/1048576}')
  echo "STEP $name rc=$rc wall=$((t1-t0))s maxrss_mb=${rss:-?}" | tee -a "$SUMMARY"
  return $rc
}

# 마지막 몇 줄을 요약에 붙인다(/usr/bin/time 측정 줄 제외)
tail_to_summary() {
  local name="$1" n="${2:-12}" err
  echo "---- $name stdout(끝 ${n}줄)" >> "$SUMMARY"
  tail -n "$n" "$LOGS/$name.out" >> "$SUMMARY"
  err=$(grep -v -E '^[[:space:]]*[0-9.]+[[:space:]]+real[[:space:]]|^[[:space:]]*[0-9]+[[:space:]]+[a-z][a-z ()-]*$' "$LOGS/$name.err" | tail -n "$n")
  if [[ -n "$err" ]]; then echo "---- $name stderr(끝 ${n}줄, 시간 측정 제외)" >> "$SUMMARY"; echo "$err" >> "$SUMMARY"; fi
}
