"""정상 자료로 v2 적합/보정, 기존 기준과 대조, 기록구간별 알림 산출."""
from pathlib import Path
import argparse
import json
import time

import numpy as np
import pandas as pd

from model import GuardModel, StreamDetector, cases, D, BASE, HERE, ALPHAS
from press.calibrate import conformal_p, segment_max
from press.scores import sine_score


def baseline(model, frame):
    x = D.quantize(D.inputs_only(frame),"matched")
    seg = D.segments(x)
    comp = model.components(x,seg)
    sine8 = model.tails["sine8"](sine_score(x[D.SENSORS[2]].to_numpy(),seg,8))
    return np.fmax(comp["g_magnitude"],sine8)


def metric(split, name, alpha, normal_pred, abnormal_pred):
    nn = normal_pred.groupby("record_id").alarm.max()
    an = abnormal_pred.groupby("record_id").alarm.max()
    tp, fp = int(abnormal_pred.alarm.sum()), int(normal_pred.alarm.sum())
    fn, tn = len(abnormal_pred)-tp, len(normal_pred)-fp
    ac = cases(abnormal_pred)
    delays = ac.detection_delay_s.to_numpy()
    return dict(split=split,model=name,alpha=alpha,tp=tp,fp=fp,fn=fn,tn=tn,f1=2*tp/(2*tp+fp+fn),
                precision=tp/(tp+fp) if tp+fp else 0,recall=tp/(tp+fn),normal_notified_segments=int(nn.sum()),
                normal_segments=len(nn),abnormal_notified_segments=int(an.sum()),abnormal_segments=len(an),
                delay_median_s=float(np.median(delays)) if len(delays) else None,
                delay_max_s=float(np.max(delays)) if len(delays) else None,
                normal_scored_rate=float(normal_pred.score.notna().mean()),abnormal_scored_rate=float(abnormal_pred.score.notna().mean()))


def evaluate_pair(model, calibration, normal, abnormal, sid, out=None):
    ref = segment_max(baseline(model,calibration),D.segments(calibration))
    result = []
    for alpha in ALPHAS:
        pn, pa = model.predict(normal,alpha), model.predict(abnormal,alpha)
        result.append(metric(sid,"guard_v2",alpha,pn,pa))
        if out is not None and alpha == .01:
            pn.to_csv(out/f"predictions_normal_{sid}.csv",index=False)
            pa.to_csv(out/f"predictions_abnormal_{sid}.csv",index=False)
            combined_cases = pd.concat([cases(pn).assign(source="normal"),cases(pa).assign(source="abnormal")],ignore_index=True)
            combined_cases.to_csv(out/f"cases_{sid}.csv",index=False)
        for frame,pred in ((normal,pn),(abnormal,pa)):
            score = baseline(model,frame)
            pred["score"],pred["p_value"] = score,conformal_p(ref,score)
            pred["alarm"] = (pred.p_value <= alpha).astype(int)
        result.append(metric(sid,"baseline_v1",alpha,pn,pa))
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root",type=Path,default=BASE)
    ap.add_argument("--out",type=Path,default=HERE/"outputs")
    ap.add_argument("--artifacts",type=Path,default=HERE/"artifacts")
    ap.add_argument("--rolling",action="store_true",help="추가 정상 시간대 5개 비교; 독립 이상 검증은 아님")
    args=ap.parse_args()
    start=time.monotonic()
    args.out.mkdir(parents=True,exist_ok=True)
    normal,abnormal,inputs=D.load(args.root)
    hashes={k:v["sha256"] for k,v in inputs["files"].items()}
    rows=[]
    for sid in D.SPLITS:
        split=D.split_normal(normal,D.segments(normal),sid)
        model=GuardModel.fit(split["train"],split["cal"],split=sid,input_hashes=hashes)
        model.save(args.artifacts/f"guard_{sid}.json")
        loaded=GuardModel.load(args.artifacts/f"guard_{sid}.json")
        pd.testing.assert_frame_equal(model.predict(abnormal),loaded.predict(abnormal))
        rows.extend(evaluate_pair(loaded,split["cal"],split["test"],abnormal,sid,args.out))
        print(f"{sid}: 정상 학습·보정 / 저장·복원 일치",flush=True)
    metrics=pd.DataFrame(rows)
    metrics.to_csv(args.out/"metrics.csv",index=False)
    # 탐색 실행과 실제 배포 구현의 결과를 독립 대조한다.
    expected=pd.read_csv(HERE.parent/"analysis"/"press_advance"/"primary.csv")
    for sid in D.SPLITS:
        e=expected[expected.split_id.eq(sid)&expected.model.eq("early6_ar2")].iloc[0]
        got=metrics[metrics.split.eq(sid)&metrics.model.eq("guard_v2")&metrics.alpha.eq(.01)].iloc[0]
        assert (e.tp,e.fp,e.fn)==(got.tp,got.fp,got.fn)
        assert abs(e.f1_all_rows-got.f1)<1e-12
    if args.rolling:
        sg=D.segments(normal)
        rolling=[]
        for end in (180,240,300,360,420):
            tr=normal[sg<end].reset_index(drop=True)
            ca=normal[(sg>=end)&(sg<end+120)].reset_index(drop=True)
            te=normal[(sg>=end+120)&(sg<end+180)].reset_index(drop=True)
            m=GuardModel.fit(tr,ca,split=f"train_to_{end}",input_hashes=hashes)
            rolling.extend(evaluate_pair(m,ca,te,abnormal,f"normal_{end+120}_{end+179}"))
        pd.DataFrame(rolling).to_csv(args.out/"rolling.csv",index=False)
    code_files=[p for p in HERE.glob("*.py") if p.name != "serve.py"]
    D.dump_json(dict(version="press-guard-v2.0",input_hashes=hashes,environment=D.environment(),
                     code_hashes={p.name:D.sha256_file(p) for p in code_files},
                     artifacts={p.name:D.sha256_file(p) for p in args.artifacts.glob("guard_*.json")},
                     outputs={p.name:D.sha256_file(p) for p in args.out.glob("*.csv")},
                     exploratory=True, elapsed_s=time.monotonic()-start),args.out/"manifest.json")
    print(metrics[metrics.alpha.eq(.01)].to_string(index=False))


if __name__=="__main__":
    main()
