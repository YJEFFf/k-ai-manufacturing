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
        model.cal = segment_max(model.components(cf, sg)["score"], sg)
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
            return pd.DataFrame(columns=["row_id","record_id","timestamp","status","position","score","p_value","alarm","notification","reason","action"])
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
                actions.append("진동·전류 함께 점검" if active[i,0] and active[i,1:].any() else
                               "진동·부하 확인" if active[i,0] else "전류 파형·계측 확인")
        out = pd.DataFrame(dict(row_id=np.arange(len(frame)), record_id=seg, timestamp=frame[D.TIME].astype(str).to_numpy(),
                                status=status, position=pos, score=comp["score"], p_value=p, alarm=alarm.astype(int),
                                reason=reasons, action=actions, alpha=alpha, **{k:v for k,v in comp.items() if k != "score"}))
        out["notification"] = (out.alarm.eq(1) & out.groupby("record_id").alarm.cumsum().eq(1)).astype(int)
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

    잘못된 행·역순·중복·샘플 누락은 경계가 된다. 같은 구간에서 첫 경보만 알림.
    외부가 새 장치로 전환할 때는 새 인스턴스를 생성해야 한다.
    """
    def __init__(self, model, alpha=.01):
        if alpha not in ALPHAS:
            raise ValueError("지원하지 않는 alpha")
        self.model, self.alpha = model, alpha
        self.tail = pd.DataFrame(columns=[D.TIME]+D.SENSORS)
        self.tail_records = np.array([], dtype=int)
        self.tail_positions = np.array([], dtype=int)
        self.rows_seen = 0
        self.last_notified_record = None

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
        result = result.iloc[n_old:].copy().reset_index(drop=True)
        result["row_id"] = np.arange(self.rows_seen,self.rows_seen+len(incoming))
        notifications = []
        for r in result.itertuples():
            notify = bool(r.alarm and r.record_id != self.last_notified_record)
            if notify:
                self.last_notified_record = r.record_id
            notifications.append(int(notify))
        result["notification"] = notifications
        self.rows_seen += len(incoming)
        self.tail = both.iloc[-7:].copy().reset_index(drop=True)
        self.tail_records, self.tail_positions = rec[-7:].copy(), positions[-7:].copy()
        return result


def cases(predictions):
    """고장 사건 수가 아니라 기록구간당 한 건의 검토 대기열이다."""
    result = []
    for record, group in predictions.groupby("record_id",sort=False):
        flagged = group[group.alarm.eq(1)]
        if flagged.empty:
            continue
        first = flagged.iloc[0]
        reasons = sorted(set("+".join(flagged.reason).split("+")) - {""})
        result.append(dict(record_id=int(record), first_row=int(first.row_id), first_timestamp=first.timestamp,
                           first_alarm_position=int(first.position), detection_delay_s=float(first.position*D.DT),
                           alarm_rows=len(flagged), observed_rows=len(group), peak_score=float(flagged.score.max()),
                           min_p=float(flagged.p_value.min()), evidence="+".join(reasons),
                           action="진동·전류 함께 점검" if "magnitude" in reasons and len(reasons)>1 else str(first.action)))
    return pd.DataFrame(result)
