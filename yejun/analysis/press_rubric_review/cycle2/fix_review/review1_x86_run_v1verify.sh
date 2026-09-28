# 검토 1(x86-64): 컨테이너 안에서 실행한다. 사용: docker run --rm --platform linux/amd64 -v <x86 사본 루트(yejun/를 담은 폴더)>:/work -w /work pg-x86 bash /work/<이 파일>
cd /work/yejun/press_submission
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
python verify.py --out outputs --steps 2 > /work/x86_v1verify.log 2>&1; echo "v1 verify exit $?"
tail -5 /work/x86_v1verify.log
