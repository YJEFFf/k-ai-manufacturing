#!/usr/bin/env bash
# 평가관 06(코드·재현성) 사이클2 2회차 공용 함수. 저장소 안에는 이 폴더의 judge06_* 기록만 쓴다.
# 클론·가상환경·실행 산출물은 모두 시스템 임시 폴더($J06_BASE)에 둔다. git은 읽기(clone·archive·rev-parse)만 한다.
REPO="/Volumes/YJSSD/공모전/k-제조데이터"
OUTDIR="$REPO/yejun/analysis/press_rubric_review/cycle2/round2"
J06_BASE="${J06_BASE:-/private/tmp/claude-501/-Volumes-YJSSD-----k------/69347b62-83f2-47fa-8d8d-9aa723b0597a/scratchpad/judge06r2}"
COMMIT="${COMMIT:-f5679ca}"
PY="${PY:-/opt/anaconda3/bin/python}"
ORG_ZIP="$REPO/데이터셋/프레스_유압펌프_예지보전/Dataset_소성가공 예지보전 AI 데이터셋.zip"   # 주최 측 원본 ZIP(data/*.csv)
UCI_ZIP="$REPO/yejun/analysis/press_external/data/hydraulic.zip"                              # Git 제외 외부 자료(보완 E2)
mkdir -p "$J06_BASE"
export PYTHONDONTWRITEBYTECODE=1

# 새 git 클론(기준 커밋 고정). 원본 CSV·학습 상태·행별 예측·LSTM 캐시는 복사하지 않는다(원본은 --data ZIP으로 준다).
make_clone() {
  local dest="$1"
  rm -rf "$dest"
  git clone -q "$REPO" "$dest"
  git -C "$dest" -c advice.detachedHead=false checkout -q "$COMMIT"
}

# git 없는 사본(git archive = ZIP을 푼 상태와 같다)
make_archive() {
  local dest="$1"
  rm -rf "$dest"; mkdir -p "$dest"
  git -C "$REPO" archive "$COMMIT" yejun | tar -x -C "$dest"
}

# step <이름> <명령...>: 종료 코드·경과 시간·최대 메모리·부하 평균을 $SUMMARY에 한 줄로. 출력은 $LOGS/<이름>.out/.err
step() {
  local name="$1"; shift
  local t0 t1 rc rss load
  load=$(sysctl -n vm.loadavg | awk '{print $2}')
  t0=$(date +%s)
  /usr/bin/time -l "$@" > "$LOGS/$name.out" 2> "$LOGS/$name.err"
  rc=$?
  t1=$(date +%s)
  rss=$(grep "maximum resident set size" "$LOGS/$name.err" | awk '{printf "%.0f", $1/1048576}')
  echo "STEP $name rc=$rc wall=$((t1-t0))s maxrss_mb=${rss:-?} load_start=$load load_end=$(sysctl -n vm.loadavg | awk '{print $2}')" | tee -a "$SUMMARY"
  return $rc
}

# 표준출력·오류 끝 몇 줄을 요약에 붙인다(/usr/bin/time 측정 줄 제외)
tail_to_summary() {
  local name="$1" n="${2:-12}" err
  echo "---- $name stdout(끝 ${n}줄)" >> "$SUMMARY"
  tail -n "$n" "$LOGS/$name.out" >> "$SUMMARY"
  err=$(grep -v -E '^[[:space:]]*[0-9.]+[[:space:]]+real[[:space:]]|^[[:space:]]*[0-9]+[[:space:]]+[a-z][a-z ()-]*$' "$LOGS/$name.err" | tail -n "$n")
  if [[ -n "$err" ]]; then echo "---- $name stderr(끝 ${n}줄, 시간 측정 제외)" >> "$SUMMARY"; echo "$err" >> "$SUMMARY"; fi
}

# reproduce.py 단계 요약(reproduce_summary.json)을 한 줄씩 요약에 붙인다
summary_to_log() {
  local json="$1"
  "$PY" - "$json" >> "$SUMMARY" <<'PYEOF'
import json, sys
s = json.load(open(sys.argv[1], encoding="utf-8"))
print(f"== reproduce_summary: mode={s['mode']} python={s['python']} {s['passed']}/{s['planned']} 통과 · 실패 {s['failed']} · {s['total_seconds']}초")
for i, r in enumerate(s["steps"], 1):
    print(f"  [{i:02d}] rc={r['returncode']} {r['seconds']:>7}s  {r['step']}  | {r['last_line'][:110]}")
PYEOF
}
