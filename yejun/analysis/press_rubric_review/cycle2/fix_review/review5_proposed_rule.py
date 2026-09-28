"""검토 5: R5-01 권고안 모의 — 튐 예외의 '다음 표본'을 '튀기 전 기준 + 0.1·k초 ± 20 ms(k = 1~3)'로 넓히면
표본 자리를 차지한 튐(R5-01)은 건너뛰고, 검토 3의 R3-03 반례(공백 안 과거 행·재전송)는 그대로 보류하는가.

    REVIEW_ENV=<3c6fbf3 사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review5_proposed_rule.py
사본의 파일은 고치지 않는다. 실행 중에만 model.TimeOrder.step을 바꾼다(일괄·스트림 모두 이 메서드를 쓴다).
"""
import os
import sys
from pathlib import Path

ENV = Path(os.environ["REVIEW_ENV"])
sys.path.insert(0, str(ENV / "press_guard"))
import numpy as np
import pandas as pd
import model as M
from model import D, layout, load_bundle, StreamDetector, time_order_events

K_MAX = 3


def step(self, t):
    if t is None or pd.isna(t):
        return M.ORDER_OK
    if self.ref is None or t >= self.ref:
        jump = self.ref is not None and (t - self.ref).total_seconds() > D.DT + M.TIME_TOL_S
        self.prev_ref, self.ref, self.run, self.run_last, self.jumped = self.ref, t, 0, None, jump
        return M.ORDER_OK
    if self.jumped and self.prev_ref is not None:
        since = (t - self.prev_ref).total_seconds()
        near = any(abs(since - k * D.DT) <= M.TIME_TOL_S for k in range(1, K_MAX + 1))      # 권고: 몇 표본 안
        after_gap = (self.ref - self.prev_ref).total_seconds() > M.SPIKE_MIN_JUMP_S and D.DT - M.TIME_TOL_S <= since <= M.SPIKE_MIN_JUMP_S
        if near or after_gap:
            self.ref, self.run, self.run_last, self.jumped = t, 0, None, False
            return M.ORDER_SPIKE_SKIPPED
    steady = self.run_last is not None and abs((t - self.run_last).total_seconds() - D.DT) <= M.TIME_TOL_S
    previous = self.run_last
    self.run, self.run_last = (self.run + 1 if steady else 1), t
    if self.run >= M.REANCHOR_ROWS:
        self.prev_ref, self.ref, self.run, self.run_last, self.jumped = previous, t, 0, None, False
        return M.ORDER_REANCHOR
    return M.ORDER_HELD


MODEL = load_bundle(ENV / "press_guard" / "artifacts" / "guard_B.json")
_, abnormal, _ = D.load()
ABN = D.inputs_only(abnormal).reset_index(drop=True)
T = pd.to_datetime(ABN[D.TIME])
POS = np.sort(np.random.default_rng(5).choice(np.arange(1, 599), 80, replace=False))
normal = D.load()[0]
split = D.split_normal(normal, D.segments(normal), "B")
TEST = D.inputs_only(split["test"]).reset_index(drop=True)
CLEAN = TEST[layout(TEST)[1] == 0].reset_index(drop=True)
T0 = pd.Timestamp("2022-07-17 10:00:00")


def fmt(x):
    return pd.Timestamp(x).strftime("%Y-%m-%d %H:%M:%S.%f")


def stamp(frame, times):
    out = frame.copy().reset_index(drop=True); out[D.TIME] = [fmt(t) for t in times]; return out


def split_rate(kind, delta):
    split = starts = held = 0
    for i in POS:
        if kind == "replace":
            t = T.copy(); t.iloc[int(i)] += pd.Timedelta(seconds=delta); f = ABN.copy(); f[D.TIME] = t.dt.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            ins = ABN.iloc[[int(i)]].copy(); ins[D.TIME] = fmt(T.iloc[int(i) - 1] + pd.Timedelta(seconds=delta))
            f = pd.concat([ABN.iloc[:int(i)], ins, ABN.iloc[int(i):]], ignore_index=True)
        p = MODEL.predict(f)
        split += int(p.incident_id.max()) > 1; starts += int(p.incident_notification.sum()) > 1; held += time_order_events(p)[0]
    return f"사건 2개 이상 {split}/{len(POS)} · 시작 2건 이상 {starts} · 보류 행 합 {held}"


def u3():
    mag_idx = np.flatnonzero(MODEL.predict(stamp(ABN, [T0 + pd.Timedelta(seconds=10 * i) for i in range(len(ABN))])).alarm.eq(1).to_numpy())
    mag = ABN.iloc[mag_idx[:6]].reset_index(drop=True)
    base = [T0 + pd.Timedelta(seconds=.1 * i) for i in range(len(CLEAN))]
    s = T0 + pd.Timedelta(seconds=7.0)
    out = []
    end = (base[-1] - T0).total_seconds()                                                  # 앞 기록 끝(3.7초)
    for label, late in (("U3a 공백 안 과거 행(6.0초)", 6.0), (f"U3c 앞 기록 마지막 행 재전송({end:.1f}초)", end),
                        (f"과거 행이 앞 기록 끝 + 0.2초({end + .2:.1f}초)", end + .2), (f"과거 행이 앞 기록 끝 + 0.5초({end + .5:.1f}초)", end + .5)):
        f = pd.concat([stamp(CLEAN, base), stamp(mag.iloc[:1], [s]), stamp(CLEAN.iloc[[10]], [T0 + pd.Timedelta(seconds=late)]),
                       stamp(mag.iloc[1:], [s + pd.Timedelta(seconds=.1 * i) for i in range(1, len(mag))])], ignore_index=True)
        p = MODEL.predict(f)
        out.append(f"{label}: 시각 사건 {time_order_events(p)}, 사건 {int(p.incident_id.max())}, 시작 {int(p.incident_notification.sum())}")
    return out


def stream_equal(trials=40):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import review5_fuzz_stream as F
    F.MODEL = MODEL
    rng = np.random.default_rng(20260930)
    bad, inv = 0, 0
    for _ in range(trials):
        f = F.random_frame(rng)
        pred = MODEL.predict(f)
        g = pred[pred.incident_id.gt(0)].groupby("incident_id")
        inv += int(((g.incident_notification.sum() > 1) | (g.incident_escalation.sum() > 1)).sum())
        for chunks in ([1], [7], [128], list(rng.integers(1, 12, size=40))):
            if not F.equal(F.stream(f, chunks), pred):
                bad += 1; break
    return f"무작위 {trials}회: 일괄≠스트림 {bad}, 사건 불변식 위반 {inv}"


for label, patched in (("3c6fbf3 규칙", False), (f"권고안(k = 1~{K_MAX})", True)):
    original = M.TimeOrder.step
    if patched:
        M.TimeOrder.step = step
    try:
        print(f"## {label}")
        for kind in ("replace", "insert"):
            for delta in (1.0, 5.0, 30.0, 59.9):
                print(f"  {kind:7s} Δ={delta:>5g}초: {split_rate(kind, delta)}")
        for line in u3():
            print("  " + line)
        print("  " + stream_equal())
    finally:
        M.TimeOrder.step = original
