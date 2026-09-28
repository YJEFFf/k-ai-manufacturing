"""검토 3: review3_fuzz_stream.py에서 격상이 두 번 나간 시행을 같은 난수로 다시 만들어, 둘째 격상 직전에 튄 행 되돌리기가 있었는지 본다.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review3_fuzz_dup_cause.py
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import review3_fuzz_stream as F

rng = np.random.default_rng(20260929)
for trial in range(150):
    f = F.random_frame(rng)
    rng.integers(1, 12, size=40)          # 원 스크립트가 시행마다 한 번 뽑는 무작위 청크 목록
    pred = F.MODEL.predict(f)
    g = pred[pred.incident_id.gt(0)].groupby("incident_id").incident_escalation.sum()
    for inc in g[g > 1].index:
        rows = pred.index[(pred.incident_id == inc) & pred.incident_escalation.eq(1)].tolist()
        second = rows[1]
        skipped_between = pred.time_order_event.iloc[rows[0] + 1:second + 1].eq(2).any()
        print(f"시행 {trial} 사건 {inc}: 격상 행 {rows}, 첫 격상 행 time_order_event {int(pred.time_order_event.iloc[rows[0]])}, "
              f"그 사이·둘째 격상 행에 튐 건너뜀(2) {bool(skipped_between)}, 둘째 격상 행 event {int(pred.time_order_event.iloc[second])}, "
              f"첫 격상 행 시각 {f[F.D.TIME].iloc[rows[0]][11:]} → 다음 행 {f[F.D.TIME].iloc[rows[0] + 1][11:]}")
