"""정상 자료로 v2 적합/보정, 기존 기준과 대조, 기록구간별 알림 산출."""
from pathlib import Path
import argparse
import sys
import json
import time

import numpy as np
import pandas as pd

from model import GuardModel, StreamDetector, cases, incidents, incident_columns, record_running_max, D, BASE, HERE, ALPHAS
from probability import ProbabilityCalibrator, posterior, DEFAULT_PRIOR
from press.calibrate import conformal_p, segment_max
from press.scores import sine_score
from contracts import CODE_FILES, TRAIN_TABLES, PREDICTIONS
import runtime


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


def fit_probability(model, calibration, abnormal, sid, hashes):
    """이상 확률 층: 정상 보정 행과 이상 21구간 전체로 맞춘 배포용 보정기, 그리고 평가용으로 이상 기록을 하나씩 뺀 우도비."""
    cal_scores = model.predict(calibration).score.to_numpy()
    pa = model.predict(abnormal)
    deploy = ProbabilityCalibrator.fit(cal_scores, pa.score.to_numpy(), calibration_units=len(model.cal), split=sid,
                                       source=dict(normal="정상 보정 구간 행", abnormal="이상 21구간 전체", input_hashes=hashes))
    return deploy, oof_likelihood_ratio(model, calibration, abnormal)


def oof_likelihood_ratio(model, calibration, abnormal):
    """평가용 이상 행 우도비: 그 이상 기록을 뺀 나머지로 맞춘 보정기(기록 하나씩 떼어 낸 교차 적합)."""
    cal_scores = model.predict(calibration).score.to_numpy()
    pa = model.predict(abnormal)
    oof = np.full(len(pa), np.nan)
    for r in np.unique(pa.record_id):
        keep = pa.record_id.to_numpy() != r
        fold = ProbabilityCalibrator.fit(cal_scores, pa.score.to_numpy()[keep], calibration_units=len(model.cal))
        oof[~keep] = fold.likelihood_ratio(pa.score.to_numpy()[~keep])
    return oof


def use_oof(pa, oof_lr):
    """평가용 이상 행 확률은 그 기록을 뺀 보정기 값으로 바꾼다(정상 평가 행은 어느 적합에도 쓰지 않았다)."""
    pa["likelihood_ratio"] = oof_lr
    pa["anomaly_probability"] = posterior(oof_lr, pa.probability_prior.iloc[0])
    pa["record_likelihood_ratio"] = record_running_max(oof_lr, pa.record_id.to_numpy())
    pa["record_probability"] = posterior(pa.record_likelihood_ratio.to_numpy(), pa.probability_prior.iloc[0])
    return pa


def test_prediction_file(pn, pa):
    """제출용 테스트 예측 파일(분할별 1개): 정상 평가 기록 + 이상 기록. 정답 구분 열(subset·label)로 파일만으로 F1을 다시 계산할 수 있다.
    이상 600행은 두 분할이 같다. 이상 행의 확률 열은 그 기록을 뺀 교차 적합 값이다(probability_source)."""
    both = pd.concat([pn.assign(subset="normal_test", label=0), pa.assign(subset="abnormal", label=1)], ignore_index=True)
    # anomaly_probability는 현장 가정 π=1%(행 비율)라 우도비 상한 121에서 0.55에 멈춘다. 파일 라벨로 확률을 채점할 때는
    # 사전 비율을 이 파일의 이상 행 비율로 바꾼 열을 쓴다(같은 우도비, 사전 오즈만 교체).
    file_prior = float(both.label.mean())
    both["file_prior"] = file_prior
    both["anomaly_probability_file_prior"] = posterior(both.likelihood_ratio.to_numpy(float), file_prior)
    return both[["subset", "label"] + [c for c in both.columns if c not in ("subset", "label")]]


