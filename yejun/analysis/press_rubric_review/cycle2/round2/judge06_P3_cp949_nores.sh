#!/usr/bin/env bash
# P3 — 한국어 Windows 조건 모의: LC_ALL=ko_KR.CP949(PYTHONUTF8 없음) + resource 모듈 차단(sitecustomize) + 새 git 클론.
#  a) README 한 명령(--data ZIP) + --tests  (R1 완료 기준: v1 2단계·train·analyze·audit·verify·보완 verify·press_supervised)
#  b) 같은 조건에서 운영 도구: 웹 콘솔 HTTP(/api/overview·/api/analyze), predict.py --input·--split, simulate.py, recalibrate.py,
#     package_manifest.py, v1 run_all 3~5단계(LSTM 캐시 사용), 보완 E1~E3 재실행(UCI ZIP 넣음)
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
P="$J06_BASE/P3_cp949"; rm -rf "$P"; mkdir -p "$P/logs" "$P/nores" "$P/tmp" "$P/x"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_P3_cp949_nores.log"; : > "$SUMMARY"
printf 'import sys\nsys.modules["resource"] = None\n' > "$P/nores/sitecustomize.py"
unset PYTHONUTF8 PYTHONIOENCODING
W=(env LC_ALL=ko_KR.CP949 LANG=ko_KR.CP949 PYTHONPATH="$P/nores" TMPDIR="$P/tmp")
echo "P3 시작 $(date '+%F %T') 기준=$COMMIT PY=$PY" | tee -a "$SUMMARY"
"${W[@]}" "$PY" -c "import locale,sys,importlib; print('조건 확인: 기본 인코딩', locale.getpreferredencoding(False), '| utf8_mode', sys.flags.utf8_mode, '| stdout', sys.stdout.encoding)
try:
    importlib.import_module('resource'); print('resource: 있음(차단 실패)')
except ImportError as e:
    print('resource: 차단됨', e)" 2>&1 | tee -a "$SUMMARY"
make_clone "$P/clone"; cd "$P/clone"
# a) 한 명령 + 시험
step P3a_reproduce_tests "${W[@]}" "$PY" yejun/press_guard/reproduce.py --data "$ORG_ZIP" --tests; tail_to_summary P3a_reproduce_tests 30
summary_to_log yejun/press_guard/outputs/reproduce_summary.json
# b) 운영 도구
PG=yejun/press_guard; RAW=yejun/press_submission/data/3_소성가공_예지보전
step P3b1_predict_input "${W[@]}" "$PY" $PG/predict.py --input $RAW/outlier_data.csv --out "$P/x/pred_outlier.csv" --cases "$P/x/cases_outlier.csv" --model $PG/artifacts/guard_B.json; tail_to_summary P3b1_predict_input 3
step P3b2_predict_splitA "${W[@]}" "$PY" $PG/predict.py --split A --out "$P/x/test_predictions_A.csv"; tail_to_summary P3b2_predict_splitA 3
step P3b3_simulate "${W[@]}" "$PY" $PG/simulate.py --csv $RAW/outlier_data.csv --split B --speed 0 --log "$P/x/sim_alerts.csv"; tail_to_summary P3b3_simulate 4
step P3b4_recalibrate "${W[@]}" "$PY" $PG/recalibrate.py --normal $RAW/press_data_normal.csv --out "$P/x/site_model.json" --report "$P/x/site_report.json" --save-failed; tail_to_summary P3b4_recalibrate 6
step P3b5_package_manifest "${W[@]}" "$PY" $PG/tools/package_manifest.py --out "$P/x/package_list.csv"; tail_to_summary P3b5_package_manifest 14
# 웹 콘솔: 서버를 CP949 조건으로 띄우고 API를 부른다
( "${W[@]}" "$PY" $PG/serve.py --port 18766 > "$LOGS/P3b6_serve.out" 2> "$LOGS/P3b6_serve.err" & echo $! > "$P/serve.pid" )
for i in $(seq 1 60); do curl -s -o /dev/null http://127.0.0.1:18766/ && break; sleep 1; done
{ echo "---- P3b6 웹 콘솔(CP949·resource 차단)"
  curl -s -o "$P/x/overview.json" -w "GET /api/overview http=%{http_code} bytes=%{size_download}\n" http://127.0.0.1:18766/api/overview
  "$PY" -c "import json;d=json.load(open('$P/x/overview.json',encoding='utf-8'));print('overview audit.all_ok=',d['audit'].get('all_ok'),'| 검사',len(d['audit'].get('checks',[])),'| metrics',len(d['metrics']))"
  curl -s -o "$P/x/analyze.json" -w "POST /api/analyze(mixed,B) http=%{http_code} bytes=%{size_download}\n" -H 'Content-Type: application/json' -d '{"split":"B","alpha":0.01,"prior":0.01,"dataset":"mixed"}' http://127.0.0.1:18766/api/analyze
  "$PY" -c "import json;d=json.load(open('$P/x/analyze.json',encoding='utf-8'));print('analyze stats=',d['stats'],'| 1·2단계',d['level_counts'])"
  "$PY" -c "import json,io;csv=open('$RAW/outlier_data.csv',encoding='utf-8').read();open('$P/x/upload.json','w',encoding='utf-8').write(json.dumps(dict(split='A',alpha=0.01,prior=0.01,dataset='upload',csv=csv)))"
  curl -s -o "$P/x/upload_out.json" -w "POST /api/analyze(upload outlier_data.csv) http=%{http_code} bytes=%{size_download}\n" -H 'Content-Type: application/json' --data-binary @"$P/x/upload.json" http://127.0.0.1:18766/api/analyze
  "$PY" -c "import json;d=json.load(open('$P/x/upload_out.json',encoding='utf-8'));print('upload stats=',d['stats'],'| 대기열',len(d['cases']))"
} >> "$SUMMARY" 2>&1
kill "$(cat "$P/serve.pid")" 2>/dev/null; sleep 1
{ echo "---- 서버 로그 끝(CP949 출력을 UTF-8로 풀어 적음)"; tail -3 "$LOGS/P3b6_serve.out" | iconv -f CP949 -t UTF-8 2>/dev/null; grep -v -E '^[[:space:]]*$' "$LOGS/P3b6_serve.err" | tail -3 | iconv -f CP949 -t UTF-8 2>/dev/null; } >> "$SUMMARY"
# v1 3~5단계(LSTM 캐시로 시간 단축, 저장소 원본 캐시를 복사)와 보완 E1~E3 재실행(UCI ZIP)
mkdir -p "$P/x/v1_art" && cp -R "$REPO/yejun/press_submission/artifacts/lstm_cache" "$P/x/v1_art/lstm_cache"   # 캐시 위치는 <artifacts>/lstm_cache(run_all.py:229)
mkdir -p yejun/analysis/press_external/data && cp "$UCI_ZIP" yejun/analysis/press_external/data/
step P3b7_v1_full_cp949 "${W[@]}" OMP_NUM_THREADS=1 "$PY" yejun/press_submission/run_all.py --root yejun/press_submission --out "$P/x/v1_out" --artifacts "$P/x/v1_art"; tail_to_summary P3b7_v1_full_cp949 4
step P3b8_v1_verify_cp949 "${W[@]}" "$PY" yejun/press_submission/verify.py --out "$P/x/v1_out" --artifacts "$P/x/v1_art"; tail_to_summary P3b8_v1_verify_cp949 3
step P3b9_supp_rerun_cp949 "${W[@]}" "$PY" yejun/analysis/press_supplement/verify.py --rerun E1,E2,E3; tail_to_summary P3b9_supp_rerun_cp949 8
echo "P3 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
