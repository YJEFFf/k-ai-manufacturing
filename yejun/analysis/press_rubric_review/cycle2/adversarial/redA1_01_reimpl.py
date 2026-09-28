"""A1-1 독립 재구현: 원본 CSV → v2 검출기 → 팀 행 단위 경보와 대조.

팀 모듈을 import하지 않는다. 팀 결과는 CSV 파일(press_guard/outputs/test_predictions_{A,B}.csv, metrics.csv)로만 읽는다.
"""
import json
import time

import numpy as np
import pandas as pd

import redA1_common as C

t0 = time.time()
normal, abnormal = C.load_raw()
seg_n = C.segment_ids(normal[C.TIME])
seg_a = C.segment_ids(abnormal[C.TIME])
# v1 규칙(1 µs)과 v2 규칙(20 ms)이 같은 기록을 주는지
seg_n_strict = C.segment_ids(normal[C.TIME], tol=1e-6)
seg_a_strict = C.segment_ids(abnormal[C.TIME], tol=1e-6)
Xn = C.quantize(normal[C.SENS].to_numpy(float))
Xa = C.quantize(abnormal[C.SENS].to_numpy(float))
out = dict(segments=dict(normal=int(seg_n.max() + 1), abnormal=int(seg_a.max() + 1),
                         same_as_1us_rule=bool((seg_n == seg_n_strict).all() and (seg_a == seg_a_strict).all())))
print("기록 수", out["segments"])

team_metrics = pd.read_csv(C.REPO / "yejun/press_guard/outputs/metrics.csv")
rows = []
mismatch = {}
for sid in ("A", "B"):
    m = C.split_frames(normal, seg_n, sid)
    det = C.Detector().fit(Xn[m["train"]], seg_n[m["train"]]).calibrate(Xn[m["cal"]], seg_n[m["cal"]])
    team = pd.read_csv(C.REPO / f"yejun/press_guard/outputs/test_predictions_{sid}.csv", low_memory=False)
    tn, ta = team[team.subset.eq("normal_test")].reset_index(drop=True), team[team.subset.eq("abnormal")].reset_index(drop=True)
    # 행 대응 확인: 시각 문자열이 같은 순서여야 한다
    assert (tn.timestamp.astype(str).to_numpy() == normal.loc[m["test"], C.TIME].astype(str).to_numpy()).all()
    assert (ta.timestamp.astype(str).to_numpy() == abnormal[C.TIME].astype(str).to_numpy()).all()
    for alpha in C.ALPHAS:
        pn = det.predict(Xn[m["test"]], seg_n[m["test"]], alpha)
        pa = det.predict(Xa, seg_a, alpha)
        mine = C.f1_rows(pn["alarm"], pa["alarm"])
        mine_rec_n = int(pd.Series(pn["alarm"]).groupby(seg_n[m["test"]]).max().sum())
        mine_rec_a = int(pd.Series(pa["alarm"]).groupby(seg_a).max().sum())
        tm = team_metrics[team_metrics.split.eq(sid) & team_metrics.model.eq("guard_v2") & np.isclose(team_metrics.alpha, alpha)].iloc[0]
        # 팀 행 단위 경보: 파일의 p값으로 α별 경보를 다시 만든다(파일의 alarm 열은 α 1%)
        team_alarm_n = (tn.p_value.to_numpy() <= alpha) & np.isfinite(tn.p_value.to_numpy())
        team_alarm_a = (ta.p_value.to_numpy() <= alpha) & np.isfinite(ta.p_value.to_numpy())
        if alpha == 0.01:
            assert (team_alarm_n == tn.alarm.eq(1).to_numpy()).all() and (team_alarm_a == ta.alarm.eq(1).to_numpy()).all()
        dn = np.flatnonzero(team_alarm_n != pn["alarm"])
        da = np.flatnonzero(team_alarm_a != pa["alarm"])
        score_diff = float(np.nanmax(np.abs(np.r_[tn.score.to_numpy() - pn["score"], ta.score.to_numpy() - pa["score"]])))
        p_diff = float(np.nanmax(np.abs(np.r_[tn.p_value.to_numpy() - pn["p"], ta.p_value.to_numpy() - pa["p"]])))
        nan_same = bool((np.isnan(tn.score.to_numpy()) == np.isnan(pn["score"])).all() and (np.isnan(ta.score.to_numpy()) == np.isnan(pa["score"])).all())
        rows.append(dict(split=sid, alpha=alpha, **{f"mine_{k}": v for k, v in mine.items()},
                         mine_normal_records=mine_rec_n, mine_abnormal_records=mine_rec_a,
                         team_tp=int(tm.tp), team_fp=int(tm.fp), team_fn=int(tm.fn), team_f1=float(tm.f1),
                         team_normal_records=int(tm.normal_notified_segments), team_abnormal_records=int(tm.abnormal_notified_segments),
                         rows_differ_normal=int(len(dn)), rows_differ_abnormal=int(len(da)),
                         max_abs_score_diff=score_diff, max_abs_p_diff=p_diff, nan_pattern_same=nan_same))
        mismatch[f"{sid}_{alpha}"] = dict(normal=dn.tolist(), abnormal=da.tolist())
    # 적합값 요약
    out[f"fit_{sid}"] = dict(mean=det.mean.tolist(), scale=det.scale.tolist(), ar2=det.ar.tolist(),
                             tails={k: dict(n=t.n, u=t.u, beta=t.beta) for k, t in
                                    dict(magnitude=det.t_mag, sine6=det.t_s6, sine8=det.t_s8, dynamics=det.t_dyn).items()},
                             n_cal=int(len(det.cal)), cal_max=float(det.cal.max()),
                             cal_sorted_top6=np.sort(det.cal)[::-1][:6].tolist(),
                             train_rows=int(m["train"].sum()), cal_rows=int(m["cal"].sum()), test_rows=int(m["test"].sum()))

table = pd.DataFrame(rows)
pd.set_option("display.width", 250, "display.max_columns", 50)
print(table.to_string(index=False))
table.to_csv(C.OUT / "redA1_01_reimpl_compare.csv", index=False)
out["mismatch_rows"] = mismatch
out["elapsed_s"] = time.time() - t0
(C.OUT / "redA1_01_reimpl.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in out.items() if k.startswith("fit_")}, ensure_ascii=False, indent=1))
print("걸린 시간(초)", round(out["elapsed_s"], 1))