def combine_streams(pn, pa):
    """정상 평가와 이상을 한 흐름으로 이어 대기열 순위를 한 번에 매긴다(구간·행 번호가 겹치지 않게 옮긴다)."""
    shifted = pa.copy()
    shifted["record_id"] += int(pn.record_id.max()) + 1
    shifted["row_id"] += len(pn)
    both = pd.concat([pn, shifted], ignore_index=True)
    # 사건 번호는 한 흐름으로 다시 매긴다(정상 평가와 이상은 서로 다른 날이라 사이 공백이 60초를 넘는다)
    inc = incident_columns(both.record_id.to_numpy(), both.alert_unit.to_numpy(), both.alarm.to_numpy(), both.reason.to_numpy(),
                           pd.to_datetime(both.timestamp, format="mixed", utc=True, errors="coerce"))
    both["incident_id"], both["incident_notification"], both["incident_escalation"], both["incident_update"] = inc.T
    queue = cases(both)
    if len(queue):
        queue.insert(0, "source", np.where(queue.record_id > pn.record_id.max(), "abnormal", "normal"))
        queue.loc[queue.source.eq("abnormal"), "record_id"] -= int(pn.record_id.max()) + 1
    return queue


def evaluate_pair(model, calibration, normal, abnormal, sid, out=None, oof_lr=None):
    ref = segment_max(baseline(model,calibration),D.segments(calibration))
    result = []
    for alpha in ALPHAS:
        pn, pa = model.predict(normal,alpha), model.predict(abnormal,alpha)
        if oof_lr is not None:   # 평가용 이상 행 확률은 그 기록을 뺀 보정기로(정상 평가 행은 어느 적합에도 쓰지 않았다)
            pa = use_oof(pa, oof_lr)
            pn["probability_source"], pa["probability_source"] = "deployment_calibrator", "leave_one_record_out"
        result.append(metric(sid,"guard_v2",alpha,pn,pa))
        if out is not None and alpha == .01:
            pn.to_csv(out/f"predictions_normal_{sid}.csv",index=False)
            pa.to_csv(out/f"predictions_abnormal_{sid}.csv",index=False)
            test_prediction_file(pn, pa).to_csv(out/f"test_predictions_{sid}.csv",index=False)
            queue = combine_streams(pn, pa)
            queue.to_csv(out/f"cases_{sid}.csv",index=False)
            # 사건 대기열: 정상 평가 뒤에 이상 기록을 이어 붙인 한 흐름(두 날 사이 공백이 60초를 넘어 서로 다른 사건이 된다)
            incident_queue = incidents(queue)
            if len(incident_queue):
                incident_queue.insert(1, "source", incident_queue.case_uids.map(lambda u: "abnormal" if int(str(u).split("+")[0]) >= len(pn) else "normal"))
            incident_queue.to_csv(out/f"incidents_{sid}.csv",index=False)
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
    runtime.setup()
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
        deploy, oof = fit_probability(loaded, split["cal"], abnormal, sid, hashes)
        deploy.save(args.artifacts/f"probability_{sid}.json")
        loaded.attach_probability(ProbabilityCalibrator.load(args.artifacts/f"probability_{sid}.json"))
        rows.extend(evaluate_pair(loaded,split["cal"],split["test"],abnormal,sid,args.out,oof_lr=oof))
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
    written=tuple(n for n in TRAIN_TABLES if n!="rolling.csv" or args.rolling)+PREDICTIONS
    D.dump_json(dict(version="press-guard-v2.0",input_hashes=hashes,environment=runtime.environment(D.environment()),resources={"peak_rss_mb":runtime.peak_rss_mb()},
                     code_hashes={n:D.sha256_file(HERE/n) for n in CODE_FILES},config={"rolling":args.rolling},
                     artifacts={p.name:D.sha256_file(p) for p in sorted(args.artifacts.glob("*.json")) if p.name.startswith(("guard_","probability_"))},
                     outputs={n:D.sha256_file(args.out/n) for n in written},
                     exploratory=True, elapsed_s=time.monotonic()-start),args.out/"manifest.json")
    print(metrics[metrics.alpha.eq(.01)].to_string(index=False))


if __name__=="__main__":
    main()
