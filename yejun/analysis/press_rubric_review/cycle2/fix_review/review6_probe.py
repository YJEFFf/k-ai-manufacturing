"""검토 6 보조 탐침: 결과 파일이 없는 문서 수치를 동결 모델(사본의 artifacts/ = outputs/expected/ 동결 사본)로 다시 계산한다.

    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review6_probe.py <사본>/yejun

1) README:147-149 크기 문턱 |z|(α1%)와 센서별 문턱 초과 이상 행 수, 이상 행 |z| 95백분위
2) README:191 튄 행(미래 시각 한 행) 주변의 경보 행 감소 폭과 보류 행 수(+1시간 튐, +30초 튐; 행 시각을 대체한 경우와 행을 끼워 넣은 경우)
3) R10·R4: 저장 AR(2) 계수의 (1−φ1−φ2)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / "press_guard"))
from model import load_bundle, D, HERE, ORDER_HELD, ORDER_SPIKE_SKIPPED, ORDER_REANCHOR  # noqa: E402
from press.calibrate import conformal_p  # noqa: E402

normal, abnormal, _ = D.load()
models = {s: load_bundle(HERE / "artifacts" / f"guard_{s}.json") for s in "AB"}

print("== 1) 크기 문턱과 센서별 초과")
for s, m in models.items():
    q = D.quantize(D.inputs_only(abnormal), "matched")
    z = np.abs((q[D.SENSORS].to_numpy(float) - m.mean) / m.scale)
    thr = m.cal.max()                                     # α 1%: 보정 최댓값을 넘어야 경보
    tail = m.tails["magnitude"]
    lo, hi = 0.0, 100.0
    for _ in range(200):                                  # g(|z|) = thr 인 |z|
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if tail(np.array([mid]))[0] <= thr else (lo, mid)
    zthr = hi
    over = {c: int((conformal_p(m.cal, tail(z[:, i])) <= .01).sum()) for i, c in enumerate(D.SENSORS)}
    p95 = {c: float(np.percentile(z[:, i], 95)) for i, c in enumerate(D.SENSORS)}
    print(f"{s}: 문턱 g {thr:.4f} → |z| {zthr:.4f}; 초과 이상 행 {over}; |z| 95백분위 " + ", ".join(f"{k} {v:.2f}" for k, v in p95.items()))

print("== 2) 튄 행")
m = models["A"]
base = m.predict(abnormal, .01)
n0 = int(base.alarm.sum())
t = pd.to_datetime(abnormal.TimeStamp)
seg = base.record_id.to_numpy(); pos = base.position.to_numpy()
fmt = lambda x: x.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
for label, jump in (("+1시간", 3600.0), ("+30초", 30.0)):
    for mode in ("대체", "삽입"):
        drops, held, skipped, reanch = [], [], [], []
        for i in range(1, len(abnormal)):
            if pos[i] == 0:
                continue                                    # 기록 첫 행은 앞 공백이 있어 제외(기록 안 행만)
            f = abnormal.copy()
            if mode == "대체":
                f.loc[i, "TimeStamp"] = fmt(t[i] + pd.Timedelta(seconds=jump))
                r = m.predict(f, .01)
                alarms = int(r.alarm.sum()) - int(r.alarm.iloc[i])          # 튄 행 자신의 경보는 뺀다
                base_n = n0 - int(base.alarm.iloc[i])
            else:
                row = f.iloc[[i - 1]].copy(); row["TimeStamp"] = fmt(t[i - 1] + pd.Timedelta(seconds=jump))
                f = pd.concat([f.iloc[:i], row, f.iloc[i:]], ignore_index=True)
                r = m.predict(f, .01)
                alarms = int(r.alarm.sum()) - int(r.alarm.iloc[i])
                base_n = n0
            drops.append(base_n - alarms)
            ev = r.time_order_event.to_numpy()
            held.append(int((ev == ORDER_HELD).sum())); skipped.append(int((ev == ORDER_SPIKE_SKIPPED).sum())); reanch.append(int((ev == ORDER_REANCHOR).sum()))
        d = pd.Series(drops)
        print(f"{label} {mode}: 시험 {len(d)}곳, 경보 행 감소(튄 행 제외) 최소 {d.min()} 중앙 {d.median():.0f} 90% {d.quantile(.9):.0f} 최대 {d.max()}, "
              f"감소 0~3행 비율 {(d.between(0, 3)).mean():.1%}; 보류 행 {sorted(set(held))}, 튐 건너뜀 {sorted(set(skipped))}, 새 기준 {sorted(set(reanch))}")

print("== 3) AR(2) 수준 이동 이득")
for s, mm in models.items():
    c, p1, p2 = mm.coef
    print(f"{s}: 상수 {c:.4f}, φ1 {p1:.4f}, φ2 {p2:.4f}, 1−φ1−φ2 = {1 - p1 - p2:.4f}")
