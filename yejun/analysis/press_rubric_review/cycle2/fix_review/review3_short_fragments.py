"""검토 3: 8행 미만 무경보 조각이 공백 기준 시각을 옮기지 않게 바뀐 뒤(110afa2), 반대로 진행 중인 이상이 쪼개지거나
사건이 너무 일찍 닫히는 경우가 있는가.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review3_short_fragments.py

F1  대회 이상 21기록(3분 한 에피소드)을 수집 시각 흔들림(k행마다 +30 ms)이나 진동 결측(k행마다)으로 k행 조각으로 쪼갠다.
    수정 규칙, 수정 전 규칙(짧은 조각도 공백 기준을 옮김), 처음 규칙(모든 무경보 단위가 사건을 닫음)의 사건 수·알림 수를 비교한다.
F2  같은 이상 에피소드 안에 무경보 7행 조각만 61초 이어지는 구간을 넣는다(조각이 공백 기준을 옮기지 않으므로 사건이 나뉜다).
"""
import os
import sys
from pathlib import Path

ENV = Path(os.environ["REVIEW_ENV"])
sys.path.insert(0, str(ENV / "press_guard"))
import numpy as np
import pandas as pd

import model as M
from model import D, layout, load_bundle, IncidentTracker

MODEL = load_bundle(ENV / "press_guard" / "artifacts" / "guard_B.json")
normal, abnormal, _ = D.load()
ABN = D.inputs_only(abnormal).reset_index(drop=True)
SEG = D.segments(abnormal)
split = D.split_normal(normal, D.segments(normal), "B")
TEST = D.inputs_only(split["test"]).reset_index(drop=True)
CLEAN = TEST[layout(TEST)[1] == 0].reset_index(drop=True)


class PreFix(IncidentTracker):
    """수정 전(검토 1 대상) 규칙: 짧은 무경보 조각은 사건을 닫지 않지만 공백 기준(prev_end)은 옮긴다."""
    def update(self, record, block, alarm, reason, time, valid=True):
        if not valid:
            return 0, 0, 0, 0
        t = time if time is not None and not pd.isna(time) else self.last_time
        if (record, block) != self.unit and self.unit is not None and not (self.unit_alarmed or self.unit_rows >= M.INCIDENT_MIN_CLEAR_ROWS):
            self.prev_end = self.last_time            # 짧은 조각도 공백 기준을 옮긴다(경보 여부는 그대로)
        return super().update(record, block, alarm, reason, time, valid)


def run(frame, rule):
    old_tracker, old_rows = M.IncidentTracker, M.INCIDENT_MIN_CLEAR_ROWS
    try:
        if rule == "수정 전(조각이 공백 기준 옮김)":
            M.IncidentTracker = PreFix
        elif rule == "처음 규칙(모든 무경보 단위가 닫음)":
            M.INCIDENT_MIN_CLEAR_ROWS = 1
        return MODEL.predict(frame)
    finally:
        M.IncidentTracker, M.INCIDENT_MIN_CLEAR_ROWS = old_tracker, old_rows


def summary(pred):
    return (f"경보 {int(pred.alarm.sum())}행, 사건 {int(pred.incident_id.max())}, 시작 알림 {int(pred.incident_notification.sum())}, "
            f"격상 {int(pred.incident_escalation.sum())}, 기록 {pred.record_id.nunique()}")


def jitter(frame, every, extra=.03):
    f = frame.copy().reset_index(drop=True)
    t = pd.to_datetime(f[D.TIME])
    pos = pd.Series(np.arange(len(f))).groupby(SEG).cumcount().to_numpy()
    shift = np.zeros(len(f))
    for r in np.unique(SEG):
        m = np.flatnonzero(SEG == r)
        shift[m] = np.floor(np.arange(len(m)) / every) * extra     # 기록 안 every행마다 +30 ms 누적
    f[D.TIME] = (t + pd.to_timedelta(shift, unit="s")).dt.strftime("%Y-%m-%d %H:%M:%S.%f")
    return f


def nan_every(frame, every):
    f = frame.copy().reset_index(drop=True)
    pos = pd.Series(np.arange(len(f))).groupby(SEG).cumcount().to_numpy()
    f.loc[pos % every == every - 1, D.SENSORS[0]] = np.nan
    return f


RULES = ("수정(110afa2)", "수정 전(조각이 공백 기준 옮김)", "처음 규칙(모든 무경보 단위가 닫음)")


def f1():
    print("## F1 대회 이상 에피소드(21기록, 3분)를 k행 조각으로 쪼갬")
    cases = [("원래", ABN)] + [(f"흔들림 {k}행 조각", jitter(ABN, k)) for k in (7, 5, 3, 2)] + [(f"진동 결측 {k}행마다", nan_every(ABN, k)) for k in (6, 4, 3)]
    for name, frame in cases:
        print(f"  [{name}]")
        for rule in RULES:
            print(f"     {rule:28s}: {summary(run(frame, rule))}")


def f2():
    print("\n## F2 이상 에피소드 가운데(기록 10과 11 사이)에 무경보 7행 조각을 k초 동안 넣는다")
    first, second = ABN[SEG <= 10], ABN[SEG > 10]
    t_end = pd.to_datetime(first[D.TIME].iloc[-1])
    for seconds in (30, 61, 120):
        pieces, t = [], t_end + pd.Timedelta(seconds=2)
        while t < t_end + pd.Timedelta(seconds=seconds):
            p = CLEAN.iloc[:7].copy()
            p[D.TIME] = (t + pd.to_timedelta(np.arange(7) * .1, unit="s")).strftime("%Y-%m-%d %H:%M:%S.%f")
            pieces.append(p); t += pd.Timedelta(seconds=2)
        shift = (t - pd.to_datetime(second[D.TIME].iloc[0])) + pd.Timedelta(seconds=2)
        sec = second.copy(); sec[D.TIME] = (pd.to_datetime(sec[D.TIME]) + shift).dt.strftime("%Y-%m-%d %H:%M:%S.%f")
        frame = pd.concat([first] + pieces + [sec], ignore_index=True)
        print(f"  [무경보 7행 조각 {len(pieces)}개, 약 {seconds}초]")
        for rule in RULES:
            pred = run(frame, rule)
            mid = pred.iloc[len(first):len(first) + 7 * len(pieces)]
            print(f"     {rule:28s}: {summary(pred)} | 조각 구간 경보 {int(mid.alarm.sum())}")


def f3():
    from model import timing_warning
    print("\n## F3 짧은 기록 경고")
    for k in (7, 5):
        p = MODEL.predict(jitter(ABN, k)); ok = p[p.status.eq("ok")]
        print(f"  {k}행 조각: 평균 기록 {len(ok) / ok.record_id.nunique():.2f}행, 경보 {int(p.alarm.sum())}행(원래 569), 경고='{timing_warning(p)[:60]}'")


if __name__ == "__main__":
    f1()
    f2()
    f3()
