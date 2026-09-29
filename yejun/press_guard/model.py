"""Press Guard v2: 정상 전류 동역학 + 초반 6→8 파형 + 센서 크기.

v1 모듈을 재사용하되 기존 패키지/동결 산출물은 수정하지 않는다.
경보는 정상 자료만으로 정한 conformal p값 규칙이다. 이상 확률은 경보와 분리된 보정 층(probability.py)이
대회 자료의 이상 비율과 사전 비율 가정에 조건부로 계산한다. 고장 종류·잔여수명은 추정하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "press_submission"
sys.path.insert(0, str(BASE))
from press import data as D
from press.calibrate import conformal_p, segment_max
from press.scores import ExpTail, Scorer, FREQS, window_index
from press.validation import code_sha256

VERSION = "press-guard-v2.0"
MODEL = "early6_ar2"
ALPHAS = (.01, .03, .05)
# 보정·알림 단위의 최대 길이. 대회 자료의 수집 묶음(기록구간)은 최대 50행(5초)이다. 더 긴 연속 입력은 기록구간 안에서
# 50행 블록으로 나눠 보정·알림한다. 대회 자료에서는 블록이 기록구간과 같으므로 결과가 바뀌지 않는다.
ALERT_UNIT_ROWS = 50
# 2단계 경보: 건(경보가 이어진 블록 묶음)의 첫 경보는 1단계 "주의", 경보 행이 이 수에 이르면 2단계 "점검 요청"으로 격상해 다시 알린다.
# 흔한 지속성 규칙(2표본)이다. 루브릭 사이클2 평가관 04의 사후 관찰(대회 B의 오경보는 모두 경보 1행)을 본 뒤 정했다.
ESCALATION_ALARM_ROWS = 2
LEVEL_NAMES = {1: "주의", 2: "점검 요청"}
# 의심 생산 시간창의 끝을 찾을 때, 경보 없는 단위가 이보다 멀리 떨어져 있으면 그사이 생산 상태를 모르므로 창을 열어 둔다.
# 대회 자료의 기록구간 사이 공백은 1.5~16.6초다.
SUSPECT_MAX_GAP_S = 60.0
# 사건(incident): 경보가 난 알림 단위가 이어지고 단위 사이 공백이 이 값 이하면 한 사건이다(기록구간을 넘어서도 묶는다).
# 사건마다 1단계 알림과 2단계 격상 알림을 한 번씩만 낸다. 근거 성분이 늘면 사건 기록만 갱신한다(새 알림 아님).
INCIDENT_MAX_GAP_S = SUSPECT_MAX_GAP_S
# 경보 없는 단위가 사건을 닫으려면 판정한 유효 행이 이만큼(8행 파형 창이 한 번 찬 길이) 있어야 한다. 수집 오류·기록 경계로 생긴
# 더 짧은 조각은 성분이 다 차지 않아 정상 복귀의 근거가 못 된다(사건을 닫지도 잇지도 않는다).
INCIDENT_MIN_CLEAR_ROWS = 8
# 사건 추적 단위의 연속 판정 허용오차: 받아들인 두 행의 간격이 0.1초 × j ± 이 값이고, j가 그사이 도착한 행 수(보류·튄 행을 뺀 수 ~ 전체)와
# 맞으면 같은 단위다(같은 시각 중복도 이어짐). 시각 결측·센서 오류·보류·확인된 튄 행·40 ms 이하 흔들림은 기록구간을 자르지만 사건 단위는 자르지
# 않는다(검토 7 R7-01). 기록 사이 공백·표본 누락·시각이 틀려 옮겨진 행은 간격이 도착한 행 수와 맞지 않아 단위를 나눈다(검토 8 R8-01·02).
# 반올림한 j에 대해 반 표본(50 ms) 허용은 늘 참이라 검사가 되지 않으므로 그보다 작게 둔다(검토 9 R9-01·D9-02).
UNIT_TOL_S = 0.04
# 기록 경계: 이웃 행의 시각 간격이 0.1초에서 이 값보다 벗어나면 새 기록구간이다. v1(1 µs)은 대회 자료의 정확한 0.1초 간격에 맞춘 값이라
# 수집 시각이 1 ms만 흔들려도 기록이 쪼개진다. 대회 자료의 기록 사이 공백은 1.5초 이상이라 20 ms에서도 구간이 같다.
TIME_TOL_S = 0.02
SHORT_RECORD_WARN = 8      # 평균 기록 길이가 이보다 짧으면 수집 시각 간격 경고(8행 파형 창이 거의 차지 않는다, 검토 3 F3: 7행 조각이면 경보 569→428행)
# 수집 시각 순서: 기준(마지막으로 받아들인 시각)보다 이른 행은 판정을 보류한다. 그런 행이 정상 간격(0.1초 ± TIME_TOL_S)으로
# 이만큼 이어지면 시계 재설정·지난 자료로 보고 새 기준으로 받아들인다. 한 행의 시각 오류가 뒤 자료 전체를 막지 않게 하는 값이다.
REANCHOR_ROWS = 3
# 튄 행 뒤의 행이 튀기 전 기준에서 표본 1~SPIKE_SKIP_SAMPLES칸(0.1·k초 ± TIME_TOL_S) 뒤면 원래 시간축을 잇는 것으로 본다.
# 튄 행이 끼어든 경우(1칸)와 표본 하나를 대신한 경우(2칸)를 받고, 기록 사이 공백 안의 과거 행·재전송은 보류한다(검토 3 R3-03, 검토 5 R5-01).
SPIKE_SKIP_SAMPLES = 3
# 사후 진단용 상태 대리변수. 정상 기록의 2성분 경계 91.886을 반올림한 값이며 경보·학습에는 쓰지 않는다.
# 원 전류의 기록 평균 제거 RMS(ddof=0). 0.6 Hz 한 주기 이상(17행)을 본 뒤에만 상태를 표시한다.
LOAD_STATE_RMS = 91.9
STATE_MIN_ROWS = 17
QUALITY_ACTIONS = {1: "다음 샘플 검사를 앞당긴다(가설)",
                   2: "의심 시간창에 만든 가공품을 보류하고 전단면·버·치수·평탄도를 전수 확인한다(가설)"}
ACTIONS = dict(vibration="진동·부하 확인", vibration_and_current="진동·전류 함께 점검",
               current_magnitude="전류 크기·부하·계측 확인", current_magnitude_and_shape="전류 크기·파형·계측 확인",
               current_shape="전류 파형·계측 확인", invalid="수집 상태 확인")
# 경보 근거 → 확인 대상(가설) → 권장 확인 → 점검 항목(가설). 조치 규칙(action_for)과 같은 원천이며 정비 결과로 검증한 것은 아니다.
# failure_modes는 analysis/press_evidence/failure_mode_map.csv의 행(FM1 베어링, FM2 캐비테이션·흡입 공기, FM3 체결·정렬,
# FM4 내부 누설·기어 마모, FM5 전기·전원, FM6 계측·배선)이다. 10 Hz 순시값으로는 고장 모드를 식별할 수 없어 후보 목록이다.
GUIDEBOOK = "가이드북 6~7쪽: 펌프 내부 기어 마모 → 진동·소음 증가, 출력 유압 약화 → 불량품"
# 계측 항목(센서 부착·영점·접지, 수집 표본화 시각)을 설비 점검 항목보다 앞에 둔다. 예측 오차(AR(2)) 성분은 전류 수준 이동에 반응하고
# (current_offset.csv), 대회 이상 파일의 전류에는 기록 사이로 이어지는 수준 치우침이 있다(class_differences.csv). 앨리어싱 가설 아래
# 파형·예측 오차 성분은 0.1 ms 수준의 표본화 시각 흔들림에도 반응한다(sampling_jitter_stress.csv, 모두 analysis/press_evidence).
# 부착·케이블·접지 상태는 운전 중에 볼 수 있지만 전류 센서 영점은 무전류(정지) 상태에서 확인한다[가정].
MEASUREMENT = "; 계측 항목은 일반 공학 지식(가설)"
DECISION_TABLE = (
    dict(evidence="크기(진동 센서)", check_target="펌프 상·하부 진동 증가: 기어 마모·체결·베어링·부하 변화 또는 센서 부착 이상(가설)", action=ACTIONS["vibration"],
         checklist="진동 센서 부착·케이블(먼저), 펌프·모터 체결 볼트, 커플링 정렬, 베어링 온도·소음, 흡입측 공기 혼입(캐비테이션 소음), 작동유 레벨·온도",
         failure_modes="FM1·FM2·FM3·FM4·FM6", source=GUIDEBOOK + MEASUREMENT),
    dict(evidence="크기(전류 센서)", check_target="전류 크기 변화: 부하(가압력) 증가 또는 계측 이상(가설)", action=ACTIONS["current_magnitude"],
         checklist="전류 센서 배선·영점(먼저), 가압력·금형 조건 변경 여부, 전원 전압·상 불평형", failure_modes="FM5·FM6", source="일반 공학 지식(가설)"),
    dict(evidence="파형 또는 예측 오차(전류)", check_target="전류 파형 흐트러짐: 모터·전원·계측·수집 시각 또는 출력 유압 불안정(가설)", action=ACTIONS["current_shape"],
         checklist="전류 센서 영점·접지·수집 장비 표본화 시각(먼저), 출력 유압(압력계) 안정성, 릴리프 밸브, 모터 전원 품질·접촉기", failure_modes="FM4·FM5·FM6",
         source=GUIDEBOOK + MEASUREMENT),
    dict(evidence="크기(진동) + 파형·예측 오차, 또는 구간 안에서 진동·전류 크기 모두",
         check_target="진동과 전류가 함께 변함: 기어 마모로 출력 유압 약화 가능성 또는 계측·수집 변화(가설)",
         action=ACTIONS["vibration_and_current"], checklist="센서 부착·영점·접지와 수집 설정(먼저), 위 진동·전류 항목 전부, 출력 유압 저하 여부, 작동유 필터 차압·오염",
         failure_modes="FM1·FM2·FM3·FM4·FM6", source=GUIDEBOOK + MEASUREMENT),
    dict(evidence="크기(전류) + 파형·예측 오차", check_target="전류 크기와 파형이 함께 변함: 부하 급변·유압 회로 이상 또는 계측 이상(가설)", action=ACTIONS["current_magnitude_and_shape"],
         checklist="전류 센서 배선·영점·수집 설정(먼저), 유압 회로 압력, 릴리프 밸브, 모터 권선·전원", failure_modes="FM4·FM5·FM6", source="일반 공학 지식(가설)"),
    dict(evidence="수집 오류(결측·비유한 값·시각 오류)", check_target="수집 경로·센서 연결", action=ACTIONS["invalid"],
         checklist="센서 케이블·커넥터, 수집 PC 시각 동기화", failure_modes="FM6", source="수집 규칙"),
)


def action_for(magnitude_vibration, magnitude_current, shape):
    """권장 확인. 크기 성분은 최대 편차가 진동 센서인지 전류 센서인지까지 구분한다."""
    if magnitude_vibration and (shape or magnitude_current):
        return ACTIONS["vibration_and_current"]
    if magnitude_vibration:
        return ACTIONS["vibration"]
    if magnitude_current and shape:
        return ACTIONS["current_magnitude_and_shape"]
    if magnitude_current:
        return ACTIONS["current_magnitude"]
    return ACTIONS["current_shape"]


def alert_units(seg, pos):
    """보정·알림 단위 번호: 기록구간 안의 50행 블록. 기록구간이 50행 이하면 기록구간 번호와 같은 묶음이다."""
    seg, block = np.asarray(seg), np.asarray(pos) // ALERT_UNIT_ROWS
    if not len(seg):
        return np.array([], dtype=int)
    return np.cumsum(np.r_[False, (seg[1:] != seg[:-1]) | (block[1:] != block[:-1])])


def first_alerts(record, block, alarm):
    """경보 단위의 첫 경보에 알린다. 같은 기록구간의 바로 앞 블록도 경보였으면 이어지는 이상으로 보고 새로 알리지 않는다."""
    f = pd.DataFrame(dict(r=np.asarray(record), b=np.asarray(block), a=np.asarray(alarm, bool)))
    first = f.a & f.groupby(["r", "b"]).a.cumsum().eq(1)
    alarmed = f.groupby(["r", "b"]).a.any()
    previous = alarmed.reindex(pd.MultiIndex.from_arrays([f.r, f.b - 1]), fill_value=False).to_numpy()
    return (first.to_numpy() & ~previous).astype(int)


def episode_ids(record, block, alarm):
    """건 번호: 같은 기록구간에서 경보가 이어진 블록 묶음. 경보 없는 블록의 행은 0."""
    f = pd.DataFrame(dict(r=np.asarray(record), b=np.asarray(block), a=np.asarray(alarm, bool)))
    blocks = f.groupby(["r", "b"], sort=False).a.any().reset_index()
    continues = blocks.groupby("r").a.shift(1, fill_value=False)
    blocks["episode"] = np.where(blocks.a, np.cumsum(blocks.a & ~continues), 0)
    return pd.MultiIndex.from_arrays([f.r, f.b]).map(blocks.set_index(["r", "b"]).episode).to_numpy()


def alert_levels(record, block, alarm):
    """행별 경보 단계(0 없음, 1 주의, 2 점검 요청)와 격상 행. 건 안의 누적 경보 행이 ESCALATION_ALARM_ROWS에 이르면 격상."""
    alarm = np.asarray(alarm, bool)
    ep = episode_ids(record, block, alarm)
    count = pd.Series(alarm.astype(int)).groupby(ep).cumsum().to_numpy()
    level = np.where(alarm, np.where(count >= ESCALATION_ALARM_ROWS, 2, 1), 0)
    return level, (alarm & (count == ESCALATION_ALARM_ROWS)).astype(int)


class IncidentTracker:
    """행을 시간 순서대로 넣으면 사건 번호·사건 첫 알림·사건 격상·근거 추가를 돌려준다. 일괄 분석과 스트림이 같은 규칙을 쓴다.

    상태는 둘로 나뉜다. 사건 배정(지금 어느 단위·사건에 있는가, 공백 계산용 시각)은 튄 행을 되돌릴 때 복원한다. 사건별 알림 상태
    (누적 경보 행·근거 성분)는 이미 사람에게 나간 알림을 뜻하므로 되돌리지 않는다. 그래서 되돌린 뒤에도 한 사건에 시작·격상 알림이
    두 번 나가지 않는다(검토 3 R3-01). 튄 행의 경보도 실제 측정값의 경보이므로 그 사건의 누적 경보에 남는다."""

    _FIELDS = ("unit", "unit_alarmed", "unit_start", "unit_rows", "prev_alarmed", "prev_end", "last_time", "open", "incident")

    def __init__(self):
        self.unit = None; self.unit_alarmed = False; self.unit_start = None; self.unit_rows = 0
        self.prev_alarmed = False; self.prev_end = None; self.last_time = None
        self.open = False; self.incident = 0   # 사건 번호는 1부터
        self.issued = 0              # 지금까지 발급한 가장 큰 사건 번호(되돌리지 않아 번호가 겹치지 않는다)
        self.alarms = {}             # 사건 번호 → 누적 경보 행(되돌리지 않는다)
        self.evidence = {}           # 사건 번호 → 근거 성분(되돌리지 않는다)
        self._undo = None

    def undo(self):
        """마지막 유효 행의 사건 배정·공백 효과를 되돌린다(미래로 튄 한 행). 발급한 번호와 사건별 알림 상태는 되돌리지 않는다."""
        if self._undo is not None:
            for k, v in self._undo.items():
                setattr(self, k, v)
            self._undo = None

    def _prune(self):
        """되돌리기로 돌아갈 수 있는 사건(현재·직전 배정)의 알림 상태만 남긴다."""
        keep = {self.incident, (self._undo or {}).get("incident")}
        for k in [k for k in self.alarms if k not in keep]:
            del self.alarms[k], self.evidence[k]

    def update(self, record, block, alarm, reason, time, valid=True):
        """valid=False(수집 오류 행)는 상태를 바꾸지 않는다. 오류 행은 정상 복귀의 근거가 아니다. 단위(record, block)는 CollectionUnits가
        도착한 행 수로 설명되지 않는 간격에서만 나누므로 오류 행이 기록을 잘라도 사건 단위는 그대로다(유효 행 수는 오류 행만큼 준다).
        단위가 끝날 때 경보가 났거나 유효 행이 INCIDENT_MIN_CLEAR_ROWS 이상인 단위만 '앞 단위'(경보 여부·끝 시각)가 된다.
        더 짧은 무경보 조각은 사건을 닫지도, 공백 기준 시각을 옮기지도 않는다."""
        if not valid:
            return 0, 0, 0, 0
        self._undo = {k: getattr(self, k) for k in self._FIELDS}
        t = time if time is not None and not pd.isna(time) else self.last_time
        if (record, block) != self.unit:
            if self.unit is not None and (self.unit_alarmed or self.unit_rows >= INCIDENT_MIN_CLEAR_ROWS):
                self.prev_alarmed, self.prev_end = self.unit_alarmed, self.last_time
            self.unit, self.unit_alarmed, self.unit_start, self.unit_rows = (record, block), False, t, 0
        self.unit_rows += 1
        self.last_time = t
        if not alarm:
            return 0, 0, 0, 0
        first_in_unit = not self.unit_alarmed
        self.unit_alarmed = True
        if first_in_unit:
            gap = (self.unit_start - self.prev_end).total_seconds() if self.prev_end is not None and self.unit_start is not None else np.inf
            if not (self.open and self.prev_alarmed and 0 <= gap <= INCIDENT_MAX_GAP_S):
                self.issued += 1; self.incident = self.issued; self.open = True
                self.alarms[self.incident], self.evidence[self.incident] = 0, set()
                self._prune()
        k = self.incident
        self.alarms[k] += 1
        count, seen = self.alarms[k], self.evidence[k]
        new = set(filter(None, str(reason).split("+"))) - seen
        update = int(bool(new) and count > 1 and bool(seen))
        seen |= new
        return k, int(count == 1), int(count == ESCALATION_ALARM_ROWS), update


def spike_rows(order_event, has_time):
    """튄 행을 확인한 행(SPIKE_EVENTS)마다 그 앞의 튄 행(기준 시각을 앞으로 옮긴 마지막 행) 번호. 둘 사이에는 시각 결측·보류 행만 있을 수 있다
    (시각이 있는 다른 행을 받아들이면 기준이 바뀌어 튐 예외가 사라진다). 튄 행이 없으면 -1."""
    out = np.full(len(order_event), -1)
    last = -1
    for i, (ev, ok) in enumerate(zip(order_event, has_time)):
        if ev in SPIKE_EVENTS:
            out[i] = last
        if ev != ORDER_HELD and ok:
            last = i
    return out


class CollectionUnits:
    """사건 추적 단위: (연속 수집 번호, 그 안의 5초 블록). 받아들인 행(시각 있음·보류 아님)이 앞에 받아들인 행과 0.1초 × j ± UNIT_TOL_S
    간격이고 j가 그사이 도착한 표본 수로 설명되면 같은 연속 수집이다. 도착한 행 k개(이 행 포함) 가운데 보류 행과 확인된 튄 행은 표본이 아닐 수
    있으므로(재전송·끼어듦) j는 k − 보류 − 튄 행 이상이면 된다. 위쪽은 k에서 표본일 수 없는 보류 행(기준보다 한 표본 넘게 이른 재전송·지난 자료)을
    뺀 수다. 시각 결측·센서 오류 행은 표본 자리를 차지한 것으로 본다. 같은 시각 중복(간격 1 ms 이하)도 이어진다. 기록 사이 공백·표본 누락·시각 역행·시각이 틀려 옮겨진 행은 설명되지 않아 새 단위다.
    연속 수집 안에서는 ALERT_UNIT_ROWS × 0.1초마다 새 블록을 연다. 튄 행을 확인하면 undo()로 그 행이 옮긴 상태를 되돌린다."""

    _STATE = ("run", "run_start", "last", "last_index", "held", "extra", "undone")

    def __init__(self):
        self.run, self.run_start, self.last, self.last_index, self.held, self.extra, self.undone = -1, None, None, None, 0, 0, 0
        self.index, self._undo = -1, None

    def step(self, t, accepted, held=False):
        """행마다 한 번 부른다(받아들이지 않은 행 포함, held는 판정 보류 행). 돌려주는 값: (연속 수집 번호, 블록)."""
        self.index += 1
        if held:
            self.held += 1
            # 기준보다 한 표본 넘게 이른 보류 행은 재전송·지난 자료라 표본 자리가 아니다(조금 이르게 찍힌 표본만 자리를 차지할 수 있다)
            self.extra += not (self.last is not None and t is not None and not pd.isna(t) and t > self.last - pd.Timedelta(seconds=D.DT))
        if accepted:
            self._undo = {k: getattr(self, k) for k in self._STATE}
            same = False
            if self.last is not None:
                gap = (t - self.last).total_seconds()
                j = int(round(gap / D.DT))
                arrived = self.index - self.last_index
                if j == 0:
                    same = abs(gap) <= 1e-3        # 같은 시각 중복(재전송)만. 0.04초처럼 짧은 간격은 옮겨진 행일 수 있다
                else:
                    same = abs(gap - j * D.DT) <= UNIT_TOL_S + 1e-9 and arrived - self.held - self.undone <= j <= arrived - self.extra
            if not same:
                self.run, self.run_start = self.run + 1, t
            self.last, self.last_index, self.held, self.extra, self.undone = t, self.index, 0, 0, 0
        if self.last is None:
            return -1, 0
        return self.run, int((self.last - self.run_start).total_seconds() / (ALERT_UNIT_ROWS * D.DT) + 1e-9)

    def undo(self):
        """튄 행의 효과를 되돌린다. 튄 행 뒤에 온 보류 행 수는 남기고, 튄 행은 표본이 아닐 수 있는 행으로 센다."""
        if self._undo is not None:
            held_after, extra_after = self.held, self.extra
            for k, v in self._undo.items():
                setattr(self, k, v)
            self.held += held_after
            self.extra += extra_after
            self.undone += 1
            self._undo = None


def incident_columns(alarm, reason, time, valid=None, order_event=None):
    """일괄 분석용: 행마다 (사건 번호, 사건 첫 알림, 사건 격상, 근거 추가). 경보 없는 유효 단위(8행 이상)가 끼면 사건이 닫힌다.
    단위는 CollectionUnits(간격이 도착한 행 수로 설명되지 않는 곳에서만 나뉨)다. 수집 오류 행(valid=False)은 건너뛴다.
    튄 행을 확인한 행(SPIKE_EVENTS)에서는 단위 상태를 되돌리고, 그 앞의 튄 행이 사건 추적에 들어간 유효 행이었으면
    그 행의 사건 배정·공백 효과도 되돌린다(사이에 수집 오류·보류 행이 끼어도 같다, 검토 3 R3-02)."""
    tr, units = IncidentTracker(), CollectionUnits()
    valid = np.ones(len(alarm), bool) if valid is None else np.asarray(valid, bool)
    order_event = np.zeros(len(alarm), int) if order_event is None else np.asarray(order_event, int)
    has_time = pd.notna(pd.Series(list(time), dtype=object)).to_numpy()
    spike = spike_rows(order_event, has_time)
    out = np.zeros((len(alarm), 4), dtype=int)
    for i, (a, why, t, ok, ev, ht) in enumerate(zip(alarm, reason, time, valid, order_event, has_time)):
        if ev in SPIKE_EVENTS and spike[i] >= 0:
            units.undo()
            if valid[spike[i]]:
                tr.undo()
        run, block = units.step(t, bool(ht) and ev != ORDER_HELD, ev == ORDER_HELD)
        out[i] = tr.update(run, block, bool(a), why, t, bool(ok))
    return out


def record_running_max(values, record):
    """기록구간 안에서 지금까지의 최댓값(결측은 직전 값 유지). 기록구간 확률용."""
    v = pd.Series(np.asarray(values, float))
    return v.groupby(np.asarray(record)).cummax().groupby(np.asarray(record)).ffill().to_numpy()


class CurrentState:
    """원 전류의 인과적 누적 RMS. 일괄·스트림에서 같은 행 순서로 Welford 갱신한다."""

    def __init__(self):
        self.n = 0
        self.mean = self.m2 = 0.0

    def update(self, value):
        if not np.isfinite(value):
            return np.nan, "short"
        self.n += 1
        delta = value - self.mean
        self.mean += delta / self.n
        self.m2 += delta * (value - self.mean)
        rms = float(np.sqrt(max(0.0, self.m2 / self.n)))
        state = "short" if self.n < STATE_MIN_ROWS else ("load" if rms >= LOAD_STATE_RMS else "low")
        return rms, state


def current_states(values, records):
    """기록 경계마다 초기화한 누적 RMS와 상태(경보 결정에 사용하지 않음)."""
    rms, states = [], []
    previous = None
    current = CurrentState()
    for value, record in zip(values, records):
        if record != previous:
            current = CurrentState()
            previous = record
        value_rms, state = current.update(value)
        rms.append(value_rms)
        states.append(state)
    return np.asarray(rms, float), np.asarray(states, object)


ORDER_OK, ORDER_HELD, ORDER_SPIKE_SKIPPED, ORDER_REANCHOR, ORDER_SPIKE_REANCHOR = 0, 1, 2, 3, 4
SPIKE_EVENTS = (ORDER_SPIKE_SKIPPED, ORDER_SPIKE_REANCHOR)   # 앞의 튄 행을 확인한 부호(사건 추적이 그 행의 효과를 되돌린다)


class TimeOrder:
    """수집 시각 순서 판정. 행을 받은 순서대로 넣으면 행마다 부호를 돌려준다. 일괄·스트림이 같은 상태를 이어 쓴다.

    - 기준 시각은 마지막으로 받아들인 시각이다. 같거나 늦은 시각은 받아들인다(ORDER_OK, 동률 허용).
    - 미래 시각 한 행(튐): 기준 행(마지막으로 받아들인 행, 사이에 시각 결측·보류 행이 있어도 된다)이 그 앞 기준보다 정상 간격
      (0.1초 ± TIME_TOL_S)보다 크게 앞으로 뛰었고, 이 행이 튀기 전 기준에서 표본 1~SPIKE_SKIP_SAMPLES칸 뒤(튄 행이 끼어들었거나 표본
      하나를 대신함)이면 기준 행을 튄 행으로 보고 이 행부터 계속 판정한다(ORDER_SPIKE_SKIPPED, 보류 없음). 늦게 도착한 앞 기록의 행도
      이 조건을 채우면 새 기록의 정상 첫 행이 튄 행으로 판정된다(알려진 한계). 그 밖의 이른 시각(기록 사이 공백 안의 과거 행·재전송)은
      아래처럼 보류한다. 이 예외는 연속으로 쓰지 않는다(두 행 이상 연속으로 튀면 확인하지 못한다).
      튄 행 자체는 이미 판정했으므로(인과) 되돌리지 않는다. 사건 추적은 그 행의 사건 배정·공백 효과만 되돌린다.
    - 순서 뒤바뀜·시계 재설정·지난 자료: 기준보다 이른 행은 판정을 보류한다(ORDER_HELD). 정상 간격으로 REANCHOR_ROWS행 이어지면
      셋째 행부터 새 기준으로 받아들인다(ORDER_REANCHOR, 보류 REANCHOR_ROWS − 1행). 역순·불규칙 간격이면 계속 보류하고 경고한다.
      앞으로 튄 행 바로 뒤에 새 기록이 오면(기록 끝·첫 행의 튐) 그 새 기록은 보류되다가 이렇게 받아들여진다(보통 2행, 다음 기록이 짧으면
      그 뒤 기록까지 3~5행). 이때 새 시간축이 튀기 전 기준보다 뒤에서 시작했으면 튄 행을 확인한 것으로 보고 ORDER_SPIKE_REANCHOR를 낸다
      (사건 추적이 튄 행의 효과를 되돌린다). 튄 시각이 다음 기록 셋째 행보다 이르면 보류 1~2행뿐 확인하지 않는다.
    - 시각을 읽을 수 없는 행은 상태를 바꾸지 않는다. 센서 값 오류 행도 시각이 있으면 순서 판정에 쓴다.
    """

    _STATE = ("ref", "prev_ref", "run_last", "run_first", "run", "jumped")

    def __init__(self):
        self.ref = self.prev_ref = self.run_last = self.run_first = None
        self.run = 0
        self.jumped = False          # 기준 행이 정상 간격보다 크게 앞으로 뛰어 받아들인 행인가

    def copy(self):
        other = TimeOrder()
        for k in self._STATE:
            setattr(other, k, getattr(self, k))
        return other

    def step(self, t):
        if t is None or pd.isna(t):
            return ORDER_OK
        if self.ref is None or t >= self.ref:
            jump = self.ref is not None and (t - self.ref).total_seconds() > D.DT + TIME_TOL_S
            self.prev_ref, self.ref, self.run, self.run_last, self.run_first, self.jumped = self.ref, t, 0, None, None, jump
            return ORDER_OK
        if self.jumped and self.prev_ref is not None:
            since = (t - self.prev_ref).total_seconds()
            k = round(since / D.DT)
            if 1 <= k <= SPIKE_SKIP_SAMPLES and abs(since - k * D.DT) <= TIME_TOL_S:   # 튀기 전 시간축의 1~3칸 뒤 표본
                self.ref, self.run, self.run_last, self.run_first, self.jumped = t, 0, None, None, False
                return ORDER_SPIKE_SKIPPED
        steady = self.run_last is not None and abs((t - self.run_last).total_seconds() - D.DT) <= TIME_TOL_S
        previous = self.run_last
        if steady:
            self.run += 1
        else:
            self.run, self.run_first = 1, t
        self.run_last = t
        if self.run >= REANCHOR_ROWS:                                                # 새 시간축으로 받아들인다
            spike = self.jumped and self.prev_ref is not None and self.run_first > self.prev_ref
            self.prev_ref, self.ref, self.run, self.run_last, self.run_first, self.jumped = previous, t, 0, None, None, False
            return ORDER_SPIKE_REANCHOR if spike else ORDER_REANCHOR
        return ORDER_HELD


def timestamp_order(timestamp, state=None):
    """행마다 순서 부호(ORDER_*)와 끝난 뒤의 순서 상태. state를 주면 복사해서 이어 쓴다(원본은 바꾸지 않는다)."""
    order = TimeOrder() if state is None else state.copy()
    codes = np.fromiter((order.step(t) for t in timestamp), dtype=np.int8, count=len(timestamp))
    return codes, order


def layout_with_order(frame, *, time_state=None):
    """(상태, 기록구간 번호, 수집 시각 순서 부호). 순서 부호는 ORDER_* 값이다."""
    missing = [c for c in [D.TIME]+D.SENSORS if c not in frame]
    if missing:
        raise KeyError(f"필수 열 없음: {missing}")
    # 자동 형식 추정은 청크 첫 행에 따라 달라진다. 각 행을 동일한 규칙으로 파싱한다.
    timestamp = pd.to_datetime(frame[D.TIME],format="mixed",utc=True,errors="coerce")
    values = frame[D.SENSORS].apply(pd.to_numeric,errors="coerce").to_numpy(float)
    status = np.full(len(frame),"ok",dtype=object)
    status[~np.isfinite(values).all(axis=1)] = "bad_value"
    status[timestamp.isna().to_numpy()] = "bad_timestamp"
    codes, _ = timestamp_order(timestamp, time_state)
    status[codes == ORDER_HELD] = "bad_time_order"
    bad = status != "ok"
    boundary = timestamp.diff().dt.total_seconds().sub(D.DT).abs().gt(TIME_TOL_S).to_numpy() | bad
    boundary[1:] |= bad[:-1]
    if len(boundary): boundary[0] = False
    return status, np.cumsum(boundary), codes


def layout(frame, *, time_state=None):
    status, seg, _ = layout_with_order(frame, time_state=time_state)
    return status, seg


SINE_RCOND = 1e-10   # 사인 적합 기저의 유효 계수 판정(최대 특이값 대비). 5.0 Hz(나이퀴스트)에서는 사인 열이 부동소수 잡음(약 3e-15)뿐이다


def stable_hats(win):
    """주파수 격자별 사인 적합 투영 행렬. v1 _hats와 같은 격자·기저를 쓰되, 5.0 Hz(나이퀴스트)에서는 사인 열이 부동소수 잡음뿐인데
    기본 pinv가 그 잡음을 유효 방향으로 받아 계수 3(8행 창)이 된다. rcond로 수학적 계수 2(cos·상수)를 쓴다. 대회 이상 31행의 파형 점수가
    바뀌지만 경보는 α 1·3·5%에서 같다. 기기 간 점수 차이의 원인으로 확인한 것은 아니다(x86-64에서도 5 Hz 투영은 1.7e-16 안에서 같았다)."""
    t = np.arange(win) * D.DT
    hats = []
    for f in FREQS:
        A = np.column_stack([np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t), np.ones(win)])
        hats.append(A @ np.linalg.pinv(A, rcond=SINE_RCOND))
    return np.stack(hats)


_HATS = {}


def sine_score(current,seg,win):
    """행별 합산 순서를 고정해 BLAS 배치 크기 → ECDF 순위 변화를 차단한다."""
    x=np.asarray(current,float)
    result=np.full(len(x),np.nan)
    idx=window_index(seg,win)
    if not len(idx): return result
    windows=np.stack([x[i-win+1:i+1] for i in idx])
    sst=((windows-windows.mean(axis=1,keepdims=True))**2).sum(axis=1)
    best=np.full(len(idx),np.inf)
    hats = _HATS.get(win)
    if hats is None:                  # setdefault(win, stable_hats(win))는 기본값을 매번 계산해 캐시가 되지 않는다(검토 3 R3-04)
        hats = _HATS[win] = stable_hats(win)
    for hat in hats:
        residual=windows-np.einsum("ij,kj->ik",windows,hat,optimize=False)
        np.minimum(best,(residual*residual).sum(axis=1),out=best)
    np.divide(best,sst,out=best,where=sst>0)
    best[sst<=0]=np.nan
    result[idx]=np.clip(best,0,None)
    return result


def ar_residual(frame, seg, coefficients):
    x = frame[D.SENSORS[2]].to_numpy(float)
    idx = window_index(seg, 3)
    result = np.full(len(x), np.nan)
    result[idx] = np.abs(x[idx] - coefficients[0] - coefficients[1]*x[idx-1] - coefficients[2]*x[idx-2])
    return result


class GuardModel:
    def __init__(self, state):
        if state.get("version") != VERSION or state.get("model") != MODEL:
            raise ValueError("지원하지 않는 모델 형식")
        self.state = state
        self.mean = np.asarray(state["mean"], float)
        self.scale = np.asarray(state["scale"], float)
        self.coef = np.asarray(state["ar2"], float)
        if self.mean.shape != (3,) or self.scale.shape != (3,) or self.coef.shape != (3,):
            raise ValueError("센서/동역학 계수 형식 오류")
        if not np.isfinite(np.r_[self.mean,self.scale,self.coef]).all() or (self.scale <= 0).any():
            raise ValueError("비정상 모델 계수")
        self.tails = {k: ExpTail.from_state(v) for k,v in state["tails"].items()}
        if set(self.tails) != {"magnitude", "sine6", "sine8", "dynamics"} or not all(t.ok for t in self.tails.values()):
            raise ValueError("정상 참조 점수 분포 오류")
        self.cal = np.asarray(state.get("calibration", []), float)
        self.probability = None   # 선택: probability.ProbabilityCalibrator(경보와 무관한 이상 확률 층)

    def attach_probability(self, calibrator):
        self.probability = calibrator
        return self

    @classmethod
    def fit(cls, train, calibration, *, split="custom", input_hashes=None):
        if (layout(train)[0] != "ok").any() or (layout(calibration)[0] != "ok").any():
            raise ValueError("학습/보정에는 유효한 정상 입력만 사용할 수 있다")
        tr = D.quantize(D.inputs_only(train), "matched")
        seg = layout(tr)[1]
        scorer = Scorer(tr, seg, D.load_vendor(), wins=(6,8), baselines=False)
        x = tr[D.SENSORS[2]].to_numpy(float)
        idx = window_index(seg, 3)
        design = np.column_stack([np.ones(len(idx)), x[idx-1], x[idx-2]])
        coef = np.linalg.lstsq(design, x[idx], rcond=None)[0]
        tail = ExpTail(ar_residual(tr, seg, coef))
        state = dict(version=VERSION, model=MODEL, split=split, mean=scorer.scaler.mean_, scale=scorer.scaler.scale_,
                     ar2=coef, preprocess=D.QUANTIZATION["matched"], sampling_seconds=D.DT,
                     tails={"magnitude":scorer.tail_z3.state(), "sine6":ExpTail(sine_score(x,seg,6)).state(),
                            "sine8":ExpTail(sine_score(x,seg,8)).state(), "dynamics":tail.state()},
                     calibration=[], calibration_unit="recording_segment_max", input_hashes=input_hashes or {},
                     base_code_sha256=code_sha256(), selection="exploratory; original abnormal data previously observed")
        model = cls(state)
        cf = D.quantize(D.inputs_only(calibration), "matched")
        sg = layout(cf)[1]
        # 보정 단위 = 알림 단위(기록구간 안 50행 블록). 대회 자료는 기록구간과 같다.
        model.cal = segment_max(model.components(cf, sg)["score"], alert_units(sg, D.segment_positions(sg)[0]))
        if not len(model.cal) or not np.isfinite(model.cal).all():
            raise ValueError("유효한 보정 구간 부족")
        model.state["calibration"] = model.cal
        return model

    def components(self, frame, seg):
        z = (frame[D.SENSORS].to_numpy(float) - self.mean) / self.scale
        mag = np.abs(z).max(axis=1)
        pos, _ = D.segment_positions(seg)
        cur = frame[D.SENSORS[2]].to_numpy(float)
        s6, s8 = sine_score(cur, seg, 6), sine_score(cur, seg, 8)
        residual = ar_residual(frame, seg, self.coef)
        gz = self.tails["magnitude"](mag)
        gs = np.where(pos < 7, self.tails["sine6"](s6), self.tails["sine8"](s8))
        ga = self.tails["dynamics"](residual)
        return dict(magnitude=mag, current_residual=residual, g_magnitude=gz, g_waveform=gs, g_dynamics=ga,
                    waveform_window=np.where(pos < 7, 6, 8), score=np.fmax(np.fmax(gz, gs), ga),
                    magnitude_sensor=np.asarray(D.SENSORS)[np.abs(z).argmax(axis=1)])

    def predict(self, frame, alpha=.01, prior=None, *, time_state=None):
        if alpha not in ALPHAS:
            raise ValueError(f"alpha는 {ALPHAS} 중 하나여야 한다")
        from probability import DEFAULT_PRIOR, posterior
        prior = DEFAULT_PRIOR if prior is None else float(prior)
        if not 0 < prior < 1:
            raise ValueError("사전 비율은 0과 1 사이여야 한다")
        status, seg, order_codes = layout_with_order(frame, time_state=time_state)
        if len(frame) == 0:
            return pd.DataFrame(columns=["row_id","record_id","timestamp","status","position","score","p_value","alarm","notification","reason","action",
                                         "is_scored","anomaly_score","criterion","model_id","protocol_version","alert_unit","beyond_calibration_length",
                                         "alert_level","escalation","likelihood_ratio","anomaly_probability","probability_prior",
                                         "record_likelihood_ratio","record_probability","incident_id","incident_notification",
                                         "incident_escalation","incident_update","record_current_rms","operating_state","time_order_event"])
        pos, _ = D.segment_positions(seg)
        clean = D.inputs_only(frame)
        for c in D.SENSORS:
            clean[c] = pd.to_numeric(clean[c], errors="coerce").where(status == "ok")
        state_rms, state_labels = current_states(clean[D.SENSORS[2]].to_numpy(float), seg)
        clean = D.quantize(clean, "matched")
        comp = self.components(clean, seg)
        p = conformal_p(self.cal, comp["score"])
        alarm = np.isfinite(p) & (p <= alpha)
        evidence = np.column_stack([comp[k] for k in ("g_magnitude","g_waveform","g_dynamics")])
        active = np.column_stack([conformal_p(self.cal, evidence[:,k]) <= alpha for k in range(3)])
        reasons, actions = [], []
        for i in range(len(frame)):
            if status[i] != "ok":
                reasons.append("invalid_input"); actions.append("수집 상태 확인")
            elif not alarm[i]:
                reasons.append(""); actions.append("관측 지속")
            else:
                names = [name for name,yes in zip(("magnitude","waveform","dynamics"),active[i]) if yes]
                reasons.append("+".join(names))
                current = comp["magnitude_sensor"][i] == D.SENSORS[2]
                actions.append(action_for(active[i,0] and not current, active[i,0] and current, active[i,1:].any()))
        out = pd.DataFrame(dict(row_id=np.arange(len(frame)), record_id=seg, timestamp=frame[D.TIME].astype(str).to_numpy(),
                                status=status, position=pos, score=comp["score"], p_value=p, alarm=alarm.astype(int),
                                reason=reasons, action=actions, alpha=alpha, **{k:v for k,v in comp.items() if k != "score"}))
        # v1 예측 계약(PLAN §7)과의 대응: is_scored·anomaly_score(1−p)·criterion·model_id. 결과 파일만으로 출처를 알 수 있게 한다.
        out["is_scored"] = np.isfinite(comp["score"]).astype(int)
        out["anomaly_score"] = 1 - p
        out["criterion"] = "conformal"
        out["model_id"] = f"{MODEL}_{self.state.get('split', 'custom')}"
        out["protocol_version"] = VERSION
        out["alert_unit"] = pos // ALERT_UNIT_ROWS
        out["beyond_calibration_length"] = (pos >= ALERT_UNIT_ROWS).astype(int)   # 대회 보정 기록구간(최대 50행)보다 긴 연속 입력
        out["notification"] = first_alerts(seg, out.alert_unit, alarm)
        out["alert_level"], out["escalation"] = alert_levels(seg, out.alert_unit, alarm)
        times = pd.to_datetime(out.timestamp, format="mixed", utc=True, errors="coerce")
        inc = incident_columns(alarm, out.reason.to_numpy(), times, status == "ok", order_codes)
        out["incident_id"], out["incident_notification"], out["incident_escalation"], out["incident_update"] = inc.T
        # 이상 확률: 경보와 무관한 별도 층. 보정기가 없으면 결측. LR은 사전 비율과 무관하고 확률은 prior에 조건부다.
        lr = self.probability.likelihood_ratio(comp["score"]) if self.probability is not None else np.full(len(frame), np.nan)
        out["likelihood_ratio"] = lr
        out["anomaly_probability"] = posterior(lr, prior)
        out["probability_prior"] = prior
        # 기록구간 확률: 기록 안에서 지금까지의 최대 우도비(인과). 확률은 점수에 단조이므로 기록 최대 점수의 확률과 같다.
        out["record_likelihood_ratio"] = record_running_max(lr, seg)
        out["record_probability"] = posterior(out.record_likelihood_ratio.to_numpy(), prior)
        out["record_current_rms"], out["operating_state"] = state_rms, state_labels
        out["time_order_event"] = order_codes.astype(int)      # 0 없음, 1 판정 보류, 2 앞 행을 튄 행으로 확인, 3 새 기준, 4 새 기준을 잡으며 앞 튄 행을 확인
        return out

    def save(self, path):
        payload = D.to_jsonable(self.state)
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)
        envelope = dict(sha256=hashlib.sha256(canonical.encode()).hexdigest(), state=payload)
        path = Path(path); path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(envelope,ensure_ascii=False,indent=2,allow_nan=False), encoding="utf-8")

    @classmethod
    def load(cls, path):
        envelope = json.loads(Path(path).read_text(encoding="utf-8"))
        canonical = json.dumps(envelope["state"],ensure_ascii=False,sort_keys=True,allow_nan=False)
        if hashlib.sha256(canonical.encode()).hexdigest() != envelope["sha256"]:
            raise ValueError("모델 상태 해시 불일치")
        if envelope["state"]["base_code_sha256"] != code_sha256():
            raise ValueError("학습 당시와 v1 의존 코드가 다름; 재학습 필요")
        obj = cls(envelope["state"])
        if not len(obj.cal) or not np.isfinite(obj.cal).all():
            raise ValueError("보정값 누락/손상")
        return obj


def load_bundle(model_path):
    """모델과, 같은 폴더에 있으면 확률 보정기(probability_<split>.json)를 함께 불러온다."""
    from probability import ProbabilityCalibrator
    model = GuardModel.load(model_path)
    path = Path(model_path).with_name(f"probability_{model.state.get('split', 'custom')}.json")
    if path.is_file():
        model.attach_probability(ProbabilityCalibrator.load(path))
    return model


class StreamDetector:
    """청크 크기에 무관한 추론. 센서 원본은 직전 7행만 유지한다.

    수집 시각 순서는 TimeOrder 규칙을 따른다(튄 한 행도 판정하되 그 뒤로 원래 시간축을 잇고, 이른 시각은 보류하다가 정상 간격으로 이어지면 새 기준).
    잘못된 행·중복·샘플 누락은 경계가 된다. 센서 원본 7행 외에 그 앞까지의 순서 상태 하나를 유지한다.
    경보 단위(기록구간 안 50행 블록)의 첫 경보만 알리고,
    바로 앞 블록도 경보였으면 이어지는 이상으로 묶는다. 외부가 새 장치로 전환할 때는 새 인스턴스를 생성해야 한다.
    """
    def __init__(self, model, alpha=.01, prior=None):
        if alpha not in ALPHAS:
            raise ValueError("지원하지 않는 alpha")
        self.model, self.alpha, self.prior = model, alpha, prior
        self.tail = pd.DataFrame(columns=[D.TIME]+D.SENSORS)
        self.tail_records = np.array([], dtype=int)
        self.tail_positions = np.array([], dtype=int)
        self.tail_time_state = None   # tail보다 앞의 행까지 반영한 수집 시각 순서 상태(TimeOrder)
        self.rows_seen = 0
        self.alert_record = None      # 현재 기록구간 번호와 그 안에서 경보가 난 블록
        self.alerted_blocks = set()
        self.episode_alarms = 0       # 현재 건의 누적 경보 행(격상 판단)
        self.record_lr = np.nan       # 현재 기록구간의 지금까지 최대 우도비
        self.current_state = CurrentState()
        self.incidents = IncidentTracker()   # 기록구간을 넘는 사건 묶음(스트림 전체에서 이어진다)
        self.units = CollectionUnits()       # 사건 추적 단위(간격이 도착한 행 수로 설명되지 않는 곳에서 나뉜다)
        self.ref_valid = False               # 기준 시각을 마지막으로 옮긴 행이 사건 추적에 들어간 유효 행인가(튄 행 되돌리기, spike_rows와 같은 규칙)

    def push(self, frame):
        from probability import posterior
        layout(frame)
        if len(frame) == 0:
            return self.model.predict(frame,self.alpha,self.prior)
        incoming = D.inputs_only(frame)
        n_old = len(self.tail)
        both = pd.concat([self.tail,incoming],ignore_index=True) if n_old else incoming
        result = self.model.predict(both,self.alpha,self.prior,time_state=self.tail_time_state)
        rec = result.record_id.to_numpy().copy()
        positions = result.position.to_numpy().copy()
        if n_old:
            rec += self.tail_records[-1] - rec[n_old-1]
            continuation = rec == self.tail_records[-1]
            positions[continuation] += self.tail_positions[-1] - positions[n_old-1]
        result["record_id"], result["position"] = rec, positions
        result["alert_unit"] = positions // ALERT_UNIT_ROWS
        result["beyond_calibration_length"] = (positions >= ALERT_UNIT_ROWS).astype(int)
        result = result.iloc[n_old:].copy().reset_index(drop=True)
        result["row_id"] = np.arange(self.rows_seen,self.rows_seen+len(incoming))
        notifications, levels, escalations, record_lr, inc, state_rms, state_labels = [], [], [], [], [], [], []
        times = pd.to_datetime(result.timestamp, format="mixed", utc=True, errors="coerce")
        raw_current = pd.to_numeric(incoming[D.SENSORS[2]], errors="coerce").to_numpy(float)
        for r, t, value in zip(result.itertuples(), times, raw_current):
            if r.record_id != self.alert_record:
                self.alert_record, self.alerted_blocks, self.record_lr = r.record_id, set(), np.nan
                self.current_state = CurrentState()
            rms, state = self.current_state.update(value if r.status == "ok" else np.nan)
            state_rms.append(rms); state_labels.append(state)
            self.record_lr = np.fmax(self.record_lr, r.likelihood_ratio)
            record_lr.append(self.record_lr)
            notify = bool(r.alarm) and r.alert_unit not in self.alerted_blocks and r.alert_unit - 1 not in self.alerted_blocks
            level = escalate = 0
            if r.alarm:
                if notify:
                    self.episode_alarms = 0
                self.episode_alarms += 1
                level = 2 if self.episode_alarms >= ESCALATION_ALARM_ROWS else 1
                escalate = int(self.episode_alarms == ESCALATION_ALARM_ROWS)
                self.alerted_blocks = {b for b in self.alerted_blocks if b >= r.alert_unit - 1} | {r.alert_unit}
            notifications.append(int(notify)); levels.append(level); escalations.append(escalate)
            if r.time_order_event in SPIKE_EVENTS:
                self.units.undo()
                if self.ref_valid:
                    self.incidents.undo()
            accepted = not pd.isna(t) and r.time_order_event != ORDER_HELD
            run, block = self.units.step(t, accepted, r.time_order_event == ORDER_HELD)
            inc.append(self.incidents.update(run, block, bool(r.alarm), r.reason, t, r.status == "ok"))
            if accepted:
                self.ref_valid = r.status == "ok"
        result["notification"], result["alert_level"], result["escalation"] = notifications, levels, escalations
        result["record_likelihood_ratio"] = record_lr
        inc = np.asarray(inc, dtype=int).reshape(-1, 4)
        result["incident_id"], result["incident_notification"], result["incident_escalation"], result["incident_update"] = inc.T
        result["record_probability"] = posterior(np.asarray(record_lr, float), result.probability_prior.to_numpy(float))
        result["record_current_rms"], result["operating_state"] = state_rms, state_labels
        self.rows_seen += len(incoming)
        dropped = len(both) - 7
        if dropped > 0:
            discarded_times = pd.to_datetime(both[D.TIME].iloc[:dropped], format="mixed", utc=True, errors="coerce")
            _, self.tail_time_state = timestamp_order(discarded_times, self.tail_time_state)
        self.tail = both.iloc[-7:].copy().reset_index(drop=True)
        self.tail_records, self.tail_positions = rec[-7:].copy(), positions[-7:].copy()
        return result


PRIORITY_KEYS = {
    "evidence_share_peak": ("evidence_count", "alarm_share", "peak_score"),          # 사이클1 키(비교용)
    "level_evidence_share_peak": ("level", "evidence_count", "alarm_share", "peak_score"),
    "level_evidence_peak_share": ("level", "evidence_count", "peak_score", "alarm_share"),
    "level_peak": ("level", "peak_score"),
}
PRIORITY_KEY = "level_evidence_share_peak"


def priority_ranks(queue, key=None):
    """이상 라벨 없이 정한 정렬 키로 순위를 매긴다(1이 먼저). 동점은 시간 순서."""
    cols = PRIORITY_KEYS[key or PRIORITY_KEY]
    order = queue.sort_values(list(cols), ascending=False, kind="stable").index
    ranks = pd.Series(0, index=queue.index)
    ranks.loc[order] = np.arange(1, len(queue) + 1)
    return ranks.astype(int)


def cases(predictions):
    """점검 대기열. 고장 사건 수가 아니라, 같은 기록구간에서 경보가 이어진 블록 묶음 하나가 한 건이다(대회 자료는 기록구간당 한 건).

    - level: 경보 행이 ESCALATION_ALARM_ROWS 이상이면 2(점검 요청), 아니면 1(주의). escalation_*: 격상 행과 기록 시작·첫 경보 기준 지연.
    - suspect_from/to: 건 앞뒤로 가장 가까운 경보 없는 유효 단위(수집 오류·튄 행 제외)의 끝·시작 시각. 그사이 만든 가공품이 품질 확인 대상이다. 없거나
      SUSPECT_MAX_GAP_S보다 멀면 열림(진행 중·수집 공백).
    - priority_rank: 이상 라벨 없이 정한 정렬 키(PRIORITY_KEY).
    """
    p = predictions
    if not len(p) or not p.alarm.eq(1).any():
        return pd.DataFrame()
    block = p.alert_unit.to_numpy() if "alert_unit" in p else p.position.to_numpy() // ALERT_UNIT_ROWS
    episode = episode_ids(p.record_id.to_numpy(), block, p.alarm.eq(1).to_numpy())
    blocks_of_rows = pd.Series(block, index=p.index)
    time = pd.to_datetime(p.timestamp, format="mixed", utc=True, errors="coerce")
    unit_key = pd.Series(list(zip(p.record_id.to_numpy(), block)), index=p.index)
    spike = np.zeros(len(p), bool)            # 튄 행은 시각이 틀려 품질 시간창의 경계가 되지 못한다(검토 3 R3-06)
    if "time_order_event" in p:
        target = spike_rows(p.time_order_event.to_numpy(), time.notna().to_numpy())
        spike[target[target >= 0]] = True
    units = pd.DataFrame(dict(key=unit_key, t=time, a=p.alarm.eq(1), valid=p.status.eq("ok") & ~spike, ep=episode)).groupby("key", sort=False).agg(
        start=("t", "min"), end=("t", "max"), alarmed=("a", "any"), valid=("valid", "all"), ep=("ep", "max")).reset_index()
    result = []
    for ep, group in p.groupby(episode, sort=True):
        if ep == 0:
            continue
        flagged = group[group.alarm.eq(1)]
        first = flagged.iloc[0]
        reasons = sorted(set("+".join(flagged.reason).split("+")) - {""})
        magnitude = flagged[flagged.reason.str.contains("magnitude")].magnitude_sensor if "magnitude_sensor" in flagged else pd.Series(dtype=str)
        sensors = sorted(set(magnitude))
        shape = bool({"waveform", "dynamics"} & set(reasons))
        level = 2 if len(flagged) >= ESCALATION_ALARM_ROWS else 1
        second = flagged.iloc[ESCALATION_ALARM_ROWS - 1] if level == 2 else None
        members = np.flatnonzero(units.ep.to_numpy() == ep)
        before = units.iloc[:members.min()]; before = before[~before.alarmed & before.valid]
        after = units.iloc[members.max() + 1:]; after = after[~after.alarmed & after.valid]
        start = before.end.iloc[-1] if len(before) else pd.NaT
        end = after.start.iloc[0] if len(after) else pd.NaT
        ep_start, ep_end = units.start.iloc[members.min()], units.end.iloc[members.max()]
        if pd.notna(start) and not 0 <= (ep_start - start).total_seconds() <= SUSPECT_MAX_GAP_S:
            start = pd.NaT          # 역순이거나 앞 정상 기록이 너무 멀면 시작을 모른다
        if pd.notna(end) and not 0 <= (end - ep_end).total_seconds() <= SUSPECT_MAX_GAP_S:
            end = pd.NaT
        result.append(dict(case_uid=int(first.row_id), incident_id=int(first.incident_id) if "incident_id" in first else 0,
                           row_from=int(group.row_id.min()), row_to=int(group.row_id.max()),
                           record_id=int(first.record_id), first_row=int(first.row_id), first_timestamp=first.timestamp,
                           first_alarm_position=int(first.position), detection_delay_s=float(first.position*D.DT),
                           alarm_rows=len(flagged), observed_rows=len(group), peak_score=float(flagged.score.max()),
                           min_p=float(flagged.p_value.min()), evidence="+".join(reasons),
                           action=action_for(any(x != D.SENSORS[2] for x in sensors), D.SENSORS[2] in sensors, shape),
                           magnitude_sensors="+".join(sensors), alarm_share=len(flagged) / len(group),
                           alert_units=int(blocks_of_rows.loc[group.index].nunique()),
                           beyond_calibration_length=int(group.position.max() >= ALERT_UNIT_ROWS),
                           level=level, level_name=LEVEL_NAMES[level],
                           escalation_row=int(second.row_id) if second is not None else np.nan,
                           escalation_delay_s=float(second.position * D.DT) if second is not None else np.nan,
                           escalation_after_first_s=float((second.position - first.position) * D.DT) if second is not None else np.nan,
                           suspect_from=start.isoformat() if pd.notna(start) else "", suspect_to=end.isoformat() if pd.notna(end) else "",
                           suspect_seconds=float((end - start).total_seconds()) if pd.notna(start) and pd.notna(end) else np.nan,
                           suspect_open=int(pd.isna(start) or pd.isna(end)), quality_action=QUALITY_ACTIONS[level],
                           evidence_count=len(reasons),
                           record_current_rms=float(group.record_current_rms.iloc[-1]) if "record_current_rms" in group else np.nan,
                           operating_state=str(group.operating_state.iloc[-1]) if "operating_state" in group else "short",
                           first_alarm_operating_state=str(first.get("operating_state", "short")),
                           max_likelihood_ratio=float(flagged.likelihood_ratio.max()) if "likelihood_ratio" in flagged else np.nan,
                           max_probability=float(flagged.anomaly_probability.max()) if "anomaly_probability" in flagged else np.nan))
    queue = pd.DataFrame(result)
    queue["priority_rank"] = priority_ranks(queue)
    return queue


def incidents(queue, predictions=None):
    """사건 대기열: 건(case)을 사건 번호로 묶는다. 사건마다 1·2단계 알림은 한 번씩이다. 순위는 건과 같은 규칙(이상 라벨 없이 정함).
    단계는 사건 전체 경보 행의 누적으로 정한다. 격상 행은 건의 시간순 누적으로 복원하고, predictions가 있으면 직접 대조한다."""
    if not len(queue) or "incident_id" not in queue:
        return pd.DataFrame()
    esc = {}
    if predictions is not None and "incident_escalation" in predictions:
        e = predictions[predictions.incident_escalation.eq(1)]
        esc = dict(zip(e.incident_id.astype(int), e.row_id.astype(int)))
    rows = []
    for inc, g in queue.sort_values("first_row").groupby("incident_id", sort=True):
        ev = sorted(set("+".join(g.evidence).split("+")) - {""})
        alarm_rows = int(g.alarm_rows.sum())
        level = 2 if alarm_rows >= ESCALATION_ALARM_ROWS else 1
        escalation_row = np.nan
        before = 0
        for case in g.itertuples():
            if before + case.alarm_rows >= ESCALATION_ALARM_ROWS:
                escalation_row = case.first_row if before == ESCALATION_ALARM_ROWS - 1 else case.escalation_row
                break
            before += case.alarm_rows
        escalation_row = esc.get(int(inc), escalation_row)
        opened = int(g.suspect_open.max())
        rows.append(dict(incident_id=int(inc), first_row=int(g.first_row.min()), first_timestamp=g.first_timestamp.iloc[0], last_case_timestamp=g.first_timestamp.iloc[-1],
                         cases=len(g), case_uids="+".join(map(str, g.case_uid)), records="+".join(map(str, g.record_id)), level=level, level_name=LEVEL_NAMES[level],
                         evidence="+".join(ev), evidence_count=len(ev), alarm_rows=alarm_rows, observed_rows=int(g.observed_rows.sum()),
                         operating_state="+".join(dict.fromkeys(g.operating_state.astype(str))) if "operating_state" in g else "short",
                         alarm_share=float(g.alarm_rows.sum() / g.observed_rows.sum()), peak_score=float(g.peak_score.max()),
                         max_probability=float(g.max_probability.max()) if g.max_probability.notna().any() else np.nan,
                         max_likelihood_ratio=float(g.max_likelihood_ratio.max()) if g.max_likelihood_ratio.notna().any() else np.nan,
                         suspect_from=g.suspect_from.iloc[0], suspect_to=g.suspect_to.iloc[-1], suspect_open=opened, quality_action=QUALITY_ACTIONS[level],
                         action=g.sort_values("priority_rank").action.iloc[0], escalation_row=escalation_row))
    out = pd.DataFrame(rows)
    out["priority_rank"] = priority_ranks(out)
    return out


def time_order_events(predictions):
    """(판정 보류 행 수, 새 기준 채택 횟수, 미래로 튄 행을 확인한 횟수). 기록 끝의 튐(ORDER_SPIKE_REANCHOR)은 튐으로 센다.
    time_order_event 열이 없는 옛 예측은 상태로 센다."""
    if not len(predictions):
        return 0, 0, 0
    if "time_order_event" in predictions:
        e = predictions.time_order_event.to_numpy()
        return int((e == ORDER_HELD).sum()), int((e == ORDER_REANCHOR).sum()), int(np.isin(e, SPIKE_EVENTS).sum())
    held = predictions.status.eq("bad_time_order").to_numpy()
    return int(held.sum()), int((predictions.status.eq("ok").to_numpy()[1:] & held[:-1]).sum()), 0


def timing_warning(predictions):
    """수집 시각 순서 문제(판정 보류·새 기준 채택)와, 짧게 쪼개진 기록의 시각 간격 문제를 안내한다."""
    held, resumed, skipped = time_order_events(predictions)
    warnings = []
    if held:
        warnings.append(f"역순 수집 시각 {held}행: 기준 시각보다 이르므로 판정을 보류했습니다"
                        + (f"(정상 간격으로 이어진 이른 시각을 새 기준으로 받아들인 곳 {resumed}곳)" if resumed else "")
                        + ". 수집 PC 시각과 입력 순서를 확인하세요.")
    if skipped:
        e = predictions.time_order_event.to_numpy() if "time_order_event" in predictions else np.zeros(0, int)
        held_before = []
        for i in np.flatnonzero(e == ORDER_SPIKE_REANCHOR):       # 새 기준 앞에 이어진 보류 행 수
            j = i - 1
            while j >= 0 and e[j] == ORDER_HELD:
                j -= 1
            held_before.append(i - 1 - j)
        span = (f"{min(held_before)}행" if min(held_before) == max(held_before) else f"{min(held_before)}~{max(held_before)}행") if held_before else ""
        warnings.append(f"튄 수집 시각 {skipped}곳: 튄 행으로 보고 그 뒤부터 원래 시간축으로 판정했습니다"
                        + (f"(튄 행 바로 뒤가 새 기록인 {len(held_before)}곳은 그 뒤 {span}을 보류한 뒤 이었습니다)" if held_before else "")
                        + ". 늦게 도착한 행 때문에 정상 행을 튄 행으로 본 경우도 여기에 셉니다. 튄 행 주변은 기록이 끊겨 첫 창이 다시 찹니다.")
    ok = predictions[predictions.status.eq("ok")] if len(predictions) else predictions
    if len(ok) < 50:
        return " ".join(warnings)
    mean_len = len(ok) / max(ok.record_id.nunique(), 1)
    if mean_len >= SHORT_RECORD_WARN:
        return " ".join(warnings)
    warnings.append(f"수집 시각 간격 확인: 평균 기록 길이 {mean_len:.1f}행. 이웃 행 간격이 0.1초 ± {TIME_TOL_S * 1000:.0f} ms를 벗어나면 기록이 쪼개져 "
                    "파형·예측 오차 성분을 계산하지 못한다(미탐 증가).")
    return " ".join(warnings)
