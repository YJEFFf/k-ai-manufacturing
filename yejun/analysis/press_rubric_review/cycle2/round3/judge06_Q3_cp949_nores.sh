#!/usr/bin/env bash
# Q3 — 한국어 Windows 조건 모의: LC_ALL=ko_KR.CP949(PYTHONUTF8 없음) + resource 모듈 차단(sitecustomize) + 새 git 클론.
#  a) README 한 명령(--data ZIP) + --tests (R2-02 완료 기준 23/23, R2-04 단계 로그 한글 보존)
#  b) 같은 조건에서 운영 도구: predict.py --input·--split, simulate.py, monitor.py(README 명령 형태, 한글 파일 이름), recalibrate.py,
#     package_manifest.py, 웹 콘솔 HTTP(/api/overview·/api/analyze 혼합·업로드)
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/Q3_cp949"; rm -rf "$P"; mkdir -p "$P/logs" "$P/nores" "$P/tmp" "$P/x"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_Q3_cp949_nores.log"; : > "$SUMMARY"
printf 'import sys\nsys.modules["resource"] = None\n' > "$P/nores/sitecustomize.py"
unset PYTHONUTF8 PYTHONIOENCODING
W=(env LC_ALL=ko_KR.CP949 LANG=ko_KR.CP949 PYTHONPATH="$P/nores" TMPDIR="$P/tmp")
echo "Q3 시작 $(date '+%F %T') 기준=$COMMIT PY=$PY" | tee -a "$SUMMARY"
"${W[@]}" "$PY" -c "import locale,sys,importlib; print('조건 확인: 기본 인코딩', locale.getpreferredencoding(False), '| utf8_mode', sys.flags.utf8_mode, '| stdout', sys.stdout.encoding)
try:
    importlib.import_module('resource'); print('resource: 있음(차단 실패)')
except ImportError as e:
    print('resource: 차단됨', e)" 2>&1 | tee -a "$SUMMARY"
make_clone "$P/clone"; cd "$P/clone"
# a) 한 명령 + 시험
step Q3a_reproduce_tests "${W[@]}" "$PY" yejun/press_guard/reproduce.py --data "$ORG_ZIP" --tests; tail_to_summary Q3a_reproduce_tests 34
summary_to_log yejun/press_guard/outputs/reproduce_summary.json
bits_to_log "$P/clone"
# b) 운영 도구
PG=yejun/press_guard; RAW=yejun/press_submission/data/3_소성가공_예지보전
cp $RAW/press_data_normal.csv "$P/x/교대.csv"; printf 'time\n2022-07-12 00:30:00\n' > "$P/x/변경기록.csv"
step Q3b1_predict_input "${W[@]}" "$PY" $PG/predict.py --input $RAW/outlier_data.csv --out "$P/x/예측.csv" --cases "$P/x/대기열.csv" --model $PG/artifacts/guard_B.json; tail_to_summary Q3b1_predict_input 3
step Q3b2_predict_splitA "${W[@]}" "$PY" $PG/predict.py --split A --out "$P/x/test_predictions_A.csv"; tail_to_summary Q3b2_predict_splitA 3
echo "     predict --split A SHA-256 $(shasum -a 256 "$P/x/test_predictions_A.csv" | cut -c1-16) / 학습 실행 $(shasum -a 256 $PG/outputs/test_predictions_A.csv | cut -c1-16)" >> "$SUMMARY"
step Q3b3_simulate "${W[@]}" "$PY" $PG/simulate.py --csv $RAW/outlier_data.csv --split B --speed 0 --log "$P/x/sim_alerts.csv"; tail_to_summary Q3b3_simulate 4
step Q3b4_monitor "${W[@]}" "$PY" $PG/monitor.py --csv "$P/x/교대.csv" --split B --changes "$P/x/변경기록.csv" --out "$P/x/창별.csv"; tail_to_summary Q3b4_monitor 8
step Q3b5_recalibrate "${W[@]}" "$PY" $PG/recalibrate.py --normal $RAW/press_data_normal.csv --out "$P/x/site_model.json" --report "$P/x/site_report.json" --save-failed; tail_to_summary Q3b5_recalibrate 6
step Q3b6_package_manifest "${W[@]}" "$PY" $PG/tools/package_manifest.py --out "$P/x/package_list.csv"; tail_to_summary Q3b6_package_manifest 14
# 웹 콘솔: 서버를 CP949 조건으로 띄우고 API를 부른다
( "${W[@]}" "$PY" $PG/serve.py --port 18767 > "$LOGS/Q3b7_serve.out" 2> "$LOGS/Q3b7_serve.err" & echo $! > "$P/serve.pid" )
for i in $(seq 1 60); do curl -s -o /dev/null http://127.0.0.1:18767/ && break; sleep 1; done
{ echo "---- Q3b7 웹 콘솔(CP949·resource 차단)"
  curl -s -o "$P/x/overview.json" -w "GET /api/overview http=%{http_code} bytes=%{size_download}\n" http://127.0.0.1:18767/api/overview
  "$PY" -c "import json;d=json.load(open('$P/x/overview.json',encoding='utf-8'));print('overview audit.all_ok=',d['audit'].get('all_ok'),'| 검사',len(d['audit'].get('checks',[])),'| metrics',len(d['metrics']))"
  curl -s -o "$P/x/analyze.json" -w "POST /api/analyze(mixed,B) http=%{http_code} bytes=%{size_download}\n" -H 'Content-Type: application/json' -d '{"split":"B","alpha":0.01,"prior":0.01,"dataset":"mixed"}' http://127.0.0.1:18767/api/analyze
  "$PY" -c "import json;d=json.load(open('$P/x/analyze.json',encoding='utf-8'));print('analyze stats=',d.get('stats'),'| keys',sorted(d)[:14])"
  "$PY" -c "import json;csv=open('$RAW/outlier_data.csv',encoding='utf-8').read();open('$P/x/upload.json','w',encoding='utf-8').write(json.dumps(dict(split='A',alpha=0.01,prior=0.01,dataset='upload',csv=csv)))"
  curl -s -o "$P/x/upload_out.json" -w "POST /api/analyze(upload outlier_data.csv) http=%{http_code} bytes=%{size_download}\n" -H 'Content-Type: application/json' --data-binary @"$P/x/upload.json" http://127.0.0.1:18767/api/analyze
  "$PY" -c "import json;d=json.load(open('$P/x/upload_out.json',encoding='utf-8'));print('upload stats=',d.get('stats'),'| 대기열',len(d.get('cases',[])),'| 사건',len(d.get('incidents',[])) if isinstance(d.get('incidents'),list) else d.get('incidents'))"
} >> "$SUMMARY" 2>&1
kill "$(cat "$P/serve.pid")" 2>/dev/null; sleep 1
{ echo "---- 서버 로그 끝(CP949 출력을 UTF-8로 풀어 적음)"; tail -3 "$LOGS/Q3b7_serve.out" | iconv -f CP949 -t UTF-8 2>/dev/null; grep -v -E '^[[:space:]]*$' "$LOGS/Q3b7_serve.err" | tail -3 | iconv -f CP949 -t UTF-8 2>/dev/null; } >> "$SUMMARY"
echo "Q3 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
