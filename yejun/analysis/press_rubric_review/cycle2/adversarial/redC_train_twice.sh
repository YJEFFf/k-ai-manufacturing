#!/bin/zsh
# redC: 임시 사본(git archive cc1aac2 + 원본 CSV, reproduce.py 완료 상태)에서 train.py --rolling을 두 번 더 돌려 산출 SHA-256을 비교한다.
# 사용: redC_train_twice.sh <임시 사본>/yejun <기록 폴더>
set -u
ROOT=$1; OUT=$2
cd $ROOT/press_guard
snap() { (cd $ROOT/press_guard && find artifacts outputs -maxdepth 1 -type f \( -name '*.json' -o -name '*.csv' \) | sort | xargs shasum -a 256) > $OUT/redC_train_sha_$1.txt; }
snap run0
for k in 1 2; do
  date "+run$k start %H:%M:%S"
  OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python train.py --rolling > $OUT/redC_train_run$k.log 2>&1; echo "run$k exit=$?"
  snap run$k
done
