"""검토 7: README의 '대회 이상 파일 200곳 +5초·+1시간 튐(대체·끼어듦) 모의' 문장 대조. review7_sweep.py의 전수 결과(모든 위치)에서
1~598행 가운데 200곳을 무작위로 1,000번 뽑아 보류가 생긴 곳 수·그 위치 종류·경보 감소(튄 행 제외)·사건 분할의 분포를 본다.

    python review7_claim200.py <sweep 결과 csv>
"""
import sys
import numpy as np
import pandas as pd

d = pd.read_csv(sys.argv[1])
d = d[(d.base == "ab") & d.pos.between(1, 598)]
rng = np.random.default_rng(0)
for kind in ("replace", "insert_after"):
    for value in (5.0, 3600.0):
        x = d[(d.kind == kind) & (d.value == value)].set_index("pos")
        held_pos = x[x.held > 0]
        counts, loss_med, loss_max = [], [], []
        for _ in range(1000):
            s = x.loc[rng.choice(x.index, 200, replace=False)]
            counts.append(int((s.held > 0).sum())); loss_med.append(s.alarm_loss.median()); loss_max.append(s.alarm_loss.max())
        cls = held_pos.cls.value_counts().to_dict()
        print(f"{kind:12s} +{value:<6g}: 전수 598곳 중 보류 {len(held_pos)}곳 {cls} · 200곳 추출 1,000번 보류 곳 수 5~95% "
              f"{np.percentile(counts, 5):.0f}~{np.percentile(counts, 95):.0f}(중앙 {np.median(counts):.0f}) · 경보 감소 중앙 {np.median(loss_med):g}·최대 {max(loss_max)} "
              f"· 사건 분할 {int(x.split.sum())}곳")
