# 검토 1(x86-64): 컨테이너 안에서 실행한다. 사용: docker run --rm --platform linux/amd64 -v <x86 사본 루트(yejun/를 담은 폴더)>:/work -w /work pg-x86 bash /work/<이 파일>
set -e
cd /work/yejun
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
t0=$(date +%s)
python press_guard/analyze.py > /work/x86_analyze.log 2>&1
echo "analyze done $(( $(date +%s) - t0 ))s"
