"""최종 v2의 영향요인·오류 보강 분석 — 루브릭 사이클2 평가관 03(E1~E5)의 요구. analyze.py가 부른다.

모델·문턱·분할은 바꾸지 않는다. 이미 본 이상 21구간을 쓰는 사후 기술 분석이며, 원인 주장이 아니다.
- sensor_importance: 센서 부분집합 재적합 절제(E1), 시간 구조를 지킨 채널 교체, 경보 행 귀속
- position_vibration_misses: 위치 × 진동 수준 미탐(E2) — 행 조건표의 초반 창 교락을 푼다
- coupling: 정상 운전의 진동–전류 진폭 결합과 이상·오경보 구간의 결합 잔차(E2)
- false_alarm_events / near_miss: 동결 A·B와 시간순 재적합의 α 1·3·5% 오경보를 모은 사건표(E3)
- condition_stats: 조건표에 신뢰구간·집중도(lift)·Fisher 검정 열(E4)
- 현장 운영(평가관 04 U1·U2·U4·U6): 2단계 경보의 업무량·지연(대회·시간순·주입), 품질 의심 시간창, 감시 규칙의 전류 배율 모의,
  가정 기반 기대효과·손익분기
- 확률(평가관 02 M1, 05 O2): 라벨 적합 확률 층의 교차 평가와, 라벨 없이 경보를 이상 확률로 바꾸는 환산표
- error_condition_summary: FN·FP가 몰리는 조건을 공정조건 대리변수로 옮긴 12행 이내 요약(평가관 03 E5)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import roc_auc_score

from model import GuardModel, D, sine_score, layout, ALERT_UNIT_ROWS, LOAD_STATE_RMS, STATE_MIN_ROWS
import runtime
from press.scores import ExpTail, window_index
from press.calibrate import conformal_p, segment_max
from press.evaluate import evaluate_models

ALPHAS = (.01, .03, .05)
YEJUN = Path(__file__).resolve().parent.parent
MAG_VARIANTS = {"full": (0, 1, 2), "drop_AI0": (1, 2), "drop_AI1": (0, 2), "drop_AI2_from_magnitude": (0, 1),
                "current_only": (2,), "vibration_only": (0, 1)}
SHAPE = {"vibration_only": False}          # 파형·예측 오차 성분을 쓰지 않는 변형


def clopper(k, n, level=.95):
    if n == 0:
        return np.nan, np.nan
    a = (1 - level) / 2
    lo = stats.beta.ppf(a, k, n - k + 1) if k > 0 else 0.0
    hi = stats.beta.ppf(1 - a, k + 1, n - k) if k < n else 1.0
    return float(lo), float(hi)


class ComponentScorer:
    """GuardModel과 같은 산식을 크기 성분의 센서 부분집합만 바꿔 적합한다. 전체 센서면 저장 모델과 같다."""

    def __init__(self, train_q, seg, mag_sensors):
        self.idx = list(mag_sensors)
        x = train_q[D.SENSORS].to_numpy(float)[:, self.idx]
        self.mean, self.scale = x.mean(axis=0), x.std(axis=0)
        self.tail_mag = ExpTail(np.abs((x - self.mean) / self.scale).max(axis=1))
        cur = train_q[D.SENSORS[2]].to_numpy(float)
        self.tail6, self.tail8 = ExpTail(sine_score(cur, seg, 6)), ExpTail(sine_score(cur, seg, 8))
        i = window_index(seg, 3)
        self.coef = np.linalg.lstsq(np.column_stack([np.ones(len(i)), cur[i - 1], cur[i - 2]]), cur[i], rcond=None)[0]
        self.tail_ar = ExpTail(self._residual(cur, seg))

    def _residual(self, cur, seg):
        i = window_index(seg, 3)
        out = np.full(len(cur), np.nan)
        out[i] = np.abs(cur[i] - self.coef[0] - self.coef[1] * cur[i - 1] - self.coef[2] * cur[i - 2])
        return out

    def parts(self, frame_q, seg):
        x = frame_q[D.SENSORS].to_numpy(float)[:, self.idx]
        pos, _ = D.segment_positions(seg)
        cur = frame_q[D.SENSORS[2]].to_numpy(float)
        return dict(magnitude=self.tail_mag(np.abs((x - self.mean) / self.scale).max(axis=1)),
                    waveform=np.where(pos < 7, self.tail6(sine_score(cur, seg, 6)), self.tail8(sine_score(cur, seg, 8))),
                    dynamics=self.tail_ar(self._residual(cur, seg)))


def _frames(normal, abnormal, sid):
    split = D.split_normal(normal, D.segments(normal), sid)
    q = {k: D.quantize(D.inputs_only(split[k]), "matched") for k in ("train", "cal", "test")}
    q["abn"] = D.quantize(D.inputs_only(abnormal), "matched")
    return split, q, {k: layout(v)[1] for k, v in q.items()}


def sensor_importance(normal, abnormal, vendor, metrics, models):
    """E1: 센서 부분집합 재적합(α 1·3·5%), 채널 교체(20회), 경보 행 귀속, 단변량 판별력."""
    rows = []
    for sid in D.SPLITS:
        split, q, segs = _frames(normal, abnormal, sid)
        for variant, sensors in MAG_VARIANTS.items():
            sc = ComponentScorer(q["train"], segs["train"], sensors)
            scores = {}
            for k in ("cal", "test", "abn"):
                p = sc.parts(q[k], segs[k])
                s = np.fmax(np.fmax(p["magnitude"], p["waveform"]), p["dynamics"]) if SHAPE.get(variant, True) else p["magnitude"]
                scores[k] = s
            mt, _ = evaluate_models(vendor, split["name"], "matched", {variant: scores}, dict(cal=q["cal"], test=q["test"], abn=q["abn"]),
                                    {"cal": segs["cal"], "test": segs["test"], "abn": segs["abn"]}, units=("recording_segments",))
            mt = mt[mt.criterion.eq("conformal")]
            if variant == "full":   # 저장 모델과 같아야 한다
                for alpha in ALPHAS:
                    got = metrics[metrics.split.eq(sid) & metrics.model.eq("guard_v2") & metrics.alpha.eq(alpha)].iloc[0]
                    row = mt[mt.alpha.eq(alpha)].iloc[0]
                    assert (int(row.tp), int(row.fp), int(row.fn)) == (int(got.tp), int(got.fp), int(got.fn)), ("전체 센서 재적합이 저장 모델과 다름", sid, alpha)
            for r in mt.itertuples():
                rows.append(dict(method="refit_ablation", split=sid, variant=variant, magnitude_sensors="+".join(D.SENSORS[i] for i in sensors),
                                 shape_components=SHAPE.get(variant, True), alpha=r.alpha, tp=int(r.tp), fp=int(r.fp), fn=int(r.fn), f1=float(r.f1_all_rows),
                                 normal_alerted_segments=int(r.normal_notified_segments), abnormal_detected_segments=int(r.abnormal_notified_segments), repeats=1))
        # 채널 교체: 이상 기록의 채널 하나를 같은 분할 정상 평가 기록(같은 길이 이상)의 앞부분으로 바꾼다. 시간 구조는 지킨다.
        model = models[sid]
        test = D.inputs_only(split["test"]); seg_t = layout(test)[1]
        abn = D.inputs_only(abnormal); seg_a = layout(abn)[1]
        lengths_t = pd.Series(seg_t).value_counts()
        for j, sensor in enumerate(D.SENSORS):
            outcomes = []
            for rep in range(20):
                rng = np.random.default_rng(1000 + rep)
                swapped = abn.copy()
                for r in np.unique(seg_a):
                    idx = np.flatnonzero(seg_a == r)
                    donors = lengths_t[lengths_t >= len(idx)].index.to_numpy()
                    d = np.flatnonzero(seg_t == rng.choice(donors))[:len(idx)]
                    swapped.loc[idx, sensor] = test[sensor].to_numpy()[d]
                p = model.predict(swapped, .01)
                outcomes.append((int((p.alarm == 0).sum()), int(p.groupby("record_id").alarm.max().sum())))
            fn = np.array([o[0] for o in outcomes]); det = np.array([o[1] for o in outcomes])
            rows.append(dict(method="channel_swap", split=sid, variant=f"swap_{sensor}", magnitude_sensors="", shape_components=True, alpha=.01,
                             tp=int(600 - np.median(fn)), fp=np.nan, fn=float(np.median(fn)), f1=np.nan, normal_alerted_segments=np.nan,
                             abnormal_detected_segments=float(np.median(det)), repeats=20, fn_min=int(fn.min()), fn_max=int(fn.max()),
                             detected_min=int(det.min()), detected_max=int(det.max())))
        # 경보 행 귀속(동결 모델, α=1%): 크기 발화 센서와 전류 성분만의 경보
        pa = model.predict(abnormal, .01)
        al = pa[pa.alarm.eq(1)]
        mag = al.reason.str.contains("magnitude")
        for label, k in (("magnitude_AI0", int((mag & al.magnitude_sensor.eq(D.SENSORS[0])).sum())), ("magnitude_AI1", int((mag & al.magnitude_sensor.eq(D.SENSORS[1])).sum())),
                         ("magnitude_AI2", int((mag & al.magnitude_sensor.eq(D.SENSORS[2])).sum())), ("current_components_only", int((~mag).sum()))):
            rows.append(dict(method="alarm_attribution", split=sid, variant=label, magnitude_sensors="", shape_components=True, alpha=.01,
                             tp=k, fp=np.nan, fn=np.nan, f1=np.nan, normal_alerted_segments=np.nan, abnormal_detected_segments=np.nan, repeats=1,
                             share_of_alarm_rows=k / len(al)))
        # 단변량 판별력(구간 SD의 AUROC): 모델 기여 순위와 다른 이유를 적기 위한 참고
        for sensor in D.SENSORS:
            sd_n = test.groupby(seg_t)[sensor].std().dropna(); sd_a = abn.groupby(seg_a)[sensor].std().dropna()
            auc = roc_auc_score(np.r_[np.zeros(len(sd_n)), np.ones(len(sd_a))], np.r_[sd_n, sd_a])
            z_a = abn.groupby(seg_a)[sensor].std().median() / model.scale[D.SENSORS.index(sensor)]
            rows.append(dict(method="univariate_segment_sd", split=sid, variant=sensor, magnitude_sensors="", shape_components=np.nan, alpha=np.nan,
                             tp=np.nan, fp=np.nan, fn=np.nan, f1=np.nan, normal_alerted_segments=np.nan, abnormal_detected_segments=np.nan, repeats=1,
                             auroc=float(auc), abnormal_sd_over_train_scale=float(z_a)))
    return pd.DataFrame(rows)


def _record_features(frame_q, seg, model, train_bounds=None):
    v = frame_q[D.SENSORS[:2]].to_numpy(float); cur = frame_q[D.SENSORS[2]].to_numpy(float)
    zvib = np.abs((v - model.mean[:2]) / model.scale[:2]).max(axis=1)
    rows = []
    for s in np.unique(seg):
        i = np.flatnonzero(seg == s)
        c = cur[i] - cur[i].mean()
        rows.append(dict(record=int(s), length=len(i), vib_sd=float(np.sqrt(v[i, 0].var(ddof=1) + v[i, 1].var(ddof=1))) if len(i) > 1 else np.nan,
                         ai0_sd=float(v[i, 0].std(ddof=1)) if len(i) > 1 else np.nan, ai1_sd=float(v[i, 1].std(ddof=1)) if len(i) > 1 else np.nan,
                         current_amp=float(np.sqrt(2 * np.mean(c ** 2))), vib_maxz=float(zvib[i].max())))
    return pd.DataFrame(rows)


def position_vibration_misses(normal, abnormal, models):
    """E2 ①: 위치(0–1 / 2–6 / ≥7) × 구간 진동 수준(max|z| > 정상 학습 q95) 미탐. 초반 창 교락을 푼다."""
    rows = []
    for sid, model in models.items():
        split, q, segs = _frames(normal, abnormal, sid)
        q95 = _record_features(q["train"], segs["train"], model).vib_maxz.quantile(.95)
        feat = _record_features(q["abn"], segs["abn"], model).set_index("record")
        pa = model.predict(abnormal, .01)
        pos = pa.position.to_numpy()
        vib_high = pa.record_id.map(feat.vib_maxz > q95).to_numpy(bool)
        miss = pa.alarm.to_numpy() == 0
        bins = {"0-1": pos <= 1, "2-6": (pos >= 2) & (pos <= 6), ">=7": pos >= 7, ">=2": pos >= 2}
        # 진동 수준을 가리지 않은 위치 0–1 대 ≥2(행 단위, 초반 창 미탐 집중)
        k01, n01 = int((miss & (pos <= 1)).sum()), int((pos <= 1).sum())
        k2, n2 = int((miss & (pos >= 2)).sum()), int((pos >= 2).sum())
        p01 = stats.fisher_exact([[k01, n01 - k01], [k2, n2 - k2]], alternative="greater").pvalue
        for label, (k, n) in (("0-1", (k01, n01)), (">=2", (k2, n2))):
            lo, hi = clopper(k, n)
            rows.append(dict(split=sid, position=label, vibration="all", missed_rows=k, rows=n, miss_rate=k / n, ci_low=lo, ci_high=hi,
                             records=int(len(np.unique(pa.record_id.to_numpy()[(pos <= 1) if label == "0-1" else (pos >= 2)]))),
                             vib_threshold_train_q95=float(q95), fisher_p_normal_vs_high=np.nan, fisher_p_greater=np.nan,
                             fisher_p_pos01_vs_ge2_greater=float(p01)))
        for label, m in bins.items():
            cells = {}
            for vib_label, v in (("vibration_normal_range", ~vib_high), ("vibration_high", vib_high)):
                k, n = int((miss & m & v).sum()), int((m & v).sum())
                lo, hi = clopper(k, n)
                cells[vib_label] = (k, n)
                rows.append(dict(split=sid, position=label, vibration=vib_label, missed_rows=k, rows=n, miss_rate=k / n if n else np.nan, ci_low=lo, ci_high=hi,
                                 records=int(len(np.unique(pa.record_id.to_numpy()[m & v]))), vib_threshold_train_q95=float(q95)))
            (k1, n1), (k2, n2) = cells["vibration_normal_range"], cells["vibration_high"]
            p = stats.fisher_exact([[k1, n1 - k1], [k2, n2 - k2]]).pvalue if n1 and n2 else np.nan
            p1 = stats.fisher_exact([[k1, n1 - k1], [k2, n2 - k2]], alternative="greater").pvalue if n1 and n2 else np.nan
            rows[-1]["fisher_p_normal_vs_high"] = rows[-2]["fisher_p_normal_vs_high"] = float(p)          # 양측
            rows[-1]["fisher_p_greater"] = rows[-2]["fisher_p_greater"] = float(p1)                      # 단측: 진동 정상 범위의 미탐률이 더 높다
    return pd.DataFrame(rows)


def coupling(normal, abnormal, models, fa_records):
    """E2 ③: 정상 학습 구간(길이≥17, 사인 유사)에서 log 진동 SD ~ log 전류 진폭 결합, 블록별 재현, 결합 잔차 z."""
    fit_rows, rec_rows = [], []
    from analyze import segment_feature_table, condition_bounds
    for sid, model in models.items():
        split, q, segs = _frames(normal, abnormal, sid)
        bounds = condition_bounds(segment_feature_table(q["train"], D.segments(q["train"]), model.mean, model.scale))
        def table(part):
            f = _record_features(q[part], segs[part], model)
            r2 = segment_feature_table(q[part], D.segments(q[part]), model.mean, model.scale).set_index("record_id").r2_segment
            f["r2"] = f.record.map(r2)
            return f
        tr = table("train")
        ok = (tr.length >= 17) & (tr.r2 >= bounds["r2_low"]) & (tr.vib_sd > 0) & (tr.current_amp > 0)
        x, y = np.log(tr.current_amp[ok]), np.log(tr.vib_sd[ok])
        slope, icpt, r, _, _ = stats.linregress(x, y)
        resid_sd = float(np.std(y - (icpt + slope * x), ddof=2))
        per_sensor = {s: float(np.corrcoef(x, np.log(tr[s][ok]))[0, 1]) for s in ("ai0_sd", "ai1_sd")}
        seg_all = D.segments(normal)
        _, train_end, _ = D.SPLITS[sid]
        block_r = []
        for b in range(0, train_end, 60):
            m = ok & (tr.record >= b) & (tr.record < b + 60)
            if m.sum() >= 10:
                block_r.append(float(np.corrcoef(np.log(tr.current_amp[m]), np.log(tr.vib_sd[m]))[0, 1]))
        fit_rows.append(dict(split=sid, records=int(ok.sum()), slope=float(slope), intercept=float(icpt), r=float(r), resid_sd=resid_sd,
                             r_ai0=per_sensor["ai0_sd"], r_ai1=per_sensor["ai1_sd"], block_r_min=min(block_r), block_r_max=max(block_r), blocks=len(block_r),
                             note="정상 학습 기록구간(길이≥17, 사인 유사). 운전 강도(부하)라는 공통 요인으로 해석하는 가설"))
        for part, label in (("test", "normal_test"), ("abn", "abnormal")):
            f = table(part)
            f = f[(f.length >= 17) & (f.vib_sd > 0) & (f.current_amp > 0)].copy()
            f["resid_z"] = (np.log(f.vib_sd) - (icpt + slope * np.log(f.current_amp))) / resid_sd
            f["split"], f["subset"] = sid, label
            f["false_alarm"] = f.record.isin(fa_records.get(sid, [])) if label == "normal_test" else False
            f["resid_rank_desc"] = f.resid_z.rank(ascending=False).astype(int)
            f.insert(1, "absolute_record", f.record + (D.SPLITS[sid][2] if label == "normal_test" else 0))   # 정상은 정상 CSV 전체 번호
            rec_rows.append(f)
    return pd.DataFrame(fit_rows), pd.concat(rec_rows, ignore_index=True)


def rolling_models(normal):
    """train.py --rolling과 같은 시간순 5폴드 재적합(학습 0~end−1, 보정 다음 120구간, 평가 그다음 60구간)."""
    seg_all = D.segments(normal)
    fits = {}
    for end in (180, 240, 300, 360, 420):
        tr = normal[seg_all < end]; ca = normal[(seg_all >= end) & (seg_all < end + 120)]
        fits[f"rolling_test_{end + 120}_{end + 179}"] = (GuardModel.fit(tr, ca, split=f"train_to_{end}"), end + 120, end + 180)
    return fits


def all_fits(models, rolling):
    return {"frozen_A": (models["A"], 480, 600), "frozen_B": (models["B"], 420, 600), **rolling}


def false_alarm_events(normal, abnormal, models, rolling):
    """E3: 동결 A·B와 시간순 재적합 5폴드의 α 1·3·5% 오경보. 보정값이 같은 모델은 한 번만 센다."""
    seg_all = D.segments(normal)
    t_all = pd.to_datetime(normal[D.TIME])
    fits = all_fits(models, rolling)
    seen, rows = {}, []
    for name, (m, lo, hi) in fits.items():
        key = tuple(np.round(np.sort(m.cal), 12))
        same_as = seen.get(key)
        seen.setdefault(key, name)
        frame = normal[(seg_all >= lo) & (seg_all < hi)]
        rid = seg_all[(seg_all >= lo) & (seg_all < hi)]
        q = D.quantize(D.inputs_only(frame), "matched"); seg = layout(q)[1]
        feat = _record_features(q, seg, m)
        for alpha in ALPHAS:
            p = m.predict(frame, alpha)
            for r, g in p.groupby("record_id"):
                if not g.alarm.any():
                    continue
                first = g[g.alarm.eq(1)].iloc[0]
                absolute = int(rid[g.index[0]])
                rows.append(dict(model=name, same_calibration_as=same_as or "", alpha=alpha, record=absolute, time=f"{t_all[seg_all == absolute].iloc[0]:%H:%M:%S}",
                                 block=f"{absolute // 60 * 60}~{absolute // 60 * 60 + 59}", length=len(g), first_alarm_position=int(first.position),
                                 alarm_rows=int(g.alarm.sum()), reasons="+".join(sorted(set("+".join(g[g.alarm.eq(1)].reason).split("+")) - {""})),
                                 magnitude_sensor=first.magnitude_sensor if "magnitude" in first.reason else "",
                                 vib_maxz=float(feat.vib_maxz.iloc[r]), current_amp=float(feat.current_amp.iloc[r]), peak_score=float(g.score.max())))
    ev = pd.DataFrame(rows)
    ev["independent"] = ev.same_calibration_as.eq("")
    return ev


def near_miss(normal, models):
    """E3 ③: 정상 평가 구간의 최대 점수 / α=1% 문턱 비와 운전 조건의 순위상관."""
    rows, corr = [], []
    seg_all = D.segments(normal)
    for sid, m in models.items():
        lo = D.SPLITS[sid][2]
        frame = normal[seg_all >= lo]
        q = D.quantize(D.inputs_only(frame), "matched"); seg = layout(q)[1]
        feat = _record_features(q, seg, m)
        smax = segment_max(m.components(q, seg)["score"], seg)
        thr = np.sort(m.cal)[-1]
        feat["ratio_to_threshold"] = smax / thr
        feat["time_order"] = np.arange(len(feat))
        feat["split"] = sid
        feat.insert(1, "absolute_record", feat.record + lo)     # 정상 CSV 전체의 구간 번호(fp_events_v2의 record와 같다)
        rows.append(feat)
        for col in ("vib_maxz", "vib_sd", "current_amp", "time_order"):
            ok = feat[col].notna()
            corr.append(dict(split=sid, condition=col, spearman=float(stats.spearmanr(feat.ratio_to_threshold[ok], feat[col][ok]).statistic),
                             records=int(ok.sum()), records_ge_0_9=int((feat.ratio_to_threshold >= .9).sum())))
    return pd.concat(rows, ignore_index=True), pd.DataFrame(corr)


def condition_stats(cond_segments):
    """E4: 구간 단위 조건표에 Clopper–Pearson 95% 구간, 전체 대비 비율(lift), 조건 안팎 단측 Fisher p, 표본 부족 표시를 더한다."""
    rows = []
    for key, g in cond_segments.groupby(["split_id", "model", "alpha", "subset", "condition"], sort=False):
        total_err, total_n = int(g.error_segments.sum()), int(g.segments.sum())
        base = total_err / total_n if total_n else np.nan
        for r in g.itertuples():
            k, n = int(r.error_segments), int(r.segments)
            lo, hi = clopper(k, n)
            k_out, n_out = total_err - k, total_n - n
            p = stats.fisher_exact([[k, n - k], [k_out, n_out - k_out]], alternative="greater").pvalue if n and n_out else np.nan
            note = ("크기 성분 경보의 발화 경로라 정의상 따라온다. 원인 조건은 운전 강도·시간대(coupling·near_miss)에서 찾는다"
                    if key[3] == "normal" and key[4] == "vib_high" and str(r.value).startswith("high") else "")
            rows.append(dict(split_id=key[0], model=key[1], alpha=key[2], subset=key[3], condition=key[4], value=r.value, error_segments=k, segments=n,
                             rate=k / n if n else np.nan, ci_low=lo, ci_high=hi, lift=(k / n) / base if n and base else np.nan,
                             fisher_p_greater=float(p), small_sample=n < 5, note=note))
    return pd.DataFrame(rows)


# ---------- 이상 확률 층 평가(루브릭 사이클2 평가관 02 M1, 05 O1·O2) ----------
FOLDS = {"3fold": (np.arange(0, 7), np.arange(7, 14), np.arange(14, 21)), "21fold": tuple(np.array([k]) for k in range(21))}
PRIOR_GRID = (.001, .003, .01, .03, .1)


def _lr_out_of_fold(model, cal_scores, test_scores, abn_scores, abn_records, folds):
    """이상 행은 그 겹을 뺀 보정기, 정상 평가 행은 겹 보정기들의 우도비 중앙값(정상 평가 행은 어느 적합에도 쓰지 않음)."""
    from probability import ProbabilityCalibrator
    la, ln = np.full(len(abn_scores), np.nan), []
    for hold in folds:
        keep = ~np.isin(abn_records, hold)
        cal = ProbabilityCalibrator.fit(cal_scores, abn_scores[keep], calibration_units=len(model.cal))
        la[~keep] = cal.likelihood_ratio(abn_scores[~keep])
        ln.append(cal.likelihood_ratio(test_scores))
    return np.median(ln, axis=0), la


def _lr_variant(cal_scores, test_scores, abn_scores, abn_records, folds, kind):
    """평가 비교용 보정 변형의 교차 우도비: 상한 없는 등방 회귀, Platt(로지스틱). 배포하지 않는다."""
    from probability import ProbabilityCalibrator
    from sklearn.linear_model import LogisticRegression
    la, ln = np.full(len(abn_scores), np.nan), []
    for hold in folds:
        keep = ~np.isin(abn_records, hold)
        if kind == "isotonic_uncapped":
            cal = ProbabilityCalibrator.fit(cal_scores, abn_scores[keep], calibration_units=None)
            la[~keep] = cal.likelihood_ratio(abn_scores[~keep]); ln.append(cal.likelihood_ratio(test_scores))
        else:
            x = np.r_[cal_scores, abn_scores[keep]]; y = np.r_[np.zeros(len(cal_scores)), np.ones(int(keep.sum()))]
            ok = np.isfinite(x)
            m = LogisticRegression(C=1e6, max_iter=2000).fit(x[ok, None], y[ok])
            odds_fit = y[ok].mean() / (1 - y[ok].mean())
            def lr(s):
                q = np.clip(m.predict_proba(np.nan_to_num(np.asarray(s, float))[:, None])[:, 1], 1e-12, 1 - 1e-12)
                return q / (1 - q) / odds_fit
            la[~keep] = lr(abn_scores[~keep]); ln.append(lr(test_scores))
    return np.median(ln, axis=0), la


def probability_evaluation(normal, abnormal, models):
    from probability import ProbabilityCalibrator, posterior, expected_calibration_error, min_rank_nominal_likelihood_ratio, sellke_bayes_factor
    from sklearn.metrics import brier_score_loss, log_loss, average_precision_score
    rows, rel, conv = [], [], []
    for sid, model in models.items():
        split = D.split_normal(normal, D.segments(normal), sid)
        cal_scores = model.predict(split["cal"]).score.to_numpy()
        pt, pa = model.predict(split["test"]), model.predict(abnormal)
        st, sa, ra = pt.score.to_numpy(), pa.score.to_numpy(), pa.record_id.to_numpy()
        y = np.r_[np.zeros(len(st)), np.ones(len(sa))]
        pi_rows = len(sa) / len(y)
        rec_t, rec_a = pt.record_id.to_numpy(), ra
        n_rec_t, n_rec_a = len(np.unique(rec_t)), len(np.unique(rec_a))
        pi_rec = n_rec_a / (n_rec_a + n_rec_t)
        for cv, folds in FOLDS.items():
            ln, la = _lr_out_of_fold(model, cal_scores, st, sa, ra, folds)
            if cv == "21fold":
                la21 = la
            p = posterior(np.r_[ln, la], pi_rows)
            # 기록구간 단위: 기록 최대 우도비(확률은 점수에 단조)
            rl = np.r_[pd.Series(ln).groupby(rec_t).max().to_numpy(), pd.Series(la).groupby(rec_a).max().to_numpy()]
            yr = np.r_[np.zeros(n_rec_t), np.ones(n_rec_a)]
            pr = posterior(rl, pi_rec)
            naive = 1 - np.r_[pt.p_value.to_numpy(), pa.p_value.to_numpy()]
            for name, q in (("calibrated_isotonic", p), ("naive_1_minus_p", naive), ("prevalence_only", np.full(len(y), pi_rows))):
                q = np.clip(np.nan_to_num(q, nan=pi_rows), 1e-9, 1 - 1e-9)
                rows.append(dict(split=sid, cv=cv, unit="rows", method=name, n=len(y), prevalence=pi_rows, brier=brier_score_loss(y, q),
                                 log_loss=log_loss(y, q), ece=expected_calibration_error(y, q), auroc=roc_auc_score(y, q) if name != "prevalence_only" else .5,
                                 ap=average_precision_score(y, q) if name != "prevalence_only" else pi_rows))
            for name, q in (("calibrated_isotonic", pr), ("prevalence_only", np.full(len(yr), pi_rec))):
                q = np.clip(q, 1e-9, 1 - 1e-9)
                rows.append(dict(split=sid, cv=cv, unit="records", method=name, n=len(yr), prevalence=pi_rec, brier=brier_score_loss(yr, q),
                                 log_loss=log_loss(yr, q), ece=expected_calibration_error(yr, q), auroc=roc_auc_score(yr, q) if name != "prevalence_only" else .5,
                                 ap=average_precision_score(yr, q) if name != "prevalence_only" else pi_rec))
            if cv == "21fold":
                # 비교: 표시 상한(121)이 없는 등방 회귀와 Platt. 표시 정책으로 최상위 구간 확률을 낮추면 ECE가 커질 수 있다.
                for kind in ("isotonic_uncapped", "platt_logistic"):
                    vn, va = _lr_variant(cal_scores, st, sa, ra, folds, kind)
                    q = np.clip(posterior(np.r_[vn, va], pi_rows), 1e-9, 1 - 1e-9)
                    rows.append(dict(split=sid, cv=cv, unit="rows", method=kind, n=len(y), prevalence=pi_rows, brier=brier_score_loss(y, q),
                                     log_loss=log_loss(y, q), ece=expected_calibration_error(y, q), auroc=roc_auc_score(y, q), ap=average_precision_score(y, q)))
                edges = [0, .01, .05, .1, .3, .5, .7, .9, .99, 1.0000001]
                b = pd.cut(p, edges, right=False, include_lowest=True)
                for interval, g in pd.DataFrame(dict(y=y, p=p, b=b)).groupby("b", observed=True):
                    lo, hi = clopper(int(g.y.sum()), len(g))
                    rel.append(dict(split=sid, bin=str(interval), rows=len(g), mean_predicted=float(g.p.mean()), observed=float(g.y.mean()), ci_low=lo, ci_high=hi))
        deploy = ProbabilityCalibrator.fit(cal_scores, sa, calibration_units=len(model.cal), split=sid)
        thr = float(np.sort(model.cal)[-1])
        lr_thr = float(deploy.likelihood_ratio([thr + 1e-9])[0])
        det = float(pa.groupby("record_id").alarm.max().mean())
        # 문턱 근처 등방 회귀 계단: 문턱이 든 계단의 왼쪽 끝과 그 안의 정상 보정·이상 행 수(B의 문턱 확률이 낮은 이유)
        xs = np.asarray(deploy.x)
        lo_x = float(xs[xs < thr].max()) if (xs < thr).any() else float("nan")
        hi_x = float(xs[xs > thr].min()) if (xs > thr).any() else float("nan")
        # 실제 경보 행(α 1%)의 우도비: 예측 파일과 같은 값(정상 평가 행은 배포 보정기, 이상 행은 그 기록을 뺀 21겹 교차 적합)
        alarm_lr_n = deploy.likelihood_ratio(st[pt.alarm.to_numpy() == 1]) if (pt.alarm == 1).any() else np.array([])
        alarm_lr_a = la21[pa.alarm.to_numpy() == 1]
        both_lr = np.r_[alarm_lr_n, alarm_lr_a]
        sbb = 1 / sellke_bayes_factor(1 / (len(model.cal) + 1))
        for pi in PRIOR_GRID:
            conv.append(dict(split=sid, prior=pi, threshold_score=thr, lr_at_threshold=lr_thr, p_at_threshold=float(posterior(lr_thr, pi)),
                             iso_step_left=lo_x, iso_step_right=hi_x,
                             step_normal_cal_rows=int(((cal_scores >= lo_x) & (cal_scores <= thr)).sum()),
                             step_abnormal_rows=int(((sa >= lo_x) & (sa <= thr)).sum()),
                             step_p_hat=float(deploy.fitted([(lo_x + thr) / 2])[0]),
                             alarm_rows=int(len(both_lr)), alarm_rows_min_lr=float(both_lr.min()), alarm_rows_lr_below_1=int((both_lr < 1).sum()),
                             alarm_rows_min_p=float(posterior(both_lr.min(), pi)),
                             false_alarm_rows=int(len(alarm_lr_n)), false_alarm_max_lr=float(alarm_lr_n.max()) if len(alarm_lr_n) else np.nan,
                             false_alarm_max_p=float(posterior(alarm_lr_n.max(), pi)) if len(alarm_lr_n) else np.nan,
                             lr_cap=deploy.lr_cap, p_at_cap=float(posterior(deploy.lr_cap, pi)),
                             label_free_nominal_far=1 / (len(model.cal) + 1),
                             label_free_min_rank_nominal_lr=min_rank_nominal_likelihood_ratio(len(model.cal), det),
                             label_free_min_rank_nominal_p=float(posterior(min_rank_nominal_likelihood_ratio(len(model.cal), det), pi)),
                             sbb_reference_lr=sbb, sbb_reference_p=float(posterior(sbb, pi)),
                             sbb_note="참고값: 연속 p값을 정확히 관측하고 대립에서 p가 Beta(ξ,1) 족일 때의 회의적 환산. 알림은 p≤1/121 사건이라 상한이 아니다. label_free_min_rank_nominal_lr는 FAR=1/121 시나리오이며 LR의 보편적 상한이 아니다"))
    return pd.DataFrame(rows), pd.DataFrame(rel), pd.DataFrame(conv)


# ---------- 2단계 경보(평가관 04 U1, 03 E7) ----------
def alert_level_evaluation(normal, abnormal, models, rolling):
    """U1: 1단계(첫 알림)·2단계(격상)의 정상 알림 구간·교대 환산·이항 상한과 이상 21구간의 지연. 동결 A·B와 시간순 5폴드.
    420~479 폴드는 B, 480~539 폴드는 A와 보정값이 같다(same_calibration_as). 이상 21구간 결과는 사후 관찰이다."""
    rows, seen = [], {}
    seg_all = D.segments(normal)
    for name, (model, lo, hi) in all_fits(models, rolling).items():
        key = tuple(np.round(np.sort(model.cal), 12)); same_as = seen.get(key); seen.setdefault(key, name)
        test = normal[(seg_all >= lo) & (seg_all < hi)]
        t = pd.to_datetime(test[D.TIME]); elapsed_h = (t.max() - t.min()).total_seconds() / 3600
        for alpha in ALPHAS:
            pn, pa = model.predict(test, alpha), model.predict(abnormal, alpha)
            rec_n = pn.groupby("record_id").agg(l1=("alarm", "max"), l2=("escalation", "max"))
            rec_a = pa.groupby("record_id").agg(l1=("alarm", "max"), l2=("escalation", "max"))
            first = pa[pa.alarm.eq(1)].groupby("record_id").position.min()
            esc = pa[pa.escalation.eq(1)].groupby("record_id").position.min()
            both = pd.concat([first, esc], axis=1, keys=["first", "esc"]).dropna()
            for level, col in ((1, "l1"), (2, "l2")):
                k, n = int(rec_n[col].sum()), len(rec_n)
                lo_ci, hi_ci = clopper(k, n)
                d = first if level == 1 else esc
                rows.append(dict(model=name, split=name.split("_")[-1] if name.startswith("frozen") else name, normal_window=f"{lo}~{hi - 1}",
                                 same_calibration_as=same_as or "", alpha=alpha, level=level,
                                 normal_alerted_segments=k, normal_segments=n, normal_rate=k / n, normal_rate_ci_high=hi_ci,
                                 nominal_alerts_per_8h_elapsed=(np.floor(alpha * (len(model.cal) + 1) + 1e-9) / (len(model.cal) + 1)) * n / elapsed_h * 8 if level == 1 else np.nan,
                                 alerts_per_8h_elapsed=k / elapsed_h * 8, upper95_alerts_per_8h_elapsed=stats.beta.ppf(.95, k + 1, n - k) * n / elapsed_h * 8,
                                 abnormal_detected_segments=int(rec_a[col].sum()), abnormal_segments=len(rec_a),
                                 delay_median_s=float(d.median() * D.DT) if len(d) else np.nan, delay_max_s=float(d.max() * D.DT) if len(d) else np.nan,
                                 escalation_after_first_median_s=float(((both.esc - both["first"]) * D.DT).median()) if level == 2 and len(both) else np.nan,
                                 escalation_after_first_max_s=float(((both.esc - both["first"]) * D.DT).max()) if level == 2 and len(both) else np.nan))
    out = pd.DataFrame(rows)
    out["independent"] = out.same_calibration_as.eq("")
    return out


INJECTION_LEVELS = (("none", 0.0), ("cur_noise", .1), ("cur_noise", .2), ("cur_offset", .2), ("cur_offset", .4), ("vib_noise", 2.0), ("vib_noise", 4.0))


def alert_level_injection(normal, models, reps=5):
    """U1: 보완 실험 E1과 같은 계단형 주입(길이 30행 이상 정상 평가 단위의 10행째부터)에서 단계별 2초 안 탐지율과 지연. 잡음 족은 반복 평균."""
    from model import alert_levels
    from recalibrate import inject, unit_layout, T0, WINDOW, MIN_UNIT_ROWS
    rows = []
    for sid, model in models.items():
        test = D.inputs_only(D.split_normal(normal, D.segments(normal), sid)["test"])
        units, in_unit, size = unit_layout(test)
        eligible = size >= MIN_UNIT_ROWS
        mask = eligible & (in_unit >= T0)
        for fam, lv in INJECTION_LEVELS:
            n_rep = reps if fam in ("cur_noise", "vib_noise") else 1
            per_alpha = {a: [] for a in ALPHAS}
            for rep in range(n_rep):
                frame = test if fam == "none" else inject(test, model, fam, lv, mask, np.random.default_rng(rep))
                base = model.predict(frame, .05)
                for alpha in ALPHAS:
                    alarm = (base.p_value.to_numpy() <= alpha)
                    level, esc = alert_levels(base.record_id.to_numpy(), base.alert_unit.to_numpy(), alarm)
                    f = pd.DataFrame(dict(u=units, i=in_unit, a=alarm, e=esc.astype(bool)))[eligible]
                    post = f.i >= T0
                    win = post & (f.i < T0 + WINDOW)
                    g = f.assign(first=np.where(post & f.a, f.i, np.inf), second=np.where(post & f.e, f.i, np.inf),
                                 pre=~post & f.a, w1=win & f.a, w2=win & f.e).groupby("u").agg(first=("first", "min"), second=("second", "min"),
                                 pre=("pre", "any"), w1=("w1", "any"), w2=("w2", "any"))
                    per_alpha[alpha].append(g)
            for alpha, gs in per_alpha.items():
                g = pd.concat(gs, ignore_index=True)
                d1 = (g["first"][np.isfinite(g["first"])] - T0) * D.DT
                d2 = (g["second"][np.isfinite(g["second"])] - T0) * D.DT
                rows.append(dict(split=sid, family=fam, level_value=lv, alpha=alpha, units=int(len(gs[0])), trials=int(len(g)),
                                 level1_detect_2s=float(g.w1.mean()), level2_detect_2s=float(g.w2.mean()),
                                 level1_delay_median_s=float(d1.median()) if len(d1) else np.nan,
                                 level2_delay_median_s=float(d2.median()) if len(d2) else np.nan,
                                 pre_alarm_units=float(g.pre.mean()),
                                 note="주입 없음 행은 주입 전 구간과 같은 위치의 정상 경보율(2초 창)이다"))
    return pd.DataFrame(rows)


def workload_extras(workload, models):
    """평가관 05 O1: 보정 집합에 조건부인 실제 오경보율 분포와 관측을 더한 사후 95% 상한(교대 환산)."""
    w = workload.copy()
    n_cal = {sid: len(m.cal) for sid, m in models.items()}
    out = []
    for r in w.itertuples():
        n = n_cal[r.split_id]
        k_rank = int(np.floor(r.alpha * (n + 1) + 1e-9))       # 문턱 = 보정 최대 점수 k번째(허용 초과 k−1)
        a, b = k_rank, n + 1 - k_rank                           # 조건부 오경보율 ~ Beta(k, n+1−k)
        x, m = int(r.first_alert_segments), int(r.normal_segments)
        post95 = float(stats.beta.ppf(.95, a + x, b + m - x))
        out.append(dict(far_conditional_mean=a / (a + b), far_conditional_p_exceeds_alpha=float(stats.beta.sf(r.alpha, a, b)),
                        posterior95_rate=post95, posterior95_alerts_per_8h_elapsed=post95 * r.units_per_elapsed_hour * 8))
    return pd.concat([w.reset_index(drop=True), pd.DataFrame(out)], axis=1)


def alert_budget_design(units_per_hour_intermittent):
    """평가관 04 U1 ③: 교대(8시간)당 목표 1단계 알림 수에서 α, 필요한 보정 단위 수, 정상 수집 시간을 역산한다."""
    rows = []
    for target in (1, 3, 5, 10, 30):
        for mode, uph in (("간헐 수집(대회 밀도)", units_per_hour_intermittent), ("연속 수집(50행 블록)", 3600 / (ALERT_UNIT_ROWS * D.DT))):
            alpha = target / (uph * 8)
            n = int(np.ceil(1 / alpha - 1e-9)) - 1
            rows.append(dict(target_alerts_per_8h=target, collection=mode, units_per_hour=uph, alpha_required=alpha, calibration_units_required=n,
                             normal_collection_hours=n / uph, note="1단계 명목값(교환가능성 가정). 2단계는 관측값만 있다"))
    return pd.DataFrame(rows)


# ---------- 대기열 순위(평가관 04 U5) ----------
INJECTED = (("cur_noise", .1), ("cur_noise", .2), ("cur_offset", .4), ("vib_noise", 2.0), ("vib_noise", 4.0))


def queue_rankings(normal, abnormal, models):
    """건·사건 단위 주입 고장 대 정상 오경보 순위. 사건은 각 입력의 원래 시간 순서에서 먼저 묶는다.
    정렬 키는 고정된 사후 운영 규칙이다. 여기서 만든 인공 신호를 실제 고장 사건으로 해석하지 않는다."""
    from model import PRIORITY_KEYS, priority_ranks, cases as make_cases, incidents
    from recalibrate import inject, unit_layout
    mixed_rows, inj_rows = [], []
    for sid, model in models.items():
        split = D.split_normal(normal, D.segments(normal), sid)
        test = D.inputs_only(split["test"])
        units, in_unit, size = unit_layout(test)
        mask = (size >= 30) & (in_unit >= 10)
        for alpha in ALPHAS:
            pn, pa = model.predict(test, alpha), model.predict(abnormal, alpha)
            normal_incidents = incidents(make_cases(pn), pn)
            shifted = pa.copy(); shifted["record_id"] += int(pn.record_id.max()) + 1; shifted["row_id"] += len(pn)
            q = make_cases(pd.concat([pn, shifted], ignore_index=True))
            if len(q):
                q["source"] = np.where(q.record_id > pn.record_id.max(), "abnormal", "normal")
                for key in PRIORITY_KEYS:
                    q[f"rank_{key}"] = priority_ranks(q, key)
                for r in q.itertuples():
                    mixed_rows.append(dict(split=sid, alpha=alpha, source=r.source, record_id=int(r.record_id), level=int(r.level), evidence=r.evidence,
                                           alarm_share=float(r.alarm_share), peak_score=float(r.peak_score),
                                           **{f"rank_{k}": int(getattr(r, f"rank_{k}")) for k in PRIORITY_KEYS}))
            for fam, lv in INJECTED:
                frame = inject(test, model, fam, lv, mask, np.random.default_rng(0))
                pi = model.predict(frame, alpha)
                keep = np.isin(pi.record_id, np.unique(pi.record_id[mask]))
                inj = pi[keep].copy(); inj["record_id"] += int(pn.record_id.max()) + 1; inj["row_id"] += len(pn)
                q2 = make_cases(pd.concat([pn, inj], ignore_index=True))
                if not len(q2):
                    continue
                injected = q2.record_id > pn.record_id.max()
                # 정상·주입 입력을 이어 붙이면 사건 번호가 충돌하고 시간도 역행한다.
                # 각 입력 안에서 묶은 사건을 합쳐 순위만 비교한다. 주입 기록을 포함하는 사건만 센다.
                injected_records = set(pi.loc[mask, "record_id"].astype(int))
                all_injected_incidents = incidents(make_cases(pi), pi)
                if len(all_injected_incidents):
                    member = all_injected_incidents.records.map(
                        lambda value: bool(set(map(int, str(value).split("+"))) & injected_records))
                    injected_incidents = all_injected_incidents[member]
                else:
                    injected_incidents = all_injected_incidents
                incident_queue = pd.concat([normal_incidents.assign(source="normal"),
                                            injected_incidents.assign(source="injected")], ignore_index=True)
                is_injected_incident = incident_queue.source.eq("injected")
                for key in PRIORITY_KEYS:
                    rank = priority_ranks(q2, key)
                    best_fa = rank[~injected].min() if (~injected).any() else np.inf
                    incident_rank = priority_ranks(incident_queue, key)
                    best_fa_incident = incident_rank[~is_injected_incident].min() if (~is_injected_incident).any() else np.inf
                    inj_rows.append(dict(split=sid, alpha=alpha, family=fam, level_value=lv, key=key, injected_cases=int(injected.sum()),
                                         false_alarm_cases=int((~injected).sum()),
                                         injected_below_best_false_alarm=int((rank[injected] > best_fa).sum()) if np.isfinite(best_fa) else 0,
                                         injected_incidents=int(is_injected_incident.sum()),
                                         false_alarm_incidents=int((~is_injected_incident).sum()),
                                         injected_incidents_below_best_false_alarm=int((incident_rank[is_injected_incident] > best_fa_incident).sum())
                                         if np.isfinite(best_fa_incident) else 0,
                                         incident_note="각 입력의 시간 순서에서 사건을 묶은 뒤 순위 비교. 주입 기록을 포함한 사건 기준(인공 신호)"))
    inj = pd.DataFrame(inj_rows)
    summary = inj.groupby("key").injected_below_best_false_alarm.sum().rename("total_injected_below_best_false_alarm").reset_index()
    summary = summary.merge(inj.groupby("key").injected_incidents_below_best_false_alarm.sum().rename(
        "total_injected_incidents_below_best_false_alarm"), on="key")
    summary["key_terms"] = summary.key.map(lambda k: len(PRIORITY_KEYS[k]))
    return pd.DataFrame(mixed_rows), inj, summary.sort_values(["total_injected_below_best_false_alarm", "key_terms"]).reset_index(drop=True)


# ---------- 품질 의심 시간창(평가관 04 U2) ----------
SPM_GRID = (20, 40, 60)     # [가정] 분당 행정 수. 대회 자료에 행정·가공품 정보가 없다


def _mixed_queue(model, test, abnormal, alpha):
    from model import cases as make_cases
    pn, pa = model.predict(test, alpha), model.predict(abnormal, alpha)
    shifted = pa.copy(); shifted["record_id"] += int(pn.record_id.max()) + 1; shifted["row_id"] += len(pn)
    q = make_cases(pd.concat([pn, shifted], ignore_index=True))
    if len(q):
        q.insert(0, "source", np.where(q.record_id > pn.record_id.max(), "abnormal", "normal"))
        q.loc[q.source.eq("abnormal"), "record_id"] -= int(pn.record_id.max()) + 1
    return q


def quality_windows(normal, abnormal, models):
    """건마다 의심 생산 시간창(앞뒤로 가장 가까운 경보 없는 단위 사이)과 [가정] SPM별 해당 가공품 수. 열린 창은 수량을 내지 않는다."""
    rows = []
    for sid, model in models.items():
        test = D.split_normal(normal, D.segments(normal), sid)["test"]
        for alpha in ALPHAS:
            q = _mixed_queue(model, test, abnormal, alpha)
            for r in q.itertuples():
                row = dict(split=sid, alpha=alpha, source=r.source, record_id=int(r.record_id), priority_rank=int(r.priority_rank), level=int(r.level),
                           level_name=r.level_name, first_timestamp=r.first_timestamp, suspect_from=r.suspect_from, suspect_to=r.suspect_to,
                           suspect_seconds=r.suspect_seconds, suspect_open=int(r.suspect_open), quality_action=r.quality_action)
                for spm in SPM_GRID:
                    row[f"pieces_spm{spm}"] = r.suspect_seconds * spm / 60 if not r.suspect_open else np.nan
                rows.append(row)
    out = pd.DataFrame(rows)
    out["note"] = "가공품·로트·검사 자료 없는 제안. SPM은 가정. 품질 조치는 가이드북 6~7쪽 기전(기어 마모 → 출력 유압 약화 → 불량)에 근거한 가설"
    return out


# ---------- 라벨 없는 경보 → 이상 확률 환산(평가관 05 O2) ----------
def label_free_alert_probability(models, e1_summary, observed):
    """P(이상 | 알림) = π·TPR / (π·TPR + (1−π)·FAR). 라벨 적합 없이 정상 보정과 주입 탐지율만 쓴다.

    FAR: 명목(l/(n+1)), 보정 조건부 95%(Beta(l, n+1−l)), 관측을 더한 사후 95%. TPR: E1 2초 탐지율(계단형, 10행째 시작),
    대회 21/21의 95% 하한. LR=TPR/FAR는 각 가정의 환산값이다. 실제 FAR의 하한이 없으므로 보편적 LR 상한을 뜻하지 않는다."""
    e1 = pd.read_csv(e1_summary)
    e1 = e1[e1.model.eq("guard_v2") & e1["shape"].eq("step") & e1.t0.eq(10)]
    rows = []
    for sid, model in models.items():
        n = len(model.cal)
        for alpha in ALPHAS:
            l = int(np.floor(alpha * (n + 1) + 1e-9))
            x, m = observed[(sid, alpha)]
            fars = {"nominal": l / (n + 1), "calibrated95": float(stats.beta.ppf(.95, l, n + 1 - l)),
                    "posterior95": float(stats.beta.ppf(.95, l + x, n + 1 - l + m - x))}
            tprs = {f"E1 {f} {v:g}": float(e1[e1.split.eq(sid) & e1.family.eq(f) & e1.level.eq(v) & e1.alpha.eq(alpha)].detect_rate_2s.iloc[0])
                    for f, v in (("cur_noise", .1), ("cur_offset", .4), ("vib_noise", 2.0))}
            tprs["대회 21/21 95% 하한"] = .05 ** (1 / 21)
            for fb, far in fars.items():
                for tb, tpr in tprs.items():
                    for pi in (1e-4, 1e-3, 1e-2):
                        rows.append(dict(split=sid, alpha=alpha, far_basis=fb, far=far, tpr_basis=tb, tpr=tpr, prior=pi, likelihood_ratio=tpr / far,
                                         nominal_far=fars["nominal"], nominal_lr_reference=tpr / fars["nominal"],
                                         min_rank_nominal_lr_reference=(n + 1) * tpr,
                                         p_anomaly_given_alert=pi * tpr / (pi * tpr + (1 - pi) * far)))
    out = pd.DataFrame(rows)
    out["note"] = "π는 알림 단위당 이상 비율 가정. 교환가능성(같은 운전 조건의 정상) 가정. 주입은 실제 고장 탐지율이 아니다. nominal_lr_reference는 해당 α의 FAR=l/(n+1), min_rank_nominal_lr_reference는 최소 순위 FAR=1/(n+1) 시나리오이며 보편적 LR 상한이 아니다"
    return out


# ---------- 감시 규칙의 정상 운전변화 모의(평가관 04 U6) ----------
def monitor_gain(normal, models):
    from monitor import Reference, gain_scenarios
    rows = []
    for sid, model in models.items():
        sp = D.split_normal(normal, D.segments(normal), sid)
        ref = Reference.from_frame(pd.concat([sp["train"], sp["cal"]], ignore_index=True))
        for alpha in ALPHAS:
            g = gain_scenarios(model, ref, sp["test"], alpha)
            g.insert(0, "alpha", alpha); g.insert(0, "split", sid)
            g["reference_median"], g["band_low"], g["band_high"] = ref.median, ref.band_low, ref.band_high
            rows.append(g)
    out = pd.concat(rows, ignore_index=True)
    out["note"] = ("감시 창 60단위. 전류 전체 배율 k의 인공 모의. 변경 기록 있음 열은 매 창 시작에 변경 기록을 둔 반사실 조건이다. "
                   "incident_* 알림은 사건 시작+격상이며 alerted_units는 경보 알림 단위 수다. 조치: 관측 지속/운전 변경 재보정/"
                   "전류 수준 이동 점검/열화 의심 점검. A 평가 구간은 가장 조용한 시간대라 알림이 늘지 않는다")
    return out


# ---------- 가정 기반 기대효과·손익분기(평가관 04 U4) ----------
EFFECT_ASSUMPTIONS = dict(          # [가정] 낮음·중간·높음. 현장 자료가 없어 범위로만 쓴다
    minutes_level1=(1, 2, 3),        # 1단계(주의) 1건 화면 확인 시간(분)
    minutes_level2=(10, 20, 30),     # 2단계(점검 요청) 1건 현장 점검 시간(분)
    shifts_per_day=(1, 2, 3), days_per_year=(250, 250, 300),
    failures_per_year=(0.5, 1, 2),   # 이 설비의 가동 중단 고장 빈도
    avoided_fraction=(0.3, 0.5, 0.8),  # 조기 경보로 줄이는 가동 중단 비율
    periodic_interval_days=(7, 7, 30),  # 현행 주기점검 간격
)
DOWNTIME_DAYS = (2, 3)              # 출처: 가이드북 7쪽 "고장 시 최대 2~3일 가동 중단"


def expected_effect(levels, injection):
    """교대당 점검 시간, 현행 주기점검 대비 탐지 지연, 손익분기(가동 중단 1시간 손실 ÷ 점검 1시간 비용이 얼마를 넘어야 이득인가).

    알림 수는 B·α=1%(대회에서 오경보가 난 분할)의 교대 8시간 환산이다: 명목(1단계만 있음), 관측, 관측의 이항 95% 상한.
    운영 방식은 두 가지다: 전건 확인(1단계도 화면 확인)과 2단계만 출동(1단계는 기록만). 탐지 확률은 E1식 주입의 2단계 2초 탐지율
    최솟값(비관), 대회 21/21의 95% 하한(중간), 관측 21/21(낙관)이다. 절감액을 사실로 말하지 않는다."""
    lv = levels[levels.model.eq("frozen_B") & levels.alpha.eq(.01)].set_index("level")
    inj = injection[injection.split.eq("B") & injection.alpha.eq(.01) & injection.family.ne("none")]
    nominal = lv.loc[1, "nominal_alerts_per_8h_elapsed"]
    # 규칙은 B 평가 구간 420~599의 오경보를 본 뒤 정했다. 보정값이 다르다는 사실만으로
    # 선택 자료와 분리된 검증이 되지 않는다. 주추정은 평가가 420보다 앞인 두 폴드만 사용한다.
    # α5%에서 잰 조건부 비를 α1% 명목 업무량으로 옮기는 가정도 출처 열에 남긴다.
    alerts = [("명목", nominal, np.nan, dict(estimate_role="reference", evaluation_overlaps_rule_selection=False,
              rule_selected_post_hoc=False, level2_basis="2단계 명목값은 없다"))]
    rolling = levels[levels.independent & levels.model.str.startswith("rolling") & levels.alpha.eq(.05)]
    nonoverlap = rolling[rolling.normal_window.isin(["300~359", "360~419"])]
    sources = [("비중첩 폴드 추정", nonoverlap, "primary", False, .05),
               ("민감도(겹치는 폴드 포함)", rolling, "sensitivity", True, .05),
               ("민감도(동결 B α3%)", levels[levels.model.eq("frozen_B") & levels.alpha.eq(.03)], "sensitivity", True, .03),
               ("민감도(동결 B α5%)", levels[levels.model.eq("frozen_B") & levels.alpha.eq(.05)], "sensitivity", True, .05)]
    for name, source, role, overlap, alpha in sources:
        count = source.groupby("level").normal_alerted_segments.sum()
        k2, k1 = int(count.get(2, 0)), int(count.get(1, 0))
        ratio = k2 / k1 if k1 else np.nan
        ratio_hi = (float(stats.beta.ppf(.95, k2 + 1, k1 - k2)) if k2 < k1 else 1.0) if k1 else np.nan
        windows = "+".join(source.normal_window.drop_duplicates())
        overlap_note = ("540~599 폴드는 보정 420~539와 평가 540~599가 B 평가와 겹치며 경보 기록 570도 포함. "
                        if name == "민감도(겹치는 폴드 포함)" else "")
        basis = (f"평가 {windows}, α {alpha:.0%}: 2단계 {k2}/1단계 {k1}={ratio:.3f}. "
                 f"조건부 비를 B α1% 명목 알림에 적용하는 가정. {overlap_note}규칙 자체는 사후 선택; 같은 날 자료")
        meta = dict(estimate_role=role, evaluation_overlaps_rule_selection=overlap, rule_selected_post_hoc=True,
                    ratio_numerator=k2, ratio_denominator=k1, ratio_level2_given_level1=ratio,
                    ratio_upper95=ratio_hi, ratio_source_alpha=alpha, ratio_source_windows=windows, level2_basis=basis)
        point_name = name + "(주추정)" if role == "primary" else name
        alerts.append((point_name, nominal, nominal * ratio, meta))
        alerts.append((name + " 95% 상한", nominal, nominal * ratio_hi,
                       {**meta, "level2_basis": basis + f". 비의 단측 이항 95% 상한 {ratio_hi:.3f}(시간 의존성 미반영)"}))
    observed_meta = dict(estimate_role="reference", evaluation_overlaps_rule_selection=True,
                         rule_selected_post_hoc=True, level2_basis="2단계 규칙을 정하기 전에 본 대회 자료(표본 내)")
    alerts += [("관측", lv.loc[1, "alerts_per_8h_elapsed"], lv.loc[2, "alerts_per_8h_elapsed"], observed_meta),
               ("관측 95% 상한", lv.loc[1, "upper95_alerts_per_8h_elapsed"], lv.loc[2, "upper95_alerts_per_8h_elapsed"], observed_meta)]
    detect = (float(inj.level2_detect_2s.min()), .05 ** (1 / 21), 1.0)
    detect_basis = ("E1식 주입 2단계 2초 탐지율 최솟값(B α1%)", "대회 21/21의 95% 하한", "대회 21/21 관측")
    rows = []
    for name, a1, a2, meta in alerts:
        for policy in ("전건 확인", "2단계만 출동"):
            if policy == "2단계만 출동" and not np.isfinite(a2):
                continue            # 2단계는 명목값이 없다
            for k, case in enumerate(("비관", "중간", "낙관")):
                A = {key: v[k] for key, v in EFFECT_ASSUMPTIONS.items()}
                m1, m2 = EFFECT_ASSUMPTIONS["minutes_level1"][2 - k], EFFECT_ASSUMPTIONS["minutes_level2"][2 - k]   # 비관: 점검이 오래 걸림
                a2_used = 0.0 if not np.isfinite(a2) else a2
                hours_per_shift = ((a1 * m1 if policy == "전건 확인" else 0.0) + a2_used * m2) / 60
                inspect_h = hours_per_shift * A["shifts_per_day"] * A["days_per_year"]
                downtime = DOWNTIME_DAYS[0] if k == 0 else DOWNTIME_DAYS[1]
                avoided_h = A["failures_per_year"] * detect[k] * A["avoided_fraction"] * downtime * A["shifts_per_day"] * 8
                rows.append(dict(alert_scenario=name, post_hoc=meta["rule_selected_post_hoc"], **meta,
                                 policy=policy, case=case, level1_per_8h=a1, level2_per_8h=a2,
                                 assume_minutes_level1=m1 if policy == "전건 확인" else 0, assume_minutes_level2=m2,
                                 assume_shifts_per_day=A["shifts_per_day"], assume_days_per_year=A["days_per_year"],
                                 assume_failures_per_year=A["failures_per_year"], assume_avoided_fraction=A["avoided_fraction"],
                                 assume_periodic_interval_days=A["periodic_interval_days"],
                                 source_downtime_days=downtime, source_downtime="가이드북 7쪽(고장 시 최대 2~3일 가동 중단)",
                                 source_detect_probability=detect[k], source_detect_basis=detect_basis[k],
                                 inspection_hours_per_shift=hours_per_shift, shift_share=hours_per_shift / 8,
                                 inspection_hours_per_year=inspect_h, downtime_hours_avoided_per_year=avoided_h,
                                 breakeven_loss_ratio=inspect_h / avoided_h if avoided_h > 0 else np.inf,
                                 current_practice_mean_delay_hours=A["periodic_interval_days"] * 24 / 2,
                                 press_guard_delay_median_s=float(lv.loc[2 if policy == "2단계만 출동" else 1, "delay_median_s"])))
    out = pd.DataFrame(rows)
    out["reading"] = ("breakeven_loss_ratio: 가동 중단 1시간의 손실이 점검 인력 1시간 비용의 이 배수보다 크면 조기 경보 운영이 이득이다(0이면 점검 부담 없음). "
                      "shift_share가 1을 넘으면 한 사람이 교대 시간 안에 처리할 수 없다. 현행 지연은 주기점검 간격의 절반(평균), Press Guard 지연은 "
                      "대회 이상 기록 시작 기준이다. assume_* 열은 모두 가정이고 source_* 열은 출처가 있는 값이다")
    return out



# ---------- 사건 묶음(2회차 평가관 04 R2-03) ----------
def incident_summary(normal, abnormal, models):
    """분할 × α별 사건 수와 알림 수. 구간(건) 단위 알림과 사건 단위 알림(사건 시작 + 2단계 격상)을 나란히 둔다."""
    rows = []
    for sid, model in models.items():
        test = D.split_normal(normal, D.segments(normal), sid)["test"]
        for alpha in ALPHAS:
            for subset, frame in (("normal_test", test), ("abnormal", abnormal)):
                p = model.predict(frame, alpha)
                rows.append(dict(split=sid, alpha=alpha, subset=subset, records=int(p.record_id.nunique()),
                                 case_notifications=int(p.notification.sum()), case_escalations=int(p.escalation.sum()),
                                 incidents=int(p.incident_id.max()), incident_level2=int(p.incident_escalation.sum()),
                                 incident_notifications=int(p.incident_notification.sum() + p.incident_escalation.sum()),
                                 incident_updates=int(p.incident_update.sum())))
    out = pd.DataFrame(rows)
    out["note"] = "사건: 경보가 이어진 알림 단위(공백 60초 이하). 사건 알림 = 사건 시작(1단계) + 격상(2단계). 근거 추가는 갱신이며 알림이 아니다"
    return out


# ---------- 운전 강도별 조건부 오경보율(2회차 평가관 03 R2-01) ----------
def _independent_evaluations(normal, models, rolling):
    """보정값이 서로 다른 적합(동결 A·B, 시간순 300·360·540 폴드)이 평가한 정상 구간마다 경보 유무와 운전 강도."""
    seg_all = D.segments(normal)
    seen, rows = {}, []
    for name, (m, lo, hi) in all_fits(models, rolling).items():
        key = tuple(np.round(np.sort(m.cal), 12))
        if key in seen:
            continue
        seen[key] = name
        frame = normal[(seg_all >= lo) & (seg_all < hi)]
        q = D.quantize(D.inputs_only(frame), "matched"); seg = layout(q)[1]
        feat = _record_features(q, seg, m).set_index("record")
        # 진폭 분석은 기존 matched 특징을 유지한다. 운전 상태는 원 전류의 평균 제거
        # RMS(ddof=0)를 사용해 press_evidence·실시간 모델의 공통 경계와 맞춘다.
        raw = _record_features(D.inputs_only(frame), seg, m).set_index("record")
        for alpha in ALPHAS:
            fa = m.predict(frame, alpha).groupby("record_id").alarm.max()
            for r, v in fa.items():
                f = feat.loc[r]
                rms = float(raw.loc[r].current_amp / np.sqrt(2))
                state = "short" if int(f.length) < STATE_MIN_ROWS else ("load" if rms >= LOAD_STATE_RMS else "low")
                rows.append(dict(model=name, alpha=alpha, absolute_record=int(lo + r), length=int(f.length), current_amp=float(f.current_amp),
                                 record_current_rms=rms, operating_state=state, vib_sd=float(f.vib_sd), false_alarm=int(v)))
    return pd.DataFrame(rows)


def _cmh_statistics(tables):
    """2×2 층별 표의 MH 공통 OR와 연속성 보정 CMH. 새 통계 패키지 의존성 없이 계산한다.
    배열의 행은 노출 유무, 열은 경보 유무다. 두 주변 합이 모두 양수인 정보 있는 층만 받는다.
    statsmodels StratifiedTable.test_null_odds(correction=True)와 같은 0.5 보정이다."""
    if not len(tables):
        return np.nan, np.nan, np.nan
    t = np.asarray(tables, dtype=float)
    a, b, c, d = t[:, 0, 0], t[:, 0, 1], t[:, 1, 0], t[:, 1, 1]
    n = t.sum(axis=(1, 2))
    delta = np.sum(a - (a + b) * (a + c) / n)
    variance = np.sum((a + b) * (a + c) * (b + d) * (c + d) / (n ** 2 * (n - 1)))
    statistic = (abs(delta) - .5) ** 2 / variance if variance > 0 else np.nan
    numerator, denominator = np.sum(a * d / n), np.sum(b * c / n)
    odds = numerator / denominator if denominator > 0 else (np.inf if numerator > 0 else np.nan)
    return float(odds), float(statistic), float(stats.chi2.sf(statistic, 1))


def _block_amplitude_stats(frame, exposure, permutations=20000, seed=3):
    """60구간 블록 안 노출 순열. 블록별 노출/경보 주변 합을 고정한다.
    적합 간 겹침과 블록 안 시간 의존성은 제거하지 못하므로 p값은 사후 기술 통계다."""
    x = np.asarray(exposure, bool)
    y = frame.false_alarm.to_numpy(bool)
    labels = frame.absolute_record.to_numpy() // 60
    blocks = [np.flatnonzero(labels == label) for label in np.unique(labels)]
    tables = []
    rng = np.random.default_rng(seed)
    permutation_counts = np.zeros(permutations, dtype=int)
    for ix in blocks:
        a = int((x[ix] & y[ix]).sum()); b = int((x[ix] & ~y[ix]).sum())
        c = int((~x[ix] & y[ix]).sum()); d = int((~x[ix] & ~y[ix]).sum())
        table = np.array([[a, b], [c, d]])
        if table.sum(axis=0).min() > 0 and table.sum(axis=1).min() > 0:
            tables.append(table)
        # 매 행마다 독립 순열. 한 블록씩 처리해 20,000×전체 표를 보관하지 않는다.
        shuffled = rng.permuted(np.broadcast_to(x[ix], (permutations, len(ix))), axis=1)
        permutation_counts += shuffled[:, y[ix]].sum(axis=1)
    odds, statistic, p = _cmh_statistics(tables)
    observed = int((x & y).sum())
    return dict(mh_pooled_or=odds, cmh_statistic=statistic, cmh_p=p, cmh_continuity_correction=.5,
                cmh_informative_blocks=len(tables), permutation_p_greater=float((1 + (permutation_counts >= observed).sum()) / (permutations + 1)),
                permutation_repeats=permutations, permutation_seed=seed)


def fp_intensity(normal, models, rolling):
    """평가 단위(적합 × 구간) 분모의 운전 강도·시간 블록별 조건부 오경보율, CI, lift, 단측 Fisher. 고유 구간 기준도 함께.
    사분위 경계는 α 1% 평가 단위(길이 ≥17)의 분포다. 진동 SD 사분위는 크기 성분의 발화 경로와 겹친다."""
    ev = _independent_evaluations(normal, models, rolling)
    base = ev[ev.alpha.eq(.01)]
    amp_q = base[base.length >= STATE_MIN_ROWS].current_amp.quantile([.25, .5, .75]).to_numpy()
    vsd_q = base.vib_sd.dropna().quantile([.25, .5, .75]).to_numpy()
    split_b = D.split_normal(normal, D.segments(normal), "B")["train"]
    qb = D.quantize(D.inputs_only(split_b), "matched")
    ftr = _record_features(qb, layout(qb)[1], models["B"])
    b_q75 = float(ftr[ftr.length >= 17].current_amp.quantile(.75))
    rows = []
    for alpha in ALPHAS:
        g = ev[ev.alpha.eq(alpha)].copy().reset_index(drop=True)
        g["amp_quartile"] = np.where(g.length < 17, "짧은 기록(<17)", pd.cut(g.current_amp, [-np.inf, *amp_q, np.inf], labels=["Q1", "Q2", "Q3", "Q4"]).astype(str))
        g["vib_sd_quartile"] = pd.cut(g.vib_sd, [-np.inf, *vsd_q, np.inf], labels=["Q1", "Q2", "Q3", "Q4"]).astype(str)
        g["block"] = (g.absolute_record // 60 * 60).astype(str) + "~" + (g.absolute_record // 60 * 60 + 59).astype(str)
        tot_k, tot_n = int(g.false_alarm.sum()), len(g)
        for cond in ("amp_quartile", "vib_sd_quartile", "block", "operating_state"):
            for v, gg in g.groupby(cond):
                k, n = int(gg.false_alarm.sum()), len(gg)
                lo, hi = clopper(k, n)
                pf = stats.fisher_exact([[k, n - k], [tot_k - k, tot_n - n - (tot_k - k)]], alternative="greater").pvalue if n < tot_n else np.nan
                rows.append(dict(unit="평가 단위(적합×구간)", alpha=alpha, condition=cond, value=v, false_alarms=k, denominator=n, rate=k / n,
                                 ci_low=lo, ci_high=hi, lift=(k / n) / (tot_k / tot_n) if tot_k else np.nan, fisher_p_greater=float(pf),
                                 small_sample=tot_k < 5,
                                 comparison_false_alarms=tot_k - k, comparison_denominator=tot_n - n,
                                 state_rms_threshold=LOAD_STATE_RMS if cond == "operating_state" else np.nan,
                                 state_min_rows=STATE_MIN_ROWS if cond == "operating_state" else np.nan,
                                 note=("크기 성분 경보의 발화 경로와 겹친다" if cond == "vib_sd_quartile" else
                                       "원 전류 RMS(ddof0), load≥91.9/low<91.9/short<17행. 실제 부하 관측값이 아닌 신호 대리변수" if cond == "operating_state" else "")))
        u = g.groupby("absolute_record").agg(fa=("false_alarm", "max"), amp=("current_amp", "first"), length=("length", "first"),
                                             state=("operating_state", "first"))
        for lab, cut in (("전류 진폭 ≥ 평가 분포 q75", amp_q[2]), ("전류 진폭 ≥ B 정상 학습 q75", b_q75)):
            hi_ = (u.length >= 17) & (u.amp >= cut)
            k1, n1 = int(u[hi_].fa.sum()), int(hi_.sum()); k0, n0 = int(u[~hi_].fa.sum()), int((~hi_).sum())
            lo1, hi1 = clopper(k1, n1)
            pf = stats.fisher_exact([[k1, n1 - k1], [k0, n0 - k0]], alternative="greater").pvalue
            rows.append(dict(unit="고유 구간(300~599, 한 적합이라도 경보)", alpha=alpha, condition="amp_high", value=f"{lab} ({cut:.1f})", false_alarms=k1,
                             denominator=n1, rate=k1 / n1, ci_low=lo1, ci_high=hi1, lift=(k1 / n1) / ((k1 + k0) / (n1 + n0)) if k1 + k0 else np.nan,
                             fisher_p_greater=float(pf), small_sample=(k1 + k0) < 5, note=f"나머지 {k0}/{n0}",
                             comparison_false_alarms=k0, comparison_denominator=n0, exposed_all_load=bool(u.loc[hi_, "state"].eq("load").all())))
        for label, cut in (("B 정상 학습 q75", b_q75), ("평가 분포 q75", amp_q[2])):
            exposed = (g.length >= STATE_MIN_ROWS) & (g.current_amp >= cut)
            k1, n1 = int(g.loc[exposed, "false_alarm"].sum()), int(exposed.sum())
            k0, n0 = tot_k - k1, tot_n - n1
            lo1, hi1 = clopper(k1, n1)
            rows.append(dict(unit="평가 단위(적합×구간)", alpha=alpha, condition="amp_high_block_stratified", value=label,
                             threshold=cut, false_alarms=k1, denominator=n1, rate=k1 / n1, ci_low=lo1, ci_high=hi1,
                             comparison_false_alarms=k0, comparison_denominator=n0,
                             lift=(k1 / n1) / (tot_k / tot_n) if tot_k else np.nan, small_sample=tot_k < 5,
                             **_block_amplitude_stats(g, exposed),
                             note="60구간 블록 층화. CMH는 양측·연속성 보정, 블록 안 순열은 단측(20,000회). 적합 겹침·시간 의존성은 남아 있다"))
        load = g[g.operating_state.eq("load")]
        median = float(load.current_amp.median())
        above = load.current_amp >= median
        k1, n1 = int(load.loc[above, "false_alarm"].sum()), int(above.sum())
        k0, n0 = int(load.loc[~above, "false_alarm"].sum()), int((~above).sum())
        lo1, hi1 = clopper(k1, n1)
        rho, p_rho = stats.spearmanr(load.current_amp, load.false_alarm)
        rows.append(dict(unit="평가 단위(부하 상태)", alpha=alpha, condition="amp_within_load", value="부하 상태 안 전류 진폭 ≥ 중앙",
                         threshold=median, false_alarms=k1, denominator=n1, rate=k1 / n1, ci_low=lo1, ci_high=hi1,
                         comparison_false_alarms=k0, comparison_denominator=n0,
                         lift=(k1 / n1) / ((k1 + k0) / (n1 + n0)) if k1 + k0 else np.nan,
                         fisher_p_greater=float(stats.fisher_exact([[k1, n1 - k1], [k0, n0 - k0]], alternative="greater").pvalue),
                         spearman_amp=float(rho), spearman_p=float(p_rho), small_sample=k1 + k0 < 5,
                         note="부하 상태 안 강도 효과. Fisher는 중앙 이분화, Spearman은 연속 진폭. 동일 날의 의존 평가 단위"))
    out = pd.DataFrame(rows)
    out["post_hoc"] = True
    out["statistical_scope"] = "같은 날·적합 간 구간 겹침. 독립 표본 가정 p값/구간은 기술적 비교이며 현장 검증이나 인과 효과가 아니다"
    return out


# ---------- 고장 모양 × 운전 강도 미탐(2회차 평가관 03 R2-02) ----------
FN_FAMILIES = (("vib_noise", 2.0), ("cur_noise", .1), ("cur_offset", .2), ("cur_gain", 1.15), ("cur_gain", 1.3))


def _bh_adjust(pvalues):
    """유한 p값 전체를 한 검정군으로 묶은 Benjamini-Hochberg q값. 미정의 p값은 검정 수에서 뺀다."""
    p = np.asarray(pvalues, float)
    out = np.full(p.shape, np.nan)
    valid = np.flatnonzero(np.isfinite(p))
    order = valid[np.argsort(p[valid], kind="stable")]
    if len(order):
        adjusted = p[order] * len(order) / np.arange(1, len(order) + 1)
        out[order] = np.minimum(1, np.minimum.accumulate(adjusted[::-1])[::-1])
    return out


def _row_spearman(x, y):
    """행마다 평균 순위를 이용한 Spearman. 재표집으로 생긴 동률도 평균 순위로 처리한다."""
    rx, ry = stats.rankdata(x, axis=1), stats.rankdata(y, axis=1)
    rx -= rx.mean(axis=1, keepdims=True); ry -= ry.mean(axis=1, keepdims=True)
    denominator = np.sqrt((rx * rx).sum(axis=1) * (ry * ry).sum(axis=1))
    return np.divide((rx * ry).sum(axis=1), denominator, out=np.full(len(rx), np.nan), where=denominator > 0)


def _paired_spearman_bootstrap(amp, vibration_detection, offset_detection, repeats=4000, seed=11):
    """같은 단위를 재표집하여 두 Spearman 상관의 차이를 계산한다. 주입 반복은 표본 단위로 세지 않는다."""
    amp, vib, offset = map(lambda values: np.asarray(values, float), (amp, vibration_detection, offset_detection))
    if not (len(amp) == len(vib) == len(offset)) or repeats < 1:
        raise ValueError("상호작용 붓스트랩은 동일 단위의 두 탐지 벡터와 양의 반복 수가 필요하다")
    index = np.random.default_rng(seed).integers(0, len(amp), size=(repeats, len(amp)))
    delta = _row_spearman(amp[index], vib[index]) - _row_spearman(amp[index], offset[index])
    delta = delta[np.isfinite(delta)]
    observed = stats.spearmanr(amp, vib).statistic - stats.spearmanr(amp, offset).statistic
    low, high = np.quantile(delta, [.025, .975]) if len(delta) else (np.nan, np.nan)
    return dict(interaction_rho_difference=float(observed), interaction_ci_low=float(low), interaction_ci_high=float(high),
                interaction_bootstrap_repeats=repeats, interaction_bootstrap_valid=len(delta), interaction_bootstrap_seed=seed,
                interaction_bootstrap_share_le_zero=float((delta <= 0).mean()) if len(delta) else np.nan,
                interaction_comparison="ρ(전류 진폭, 진동 잡음 2σ 탐지) − ρ(전류 진폭, 전류 오프셋 0.2× 탐지)")


def fn_intensity(normal, models, reps=50):
    """E1과 같은 계단 주입(30행 이상 단위의 10행째부터, α 1%, 2초 안)의 단위별 탐지를 주입받은 기록의 운전 강도(전류 진폭·진동 SD)로 나눈다.
    잡음 족은 기본 50회(난수 0~49)의 단위별 평균이다. E1의 별도 난수 결과와 구분한다.
    진동형−전류 계단형 교차 효과는 동일 단위를 함께 재표집한 Spearman 차이(4,000회)로 본다."""
    from recalibrate import inject, unit_layout, T0, WINDOW, MIN_UNIT_ROWS
    if reps < 1:
        raise ValueError("잡음 주입 반복 수는 양수여야 한다")
    rows = []
    for sid, model in models.items():
        test = D.inputs_only(D.split_normal(normal, D.segments(normal), sid)["test"])
        units, in_unit, size = unit_layout(test)
        eligible = size >= MIN_UNIT_ROWS
        mask = eligible & (in_unit >= T0)
        q = D.quantize(test, "matched"); seg = layout(q)[1]
        feat = _record_features(q, seg, model).set_index("record")
        unit_rec = pd.Series(seg).groupby(units).first()
        el_units = np.unique(units[eligible])
        amp = unit_rec.loc[el_units].map(feat.current_amp).to_numpy()
        vsd = unit_rec.loc[el_units].map(feat.vib_sd).to_numpy()
        amp_q = pd.qcut(amp, 4, labels=["Q1", "Q2", "Q3", "Q4"])
        outcomes = {}
        start = len(rows)
        for fam, lv in FN_FAMILIES:
            n_rep = reps if fam in ("cur_noise", "vib_noise") else 1
            det = np.zeros(len(el_units))
            for rep in range(n_rep):
                if fam == "cur_gain":       # E1과 같은 정의: 주입 행의 전류를 정상 학습 평균 둘레로 k배
                    frame = D.inputs_only(test).copy()
                    x = pd.to_numeric(frame[D.SENSORS[2]], errors="coerce").to_numpy(float)
                    frame[D.SENSORS[2]] = np.where(mask, model.mean[2] + lv * (x - model.mean[2]), x)
                else:
                    frame = inject(test, model, fam, lv, mask, np.random.default_rng(rep))
                pr = model.predict(frame, .01)
                win = (pr.alarm.to_numpy() == 1) & (in_unit >= T0) & (in_unit < T0 + WINDOW)
                det += pd.Series(win).groupby(units).any().reindex(el_units).to_numpy(float)
            det /= n_rep
            outcomes[(fam, lv)] = det.copy()
            ra, pa_ = stats.spearmanr(amp, det) if det.std() > 0 else (np.nan, np.nan)
            rv, pv = stats.spearmanr(vsd, det) if det.std() > 0 else (np.nan, np.nan)
            row = dict(split=sid, family=fam, level_value=lv, units=len(el_units), detect_mean=float(det.mean()),
                       spearman_amp=float(ra), p_amp=float(pa_), spearman_vib_sd=float(rv), p_vib_sd=float(pv),
                       injection_repeats=n_rep, injection_seed_start=0 if n_rep > 1 else np.nan,
                       injection_seed_end=n_rep - 1 if n_rep > 1 else np.nan)
            for qlab in ("Q1", "Q2", "Q3", "Q4"):
                m = np.asarray(amp_q == qlab)
                row[f"detected_amp_{qlab}"] = float(det[m].sum()); row[f"units_amp_{qlab}"] = int(m.sum())
                # 평균 탐지 수는 소수이므로 이항 CI가 아니다. 정상 단위의 평균 탐지율을
                # 재표집해 반복 주입의 의존성을 보존한 미탐 평균 구간을 둔다.
                ix = np.random.default_rng(11).integers(0, m.sum(), size=(4000, m.sum()))
                lo, hi = np.quantile(1 - det[m][ix].mean(axis=1), [.025, .975])
                row[f"miss_amp_{qlab}_ci_low"], row[f"miss_amp_{qlab}_ci_high"] = float(lo), float(hi)
            rows.append(row)
        interaction = _paired_spearman_bootstrap(amp, outcomes[("vib_noise", 2.0)], outcomes[("cur_offset", .2)])
        rows[start].update(interaction)
    out = pd.DataFrame(rows)
    out["q_amp_bh"] = _bh_adjust(out.p_amp)
    out["n_tests_amp"] = int(np.isfinite(out.p_amp).sum())
    all_p = np.r_[out.p_amp, out.p_vib_sd]
    all_q = _bh_adjust(all_p)
    out["q_amp_joint_bh"], out["q_vib_sd_joint_bh"] = all_q[:len(out)], all_q[len(out):]
    out["n_tests_amp_vib_sd"] = int(np.isfinite(all_p).sum())
    out["p_amp_bonferroni"] = np.minimum(1, out.p_amp * out.n_tests_amp)
    out["p_amp_joint_bonferroni"] = np.minimum(1, out.p_amp * out.n_tests_amp_vib_sd)
    out["quartile_ci_method"] = "정상 단위별 평균 탐지율 재표집 4,000회 백분위 95% 구간(시드 11). 같은 날 시간 의존성 미반영"
    out["note"] = (f"사후 분석·인공 신호. 잡음 족 {reps}회(시드 0~{reps - 1}), 다른 족 1회. "
                   "E1 진동 잡음 2σ 전체 탐지 A 74.4%·B 93.9%는 별도 난수 반복 결과이며 이 표와 동일한 실험 추정값이 아니다. "
                   "사분위는 분할별 주입 대상 단위의 전류 진폭(√2×평균 제거 RMS). BH는 유한 p값만 세며 분할·족 전체를 묶었다. "
                   "같은 날·중첩 단위 의존성 때문에 q값과 붓스트랩은 사후 기술 통계다")
    return out


# ---------- FN·FP 집중 공정조건 요약(평가관 03 E5) ----------
# 공정조건 대리변수 사전(공정 상태 변수는 자료에 없다. 신호로 대신한다)
PROXIES = {"수집 재개 직후": "기록구간 안 위치 0~1(0.2초 안): 크기 성분만 있는 초반 창",
           "운전 강도(부하)": "구간 진동 SD·전류 진폭(√2×평균 제거 RMS). 정상 운전에서 함께 움직인다(coupling_fit_v2 r 0.95)",
           "운전 시간대": "60구간 블록(약 7~8분). 480~539가 가장 조용한 블록",
           "전류 수준 이동": "전류 전체 배율 k(정상 운전변화 모의)",
           "계측 정밀도": "입력 저장 정밀도(matched·coarse)",
           "고장 모양": "E1 주입 족(전류 잡음·오프셋·배율, 진동 잡음)과 시작 시점(t0)"}


def _cite(path, mask):
    """파일:행 인용(헤더가 1행, 자료 첫 행이 2행). 조건을 만족하는 행 전부를 이어진 범위로 적는다."""
    idx = np.flatnonzero(np.asarray(mask, bool)) + 2
    if not len(idx):
        raise ValueError(f"인용할 행이 없다: {path}")
    parts, start = [], idx[0]
    for a, b in zip(idx, np.r_[idx[1:], -1]):
        if b != a + 1:
            parts.append(str(start) if start == a else f"{start}-{a}")
            start = b
    return f"{path.relative_to(YEJUN).as_posix()}:{','.join(parts)}"


SELECTION_INJECTION = YEJUN / "analysis" / "press_selection" / "fp_mitigation_injection_v2.csv"


def error_condition_summary(out, e1_summary, dayshift):
    """FN·FP가 몰리는 조건을 공정조건 대리변수로 옮긴 12행 요약. 모든 값은 다른 산출물에서 읽고, 조건을 만족하는 행 전부를 파일:행으로 붙인다.
    errors/denominator는 미탐(주입은 놓친 단위)·오경보 수와 분모, comparison_*는 대조 조건의 비율이다."""
    rows = []
    names = ("position_vibration_misses_v2.csv", "error_conditions_stats_v2.csv", "fp_events_v2.csv", "near_miss_corr_v2.csv",
             "robustness_v2.csv", "fp_intensity_v2.csv", "fn_intensity_v2.csv")
    pv_path, st_path, fp_path, nm_path, rb_path, fi_path, fn_path = (out / n for n in names)
    pv, st, fp, nm, rb, fi, fn = (pd.read_csv(q) for q in (pv_path, st_path, fp_path, nm_path, rb_path, fi_path, fn_path))
    e1, ds, sel = pd.read_csv(e1_summary), pd.read_csv(dayshift), pd.read_csv(SELECTION_INJECTION)

    def add(kind, condition, proxy, definition, a, b, comp_a, comp_b, comparison, evidence, source, limitation):
        rec = dict(kind=kind, condition=condition, proxy=proxy, definition=definition)
        for lab, (k, n), comp in (("A", a, comp_a), ("B", b, comp_b)):
            lo, hi = clopper(k, n) if n else (np.nan, np.nan)
            rate = k / n if n else np.nan
            rec.update({f"errors_{lab}": k, f"denominator_{lab}": n, f"rate_{lab}": rate, f"ci_low_{lab}": lo, f"ci_high_{lab}": hi,
                        f"comparison_rate_{lab}": comp, f"lift_{lab}": rate / comp if comp and np.isfinite(comp) and comp > 0 else np.nan})
        rec.update(comparison=comparison, evidence=evidence, source=source, limitation=limitation,
                   ci_method="Clopper-Pearson 이항 95% 구간(관측 간 의존성 미반영)" if a[1] or b[1] else "해당 없음")
        rows.append(rec)

    # FN 1: 수집 재개 직후 × 진동 동반 없음
    m = {s: pv[pv.split.eq(s) & pv.position.eq("0-1") & pv.vibration.eq("vibration_normal_range")].iloc[0] for s in "AB"}
    h = {s: pv[pv.split.eq(s) & pv.position.eq("0-1") & pv.vibration.eq("vibration_high")].iloc[0] for s in "AB"}
    add("FN", "기록 시작 0.2초 안 × 진동이 동반되지 않은 이상", "수집 재개 직후 × 고장 모양", "위치 0~1 행, 구간 진동 max|z| ≤ 정상 학습 q95(α 1%)",
        (int(m["A"].missed_rows), int(m["A"].rows)), (int(m["B"].missed_rows), int(m["B"].rows)), h["A"].miss_rate, h["B"].miss_rate,
        f"진동 높은 구간 {int(h['A'].missed_rows)}/{int(h['A'].rows)}·{int(h['B'].missed_rows)}/{int(h['B'].rows)}, 단측 Fisher p {m['A'].fisher_p_greater:.2g}·{m['B'].fisher_p_greater:.2g}",
        "관측(이상 3구간, 사후)", _cite(pv_path, pv.position.eq("0-1") & pv.vibration.isin(["vibration_normal_range", "vibration_high"])),
        "구간 3·19·20의 6행씩. 크기 성분만 있는 창이라 전류 파형 이상은 위치 2 이후에 잡힌다")
    a01 = {s: pv[pv.split.eq(s) & pv.vibration.eq("all")].set_index("position") for s in "AB"}
    add("FN", "기록 시작 0.2초 안(모든 이상 구간)", "수집 재개 직후", "위치 0~1 행 대 위치 2 이상 행(α 1%)",
        (int(a01["A"].loc["0-1"].missed_rows), int(a01["A"].loc["0-1"].rows)), (int(a01["B"].loc["0-1"].missed_rows), int(a01["B"].loc["0-1"].rows)),
        a01["A"].loc[">=2"].miss_rate, a01["B"].loc[">=2"].miss_rate,
        f"위치 2 이상 {int(a01['A'].loc['>=2'].missed_rows)}/{int(a01['A'].loc['>=2'].rows)}·{int(a01['B'].loc['>=2'].missed_rows)}/{int(a01['B'].loc['>=2'].rows)}, "
        f"단측 Fisher p {a01['A'].loc['0-1'].fisher_p_pos01_vs_ge2_greater:.1e}·{a01['B'].loc['0-1'].fisher_p_pos01_vs_ge2_greater:.1e}",
        "관측(사후)", _cite(pv_path, pv.vibration.eq("all")), "초반 창 구조의 한계. 직전 기록의 위상으로 채울 수 없다(0.6 Hz 위상 시험, press_evidence)")

    def e1row(family, level, t0, shape="step"):
        k = e1.model.eq("guard_v2") & e1.alpha.eq(.01) & e1.family.eq(family) & np.isclose(e1.level, level) & e1.t0.eq(t0) & e1["shape"].eq(shape)
        r = {s: e1[k & e1.split.eq(s)].iloc[0] for s in "AB"}
        miss = {s: (int(round((1 - r[s].detect_rate_2s) * r[s].trials)), int(r[s].trials)) for s in "AB"}
        return r, miss, _cite(e1_summary, k)

    r, miss, src = e1row("cur_offset", .8, 0)
    r10, _, src10 = e1row("cur_offset", .8, 10)
    add("FN", "기록 시작부터 있는 전류 오프셋", "고장 모양(시작 시점)", "E1: 기록 시작(t0=0)부터 전류에 +0.8×진폭 계단", miss["A"], miss["B"],
        1 - r10["A"].detect_rate_2s, 1 - r10["B"].detect_rate_2s,
        f"2초 안 탐지 {r['A'].detect_rate_2s:.1%}·{r['B'].detect_rate_2s:.1%}. 같은 세기를 10행째에 넣으면 {r10['A'].detect_rate_2s:.0%}·{r10['B'].detect_rate_2s:.0%}",
        "주입(사전 등록 E1)", f"{src}; {src10}", "변화 순간이 없으면 정상 학습 크기 범위가 흡수한다. 인공 신호")
    r, miss, src = e1row("cur_gain", 1.15, 10)
    g = fn[fn.family.eq("cur_gain") & np.isclose(fn.level_value, 1.15)].set_index("split")
    add("FN", "전류 진폭만 커지는 변화 × 운전 강도", "전류 수준 이동 × 운전 강도", "E1: 전류 ×1.15 배율(10행째부터). 주입 기록의 전류 진폭 사분위별",
        miss["A"], miss["B"], np.nan, np.nan,
        f"2초 안 탐지 {r['A'].detect_rate_2s:.1%}·{r['B'].detect_rate_2s:.1%}. B는 진폭 Q1·Q2 {int(g.loc['B'].detected_amp_Q1 + g.loc['B'].detected_amp_Q2)}/"
        f"{int(g.loc['B'].units_amp_Q1 + g.loc['B'].units_amp_Q2)}, Q4 {int(g.loc['B'].detected_amp_Q4)}/{int(g.loc['B'].units_amp_Q4)}(Spearman {g.loc['B'].spearman_amp:.2f})",
        "주입(E1) + 사후 층화", f"{src}; {_cite(fn_path, fn.family.eq('cur_gain') & np.isclose(fn.level_value, 1.15))}",
        "정상 운전에서도 전류 진폭이 0.85~1.29배 오르내려 배율 변화를 구분하지 못한다")
    v = fn[fn.family.eq("vib_noise") & np.isclose(fn.level_value, 2.0)].set_index("split")
    add("FN", "4σ 미만 진동 이상 × 조용한 운전", "고장 모양 × 운전 강도",
        f"진동 두 센서 2σ 잡음(10행째부터, 반복 {int(v.loc['A'].injection_repeats)}회, 시드 0~{int(v.loc['A'].injection_seed_end)}). 전류 진폭 Q1(조용함) 대 Q4",
        (round(float(v.loc["A"].units_amp_Q1 - v.loc["A"].detected_amp_Q1), 2), int(v.loc["A"].units_amp_Q1)),
        (round(float(v.loc["B"].units_amp_Q1 - v.loc["B"].detected_amp_Q1), 2), int(v.loc["B"].units_amp_Q1)),
        1 - v.loc["A"].detected_amp_Q4 / v.loc["A"].units_amp_Q4, 1 - v.loc["B"].detected_amp_Q4 / v.loc["B"].units_amp_Q4,
        f"전체 탐지 {v.loc['A'].detect_mean:.1%}·{v.loc['B'].detect_mean:.1%}(4σ는 100%). Spearman +{v.loc['A'].spearman_amp:.2f}·+{v.loc['B'].spearman_amp:.2f}, "
        f"BH q {v.loc['A'].q_amp_bh:.2g}·{v.loc['B'].q_amp_bh:.2g}(진폭 {int(v.loc['A'].n_tests_amp)}검정). "
        f"오프셋 0.2× 대비 ρ차 95% CI A [{v.loc['A'].interaction_ci_low:.2f}, {v.loc['A'].interaction_ci_high:.2f}], "
        f"B [{v.loc['B'].interaction_ci_low:.2f}, {v.loc['B'].interaction_ci_high:.2f}]",
        "주입(E1식) + 사후 층화", _cite(fn_path, fn.family.eq("vib_noise")),
        "E1의 74.4%·93.9%와 난수 반복이 다르다. 오류 수는 단위별 평균이며 반복을 독립 표본으로 세지 않는다. 같은 날 의존성은 남는다")
    rows[-1]["ci_method"] = v.loc["A"].quartile_ci_method
    for sid in "AB":
        rows[-1][f"ci_low_{sid}"], rows[-1][f"ci_high_{sid}"] = v.loc[sid].miss_amp_Q1_ci_low, v.loc[sid].miss_amp_Q1_ci_high
    o = fn[fn.family.eq("cur_offset") & np.isclose(fn.level_value, .2)].set_index("split")
    add("FN", "약한 전류 오프셋 × 고부하 운전", "고장 모양 × 운전 강도", "전류 +0.2×진폭 계단(10행째부터). 주입 기록의 전류 진폭 Q4(고부하) 대 Q1",
        (int(o.loc["A"].units_amp_Q4 - o.loc["A"].detected_amp_Q4), int(o.loc["A"].units_amp_Q4)),
        (int(o.loc["B"].units_amp_Q4 - o.loc["B"].detected_amp_Q4), int(o.loc["B"].units_amp_Q4)),
        1 - o.loc["A"].detected_amp_Q1 / o.loc["A"].units_amp_Q1, 1 - o.loc["B"].detected_amp_Q1 / o.loc["B"].units_amp_Q1,
        f"탐지 Q1 {int(o.loc['B'].detected_amp_Q1)}/{int(o.loc['B'].units_amp_Q1)} → Q4 {int(o.loc['B'].detected_amp_Q4)}/{int(o.loc['B'].units_amp_Q4)}(B, Spearman {o.loc['B'].spearman_amp:.2f}, p {o.loc['B'].p_amp:.1e}), "
        f"A {int(o.loc['A'].detected_amp_Q1)}/{int(o.loc['A'].units_amp_Q1)} → {int(o.loc['A'].detected_amp_Q4)}/{int(o.loc['A'].units_amp_Q4)}. 0.4×는 100%",
        "주입(E1식) + 사후 층화", _cite(fn_path, fn.family.eq("cur_offset")), "고부하 운전에서 전류 계단형 약한 이상을 놓친다(가설, 인공 신호)")
    k = sel.alpha.eq(.01) & sel.family.eq("vib_shock") & np.isclose(sel.level, 4.0)
    sh = {s: sel[k & sel.split_id.eq(s)].iloc[0] for s in "AB"}
    k6 = sel.alpha.eq(.01) & sel.family.eq("vib_shock") & np.isclose(sel.level, 6.0)
    sh6 = {s: sel[k6 & sel.split_id.eq(s)].iloc[0] for s in "AB"}
    add("FN", "단발 진동 충격 4σ", "고장 모양", "10행째 한 행에만 진동 두 센서 ±4σ(반복 5회)",
        (int(round((1 - sh["A"].v2_detect_2s) * sh["A"].units * sh["A"].reps)), int(sh["A"].units * sh["A"].reps)),
        (int(round((1 - sh["B"].v2_detect_2s) * sh["B"].units * sh["B"].reps)), int(sh["B"].units * sh["B"].reps)),
        1 - sh6["A"].v2_detect_2s, 1 - sh6["B"].v2_detect_2s,
        f"2초 안 탐지 {sh['A'].v2_detect_2s:.1%}·{sh['B'].v2_detect_2s:.1%}. 6σ는 {sh6['A'].v2_detect_2s:.1%}·{sh6['B'].v2_detect_2s:.1%}",
        "주입(사후, press_selection)", _cite(SELECTION_INJECTION, (k | k6)), "A의 α 1% 문턱(max|z| 4.49)이 B(3.77)보다 높은 것은 A 보정 최댓값이 B 오경보 기록 461이기 때문이다(둘째 값 423도 B 오경보). A 평가 구간은 가장 조용한 시간대다. A·B를 독립 검증 두 건으로 세지 않는다")

    # FP
    ah = fi[fi.condition.eq("amp_high") & fi.value.str.contains("B 정상 학습")]
    hi = {a: ah[ah.alpha.eq(a)].iloc[0] for a in ALPHAS}
    rest = {a: (int(hi[a].comparison_false_alarms), int(hi[a].comparison_denominator)) for a in ALPHAS}
    ev5 = fi[fi.alpha.eq(.05) & fi.condition.eq("vib_sd_quartile") & fi.value.eq("Q4")].iloc[0]
    states = fi[fi.condition.eq("operating_state") & fi.value.eq("load")].set_index("alpha")
    block = fi[fi.condition.eq("amp_high_block_stratified") & fi.value.eq("B 정상 학습 q75")].set_index("alpha")
    within = fi[fi.condition.eq("amp_within_load") & fi.alpha.eq(.05)].iloc[0]
    state5 = states.loc[.05]
    add("FP", "고부하 운전(전류 진폭 ≥ B 정상 학습 q75)", "운전 강도(부하)", "고유 정상 구간 300~599(독립 적합 5개 중 하나라도 경보), 길이 ≥17. A 열 α 1%, B 열 α 5%",
        (int(hi[.01].false_alarms), int(hi[.01].denominator)), (int(hi[.05].false_alarms), int(hi[.05].denominator)),
        rest[.01][0] / rest[.01][1], rest[.05][0] / rest[.05][1],
        f"나머지 {rest[.01][0]}/{rest[.01][1]}(α 1%, p {hi[.01].fisher_p_greater:.2g}, 표본 부족)·{rest[.05][0]}/{rest[.05][1]}(α 5%, p {hi[.05].fisher_p_greater:.1e}). "
        f"α 3% {int(hi[.03].false_alarms)}/{int(hi[.03].denominator)} 대 {rest[.03][0]}/{rest[.03][1]}. 진동 SD Q4 {int(ev5.false_alarms)}/{int(ev5.denominator)}(크기 경보 경로). "
        f"5적합 합침 α5% 부하 상태 {int(state5.false_alarms)}/{int(state5.denominator)} 대 나머지 {int(state5.comparison_false_alarms)}/{int(state5.comparison_denominator)}, "
        f"시간블록 CMH p {block.loc[.05].cmh_p:.2g}(MH OR {block.loc[.05].mh_pooled_or:.1f}). "
        f"부하 안 진폭 ≥{within.threshold:.1f}: {int(within.false_alarms)}/{int(within.denominator)} 대 {int(within.comparison_false_alarms)}/{int(within.comparison_denominator)}",
        "관측(사후, 같은 날 77분)", _cite(fi_path, (fi.condition.eq("amp_high") & fi.value.str.contains("B 정상 학습")) |
            (fi.alpha.eq(.05) & fi.condition.eq("vib_sd_quartile")) | (fi.condition.eq("operating_state") & fi.value.eq("load")) |
            (fi.condition.eq("amp_high_block_stratified") & fi.value.eq("B 정상 학습 q75")) | (fi.alpha.eq(.05) & fi.condition.eq("amp_within_load"))),
        "A·B 열은 분할이 아니라 α다. 부하 상태는 원 전류 RMS≥91.9의 신호 대리변수. 보정은 상태 혼합의 주변 보장이고 상태 조건부 보장이 아니다. 적합 겹침·시간 의존성은 남는다")
    ind = fp[fp.independent & fp.alpha.eq(.05)]
    single = int(((ind.reasons == "magnitude") & (ind.magnitude_sensor == "AI0_Vibration")).sum())
    add("FP", "상부 진동(AI0) 단발 충격(구성비)", "운전 강도(부하)", "α 5% 오경보 사건의 구성(동결 A·B + 시간순 5폴드, 같은 모델 중복 제거)",
        (single, len(ind)), (int((ind.alarm_rows == 1).sum()), len(ind)), np.nan, np.nan,
        f"A 열: AI0 크기 단독 {single}/{len(ind)}, B 열: 경보 1행 {int((ind.alarm_rows == 1).sum())}/{len(ind)}. 고유 구간 {ind.record.nunique()}. 조건부 비율은 윗행",
        "관측(구성비, 의존 사건)", _cite(fp_path, fp.independent & fp.alpha.eq(.05)), "구성비라 조건부 오경보율이 아니다. 사건이 같은 날 77분 안이라 독립이 아니다")
    b = nm[nm.split.eq("B")].set_index("condition")
    add("FP", "문턱 근처 정상 구간과 운전 강도", "운전 강도(부하)·운전 시간대", "정상 평가 구간 최대 점수/α 1% 문턱과 조건의 Spearman(B)",
        (0, 0), (int(b.loc["vib_maxz"].records_ge_0_9), int(b.loc["vib_maxz"].records)), np.nan, np.nan,
        f"진동 max|z| {b.loc['vib_maxz'].spearman:.2f}, 진동 SD {b.loc['vib_sd'].spearman:.2f}, 전류 진폭 {b.loc['current_amp'].spearman:.2f}, 시간 {b.loc['time_order'].spearman:.2f}",
        "관측(연속 지표)", _cite(nm_path, nm.split.eq("B")), "B 열은 문턱의 0.9배 이상 구간 수(오경보 3 포함). A는 조용한 구간이라 해당 없음")
    ka = ds.split_id.eq("A") & ds.alpha.eq(.01) & ds.k.eq(1.5)
    kb = ds.split_id.eq("B") & ds.alpha.eq(.01) & ds.k.isin([1.0, 1.05, 1.5])
    d = ds[kb].set_index("k")
    add("FP", "전류 수준 상승", "전류 수준 이동", "정상 평가 전류 전체 ×k(재학습 없음, α 1%). A·B 열은 ×1.5",
        (int(ds[ka].normal_notified_segments.iloc[0]), int(ds[ka].normal_segments.iloc[0])),
        (int(d.loc[1.5].normal_notified_segments), int(d.loc[1.5].normal_segments)), np.nan, d.loc[1.0].normal_notified_segments / d.loc[1.0].normal_segments,
        f"B ×1.0 {int(d.loc[1.0].normal_notified_segments)}, ×1.05 {int(d.loc[1.05].normal_notified_segments)}, ×1.5 {int(d.loc[1.5].normal_notified_segments)}/180. "
        "변경 기록 없는 감시 초과 창은 설비 점검 요청, 기록 있으면 재보정 검토(monitor_gain_v2)",
        "스트레스(모의)", _cite(dayshift, ka | kb), "실제 부하 변화의 모양은 모른다")
    k = rb.criterion.eq("conformal") & rb.alpha.eq(.01) & rb.version.eq("v2") & rb.input_variant.isin(["matched", "coarse"])
    c = rb[k].set_index(["split_id", "input_variant"])
    add("FP", "거친 계측 정밀도", "계측 정밀도", "평가 입력만 coarse(4배 거친 정밀도)로 바꿈(재학습 없음, α 1%)",
        (int(c.loc[("A", "coarse")].normal_notified_segments), int(c.loc[("A", "coarse")].normal_segments)),
        (int(c.loc[("B", "coarse")].normal_notified_segments), int(c.loc[("B", "coarse")].normal_segments)),
        c.loc[("A", "matched")].normal_notified_segments / c.loc[("A", "matched")].normal_segments,
        c.loc[("B", "matched")].normal_notified_segments / c.loc[("B", "matched")].normal_segments,
        f"matched {int(c.loc[('A', 'matched')].normal_notified_segments)}·{int(c.loc[('B', 'matched')].normal_notified_segments)}", "스트레스", _cite(rb_path, k),
        "계측 장비·설정이 바뀌면 재보정한다(recalibrate.py)")
    out_df = pd.DataFrame(rows)
    assert len(out_df) <= 12
    out_df["proxy_definition"] = out_df.proxy.map(lambda p: "; ".join(v for key, v in PROXIES.items() if key in p))
    return out_df


# ---------- 그림(평가관 03 E8) ----------
def insight_figures(out, sens_imp, cfit, crec, prel, fa_events, normal, models, pvm=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": runtime.korean_fonts(), "axes.unicode_minus": False, "font.size": 9,
                         "axes.spines.top": False, "axes.spines.right": False})
    A_COL, B_COL, GREY, FA = "#2a78d6", "#eb6834", "#9a9a94", "#b3412e"   # dataviz 범주 1·2번(검증기 통과)
    # 1) 센서 중요도: 재적합 절제와 채널 교체의 미탐 행(α=1%)
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.4))
    ab = sens_imp[sens_imp.method.eq("refit_ablation") & sens_imp.alpha.eq(.01)]
    order = ["full", "drop_AI1", "drop_AI0", "drop_AI2_from_magnitude", "current_only", "vibration_only"]
    names = {"full": "전체(v2)", "drop_AI1": "AI1 빼기", "drop_AI0": "AI0 빼기", "drop_AI2_from_magnitude": "크기에서 AI2 빼기", "current_only": "전류만", "vibration_only": "진동만"}
    x = np.arange(len(order)); w = .38
    for k, (sid, col) in enumerate((("A", A_COL), ("B", B_COL))):
        v = ab[ab.split.eq(sid)].set_index("variant").reindex(order).fn
        axes[0].bar(x + (k - .5) * w, v, w, color=col, label=f"분할 {sid}")
    axes[0].set_xticks(x, [names[o] for o in order], rotation=20); axes[0].set_ylabel("미탐 행 / 600"); axes[0].set_title("센서·성분 재적합 절제(α=1%, 이상 600행·21구간)"); axes[0].legend(frameon=False)
    sw = sens_imp[sens_imp.method.eq("channel_swap")]
    labels = [f"{s} 교체" for s in D.SENSORS]
    for k, (sid, col) in enumerate((("A", A_COL), ("B", B_COL))):
        v = sw[sw.split.eq(sid)].set_index("variant").reindex([f"swap_{s}" for s in D.SENSORS]).fn
        axes[1].bar(np.arange(3) + (k - .5) * w, v, w, color=col, label=f"분할 {sid}")
    axes[1].set_xticks(np.arange(3), labels); axes[1].set_ylabel("미탐 행 / 600 (20회 중앙값)"); axes[1].set_title("이상 기록의 채널 하나를 정상 기록으로 교체")
    for ax in axes: ax.grid(axis="y", color="#e6e5df")
    fig.tight_layout(); fig.savefig(out / "fig_sensor_importance_v2.png", dpi=150); plt.close(fig)
    # 2) 진동–전류 진폭 결합(정상 학습 적합선)과 정상 평가·오경보·이상 구간
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
    for ax, sid in zip(axes, ("A", "B")):
        f = cfit[cfit.split.eq(sid)].iloc[0]
        r = crec[crec.split.eq(sid)]
        nt, ab_, fa = r[r.subset.eq("normal_test") & ~r.false_alarm], r[r.subset.eq("abnormal")], r[r.false_alarm.astype(bool)]
        ax.scatter(np.log(nt.current_amp), np.log(nt.vib_sd), s=10, color=GREY, label="정상 평가 구간")
        ax.scatter(np.log(ab_.current_amp), np.log(ab_.vib_sd), s=22, color=A_COL, marker="s", label="이상 구간")
        if len(fa): ax.scatter(np.log(fa.current_amp), np.log(fa.vib_sd), s=60, facecolor="none", edgecolor=FA, linewidth=1.8, label="오경보 구간(α=1%)")
        xs = np.linspace(np.log(r.current_amp).min(), np.log(r.current_amp).max(), 50)
        ax.plot(xs, f.intercept + f.slope * xs, color="#1f1f1e", lw=1.2, label=f"정상 학습 결합 r={f.r:.2f}")
        ax.set_title(f"분할 {sid}"); ax.set_xlabel("log 전류 진폭(√2×평균 제거 RMS)"); ax.grid(color="#e6e5df")
    axes[0].set_ylabel("log 진동 SD(두 센서)"); axes[0].legend(frameon=False, fontsize=8)
    n_desc = ", ".join(f"{sid}: 정상 평가 {int(((crec.split == sid) & (crec.subset == 'normal_test')).sum())}·이상 {int(((crec.split == sid) & (crec.subset == 'abnormal')).sum())}구간(길이≥17)" for sid in ("A", "B"))
    fig.suptitle(f"정상 운전에서 진동과 전류 진폭은 함께 움직이고, 이상 구간은 이 결합에서 벗어난다(상대 척도; {n_desc}; 오경보 B 3/180, α=1%)", x=.01, ha="left", fontsize=8.5)
    fig.tight_layout(); fig.savefig(out / "fig_coupling_v2.png", dpi=150); plt.close(fig)
    # 3) 오경보 사례: 분할 B α=1% 오경보 구간의 상부 진동 z와 경보 행(위), 성분 점수와 α 1% 점수 문턱(아래)
    fa = fa_events[fa_events.model.eq("frozen_B") & fa_events.alpha.eq(.01)]
    seg_all = D.segments(normal)
    model = models["B"]
    from serve import score_threshold
    thr = score_threshold(model.cal, .01)
    ncol = max(len(fa), 1)
    fig, axes = plt.subplots(2, ncol, figsize=(3.6 * ncol, 5.2), sharex="col", squeeze=False)
    for j, ev in enumerate(fa.itertuples()):
        g = normal[seg_all == ev.record]
        p = model.predict(g, .01)
        z0 = (g.AI0_Vibration.to_numpy() - model.mean[0]) / model.scale[0]
        t = np.arange(len(g)) * D.DT
        al = p.alarm.to_numpy() == 1
        ax = axes[0, j]
        ax.plot(t, z0, color=A_COL, lw=1.4, label="AI0 진동 z")
        ax.scatter(t[al], z0[al], color=FA, zorder=3, s=30, label="경보 행")
        ax.set_title(f"구간 {ev.record} · {ev.time} · 경보 {ev.alarm_rows}행", fontsize=8.5); ax.grid(color="#e6e5df")
        ax2 = axes[1, j]
        for key, name, col, ls in (("g_magnitude", "크기", "#b07510", "-"), ("g_waveform", "파형", "#178cc2", "--"), ("g_dynamics", "예측 오차", "#6d55c9", ":")):
            ax2.plot(t, p[key], color=col, lw=1.4, ls=ls, label=name)
        ax2.axhline(thr, color=FA, lw=1, ls="--", label=f"α 1% 점수 문턱 {thr:.2f}")
        ax2.set_xlabel("기록 시작 후 초"); ax2.grid(color="#e6e5df")
    axes[0, 0].set_ylabel("정상 학습 기준 z"); axes[1, 0].set_ylabel("성분 점수 g"); axes[0, 0].legend(frameon=False, fontsize=7.5); axes[1, 0].legend(frameon=False, fontsize=7.5)
    fig.suptitle(f"분할 B의 정상 오경보 {len(fa)}/180구간(α=1%): 상부 진동 단발 스파이크 1행이 크기 성분만 문턱을 넘음, 2단계로 격상되지 않음", x=.01, ha="left", fontsize=8.5)
    fig.tight_layout(); fig.savefig(out / "fig_false_alarm_cases_v2.png", dpi=150); plt.close(fig)
    # 3b) 위치 × 진동 수준 미탐(행, α=1%, 95% 구간)
    if pvm is not None:
        fig, axes = plt.subplots(1, 2, figsize=(9, 3.4), sharey=True)
        for ax, sid in zip(axes, ("A", "B")):
            r = pvm[pvm.split.eq(sid) & pvm.position.isin(["0-1", "2-6", ">=7"]) & pvm.vibration.isin(["vibration_normal_range", "vibration_high"])]
            for k, (vib, col, lab) in enumerate((("vibration_normal_range", A_COL, "진동 정상 범위 구간"), ("vibration_high", B_COL, "진동 높은 구간"))):
                rr = r[r.vibration.eq(vib)].set_index("position").reindex(["0-1", "2-6", ">=7"])
                xs = np.arange(3) + (k - .5) * .38
                ax.bar(xs, rr.miss_rate, .38, color=col, label=lab)
                ax.errorbar(xs, rr.miss_rate, yerr=[rr.miss_rate - rr.ci_low, rr.ci_high - rr.miss_rate], fmt="none", color="#1f1f1e", capsize=2, lw=.8)
                for x_, row in zip(xs, rr.itertuples()):
                    ax.text(x_, min(row.miss_rate + .06, 1.02), f"{int(row.missed_rows)}/{int(row.rows)}", ha="center", fontsize=7)
            ax.set_xticks(np.arange(3), ["위치 0–1", "위치 2–6", "위치 ≥7"]); ax.set_title(f"분할 {sid}"); ax.grid(axis="y", color="#e6e5df")
        axes[0].set_ylabel("미탐 행 비율(95% 구간)"); axes[0].legend(frameon=False, fontsize=8)
        fig.suptitle("위치 × 진동 수준 미탐(α=1%, 이상 600행). 진동이 정상 범위인 이상 3구간은 위치 0–1을 모두 놓친다", x=.01, ha="left", fontsize=9)
        fig.tight_layout(); fig.savefig(out / "fig_position_vibration_v2.png", dpi=150); plt.close(fig)
    # 4) 이상 확률 신뢰도(21겹 교차 보정, 평가 자료 비율)
    fig, ax = plt.subplots(figsize=(4.6, 4.0))
    ax.plot([0, 1], [0, 1], color=GREY, lw=1, ls=":")
    for sid, col, mk in (("A", A_COL, "o"), ("B", B_COL, "s")):
        r = prel[prel.split.eq(sid)]
        ax.errorbar(r.mean_predicted, r.observed, yerr=[r.observed - r.ci_low, r.ci_high - r.observed], fmt=mk, color=col, ms=6, capsize=2, label=f"분할 {sid}")
    ax.set_xlabel("예측 이상 확률(평가 자료 비율 기준)"); ax.set_ylabel("관측 이상 비율(95% 구간)"); ax.set_title("이상 확률 층의 신뢰도(이상 기록 21겹 교차)")
    ax.legend(frameon=False); ax.grid(color="#e6e5df")
    fig.tight_layout(); fig.savefig(out / "fig_probability_reliability_v2.png", dpi=150); plt.close(fig)


# ---------- 단위별 결과·단순 규칙 기준선(적대적 검수 X-01·X-02, 재검수 정정) ----------
V1_OUT = YEJUN / "press_submission" / "outputs"
POS_BINS = (("0-1", 0, 1), ("2-6", 2, 6), (">=7", 7, 10 ** 6))
OSC_COEF = 2 * np.cos(2 * np.pi * .6 * D.DT)      # 고정 0.6 Hz 공진 잔차의 계수(학습하지 않는다)
V1_ALARM = {.01: "alarm", .03: "alarm_conformal_0.03", .05: "alarm_conformal_0.05"}


def _fixed_rule(frame):
    """학습 없는 고정 규칙의 성분: 전류 고정 0.6 Hz 공진 잔차 |x_t − 2cos(2π·0.6·0.1)x_{t−1} + x_{t−2}|(위치 2부터)와 두 진동의 절댓값."""
    q = D.quantize(D.inputs_only(frame), "matched"); seg = layout(q)[1]
    x = q[D.SENSORS].to_numpy(float)
    pos, _ = D.segment_positions(seg)
    osc = np.full(len(x), np.nan)
    i = np.flatnonzero(pos >= 2)
    osc[i] = np.abs(x[i, 2] - OSC_COEF * x[i - 1, 2] + x[i - 2, 2])
    return np.column_stack([osc, np.abs(x[:, 0]), np.abs(x[:, 1])]), seg, pos


def _unit_row(split, alpha, model, an, aa, sn, sa, pos_a, score_n, score_a, note):
    an, aa, sn, sa = np.asarray(an, bool), np.asarray(aa, bool), np.asarray(sn), np.asarray(sa)
    score_n, score_a, pos_a = np.asarray(score_n, float), np.asarray(score_a, float), np.asarray(pos_a)
    tp, fp, fn = int(aa.sum()), int(an.sum()), int((~aa).sum())
    rec_n = pd.Series(score_n).groupby(sn).max(); rec_a = pd.Series(score_a).groupby(sa).max()
    y = np.r_[np.zeros(len(rec_n)), np.ones(len(rec_a))]; s = np.r_[rec_n.fillna(-np.inf), rec_a.fillna(-np.inf)]
    row = dict(split=split, alpha=alpha, model=model, tp=tp, fp=fp, fn=fn, f1_rows=2 * tp / (2 * tp + fp + fn),
               abnormal_records_detected=int(pd.Series(aa).groupby(sa).any().sum()), abnormal_records=int(len(np.unique(sa))),
               normal_records_alerted=int(pd.Series(an).groupby(sn).any().sum()), normal_records=int(len(np.unique(sn))),
               record_auroc=float(roc_auc_score(y, s)) if len(rec_n) and len(rec_a) else np.nan,
               record_normal_max=float(rec_n.max()), record_abnormal_min=float(rec_a.min()))
    for lab, lo, hi in POS_BINS:
        m = (pos_a >= lo) & (pos_a <= hi)
        row[f"missed_pos_{lab}"], row[f"rows_pos_{lab}"] = int((~aa & m).sum()), int(m.sum())
    row["note"] = note
    return row


def unit_results(normal, abnormal, models):
    """α별 v1·v2·단순 규칙의 행 단위(F1)와 기록 단위(21기록 탐지·정상 기록 알림·기록 최대 점수 AUROC) 결과, 이상 행의 기록 안 위치별 미탐.
    기록 단위로는 세 방법이 거의 같고, v2의 개선은 주로 기록 시작 0.2~0.6초(위치 2~6) 행에서 나온다. 단순 규칙은 성분 척도를 정상 학습
    최댓값으로 정하고, 보정 기록 최대 점수로 같은 conformal 문턱을 쓴다. 이상 자료를 본 뒤 만든 사후 비교 기준선이며 채택 후보가 아니다."""
    rows = []
    seg_all = D.segments(normal)
    fa, sa, pos_a = _fixed_rule(abnormal)
    for sid, model in models.items():
        sp = D.split_normal(normal, seg_all, sid)
        v1 = pd.read_csv(V1_OUT / f"predictions_{sid}.csv")
        v1n, v1a = v1[v1.source.eq("normal_test")], v1[v1.source.eq("abnormal")]
        ftr, _, _ = _fixed_rule(sp["train"]); fcal, scal, _ = _fixed_rule(sp["cal"]); ftest, stest, _ = _fixed_rule(sp["test"])
        scale = np.nanmax(ftr, axis=0)
        rule = lambda comp: np.fmax.reduce(comp / scale, axis=1)
        cal_max = pd.Series(rule(fcal)).groupby(scal).max().to_numpy()
        rn, ra = rule(ftest), rule(fa)
        for alpha in ALPHAS:
            pn, pa = model.predict(sp["test"], alpha), model.predict(abnormal, alpha)
            rows.append(_unit_row(sid, alpha, "v2(최종)", pn.alarm.eq(1), pa.alarm.eq(1), pn.record_id, pa.record_id, pa.position.to_numpy(),
                                  pn.score.to_numpy(), pa.score.to_numpy(), "저장 모델"))
            rows.append(_unit_row(sid, alpha, "v1(기준)", v1n[V1_ALARM[alpha]].eq(1), v1a[V1_ALARM[alpha]].eq(1), v1n.record_id, v1a.record_id,
                                  v1a.position_in_record.to_numpy(), v1n.combined_score.to_numpy(), v1a.combined_score.to_numpy(), "press_submission 예측 파일"))
            rows.append(_unit_row(sid, alpha, "단순 규칙(학습 없음, 사후)", conformal_p(cal_max, rn) <= alpha, conformal_p(cal_max, ra) <= alpha,
                                  stest, sa, pos_a, rn, ra, "고정 0.6 Hz 공진 잔차·진동 절댓값의 최댓값. 척도는 정상 학습 최댓값, 문턱은 같은 보정 기록 최대 점수"))
    return pd.DataFrame(rows)


# ---------- 같은 조건의 확률 기준선 비교(적대적 검수 X-04, 재검수 정정) ----------
def _weighted_losses(y, p, prior):
    """평가 비율 prior로 재가중한 Brier·log-loss·ECE(10구간). prior=None이면 파일 그대로(행마다 같은 가중)."""
    y = np.asarray(y, int); p = np.clip(np.asarray(p, float), 0.0, 1.0)
    w = np.full(len(y), 1.0 / len(y)) if prior is None else np.where(y == 1, prior / max((y == 1).sum(), 1), (1 - prior) / max((y == 0).sum(), 1))
    pc = np.clip(p, 1e-9, 1 - 1e-9)
    brier = float((w * (p - y) ** 2).sum()); logloss = float(-(w * (y * np.log(pc) + (1 - y) * np.log(1 - pc))).sum())
    bins = np.minimum((p * 10).astype(int), 9)
    ece = float(sum(abs((w[bins == b] * (p[bins == b] - y[bins == b])).sum()) for b in range(10)))
    return brier, logloss, ece


def probability_baselines(normal, models, out):
    """예측 사전확률 π와 평가 비율을 맞춘 확률 비교. 평가 비율은 파일 그대로(구성비를 아는 파일 안 평가)와 1%(클래스별 분포를
    그대로 두고 재가중한 배포 가정 시나리오) 두 가지다. 현재 확률 층·두 수준 교차 보정(경보 여부만, LR 상한 121)·경보 0/1·1−p(확률 아님)·
    상수 π를 같은 행·같은 가중으로 채점한다. 1−p와 경보 0/1은 확률이 아닌 점수를 그대로 채점한 참고값이다. 현재 층의 이상 행 우도비와
    두 수준의 적중률·오경보율은 기록 하나 빼기 교차 적합 값이다. log-loss는 [1e-9, 1−1e-9]로 자른다. 한 에피소드 안 평가이며 현장 확률 검증이 아니다."""
    from probability import posterior
    rows = []
    for sid, model in models.items():
        t = pd.read_csv(out / f"test_predictions_{sid}.csv")
        ok = np.isfinite(t.likelihood_ratio) & np.isfinite(t.p_value)
        t = t[ok].reset_index(drop=True)
        y = t.label.to_numpy(int); alarm = t.alarm.to_numpy(bool)
        cap = len(model.cal) + 1
        rec = t.record_id.to_numpy()
        lr2 = np.empty(len(t))
        # 두 수준 교차 보정: 경보 적중률은 이상 기록 하나 빼기, 오경보율은 정상 평가 기록 하나 빼기로 정한다
        # (보정 행은 α 1%에서 구조상 경보가 날 수 없어 오경보율 추정에 쓰지 않는다).
        norm_alarm = pd.Series(alarm[y == 0]).groupby(rec[y == 0]).agg(["sum", "size"])
        abn_alarm = pd.Series(alarm[y == 1]).groupby(rec[y == 1]).agg(["sum", "size"])
        fpr_all = float(norm_alarm["sum"].sum() / norm_alarm["size"].sum()); tpr_all = float(abn_alarm["sum"].sum() / abn_alarm["size"].sum())

        def two_level(a, tpr, fpr):
            return np.where(a, min(cap, tpr / fpr) if fpr > 0 else cap, max(1 / cap, (1 - tpr) / (1 - fpr)))
        for r in abn_alarm.index:
            m = (y == 1) & (rec == r)
            tpr = float((abn_alarm["sum"].sum() - abn_alarm.loc[r, "sum"]) / (abn_alarm["size"].sum() - abn_alarm.loc[r, "size"]))
            lr2[m] = two_level(alarm[m], tpr, fpr_all)
        for r in norm_alarm.index:
            m = (y == 0) & (rec == r)
            fpr = float((norm_alarm["sum"].sum() - norm_alarm.loc[r, "sum"]) / (norm_alarm["size"].sum() - norm_alarm.loc[r, "size"]))
            lr2[m] = two_level(alarm[m], tpr_all, fpr)
        file_ratio = float(y.mean())
        for label, prior, weight in (("파일 비율", file_ratio, None), ("1%", .01, .01)):
            methods = {"현재 확률 층(예측 π = 평가 비율)": posterior(t.likelihood_ratio.to_numpy(float), prior),
                       "두 수준 교차 보정(경보 여부, LR 상한 121)": posterior(lr2, prior),
                       "경보 0/1(미보정)": alarm.astype(float), "1−p(확률 아님)": 1 - t.p_value.to_numpy(float),
                       "상수 π": np.full(len(t), prior)}
            for name, p in methods.items():
                b, l, e = _weighted_losses(y, p, weight)
                rows.append(dict(split=sid, evaluation_prior=label, prior_value=prior, method=name, brier=b, log_loss=l, ece=e,
                                 rows=len(t), abnormal_rows=int(y.sum()), normal_alarm_rate=fpr_all, abnormal_alarm_rate=tpr_all))
    return pd.DataFrame(rows)
