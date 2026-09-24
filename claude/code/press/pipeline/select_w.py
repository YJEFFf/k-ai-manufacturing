"""창 길이 w를 정상 데이터만으로 고르는 규칙 (이상 데이터 미사용).

1. 정상 학습 구간을 시간순으로 학습-A(앞 80% 구간) / 학습-B(뒤 20%)로 나눈다
2. 학습-A로 스케일러·ECDF를 만든 결합 점수에서, 정상 보정 구간 1% 구간 예산 문턱을 정한다
3. 학습-B에서 알림 구간 비율을 잰다. 모든 후보가 판정하는 행(구간 내 max(W)번째 관측 이후)만 센다
4. 비율이 가장 낮은 w (동률이면 작은 w)

한계: 라벨 없는 규칙은 검출력을 보지 못한다. "오경보가 가장 안정적인 창"을 고를 뿐이다.
"""
import numpy as np
import pandas as pd

from scores import Scorer

CANDIDATES = (5, 6, 8, 10, 12)
BUDGET = 0.01


def select_w(yj, train, cal, candidates=CANDIDATES, budget=BUDGET):
    tb = yj.blocks(train)
    ids = np.unique(tb)
    cut = ids[int(len(ids) * 0.8)]
    train_a = train[tb < cut].reset_index(drop=True)
    train_b = train[tb >= cut].reset_index(drop=True)
    scorer = Scorer(train_a, yj.blocks, wins=candidates, baselines=False)
    s_cal, _ = scorer.score(cal, yj)
    s_b, _ = scorer.score(train_b, yj)
    gb = yj.blocks(train_b)
    pos = pd.Series(np.arange(len(gb))).groupby(gb).cumcount().to_numpy()  # 구간 내 위치(0부터)
    judged = pos >= max(candidates) - 1
    rows = []
    for w in candidates:
        key = f"maxz_plus_sine_{w}"
        thr = yj.cutoff_at_budget(yj.segment_max(s_cal[key], yj.blocks(cal)), budget)
        alarm = np.isfinite(s_b[key]) & (s_b[key] > thr) & judged
        seg_alarm = pd.Series(alarm).groupby(gb).any()
        seg_judged = pd.Series(judged).groupby(gb).any()
        rows.append(dict(w=w, threshold=thr, train_b_segments=int(seg_judged.sum()),
                         train_b_alarm_segments=int(seg_alarm[seg_judged].sum()),
                         train_b_alarm_fraction=float(seg_alarm[seg_judged].mean()),
                         train_b_alarm_rows=int(alarm.sum()), train_b_judged_rows=int(judged.sum())))
    table = pd.DataFrame(rows)
    best = table.sort_values(["train_b_alarm_fraction", "train_b_alarm_rows", "w"]).iloc[0]
    tie = int((table.train_b_alarm_fraction == best.train_b_alarm_fraction).sum())
    return int(best.w), table, tie
