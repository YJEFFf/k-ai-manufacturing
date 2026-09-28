# 검토 3(x86-64): 컨테이너 안에서 실행한다.
# 사용: docker run --rm --platform linux/amd64 -v <사본 루트(yejun/를 담은 폴더)>:/work -w /work pg-x86 bash /work/review3_x86_run_reproduce.sh
# 사본은 git archive 110afa2 yejun + 원본 CSV 2개. 모델 파일(artifacts)은 넣지 않는다(빠른 경로가 다시 학습한다).
cd /work
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
echo "== platform: $(uname -m) $(python --version)"
python -c "import numpy, pandas, sklearn, scipy; print('numpy', numpy.__version__, 'pandas', pandas.__version__, 'sklearn', sklearn.__version__, 'scipy', scipy.__version__)"
t0=$(date +%s)
python yejun/press_guard/reproduce.py --keep-going
echo "== reproduce exit $? ($(( $(date +%s) - t0 ))s)"
