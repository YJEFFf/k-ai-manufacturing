"""두 단계 경보의 행 단위 스트림 구현: 1단계 "주의" = v2 + R1(사건 지속), 2단계 "점검 요청" = v2에 R2(교차 확인)를 먼저 적용한 뒤 R1.

제출 예측 파일(tvt/outputs/test_predictions_{A,B}.csv)의 locked_v2_R1_realtime(1단계)·final_v2_R1_R2_realtime(2단계) 열을 만든
규칙을 행이 들어오는 순서대로 한 행씩 적용한다. 대응하는 공식 코드(준용 claude/code/press/tvt):
- v2 성분 점수·conformal p: 01_scores.py(GuardModel.components, 검증 정상 기록별 최대 점수로 보정)
- R2: evalcore.own_alarm(h2). 크기 성분만 p ≤ α이고 그 행까지의 기록 전류 사인 적합 R²가 r2_ref 이상이면 2단계 입력에서 뺀다
- R1: lib.stream_rules(latch=True). 직전 기록(끝난 지 60초 안)이 '확인된 이상'(자기 경보 2행 이상 또는 이어받은 경보가 끝까지
  안 풀림)이면 새 기록 첫 행부터 경보를 이어받고, 전류 R²가 r2_ref 이상인 행(8행째부터)에서 푼다
- 상수 GAP_S·CONFIRM_ROWS·R2_Q·R2_MIN_LEN·F0와 sine_r2·prefix_r2는 lib.py와 같은 값·같은 식이다(test_stages.py가 대조)

고정 상태(StageState): 정상 학습·보정한 v2 GuardModel(표준화·꼬리 분포·AR(2)·conformal 보정값), α, r2_ref(정상 학습 기록 prefix R²의
0.5% 분위). 스트림은 미래 행을 쓰지 않는다. 기록 경계는 GuardModel.layout과 같은 규칙(이웃 행 간격이 0.1초 ± 20 ms를 벗어나거나
수집 오류 행)이고, 경계에서 파형 창·AR 창·prefix R²를 새로 시작한다. 묶음 크기(1행·임의 청크)와 무관하게 같은 값을 낸다.

이 모듈은 import할 때 파일을 읽거나 쓰지 않는다(model.py가 v1 모듈 경로를 sys.path에 넣는 것은 press_guard 공통 동작이다).
수집 오류·시각 순서 보류 행은 1행짜리 기록으로 다룬다(판정 없음, R1 해제 근거가 되지 못함). 대회 자료에는 이런 행이 없어
제출 예측 파일과의 대조 범위 밖이다.
"""
from __future__ import annotations

import hashlib
import json
import pickle
from dataclasses import dataclass

import numpy as np
import pandas as pd

from model import D, GuardModel, TimeOrder, ORDER_HELD, SAMPLE_NS, TIME_TOL_NS, conformal_p, layout
from model import sine_score as v2_sine_score

GAP_S = 60.0                 # R1: 직전 기록이 끝난 뒤 이 시간 안에 시작한 기록만 이어받는다(lib.GAP_S)
CONFIRM_ROWS = 2             # R1: 자기 경보가 이 행 수 이상이면 '확인된 이상'(lib.CONFIRM_ROWS)
R2_Q = 0.005                 # r2_ref = 정상 학습 prefix R²의 0.5% 분위(lib.R2_Q)
R2_MIN_LEN = 8               # prefix R²는 기록 8행째부터 계산한다(lib.R2_MIN_LEN)
F0 = 0.6064 / 10             # 정상 전류 겉보기 주기(표본당, lib.F0)
ALPHA = 0.01                 # 운영 α(보고서 2.5절)
EVENT_GAP_S = 60.0           # 경보 사건: 60초 안에 이어지는 경보 행은 한 사건(보고서 4.2절)
TAIL_ROWS = 7                # v2 성분에 필요한 직전 행 수(8행 파형 창)
COMPONENTS = ("magnitude", "waveform", "dynamics")
STAGE_NAMES = {1: "주의", 2: "점검 요청"}
COLUMNS = ("row", "timestamp", "status", "record", "position", "score", "p_value", "g_magnitude", "g_waveform", "g_dynamics",
           "p_magnitude", "p_waveform", "p_dynamics", "magnitude_sensor", "v2_alarm", "evidence", "prefix_r2", "wave_judgeable",
           "wave_ok", "r2_hold", "own1", "own2", "stage1", "stage2", "inherited1", "inherited2", "released1", "released2",
           "level", "insufficient", "event1", "event1_start", "event2", "event2_start")
_QUANT = D.QUANTIZATION["matched"]


