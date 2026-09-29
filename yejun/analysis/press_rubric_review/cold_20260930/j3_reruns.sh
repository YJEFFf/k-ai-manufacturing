#!/bin/bash
# J3: 빠른 경로가 동결값 비교만 하는 분석 패키지를 임시 사본에서 다시 실행해 동결값과 비교한다(한 번에 하나씩).
T=/private/tmp/j3_repro.ioMcBr
until grep -q "^EXIT" $T/j3_reproduce_venv_tests.log; do sleep 10; done
cd $T/yejun
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
PY=/opt/anaconda3/bin/python
run() { local name="$1"; shift; local t0=$(date +%s); "$@" > $T/j3_rerun_$name.log 2>&1; local rc=$?; echo "$name rc=$rc sec=$(( $(date +%s) - t0 )) :: $(tail -1 $T/j3_rerun_$name.log | cut -c1-200)"; }
run advance_run $PY analysis/press_advance/run_experiment.py
run advance_check $PY analysis/package_contract.py --package analysis/press_advance
mkdir -p $T/sup_out
run supervised_run $PY analysis/press_supervised/run.py --out $T/sup_out
run supervised_check $PY analysis/package_contract.py --package analysis/press_supervised --out $T/sup_out
run selection_check $PY analysis/press_selection/run.py --check
run supplement_rerun $PY analysis/press_supplement/verify.py --rerun E1,E3
echo ALLDONE
