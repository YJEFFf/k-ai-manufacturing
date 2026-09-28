"""검토 5: current_offset.csv의 새 두 행(정상 평가 전류 +81.4·+272.4)과 흔들림 표의 문서 인용값을 팀 표 생성 코드 없이 다시 센다.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review5_offset_check.py
동결 모델의 predict만 쓴다(평가 구간: D.split_normal의 test).
"""
import os
import sys
from pathlib import Path

ENV = Path(os.environ["REVIEW_ENV"])
sys.path.insert(0, str(ENV / "press_guard"))
import numpy as np
import pandas as pd
from model import D, GuardModel

normal, abnormal, _ = D.load()
x = D.quantize(D.inputs_only(abnormal), "matched")[D.SENSORS[2]].to_numpy(float)
g = pd.Series(x).groupby(D.segments(abnormal))
lv = g.mean()[g.size() >= 10].abs()
print(f"이상 기록(길이≥10) {len(lv)}개 |평균| 중앙 {lv.median():.2f}·최대 {lv.max():.2f}")
for s in "AB":
    m = GuardModel.load(ENV / "press_guard" / "artifacts" / f"guard_{s}.json")
    test = D.split_normal(normal, D.segments(normal), s)["test"]
    for delta in (0.0, float(lv.median()), float(lv.max())):   # 팀 표와 같은 반올림 전 값
        f = D.inputs_only(test).copy(); f[D.SENSORS[2]] = f[D.SENSORS[2]].astype(float) + delta
        p = m.predict(f, .01)
        al = p.alarm.eq(1)
        print(f"  {s} +{delta:.4f}(행 {len(p)}): 경보 기록 {int(p.groupby('record_id').alarm.max().sum())}/{p.record_id.nunique()}, 경보 행 {int(al.sum())}, "
              f"예측 오차 포함 {int((al & p.reason.str.contains('dynamics')).sum())}, '전류 파형·계측 확인' {int((al & p.action.eq('전류 파형·계측 확인')).sum())}")
js = pd.read_csv(ENV / "analysis" / "press_evidence" / "sampling_jitter_stress.csv")
pick = lambda s, f, j: js[(js.split == s) & (js.source_frequency_hz.fillna(0) == f) & (js.jitter_rms_ms == j)].iloc[0]
for f, j in ((60.6, .1), (60.6, .2), (50.6, .1), (50.6, .2), (60.6, 2.4)):
    a, b = pick("A", f, j), pick("B", f, j)
    print(f"  흔들림 {f} Hz {j} ms: 경보 기록 A {a.level1_rate:.1%}·B {b.level1_rate:.1%} (2단계 {a.level2_rate:.1%}·{b.level2_rate:.1%}), 0.6 Hz 유지 {a.fit_frequency_near_06_share:.1%}·{b.fit_frequency_near_06_share:.1%}")
