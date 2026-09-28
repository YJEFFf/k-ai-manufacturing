# 검토 1(x86-64): 컨테이너 안에서 실행한다. 사용: docker run --rm --platform linux/amd64 -v <x86 사본 루트(yejun/를 담은 폴더)>:/work -w /work pg-x86 bash /work/<이 파일>
cd /work/yejun
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
run() { t=$(date +%s); "$@" > /work/x86_pkg_step.log 2>&1; rc=$?; echo "== $* -> exit $rc ($(( $(date +%s) - t ))s)"; tail -4 /work/x86_pkg_step.log; }
run python analysis/press_evidence/build_tables.py
run python analysis/press_evidence/build_diagnostics.py
for p in press_evidence press_supervised press_advance press_selection; do run python analysis/package_contract.py --package analysis/$p; done
run python analysis/press_supplement/verify.py
echo PKG-DONE