def sine_r2(x) -> float:
    """주파수를 F0로 고정한 사인 + 절편 적합의 R²(lib.sine_r2와 같은 식)."""
    x = np.asarray(x, float)
    n = np.arange(len(x))
    X = np.column_stack([np.ones(len(x)), np.sin(2 * np.pi * F0 * n), np.cos(2 * np.pi * F0 * n)])
    b, *_ = np.linalg.lstsq(X, x, rcond=None)
    sst = ((x - x.mean()) ** 2).sum()
    return float(1 - ((x - X @ b) ** 2).sum() / sst) if sst > 0 else np.nan


def prefix_r2(current, rec) -> np.ndarray:
    """각 행까지(포함) 같은 기록 안 전류의 sine_r2. 기록 앞 7행은 NaN(lib.prefix_r2와 같은 식, 일괄 계산용)."""
    current, rec = np.asarray(current, float), np.asarray(rec)
    out = np.full(len(current), np.nan)
    for r in pd.unique(rec):
        idx = np.flatnonzero(rec == r)
        for j in range(R2_MIN_LEN - 1, len(idx)):
            out[idx[j]] = sine_r2(current[idx[: j + 1]])
    return out


def fit_r2_ref(train: pd.DataFrame) -> float:
    """R2·R1 파형 기준: 정상 학습 기록의 prefix R² 0.5% 분위(tvt 01_scores·04 fit_split과 같은 계산)."""
    q = D.quantize(D.inputs_only(train), "matched")
    _, seg = layout(train)
    return float(np.nanquantile(prefix_r2(q[D.SENSORS[2]].to_numpy(float), seg), R2_Q))


def model_sha256(model: GuardModel) -> str:
    """GuardModel.save와 같은 정규 JSON의 SHA-256(저장 파일의 sha256 필드와 같은 값)."""
    payload = D.to_jsonable(model.state)
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class StageState:
    """두 단계 경보의 고정 상태. 스트림은 이 값을 바꾸지 않는다."""
    model: GuardModel
    r2_ref: float
    alpha: float = ALPHA

    @classmethod
    def fit(cls, train, calibration, *, split="custom", alpha=ALPHA, input_hashes=None):
        """정상 학습·보정 구간으로 v2를 학습·보정하고(GuardModel.fit) r2_ref를 정한다."""
        return cls(GuardModel.fit(train, calibration, split=split, input_hashes=input_hashes), fit_r2_ref(train), alpha)

    def summary(self) -> dict:
        cal = np.sort(np.asarray(self.model.cal, float))[::-1]
        allowed = int(np.floor(self.alpha * (len(cal) + 1))) - 1   # 경보 ⇔ 점수 > (allowed+1)번째 큰 보정값
        return dict(split=self.model.state.get("split"), alpha=self.alpha, r2_ref=self.r2_ref, calibration_units=int(len(cal)),
                    score_threshold=float(cal[allowed]) if 0 <= allowed < len(cal) else None,
                    min_p_attainable=1 / (len(cal) + 1), model_sha256=model_sha256(self.model),
                    constants=dict(GAP_S=GAP_S, CONFIRM_ROWS=CONFIRM_ROWS, R2_Q=R2_Q, R2_MIN_LEN=R2_MIN_LEN, F0=F0,
                                   EVENT_GAP_S=EVENT_GAP_S))


class _Latch:
    """R1 한 단계의 상태(lib.stream_rules의 on·prev_confirmed·prev_end를 행 단위로 나눈 것)."""
    __slots__ = ("on", "own_rows", "confirmed", "end", "started")

    def __init__(self):
        self.on, self.own_rows, self.confirmed, self.end, self.started = False, 0, False, None, False

    def begin(self, t):
        """새 기록의 첫 행 시각 t(np.datetime64[ns]). 직전 기록을 마감하고 이어받기 여부를 정한다."""
        if self.started:   # 직전 기록: 자기 경보 2행 이상이거나 이어받은 경보가 끝까지 안 풀렸으면 '확인된 이상'
            self.confirmed = self.own_rows >= CONFIRM_ROWS or self.on
        self.on = bool(self.confirmed and self.end is not None and t is not None
                       and (t - self.end) / np.timedelta64(1, "s") <= GAP_S)
        self.own_rows, self.started = 0, True

    def step(self, own, wave_ok, t):
        """(경보, 이어받음, 해제). 해제 행은 자기 경보만 남는다(lib: break 전에 경보를 붙이지 않음)."""
        inherited = released = False
        if self.on:
            if wave_ok:
                self.on, released = False, True
            else:
                inherited = True
        self.own_rows += int(own)
        if t is not None:
            self.end = t
        return bool(own or inherited), inherited, released


