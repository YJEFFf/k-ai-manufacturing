"""사전 고정한 정상 전류 AR(2) 후보 비교. 이미 본 이상 자료를 쓰는 탐색 실험."""
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


class Dynamics:
    def __init__(self, train, seg):
        x = train[D.SENSORS[2]].to_numpy(float)
        idx = window_index(seg, 3)
        design = np.column_stack([np.ones(len(idx)), x[idx-1], x[idx-2]])
        self.coef = np.linalg.lstsq(design, x[idx], rcond=None)[0]
        self.tail = ExpTail(self.residual(train, seg))

    def residual(self, frame, seg):
        x = frame[D.SENSORS[2]].to_numpy(float)
        idx = window_index(seg, 3)
        result = np.full(len(x), np.nan)
        result[idx] = np.abs(x[idx] - self.coef[0] - self.coef[1]*x[idx-1] - self.coef[2]*x[idx-2])
        return result


def scores(base, ar, frame, seg):
    comp, _ = base.components(frame, seg)
    gz = comp["g_maxz3"]
    pos, _ = D.segment_positions(seg)
    early = np.fmax(gz, np.where(pos < 7, comp["g_sine_6"], comp["g_sine_8"]))
    gar = ar.tail(ar.residual(frame, seg))
    return dict(baseline_w8=np.fmax(gz, comp["g_sine_8"]), early_w6_to_w8=early,
                ar2_only=gar, maxz_ar2=np.fmax(gz, gar), early6_ar2=np.fmax(early, gar))


def run():
    for stream in (sys.stdout, sys.stderr):     # 한국어 Windows(CP949) 콘솔에서 못 쓰는 기호는 바꿔 쓴다
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    started = time.monotonic()
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
    n, a, report = D.load()
    vendor = D.load_vendor()
    all_rows, all_records, fitted = [], [], {}
    for sid in D.SPLITS:
        split = D.split_normal(n, D.segments(n), sid)
        tr = D.quantize(split["train"], "matched")
        base = Scorer(tr, D.segments(tr), vendor, wins=(6,8), baselines=False)
        ar = Dynamics(tr, D.segments(tr))
        fitted[sid] = {"ar2_coefficients": ar.coef, "ar2_tail_u": ar.tail.u, "ar2_tail_beta": ar.tail.beta}
        cal = D.quantize(split["cal"], "matched")
        segcal = D.segments(cal)
        cs = scores(base, ar, cal, segcal)
        assert list(cs) == protocol["candidates"]
        frozen = {(m, "recording_segments"): thresholds_for(segment_max(s, segcal), "recording_segments") for m,s in cs.items()}
        for variant in ("matched", "raw", "coarse"):
            frames = dict(cal=cal, test=D.quantize(split["test"], variant), abn=D.quantize(a, variant))
            segs = {p:D.segments(f) for p,f in frames.items()}
            ss = {p:scores(base, ar, f, segs[p]) for p,f in frames.items()}
            by_model = {m:{p:ss[p][m] for p in frames} for m in cs}
            metrics, records = evaluate_models(vendor, split["name"], "matched", by_model, frames, segs,
                                               threshold_override=frozen, units=("recording_segments",))
            for table, target in ((metrics,all_rows),(records,all_records)):
                table["split_id"], table["input_variant"] = sid, variant
                target.append(table)
        print(sid, 'AR(2)', ar.coef, flush=True)
    metrics = pd.concat(all_rows, ignore_index=True)
    metrics.to_csv(HERE / "metrics.csv", index=False)
    pd.concat(all_records, ignore_index=True).to_csv(HERE / "segment_metrics.csv", index=False)
    selected = metrics[metrics.criterion.eq("conformal") & metrics.alpha.eq(.01) & metrics.input_variant.eq("matched")]
    selected.to_csv(HERE / "primary.csv", index=False)
    D.dump_json(dict(protocol=protocol, fit=fitted, inputs=report, code_sha256=code_sha256(),
                     script_sha256=D.sha256_file(Path(__file__)), environment=D.environment(),
                     outputs={name: D.sha256_file(HERE / name) for name in ("metrics.csv", "segment_metrics.csv", "primary.csv")},
                     elapsed_s=time.monotonic()-started), HERE / "manifest.json")
    print(selected[["split_id","model","normal_notified_segments","abnormal_notified_segments","fn","fp",
                    "f1_all_rows","abnormal_row_coverage","delay_median_s","delay_max_s"]].to_string(index=False))


if __name__ == "__main__":
    run()
