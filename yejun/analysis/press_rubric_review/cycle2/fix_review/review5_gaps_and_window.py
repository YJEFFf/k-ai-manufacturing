"""검토 5: (1) 대회 원자료의 기록 사이 공백 분포(SPIKE_MIN_JUMP_S=60초 전제 확인), (2) 튐으로 인정되지 않은 튄 행(R5-01)이
품질 의심 시간창의 경계가 되는가(R3-06 수정의 적용 범위).

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review5_gaps_and_window.py
(2) 입력은 검토 3 review3_spike_quality_window.py와 같다(앞 정상 0.0~3.7초, 경보 기록 6.0~10.9초, 뒤 정상 13.0초~).
뒤 정상 기록 첫 행의 시각만 +Δ초로 바꾼다(표본 자리를 차지한 튐). Δ=3600이면 튐 예외(after_gap)가 발동한다.
"""
import os
import sys
from pathlib import Path

ENV = Path(os.environ["REVIEW_ENV"])
sys.path.insert(0, str(ENV / "press_guard"))
import numpy as np
import pandas as pd
from model import D, layout, load_bundle, cases, time_order_events

normal, abnormal, _ = D.load()
print("## (1) 기록 사이 공백(이웃 행 간격이 0.1초 ± 20 ms 밖)")
for name, f in (("정상", normal), ("이상", abnormal)):
    d = pd.to_datetime(f[D.TIME], format="mixed").diff().dt.total_seconds().to_numpy()[1:]
    b = np.sort(d[np.abs(d - .1) > .02])
    print(f"  {name}: 경계 {len(b)}곳, 0초(동률) {int((b == 0).sum())}곳, 양수 최소 {b[b > 0].min():.3f}초, 최대 {b.max():.3f}초, 60초 초과 {int((b > 60).sum())}곳")

print("## (2) 튐으로 인정되지 않은 튄 행과 품질 시간창")
MODEL = load_bundle(ENV / "press_guard" / "artifacts" / "guard_B.json")
ABN = D.inputs_only(abnormal).reset_index(drop=True)
split = D.split_normal(normal, D.segments(normal), "B")
TEST = D.inputs_only(split["test"]).reset_index(drop=True)
CLEAN = TEST[layout(TEST)[1] == 0].reset_index(drop=True)
T0 = pd.Timestamp("2022-07-17 10:00:00")


def stamp(frame, start):
    out = frame.copy().reset_index(drop=True)
    out[D.TIME] = (pd.Timestamp(start) + pd.to_timedelta(np.arange(len(out)) * .1, unit="s")).strftime("%Y-%m-%d %H:%M:%S.%f")
    return out


rec = ABN[D.segments(abnormal) == 1]
for delta in (0.0, 5.0, 30.0, 3600.0):
    after = stamp(CLEAN, T0 + pd.Timedelta(seconds=13))
    after.loc[0, D.TIME] = (T0 + pd.Timedelta(seconds=13 + delta)).strftime("%Y-%m-%d %H:%M:%S.%f")
    frame = pd.concat([stamp(CLEAN, T0), stamp(rec, T0 + pd.Timedelta(seconds=6)), after], ignore_index=True)
    pred = MODEL.predict(frame)
    c = cases(pred).iloc[0]
    print(f"  뒤 기록 첫 행 +{delta:g}초: 시각 사건(보류·새기준·튐) {time_order_events(pred)}, 창 {c.suspect_from[11:23]} ~ {c.suspect_to[11:23] or '열림'} "
          f"({c.suspect_seconds if c.suspect_seconds == c.suspect_seconds else '—'}초)")
