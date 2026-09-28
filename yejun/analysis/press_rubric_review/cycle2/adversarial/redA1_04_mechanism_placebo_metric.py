"""A1-4 메커니즘(v2가 무엇을 잡는가)·음성 대조(정상만)·평가 지표 구조·짧은 창 신경망 기준.

팀 모듈을 import하지 않는다. 공용 구현(redA1_common)은 redA1_01에서 팀 경보와 모든 행이 같음을 확인했다.
"""
import json

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.neural_network import MLPRegressor

import redA1_common as C

pd.set_option("display.width", 250, "display.max_columns", 60, "display.max_rows", 300)
normal, abnormal = C.load_raw()
seg_n, seg_a = C.segment_ids(normal[C.TIME]), C.segment_ids(abnormal[C.TIME])
pos_n, pos_a = C.positions(seg_n), C.positions(seg_a)
Xn, Xa = C.quantize(normal[C.SENS].to_numpy(float)), C.quantize(abnormal[C.SENS].to_numpy(float))
out = {}
log = []


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    log.append(s)


# ---------- (1) 메커니즘: 0.6 Hz 성분, 기록별 AR(2), 잔차 ----------
def tone06(x):
    t = np.arange(len(x)) * C.DT
    A = np.column_stack([np.sin(2 * np.pi * 0.6 * t), np.cos(2 * np.pi * 0.6 * t), np.ones(len(x))])
    b, *_ = np.linalg.lstsq(A, x, rcond=None)
    sst = ((x - x.mean()) ** 2).sum()
    return float(np.hypot(b[0], b[1])), float(1 - ((x - A @ b) ** 2).sum() / sst) if sst > 0 else np.nan


def ar2_fit(x):
    D = np.column_stack([np.ones(len(x) - 2), x[1:-1], x[:-2]])
    c, *_ = np.linalg.lstsq(D, x[2:], rcond=None)
    roots = np.roots([1, -c[1], -c[2]])
    f = float(np.abs(np.angle(roots[0])) / (2 * np.pi * C.DT))
    return c, float(np.abs(roots).max()), f


mech = []
for label, X, seg in (("normal", Xn, seg_n), ("abnormal", Xa, seg_a)):
    for r in np.unique(seg):
        x = X[seg == r, 2]
        if len(x) < 17:
            continue
        amp, r2 = tone06(x)
        c, rad, f = ar2_fit(x)
        # 전역 A 모델의 고정 AR(2)(redA1_01 A 적합값)로 잔차
        res = x[2:] - (0.10017176356137535 + 1.833083212563616 * x[1:-1] - 0.9748619270345045 * x[:-2])
        spec = np.abs(np.fft.rfft(x - x.mean())) ** 2
        fr = np.fft.rfftfreq(len(x), C.DT)
        low = spec[(fr > 0) & (fr < 0.4)].sum() / spec[fr > 0].sum()
        band = spec[(fr >= 0.4) & (fr <= 0.8)].sum() / spec[fr > 0].sum()
        high = spec[fr > 1.5].sum() / spec[fr > 0].sum()
        mech.append(dict(data=label, record=int(r), n=len(x), sd=float(x.std()), tone06_amp=amp, tone06_r2=r2, ar_phi1=float(c[1]), ar_phi2=float(c[2]),
                         ar_pole_radius=rad, ar_freq=f, resid_rms_fixedA=float(np.sqrt((res ** 2).mean())),
                         resid_lag1=float(np.corrcoef(res[1:], res[:-1])[0, 1]), power_lt04=low, power_04_08=band, power_gt15=high))
mech = pd.DataFrame(mech)
mech.to_csv(C.OUT / "redA1_04_mechanism_records.csv", index=False)
say("== (1) 메커니즘: 길이 ≥17 기록(정상 469, 이상 14)")
summ = mech.groupby("data").agg(n=("record", "size"), sd_med=("sd", "median"), sd_min=("sd", "min"), tone_amp_med=("tone06_amp", "median"),
                                 tone_amp_min=("tone06_amp", "min"), tone_amp_max=("tone06_amp", "max"), tone_r2_med=("tone06_r2", "median"),
                                 tone_r2_min=("tone06_r2", "min"), tone_r2_max=("tone06_r2", "max"), ar_radius_med=("ar_pole_radius", "median"),
                                 ar_freq_med=("ar_freq", "median"), resid_rms_med=("resid_rms_fixedA", "median"), resid_lag1_med=("resid_lag1", "median"),
                                 p_lt04_med=("power_lt04", "median"), p_04_08_med=("power_04_08", "median"), p_gt15_med=("power_gt15", "median"))
