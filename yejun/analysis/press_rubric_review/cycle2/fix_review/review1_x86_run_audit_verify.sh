# 검토 1(x86-64): 컨테이너 안에서 실행한다. 사용: docker run --rm --platform linux/amd64 -v <x86 사본 루트(yejun/를 담은 폴더)>:/work -w /work pg-x86 bash /work/<이 파일>
cd /work/yejun
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
t0=$(date +%s)
python press_guard/audit.py > /work/x86_audit.log 2>&1; echo "audit exit $? ($(( $(date +%s) - t0 ))s)"
tail -2 /work/x86_audit.log
python press_guard/verify.py > /work/x86_verify.log 2>&1; echo "verify exit $?"
grep -E "^FAIL|통과\." /work/x86_verify.log