class _Events:
    """60초 묶음 경보 사건(단계별). 직전 경보 행과 60초를 넘게 떨어진 경보 행이 새 사건을 연다."""
    __slots__ = ("count", "last")

    def __init__(self):
        self.count, self.last = 0, None

    def step(self, alarm, t):
        if not alarm:
            return 0, False
        if t is None or self.last is None:          # 시각을 모르는 행은 진행 중 사건을 잇는다
            start = self.last is None
        else:
            start = (t - self.last) / np.timedelta64(1, "s") > EVENT_GAP_S
        self.count += int(start)
        if t is not None:
            self.last = t
        return self.count, bool(start)


def r1_rows(times, records, own, wave_ok):
    """규칙 층만: 행 순서대로 R1을 적용한 (경보, 이어받음, 해제). lib.stream_rules(latch=True)의 행 단위 판(시험·점검용).
    times는 datetime64[ns] 배열, records는 행마다 기록 번호(같은 기록은 연속), own·wave_ok는 bool 배열."""
    latch, prev = _Latch(), object()
    times = np.asarray(times, "datetime64[ns]")
    out = np.zeros((len(own), 3), bool)
    for i, (t, r, a, ok) in enumerate(zip(times, records, own, wave_ok)):
        if r != prev:
            latch.begin(t)
            prev = r
        out[i] = latch.step(bool(a), bool(ok), t)
    return out[:, 0], out[:, 1], out[:, 2]


def _quantize(x: np.ndarray) -> np.ndarray:
    """D.quantize(..., "matched")와 같은 식(진동 1e-4, 전류 1.1920929 격자 반올림)을 배열에 적용한다."""
    out = np.array(x, float)
    out[:, :2] = np.round(out[:, :2] / _QUANT["vib"]) * _QUANT["vib"]
    out[:, 2] = np.round(out[:, 2] / _QUANT["cur"]) * _QUANT["cur"]
    return out