say(summ.T.round(4).to_string())
out["mechanism_summary"] = summ.reset_index().to_dict("records")
low_state = mech[(mech.data == "normal") & (mech.sd < 91.9)]
say("정상 저수준 기록 SD 최소", round(low_state.sd.min(), 2), "| 이상 기록 SD가 정상 저수준 최소보다 작은 수",
    int((mech[mech.data == "abnormal"].sd < low_state.sd.min()).sum()), "/", int((mech.data == "abnormal").sum()))

# ---------- (2) 음성 대조: 정상만, 앞 시간대로 학습·보정한 고정 모델을 뒤 블록에 ----------
say("\n== (2) 음성 대조(정상만): 고정 모델의 블록별 기록 경보율")


def state_of(X, seg):
    s = {}
    for r in np.unique(seg):
        x = X[seg == r, 2]
        s[r] = "short" if len(x) < 17 else ("load" if x.std() >= 91.9 else "low")
    return s


plc = []
for name, tr_end, cal_end in (("early_0-179/180-299", 180, 300), ("B_0-299/300-419", 300, 420)):
    tr, ca = seg_n < tr_end, (seg_n >= tr_end) & (seg_n < cal_end)
    det = C.Detector().fit(Xn[tr], seg_n[tr]).calibrate(Xn[ca], seg_n[ca])
    st = state_of(Xn, seg_n)
    for b0 in range(cal_end, 600, 60):
        te = (seg_n >= b0) & (seg_n < b0 + 60)
        for alpha in C.ALPHAS:
            p = det.predict(Xn[te], seg_n[te], alpha)
            rec = pd.Series(p["alarm"]).groupby(seg_n[te]).max()
            states = pd.Series({r: st[r] for r in rec.index})
            row = dict(model=name, block=f"{b0}-{b0 + 59}", minutes_after_cal_end=None, alpha=alpha, records=int(len(rec)), alarmed=int(rec.sum()),
                       rate=float(rec.mean()), nominal=np.floor(alpha * 121) / 121)
            for s_ in ("load", "low", "short"):
                row[f"{s_}_alarmed"] = int(rec[states == s_].sum()); row[f"{s_}_n"] = int((states == s_).sum())
            plc.append(row)
plc = pd.DataFrame(plc)
say(plc.to_string(index=False))
plc.to_csv(C.OUT / "redA1_04_placebo_blocks.csv", index=False)
out["placebo"] = plc.to_dict("records")

# 정상 77분 안의 기록 특징 추세(드리프트)
nm = mech[mech.data == "normal"].copy()
tr_rows = []
for f in ("ar_freq", "tone06_amp", "tone06_r2", "sd", "resid_rms_fixedA"):
    rho, p = spearmanr(nm.record, nm[f])
    tr_rows.append(dict(feature=f, spearman_vs_record=float(rho), p=float(p), normal_q01=float(nm[f].quantile(.01)), normal_q99=float(nm[f].quantile(.99)),
                        abnormal_median=float(mech[mech.data == "abnormal"][f].median())))
trend = pd.DataFrame(tr_rows)
say("\n정상 기록 특징의 시간 추세(길이 ≥17, 469개)")
say(trend.round(4).to_string(index=False))
out["normal_trend"] = tr_rows

