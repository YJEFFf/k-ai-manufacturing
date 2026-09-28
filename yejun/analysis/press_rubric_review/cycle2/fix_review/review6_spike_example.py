"""검토 6: 기록 안 한 표본의 시각이 +30초로 틀린 경우(행 시각 대체)의 순서 부호·보류·경보 행 예시(동결 모델 A, 대회 이상 파일).
    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review6_spike_example.py <사본>/yejun
"""
import sys
from pathlib import Path
import pandas as pd
ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / "press_guard"))
from model import load_bundle, D, HERE, incidents, cases  # noqa: E402
_, ab, _ = D.load()
m = load_bundle(HERE / "artifacts" / "guard_A.json")
base = m.predict(ab, .01)
t = pd.to_datetime(ab.TimeStamp)
fmt = lambda x: x.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
for jump in (30.0, 3600.0):
    i = int(base.index[(base.record_id == 1) & (base.position == 20)][0])     # 기록 1(50행)의 21번째 행
    f = ab.copy(); f.loc[i, "TimeStamp"] = fmt(t[i] + pd.Timedelta(seconds=jump))
    r = m.predict(f, .01)
    w = r.iloc[i - 1:i + 5][["row_id", "timestamp", "status", "record_id", "position", "time_order_event", "alarm"]]
    print(f"== +{jump:g}초로 행 {i}의 시각을 바꿈")
    print(w.to_string(index=False))
    print(f"경보 행: 원래 {int(base.alarm.sum())} → {int(r.alarm.sum())} (튄 행 자신 {int(r.alarm.iloc[i])}); 보류 {int((r.status=='bad_time_order').sum())}행; "
          f"사건 {len(incidents(cases(r), r))}개")