def _number(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


class TwoStageStream:
    """행을 받은 순서대로 넣으면 행마다 1·2단계 경보와 근거를 돌려주는 상태 기계.

    push(frame)은 TimeStamp·AI0_Vibration·AI1_Vibration·AI2_Current 열이 있는 임의 길이의 묶음을, push_row는 한 행을 받는다.
    v2 성분: 여러 행이면 현재 기록의 직전 7행을 앞에 붙여 GuardModel.components를 그대로 부르고(StreamDetector와 같은 방식),
    한 행이면 그 행이 쓰는 창 하나(크기 즉시, AR(2) 3행, 파형 6행 또는 8행)만 같은 식으로 계산한다. 두 길의 값이 같다는 것을
    재생 검증·시험이 비트 단위로 확인한다. prefix R²는 현재 기록의 전류 전체로 다시 적합한다(기록 길이에 비례, 대회 자료 최대 50행).
    다른 설비·스트림은 새 인스턴스를 쓴다.
    """

    def __init__(self, state: StageState):
        self.state = state
        self.model, self.alpha, self.r2_ref = state.model, float(state.alpha), float(state.r2_ref)
        self.rows_seen = 0
        self.record = -1                    # 현재 기록 번호(0부터)
        self.position = 0                   # 현재 기록 안 다음 행의 위치
        self._order = TimeOrder()           # 수집 시각 순서(GuardModel.layout_with_order와 같은 규칙)
        self._prev_time = None              # 직전 입력 행의 시각(기록 경계 판정)
        self._prev_bad = False
        self._started = False
        self._tail = []                     # 현재 기록의 최근 7행(정밀도 맞춘 센서값)
        self._current = []                  # 현재 기록의 정밀도 맞춘 전류 전체(prefix R²)
        self._latch = {1: _Latch(), 2: _Latch()}
        self._events = {1: _Events(), 2: _Events()}

    # ---------- 공개 API ----------
    def push_row(self, timestamp, ai0, ai1, ai2) -> dict:
        """한 행(시각과 센서 세 값). 반환: COLUMNS 키의 dict."""
        t = pd.to_datetime(timestamp, format="mixed", utc=True, errors="coerce")
        values = np.array([[_number(ai0), _number(ai1), _number(ai2)]], float)
        return self._process([t], values, [str(timestamp)])[0]

    def push(self, frame: pd.DataFrame) -> pd.DataFrame:
        """임의 길이의 묶음. 반환: 행마다 COLUMNS 열."""
        missing = [c for c in [D.TIME] + D.SENSORS if c not in frame]
        if missing:
            raise KeyError(f"필수 열 없음: {missing}")
        frame = frame[[D.TIME] + D.SENSORS].reset_index(drop=True)
        if not len(frame):
            return pd.DataFrame(columns=COLUMNS)
        times = list(pd.to_datetime(frame[D.TIME], format="mixed", utc=True, errors="coerce"))
        values = frame[D.SENSORS].apply(pd.to_numeric, errors="coerce").to_numpy(float)
        return pd.DataFrame(self._process(times, values, frame[D.TIME].astype(str).tolist()), columns=COLUMNS)

    def mutable_state(self) -> dict:
        """고정 상태(모델)를 뺀, 스트림이 행마다 바꾸는 상태. 크기 측정·점검용."""
        return dict(rows_seen=self.rows_seen, record=self.record, position=self.position,
                    order={k: getattr(self._order, k) for k in TimeOrder._STATE}, prev_time=self._prev_time,
                    prev_bad=self._prev_bad, started=self._started, tail=[r.copy() for r in self._tail],
                    current=list(self._current),
                    latch={k: {s: getattr(v, s) for s in _Latch.__slots__} for k, v in self._latch.items()},
                    events={k: {s: getattr(v, s) for s in _Events.__slots__} for k, v in self._events.items()})

    def state_bytes(self) -> int:
        """mutable_state의 pickle 크기(바이트)."""
        return len(pickle.dumps(self.mutable_state(), protocol=pickle.HIGHEST_PROTOCOL))

    # ---------- 내부 ----------
    def _segment(self, times, values):
        """행마다 (상태, 새 기록 여부). GuardModel.layout_with_order와 같은 순서 판정·경계 규칙을 스트림 전체에 이어 적용한다."""
        n = len(values)
        status, new = np.full(n, "ok", dtype=object), np.zeros(n, bool)
        for i in range(n):
            t = times[i]
            code = self._order.step(t)
            if code == ORDER_HELD:
                status[i] = "bad_time_order"
            elif pd.isna(t):
                status[i] = "bad_timestamp"
            elif not np.isfinite(values[i]).all():
                status[i] = "bad_value"
            bad = status[i] != "ok"
            gap = (not pd.isna(t) and self._prev_time is not None and not pd.isna(self._prev_time)
                   and abs((t - self._prev_time).value - SAMPLE_NS) > TIME_TOL_NS)
            new[i] = (not self._started) or gap or bad or self._prev_bad
            self._started, self._prev_time, self._prev_bad = True, t, bad
        return status, new

    def _chunk_components(self, q, new):
        """여러 행: 현재 기록의 직전 7행을 앞에 붙여 GuardModel.components를 계산하고 새 행 부분만 돌려준다."""
        seg = self.record + np.cumsum(new)          # 새 행의 기록 번호(첫 행이 현재 기록을 이으면 같은 번호)
        if not new[0] and self._tail:
            q_all, seg_all = np.vstack([np.asarray(self._tail), q]), np.r_[np.full(len(self._tail), self.record), seg]
        else:
            q_all, seg_all = q, seg
        comp = self.model.components(pd.DataFrame(q_all, columns=D.SENSORS), seg_all)
        k = len(q_all) - len(q)
        return {key: np.asarray(comp[key])[k:] for key in ("score", "g_magnitude", "g_waveform", "g_dynamics", "magnitude_sensor")}

    def _row_components(self, q, new):
        """한 행: GuardModel.components와 같은 식을 이 행이 쓰는 창 하나로 계산한다(파형은 위치 5·6은 6행, 7부터 8행)."""
        m = self.model
        pos = 0 if new else self.position
        window = q[None, :] if new or not self._tail else np.vstack([np.asarray(self._tail), q[None, :]])
        cur = window[:, 2]
        z = (window[-1:] - m.mean) / m.scale
        gz = m.tails["magnitude"](np.abs(z).max(axis=1))
        if pos >= 7:
            gs = m.tails["sine8"](v2_sine_score(cur[-8:], np.zeros(8, int), 8)[-1:])
        else:
            s6 = v2_sine_score(cur[-6:], np.zeros(6, int), 6)[-1:] if pos >= 5 else np.array([np.nan])
            gs = m.tails["sine6"](s6)
        if pos >= 2:   # model.ar_residual과 같은 식
            x, idx = cur[-3:], np.array([2])
            residual = np.abs(x[idx] - m.coef[0] - m.coef[1] * x[idx - 1] - m.coef[2] * x[idx - 2])
        else:
            residual = np.array([np.nan])
        ga = m.tails["dynamics"](residual)
        return dict(score=np.fmax(np.fmax(gz, gs), ga), g_magnitude=gz, g_waveform=gs, g_dynamics=ga,
                    magnitude_sensor=np.asarray(D.SENSORS)[np.abs(z).argmax(axis=1)])

    def _process(self, times, values, stamps):
        n = len(values)
        status, new = self._segment(times, values)
        q = _quantize(np.where((status == "ok")[:, None], values, np.nan))
        comp = self._row_components(q[0], new[0]) if n == 1 else self._chunk_components(q, new)
        p = conformal_p(self.model.cal, comp["score"])
        cp = {c: conformal_p(self.model.cal, comp[f"g_{c}"]) for c in COMPONENTS}
        rows = []
        for i in range(n):
            t = times[i]
            t64 = None if pd.isna(t) else np.datetime64(t.value, "ns")
            if new[i]:
                self.record += 1
                self.position = 0
                self._current, self._tail = [], []
                for latch in self._latch.values():
                    latch.begin(t64 if t64 is not None else latch.end)
            self._current.append(q[i, 2])
            self._tail = (self._tail + [q[i]])[-TAIL_ROWS:]
            r2 = sine_r2(self._current) if len(self._current) >= R2_MIN_LEN else np.nan
            judgeable = bool(np.isfinite(r2))
            wave_ok = bool(judgeable and r2 >= self.r2_ref)
            act = {c: bool(np.isfinite(cp[c][i]) and cp[c][i] <= self.alpha) for c in COMPONENTS}
            v2 = bool(np.isfinite(p[i]) and p[i] <= self.alpha)
            mag_only = act["magnitude"] and not act["waveform"] and not act["dynamics"]
            hold = v2 and mag_only and wave_ok          # R2: 2단계 입력에서 뺀다(1단계에는 남는다)
            own = {1: v2, 2: v2 and not hold}
            out = {k: self._latch[k].step(own[k], wave_ok, t64) for k in (1, 2)}
            ev = {k: self._events[k].step(out[k][0], t64) for k in (1, 2)}
            ok = status[i] == "ok"
            rows.append(dict(
                row=self.rows_seen + i, timestamp=stamps[i], status=status[i], record=self.record, position=self.position,
                score=float(comp["score"][i]), p_value=float(p[i]), g_magnitude=float(comp["g_magnitude"][i]),
                g_waveform=float(comp["g_waveform"][i]), g_dynamics=float(comp["g_dynamics"][i]),
                p_magnitude=float(cp["magnitude"][i]), p_waveform=float(cp["waveform"][i]), p_dynamics=float(cp["dynamics"][i]),
                magnitude_sensor=str(comp["magnitude_sensor"][i]) if ok else "",
                v2_alarm=v2, evidence="+".join(c for c in COMPONENTS if act[c]) if v2 else "",
                prefix_r2=float(r2), wave_judgeable=judgeable, wave_ok=wave_ok, r2_hold=hold, own1=own[1], own2=own[2],
                stage1=out[1][0], stage2=out[2][0], inherited1=out[1][1], inherited2=out[2][1],
                released1=out[1][2], released2=out[2][2], level=2 if out[2][0] else (1 if out[1][0] else 0),
                insufficient=bool(not ok or not judgeable), event1=ev[1][0], event1_start=ev[1][1],
                event2=ev[2][0], event2_start=ev[2][1]))
            self.position += 1
        self.rows_seen += n
        return rows


def replay(state: StageState, frame: pd.DataFrame, chunk=None) -> pd.DataFrame:
    """frame을 처음 상태의 스트림에 흘린 결과. chunk가 None이면 한 번에, 정수면 그 행 수씩, 목록이면 그 크기 순서대로 넣는다."""
    stream = TwoStageStream(state)
    if chunk is None:
        return stream.push(frame)
    sizes = [int(chunk)] * (len(frame) // max(int(chunk), 1) + 1) if np.isscalar(chunk) else list(chunk)
    parts, i = [], 0
    for size in sizes:
        if i >= len(frame):
            break
        parts.append(stream.push(frame.iloc[i:i + size]))
        i += size
    if i < len(frame):
        parts.append(stream.push(frame.iloc[i:]))
    return pd.concat(parts, ignore_index=True)


def rows_by_row(state: StageState, frame: pd.DataFrame) -> pd.DataFrame:
    """한 행씩 push_row로 흘린 결과(지연 측정 없이)."""
    stream = TwoStageStream(state)
    cols = [D.TIME] + D.SENSORS
    rows = [stream.push_row(*r) for r in frame[cols].itertuples(index=False, name=None)]
    return pd.DataFrame(rows, columns=COLUMNS)