# ---------- (3) 평가 지표 구조 ----------
say("\n== (3) 평가 지표 구조")
struct = []
for sid in ("A", "B"):
    m = C.split_frames(normal, seg_n, sid)
    det = C.Detector().fit(Xn[m["train"]], seg_n[m["train"]]).calibrate(Xn[m["cal"]], seg_n[m["cal"]])
    v1 = C.Detector(use=("magnitude", "waveform"), early=False).fit(Xn[m["train"]], seg_n[m["train"]]).calibrate(Xn[m["cal"]], seg_n[m["cal"]])
    for mname, d in (("v2", det), ("v1_combined_w8", v1)):
        pn, pa = d.predict(Xn[m["test"]], seg_n[m["test"]]), d.predict(Xa, seg_a)
        an, aa = pn["alarm"], pa["alarm"]
        miss = ~aa
        by_pos = pd.Series(miss).groupby(np.minimum(pos_a, 7)).agg(["sum", "size"])
        # 첫 경보 이후 유지(latch)
        la = pd.Series(aa).groupby(seg_a).cummax().to_numpy()
        ln = pd.Series(an).groupby(seg_n[m["test"]]).cummax().to_numpy()
        base = C.f1_rows(an, aa)
        latch = C.f1_rows(ln, la)
        # 첫 경보 뒤 행만 채점(첫 경보 전 행은 평가에서 뺌) → 탐지 뒤 지속성만 보는 값
        first = pd.Series(np.where(aa, pos_a, 10 ** 6)).groupby(seg_a).transform("min").to_numpy()
        after = pos_a >= first
        # 위치 ≥7(모든 성분 점수 가능) 행만
        pos7 = pos_a >= 7
        rec7 = aa[pos7].mean()
        # 정상 행 가중(유병률 변화): F1(w) = 2TP/(2TP + w·FP + FN)
        tp, fp, fn = base["tp"], base["fp"], base["fn"]
        fw = {f"f1_normal_x{w}": 2 * tp / (2 * tp + w * fp + fn) for w in (1, 10, 100)}
        prior1 = 600 * 99 / len(an)   # 행 유병률 1%가 되도록 정상 행을 늘리는 배수
        struct.append(dict(split=sid, model=mname, **base, latch_tp=latch["tp"], latch_fp=latch["fp"], latch_f1=latch["f1"],
                           miss_pos0=int(by_pos.loc[0, "sum"]), miss_pos1=int(by_pos.loc[1, "sum"]), miss_pos2_6=int(by_pos.loc[2:6, "sum"].sum()),
                           miss_pos7plus=int(by_pos.loc[7, "sum"]), recall_pos7plus=float(rec7), rows_before_first_alarm=int((~after).sum()),
                           recall_after_first_alarm=float(aa[after].mean()), f1_at_row_prior_1pct=2 * tp / (2 * tp + prior1 * fp + fn),
                           normal_rows=int(len(an)), abnormal_share=600 / (600 + len(an)), **fw))
struct = pd.DataFrame(struct)
say(struct.T.to_string())
struct.to_csv(C.OUT / "redA1_04_metric_structure.csv", index=False)
out["metric_structure"] = struct.to_dict("records")

# ---------- (4) 짧은 창 신경망 예측기(공정한 기준모델 점검) ----------
say("\n== (4) 신경망 다음 값 예측기: 창 길이별(정상 학습만, AR(2) 자리 대체)")


def lag_matrix(cur, seg, k):
    idx = C.windows_index(seg, k + 1)
    Xl = np.column_stack([cur[idx - j] for j in range(1, k + 1)])
    return idx, Xl


nn_rows = []
for sid in ("A", "B"):
    m = C.split_frames(normal, seg_n, sid)
    tr_seg = seg_n[m["train"]]
    cur_tr = Xn[m["train"], 2]
    sd = cur_tr.std()
    for k in (2, 8, 19):
        idx, L = lag_matrix(cur_tr, tr_seg, k)
        net = MLPRegressor(hidden_layer_sizes=(32, 16), max_iter=400, random_state=0, early_stopping=True, validation_fraction=0.2).fit(L / sd, cur_tr[idx] / sd)

        def resid(cur, seg, net=net, k=k):
            o = np.full(len(cur), np.nan)
            i, Lx = lag_matrix(cur, seg, k)
            if len(i):
                o[i] = np.abs(cur[i] - net.predict(Lx / sd) * sd)
            return o

        det = C.Detector().fit(Xn[m["train"]], tr_seg)
        det.t_dyn = C.Tail(resid(cur_tr, tr_seg))
        det.residual = lambda cur, seg, f=resid: f(cur, seg)
        for comp in ("nn_only", "v2_with_nn"):
            det.use = ("dynamics",) if comp == "nn_only" else ("magnitude", "waveform", "dynamics")
            det.calibrate(Xn[m["cal"]], seg_n[m["cal"]])
            pn, pa = det.predict(Xn[m["test"]], seg_n[m["test"]]), det.predict(Xa, seg_a)
            r = C.f1_rows(pn["alarm"], pa["alarm"])
            nn_rows.append(dict(split=sid, lags=k, variant=comp, **r, normal_records=int(pd.Series(pn["alarm"]).groupby(seg_n[m["test"]]).max().sum()),
                                abnormal_records=int(pd.Series(pa["alarm"]).groupby(seg_a).max().sum()), scored_abnormal=float(np.isfinite(pa["score"]).mean()),
                                train_rmse_over_sd=float(np.sqrt(np.mean((net.predict(L / sd) - cur_tr[idx] / sd) ** 2)))))
nn = pd.DataFrame(nn_rows)
say(nn.to_string(index=False))
nn.to_csv(C.OUT / "redA1_04_nn_predictor.csv", index=False)
out["nn_predictor"] = nn_rows
(C.OUT / "redA1_04_mechanism_placebo_metric.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
