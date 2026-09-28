"""검토 1: IncidentTracker 최소 반례 — 8행 미만 무경보 조각이 사건을 '잇는다'(공백을 메워 60초 규칙을 우회한다).

    REVIEW_ENV=<사본의 yejun 폴더> PYTHONDONTWRITEBYTECODE=1 python review1_tracker_minimal.py
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(os.environ["REVIEW_ENV"]) / "press_guard"))
import pandas as pd
from model import IncidentTracker

T = pd.Timestamp("2022-07-14", tz="UTC")
sec = lambda s: T + pd.Timedelta(seconds=s)


def run(with_short_unit, short_rows=5):
    tr = IncidentTracker(); out = []
    out.append(tr.update(0, 0, True, "magnitude", sec(0)))                  # 경보 단위 A(한 행)
    if with_short_unit:
        for i in range(short_rows):                                          # t=50초부터 5행짜리 무경보 조각(시각 흔들림으로 쪼개진 기록)
            tr.update(1, 0, False, "", sec(50 + 0.1 * i))
    out.append(tr.update(2, 0, True, "magnitude", sec(100)))                # 100초 뒤 경보 단위 B
    return out


print("짧은 조각 없음 : (사건, 시작알림, 격상, 갱신) =", run(False))
print("5행 조각 끼움  : (사건, 시작알림, 격상, 갱신) =", run(True))
print("8행 조각 끼움  : (사건, 시작알림, 격상, 갱신) =", run(True, 8))
# 조각이 계속 이어지면 몇 시간 떨어진 경보도 한 사건
tr = IncidentTracker(); tr.update(0, 0, True, "magnitude", sec(0))
t = 2.0; rec = 1
while t < 3 * 3600:
    for i in range(7):
        tr.update(rec, 0, False, "", sec(t + 0.1 * i))
    rec += 1; t += 2.0
print("7행 조각이 3시간 이어진 뒤 경보: (사건, 시작알림, 격상, 갱신) =", tr.update(rec, 0, True, "magnitude", sec(t)))


# 권고안 시뮬레이션(저장소 코드는 바꾸지 않는다): 짧은 무경보 조각은 prev_end도 바꾸지 않게 한 하위 클래스
import model as M


class Proposed(IncidentTracker):
    def update(self, record, block, alarm, reason, time, valid=True):
        if not valid:
            return 0, 0, 0, 0
        t = time if time is not None and not pd.isna(time) else self.last_time
        if (record, block) != self.unit:
            if self.unit is None or self.unit_alarmed or self.unit_rows >= M.INCIDENT_MIN_CLEAR_ROWS:
                self.prev_alarmed = self.unit_alarmed
                self.prev_end = self.last_time            # 셈에 드는 단위의 끝만 공백 기준으로 쓴다
            self.unit, self.unit_alarmed, self.unit_start, self.unit_rows = (record, block), False, t, 0
        self.unit_rows += 1
        if self.unit_alarmed or self.unit_rows >= M.INCIDENT_MIN_CLEAR_ROWS or self.prev_end is None:
            self.last_time = t
        if not alarm:
            return 0, 0, 0, 0
        first_in_unit = not self.unit_alarmed
        self.unit_alarmed = True; self.last_time = t
        if first_in_unit:
            gap = (self.unit_start - self.prev_end).total_seconds() if self.prev_end is not None and self.unit_start is not None else float("inf")
            if not (self.open and self.prev_alarmed and 0 <= gap <= M.INCIDENT_MAX_GAP_S):
                self.incident += 1; self.open = True; self.count = 0; self.components = set()
        self.count += 1
        notify = int(self.count == 1); escalate = int(self.count == M.ESCALATION_ALARM_ROWS)
        new = set(filter(None, str(reason).split("+"))) - self.components
        update = int(bool(new) and self.count > 1 and bool(self.components)); self.components |= new
        return self.incident, notify, escalate, update


def run_p(short_rows):
    tr = Proposed(); out = [tr.update(0, 0, True, "magnitude", sec(0))]
    for i in range(short_rows):
        tr.update(1, 0, False, "", sec(50 + 0.1 * i))
    out.append(tr.update(2, 0, True, "magnitude", sec(100)))
    return out


print("[권고안] 5행 조각 끼움 :", run_p(5), "| 조각 없이 30초 뒤 경보는 합쳐지는가:",
      (lambda tr: (tr.update(0, 0, True, "m", sec(0)), tr.update(1, 0, True, "m", sec(30))))(Proposed()))
