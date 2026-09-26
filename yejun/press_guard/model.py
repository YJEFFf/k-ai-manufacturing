"""Press Guard v2: 정상 전류 동역학 + 초반 6→8 파형 + 센서 크기.

v1 모듈을 재사용하되 기존 패키지/동결 산출물은 수정하지 않는다.
고장 종류·잔여수명·고장 확률은 추정하지 않는다.
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
from press.scores import ExpTail, Scorer, _hats, window_index
from press.validation import code_sha256

VERSION = "press-guard-v2.0"
MODEL = "early6_ar2"
ALPHAS = (.01, .03, .05)
# 보정·알림 단위의 최대 길이. 대회 자료의 수집 묶음(기록구간)은 최대 50행(5초)이다. 더 긴 연속 입력은 기록구간 안에서
# 50행 블록으로 나눠 보정·알림한다. 대회 자료에서는 블록이 기록구간과 같으므로 결과가 바뀌지 않는다.
ALERT_UNIT_ROWS = 50
ACTIONS = dict(vibration="진동·부하 확인", vibration_and_current="진동·전류 함께 점검",
               current_magnitude="전류 크기·부하·계측 확인", current_magnitude_and_shape="전류 크기·파형·계측 확인",
               current_shape="전류 파형·계측 확인", invalid="수집 상태 확인")
# 경보 근거 → 확인 대상(가설) → 권장 확인. 조치 규칙(action_for)과 같은 내용이며 정비 결과로 검증한 것은 아니다.
DECISION_TABLE = (
    dict(evidence="크기(진동 센서)", check_target="펌프 상·하부 진동 증가: 체결·베어링·부하 변화(가설)", action=ACTIONS["vibration"]),
    dict(evidence="크기(전류 센서)", check_target="전류 크기 변화: 부하 증가 또는 계측 이상(가설)", action=ACTIONS["current_magnitude"]),
    dict(evidence="파형 또는 예측 오차(전류)", check_target="전류 파형 흐트러짐: 모터·전원·계측(가설)", action=ACTIONS["current_shape"]),
    dict(evidence="크기(진동) + 파형·예측 오차, 또는 구간 안에서 진동·전류 크기 모두", check_target="진동과 전류가 함께 변함(가설)", action=ACTIONS["vibration_and_current"]),
    dict(evidence="크기(전류) + 파형·예측 오차", check_target="전류 크기와 파형이 함께 변함(가설)", action=ACTIONS["current_magnitude_and_shape"]),
    dict(evidence="수집 오류(결측·비유한 값·시각 오류)", check_target="수집 경로·센서 연결", action=ACTIONS["invalid"]),
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


def layout(frame):
    missing = [c for c in [D.TIME]+D.SENSORS if c not in frame]
    if missing:
        raise KeyError(f"필수 열 없음: {missing}")
    # 자동 형식 추정은 청크 첫 행에 따라 달라진다. 각 행을 동일한 규칙으로 파싱한다.
    timestamp = pd.to_datetime(frame[D.TIME],format="mixed",utc=True,errors="coerce")
    values = frame[D.SENSORS].apply(pd.to_numeric,errors="coerce").to_numpy(float)
    status = np.full(len(frame),"ok",dtype=object)
    status[~np.isfinite(values).all(axis=1)] = "bad_value"
    status[timestamp.isna().to_numpy()] = "bad_timestamp"
    bad = status != "ok"
    boundary = timestamp.diff().dt.total_seconds().sub(D.DT).abs().gt(D.GAP_TOL).to_numpy() | bad
    boundary[1:] |= bad[:-1]
    if len(boundary): boundary[0] = False
    return status,np.cumsum(boundary)


def sine_score(current,seg,win):
    """행별 합산 순서를 고정해 BLAS 배치 크기 → ECDF 순위 변화를 차단한다."""
    x=np.asarray(current,float)
    result=np.full(len(x),np.nan)
    idx=window_index(seg,win)
    if not len(idx): return result
    windows=np.stack([x[i-win+1:i+1] for i in idx])
    sst=((windows-windows.mean(axis=1,keepdims=True))**2).sum(axis=1)
    best=np.full(len(idx),np.inf)
    for hat in _hats(win):
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

    def predict(self, frame, alpha=.01):
        if alpha not in ALPHAS:
            raise ValueError(f"alpha는 {ALPHAS} 중 하나여야 한다")
        status,seg = layout(frame)
        if len(frame) == 0:
            return pd.DataFrame(columns=["row_id","record_id","timestamp","status","position","score","p_value","alarm","notification","reason","action",
                                         "is_scored","anomaly_score","criterion","model_id","protocol_version","alert_unit","beyond_calibration_length"])
        pos, _ = D.segment_positions(seg)
        clean = D.inputs_only(frame)
        for c in D.SENSORS:
            clean[c] = pd.to_numeric(clean[c], errors="coerce").where(status == "ok")
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
        return out

    def save(self, path):
        payload = D.to_jsonable(self.state)
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)
        envelope = dict(sha256=hashlib.sha256(canonical.encode()).hexdigest(), state=payload)
        path = Path(path); path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(envelope,ensure_ascii=False,indent=2,allow_nan=False))

    @classmethod
    def load(cls, path):
        envelope = json.loads(Path(path).read_text())
        canonical = json.dumps(envelope["state"],ensure_ascii=False,sort_keys=True,allow_nan=False)
        if hashlib.sha256(canonical.encode()).hexdigest() != envelope["sha256"]:
            raise ValueError("모델 상태 해시 불일치")
        if envelope["state"]["base_code_sha256"] != code_sha256():
            raise ValueError("학습 당시와 v1 의존 코드가 다름; 재학습 필요")
        obj = cls(envelope["state"])
        if not len(obj.cal) or not np.isfinite(obj.cal).all():
            raise ValueError("보정값 누락/손상")
        return obj


class StreamDetector:
    """청크 크기에 무관한 추론. 센서 원본은 직전 7행만 유지한다.

    잘못된 행·역순·중복·샘플 누락은 경계가 된다. 경보 단위(기록구간 안 50행 블록)의 첫 경보만 알리고,
    바로 앞 블록도 경보였으면 이어지는 이상으로 묶는다. 외부가 새 장치로 전환할 때는 새 인스턴스를 생성해야 한다.
    """
    def __init__(self, model, alpha=.01):
        if alpha not in ALPHAS:
            raise ValueError("지원하지 않는 alpha")
        self.model, self.alpha = model, alpha
        self.tail = pd.DataFrame(columns=[D.TIME]+D.SENSORS)
        self.tail_records = np.array([], dtype=int)
        self.tail_positions = np.array([], dtype=int)
        self.rows_seen = 0
        self.alert_record = None      # 현재 기록구간 번호와 그 안에서 경보가 난 블록
        self.alerted_blocks = set()

    def push(self, frame):
        layout(frame)
        if len(frame) == 0:
            return self.model.predict(frame,self.alpha)
        incoming = D.inputs_only(frame)
        n_old = len(self.tail)
        both = pd.concat([self.tail,incoming],ignore_index=True) if n_old else incoming
        result = self.model.predict(both,self.alpha)
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
        notifications = []
        for r in result.itertuples():
            if r.record_id != self.alert_record:
                self.alert_record, self.alerted_blocks = r.record_id, set()
            notify = bool(r.alarm) and r.alert_unit not in self.alerted_blocks and r.alert_unit - 1 not in self.alerted_blocks
            if r.alarm:
                self.alerted_blocks = {b for b in self.alerted_blocks if b >= r.alert_unit - 1} | {r.alert_unit}
            notifications.append(int(notify))
        result["notification"] = notifications
        self.rows_seen += len(incoming)
        self.tail = both.iloc[-7:].copy().reset_index(drop=True)
        self.tail_records, self.tail_positions = rec[-7:].copy(), positions[-7:].copy()
        return result


def cases(predictions):
    """점검 대기열. 고장 사건 수가 아니라, 같은 기록구간에서 경보가 이어진 블록 묶음 하나가 한 건이다(대회 자료는 기록구간당 한 건).

    priority_rank는 이상 라벨 없이 정한 정렬 키다: 근거 성분 수가 많을수록, 경보 행 비율이 높을수록, 최대 점수가 클수록 먼저.
    """
    p = predictions
    if not len(p) or not p.alarm.eq(1).any():
        return pd.DataFrame()
    block = p.alert_unit.to_numpy() if "alert_unit" in p else p.position.to_numpy() // ALERT_UNIT_ROWS
    blocks = pd.DataFrame(dict(r=p.record_id.to_numpy(), b=block, a=p.alarm.eq(1).to_numpy())).groupby(["r", "b"], sort=False).a.any().reset_index()
    continues = blocks.groupby("r").a.shift(1, fill_value=False)
    blocks["episode"] = np.where(blocks.a, np.cumsum(blocks.a & ~continues), 0)
    episode = pd.MultiIndex.from_arrays([p.record_id.to_numpy(), block]).map(blocks.set_index(["r", "b"]).episode).to_numpy()
    blocks_of_rows = pd.Series(block, index=p.index)
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
        result.append(dict(record_id=int(first.record_id), first_row=int(first.row_id), first_timestamp=first.timestamp,
                           first_alarm_position=int(first.position), detection_delay_s=float(first.position*D.DT),
                           alarm_rows=len(flagged), observed_rows=len(group), peak_score=float(flagged.score.max()),
                           min_p=float(flagged.p_value.min()), evidence="+".join(reasons),
                           action=action_for(any(x != D.SENSORS[2] for x in sensors), D.SENSORS[2] in sensors, shape),
                           magnitude_sensors="+".join(sensors), alarm_share=len(flagged) / len(group),
                           alert_units=int(blocks_of_rows.loc[group.index].nunique()),
                           beyond_calibration_length=int(group.position.max() >= ALERT_UNIT_ROWS)))
    queue = pd.DataFrame(result)
    order = queue.assign(n=queue.evidence.str.count(r"\+") + 1).sort_values(["n", "alarm_share", "peak_score"], ascending=False, kind="stable").index
    queue.loc[order, "priority_rank"] = np.arange(1, len(queue) + 1)
    queue["priority_rank"] = queue.priority_rank.astype(int)
    return queue
