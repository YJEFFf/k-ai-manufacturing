"""위치 0·1 미탐 후보의 사전 고정 비교 — protocol.json. 이미 본 이상 자료를 쓰는 탐색 실험. v2 코드·산출물은 바꾸지 않는다."""
from pathlib import Path
import json
import sys
import time

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parents[1] / "press_submission"
sys.path.insert(0, str(PACKAGE))
from press import data as D
from press.scores import Scorer, ExpTail, window_index
from press.calibrate import segment_max, thresholds_for
from press.evaluate import evaluate_models
from press.validation import code_sha256


class Linear:
    """정상 전류의 p차 선형 예측(상수항 포함) 절대 잔차. p=2가 v2의 AR(2), p=1이 diff1 후보."""
    def __init__(self, train, seg, order):
        self.order = order
        x = train[D.SENSORS[2]].to_numpy(float)
        idx = window_index(seg, order + 1)
        design = np.column_stack([np.ones(len(idx))] + [x[idx - k] for k in range(1, order + 1)])
        self.coef = np.linalg.lstsq(design, x[idx], rcond=None)[0]
        self.tail = ExpTail(self.residual(train, seg))

    def residual(self, frame, seg):
        x = frame[D.SENSORS[2]].to_numpy(float)
        idx = window_index(seg, self.order + 1)
        pred = self.coef[0] + sum(self.coef[k] * x[idx - k] for k in range(1, self.order + 1))
        out = np.full(len(x), np.nan); out[idx] = np.abs(x[idx] - pred)
        return out


class Joint:
    """세 센서 표준화 값의 정상 학습 공분산 Mahalanobis 거리(모든 행)."""
    def __init__(self, scaler, train):
        z = scaler.transform(train[D.SENSORS])
        cov = np.cov(z, rowvar=False) + 1e-9 * np.eye(3)
        self.inv = np.linalg.inv(cov)
        self.scaler = scaler
        self.tail = ExpTail(self.distance(train))

    def distance(self, frame):
        z = self.scaler.transform(frame[D.SENSORS])
        return np.sqrt(np.einsum("ij,jk,ik->i", z, self.inv, z))


def scores(base, ar2, joint, ar1, frame, seg):
    comp, _ = base.components(frame, seg)
    pos, _ = D.segment_positions(seg)
    early = np.fmax(comp["g_maxz3"], np.where(pos < 7, comp["g_sine_6"], comp["g_sine_8"]))
    v2 = np.fmax(early, ar2.tail(ar2.residual(frame, seg)))
    gj = joint.tail(joint.distance(frame))
    g1 = ar1.tail(ar1.residual(frame, seg))
    return dict(v2=v2, v2_joint=np.fmax(v2, gj), v2_diff1=np.fmax(v2, g1), v2_joint_diff1=np.fmax(np.fmax(v2, gj), g1),
                joint_only=gj, diff1_only=g1)


def run():
    started = time.monotonic()
    protocol = json.loads((HERE / "protocol.json").read_text())
    n, a, report = D.load()
    vendor = D.load_vendor()
    all_rows, fitted = [], {}
    for sid in D.SPLITS:
        split = D.split_normal(n, D.segments(n), sid)
        tr = D.quantize(split["train"], "matched"); seg_tr = D.segments(tr)
        base = Scorer(tr, seg_tr, vendor, wins=(6, 8), baselines=False)
        ar2, ar1, joint = Linear(tr, seg_tr, 2), Linear(tr, seg_tr, 1), Joint(base.scaler, tr)
        fitted[sid] = dict(ar2=ar2.coef, ar1=ar1.coef, joint_tail_u=joint.tail.u, joint_tail_beta=joint.tail.beta, ar1_tail_u=ar1.tail.u, ar1_tail_beta=ar1.tail.beta)
        cal = D.quantize(split["cal"], "matched"); segcal = D.segments(cal)
        cs = scores(base, ar2, joint, ar1, cal, segcal)
        assert list(cs) == protocol["candidates"]
        frozen = {(m, "recording_segments"): thresholds_for(segment_max(s, segcal), "recording_segments") for m, s in cs.items()}
        for variant in ("matched", "raw", "coarse"):
            frames = dict(cal=cal, test=D.quantize(split["test"], variant), abn=D.quantize(a, variant))
            segs = {p: D.segments(f) for p, f in frames.items()}
            ss = {p: scores(base, ar2, joint, ar1, f, segs[p]) for p, f in frames.items()}
            by_model = {m: {p: ss[p][m] for p in frames} for m in cs}
            metrics, _ = evaluate_models(vendor, split["name"], "matched", by_model, frames, segs, threshold_override=frozen, units=("recording_segments",))
            metrics["split_id"], metrics["input_variant"] = sid, variant
            all_rows.append(metrics)
        print(sid, "AR(2)", ar2.coef, "AR(1)", ar1.coef, flush=True)
    metrics = pd.concat(all_rows, ignore_index=True)
    metrics.to_csv(HERE / "metrics.csv", index=False)
    primary = metrics[metrics.criterion.eq("conformal") & metrics.alpha.eq(.01) & metrics.input_variant.eq("matched")]
    primary.to_csv(HERE / "primary.csv", index=False)
    # v2 후보가 press_advance의 early6_ar2와 같은지(구현 일치) 확인
    adv = pd.read_csv(HERE.parent / "press_advance" / "primary.csv")
    for sid in D.SPLITS:
        e = adv[adv.split_id.eq(sid) & adv.model.eq("early6_ar2")].iloc[0]
        g = primary[primary.split_id.eq(sid) & primary.model.eq("v2")].iloc[0]
        assert (e.tp, e.fp, e.fn) == (g.tp, g.fp, g.fn), (sid, e.fn, g.fn)
    ref = {sid: primary[primary.split_id.eq(sid) & primary.model.eq("v2")].iloc[0] for sid in D.SPLITS}
    verdict = {}
    for m in protocol["candidates"]:
        rows = {sid: primary[primary.split_id.eq(sid) & primary.model.eq(m)].iloc[0] for sid in D.SPLITS}
        verdict[m] = dict(normal_notified={sid: int(r.normal_notified_segments) for sid, r in rows.items()},
                          abnormal_notified={sid: int(r.abnormal_notified_segments) for sid, r in rows.items()},
                          fn={sid: int(r.fn) for sid, r in rows.items()}, f1={sid: round(float(r.f1_all_rows), 6) for sid, r in rows.items()},
                          meets_selection_rule=bool(all(rows[s].normal_notified_segments <= ref[s].normal_notified_segments and rows[s].abnormal_notified_segments == 21 for s in D.SPLITS)),
                          fn_lower_than_v2=bool(all(rows[s].fn < ref[s].fn for s in D.SPLITS)))
    D.dump_json(dict(protocol=protocol, fit=fitted, verdict=verdict, inputs=report, code_sha256=code_sha256(),
                     script_sha256=D.sha256_file(Path(__file__)), environment=D.environment(), elapsed_s=time.monotonic() - started), HERE / "manifest.json")
    print(primary[["split_id", "model", "normal_notified_segments", "abnormal_notified_segments", "fn", "fp", "f1_all_rows", "delay_max_s"]].to_string(index=False))
    print(json.dumps(verdict, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    run()
