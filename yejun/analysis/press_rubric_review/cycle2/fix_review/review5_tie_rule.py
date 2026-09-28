"""검토 5: R5-04(튄 행 재전송) 권고 확인 — TimeOrder에서 동률이 jumped를 끄지 않게만 바꾸면 사건 분할이 없어지는가.

    REVIEW_ENV=<3c6fbf3 사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review5_tie_rule.py
사본 파일은 고치지 않는다. 실행 중에만 model.TimeOrder.step을 감싼다. 입력은 review5_time_rules.py D와 같다.
"""
import os
import sys
from pathlib import Path

ENV = Path(os.environ["REVIEW_ENV"])
sys.path.insert(0, str(ENV / "press_guard"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd
import model as M
import review5_time_rules as R

original = M.TimeOrder.step


def step(self, t):
    if t is not None and not pd.isna(t) and self.ref is not None and t == self.ref and self.jumped:
        return M.ORDER_OK                      # 동률 재전송: 기준·jumped·튀기 전 기준을 그대로 둔다
    return original(self, t)


i = 70
for label, patched in (("3c6fbf3", False), ("모의: 동률이 jumped 유지", True)):
    M.TimeOrder.step = step if patched else original
    try:
        for delta in (5.0, 3600.0):
            ins = R.ABN.iloc[[i]].copy(); ins[R.D.TIME] = R.fmt(R.ABN_T.iloc[i - 1] + pd.Timedelta(seconds=delta))
            two = pd.concat([R.ABN.iloc[:i], ins, ins, R.ABN.iloc[i:]], ignore_index=True)
            R.run(f"[{label}] +{delta:g}초 튄 행 두 번", two, stream=False)
    finally:
        M.TimeOrder.step = original
