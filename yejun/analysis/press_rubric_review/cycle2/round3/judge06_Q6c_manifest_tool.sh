#!/usr/bin/env bash
# Q6c — 목록 도구(package_manifest.py) 블라인드 검사가 실제로 결함을 잡는가(R2-01 할 일 ④). 한 명령 재현을 마친 git 클론(기본 Q10)에서
#       시나리오마다 파일을 임시로 바꿨다가 되돌린다(클론은 평가관 임시 폴더, 저장소는 건드리지 않는다).
#  M0 변조 없음 → 통과
#  M1 GROUPS에서 의존 묶음 한 줄(press_dayshift) 삭제 → "실행 기록이 가리키는 파일이 목록에 없음"
#  M2 EXCLUDE에 expected/predictions_digest.json이 걸리게 바꿈 → "필수 파일 없음"
#  M3 목록에 드는 실행 기록 JSON에 개발 기기 절대 경로 삽입 → "절대 경로"
#  M4 목록에 드는 CSV에 절대 경로 삽입(검사 대상 확장자 밖) → 통과(설계 범위 밖, 참고)
#  M5 --copy-test를 비어 있지 않은 폴더에 → 거부
set -uo pipefail
source "$(dirname "$0")/judge06_lib.sh"
SRC="${1:-$J06_BASE/Q10_crlf/clone}"
P="$J06_BASE/Q6c_manifest"; rm -rf "$P"; mkdir -p "$P/logs" "$P/nonempty"; touch "$P/nonempty/keep.txt"
LOGS="$P/logs"; SUMMARY="$OUTDIR/judge06_Q6c_manifest_tool.log"; : > "$SUMMARY"
echo "Q6c 시작 $(date '+%F %T') 원천=$SRC" | tee -a "$SUMMARY"
cd "$SRC"
T=yejun/press_guard/tools/package_manifest.py
cp "$T" "$P/pm_orig.py"
run_pm() { step "$1" env OMP_NUM_THREADS=1 "$PY" "$T" "${@:2}"; grep -E "검사 실패|블라인드 검사|합계|거부|비어 있지" "$LOGS/$1.out" "$LOGS/$1.err" | sed 's#^.*/logs/##' | head -8 >> "$SUMMARY"; }
run_pm Q6c_M0_clean
"$PY" - "$T" <<'PYEOF'
import sys; p = sys.argv[1]; s = open(p, encoding="utf-8").read()
s = s.replace('    ("dependency", "analysis/press_dayshift", ["v2_current_scale.csv"]),\n', '', 1)
open(p, "w", encoding="utf-8").write(s)
PYEOF
run_pm Q6c_M1_drop_dependency_group; cp "$P/pm_orig.py" "$T"
"$PY" - "$T" <<'PYEOF'
import sys; p = sys.argv[1]; s = open(p, encoding="utf-8").read()
s = s.replace('|^press_guard/outputs/demo', '|predictions_digest|^press_guard/outputs/demo', 1)
open(p, "w", encoding="utf-8").write(s)
PYEOF
run_pm Q6c_M2_exclude_digest; cp "$P/pm_orig.py" "$T"
J=yejun/analysis/press_selection/manifest.json; cp "$J" "$P/j_orig.json"
"$PY" - "$J" <<'PYEOF'
import json, sys; p = sys.argv[1]; m = json.load(open(p, encoding="utf-8"))
m["judge06_probe"] = "/Volumes/SOMEDISK/dev/yejun/press_submission/data"
open(p, "w", encoding="utf-8").write(json.dumps(m, ensure_ascii=False, indent=2))
PYEOF
run_pm Q6c_M3_abs_path_json; cp "$P/j_orig.json" "$J"
C=yejun/analysis/press_selection/unified_comparison.csv; cp "$C" "$P/c_orig.csv"
printf '# /Users/someone/secret\n' >> "$C"
run_pm Q6c_M4_abs_path_csv; cp "$P/c_orig.csv" "$C"
run_pm Q6c_M5_copytest_nonempty --copy-test "$P/nonempty"
echo "되돌림 확인: git status 변경 $(git status --short -- yejun/press_guard/tools yejun/analysis/press_selection | wc -l | tr -d ' ')개" | tee -a "$SUMMARY"
echo "Q6c 끝 $(date '+%F %T')" | tee -a "$SUMMARY"
