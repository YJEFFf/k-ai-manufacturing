# 검토 1(x86-64): 컨테이너 안에서 실행한다. 사용: docker run --rm --platform linux/amd64 -v <x86 사본 루트(yejun/를 담은 폴더)>:/work -w /work pg-x86 bash /work/<이 파일>
# 첫 실행: v1 2단계는 성공했고, train.py는 사본에 analysis/press_advance가 없어 실패했다. 그 폴더를 넣고 review1_x86_run_train.sh로 학습을 다시 했다.
set -e
cd /work/yejun
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
t0=$(date +%s)
python press_submission/run_all.py --steps 2 > /work/x86_v1.log 2>&1
echo "v1 done $(( $(date +%s) - t0 ))s"
python press_guard/train.py --rolling > /work/x86_train.log 2>&1
echo "train done $(( $(date +%s) - t0 ))s"
