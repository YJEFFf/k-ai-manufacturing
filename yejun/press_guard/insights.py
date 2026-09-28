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

from model import GuardModel, D, sine_score, layout, ALERT_UNIT_ROWS
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
    from probability import ProbabilityCalibrator, posterior, expected_calibration_error, alert_evidence_bound, sellke_bayes_factor
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
                # 비교: 상한(121)이 없는 등방 회귀와 Platt. 상한은 증거력 제한이라 최상위 구간 확률을 낮춰 ECE를 키운다(평가관 02 M1의 Platt 값과 차이의 이유).
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
                             label_free_alert_lr=alert_evidence_bound(len(model.cal), det), label_free_alert_p=float(posterior(alert_evidence_bound(len(model.cal), det), pi)),
                             sbb_reference_lr=sbb, sbb_reference_p=float(posterior(sbb, pi)),
                             sbb_note="참고값: 연속 p값을 정확히 관측하고 대립에서 p가 Beta(ξ,1) 족일 때의 회의적 환산. 알림은 p≤1/121 사건이라 상한이 아니다(알림 우도비 상한은 label_free_alert_lr)"))
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
    """혼합 대기열(정상 평가 + 이상)의 순위와, 주입 고장 대 정상 오경보 순위를 정렬 키 후보마다 센다. 키 선택에는 이상 라벨을 쓰지 않는다."""
    from model import PRIORITY_KEYS, priority_ranks, cases as make_cases
    from recalibrate import inject, unit_layout
    mixed_rows, inj_rows = [], []
    for sid, model in models.items():
        split = D.split_normal(normal, D.segments(normal), sid)
        test = D.inputs_only(split["test"])
        units, in_unit, size = unit_layout(test)
        mask = (size >= 30) & (in_unit >= 10)
        for alpha in ALPHAS:
            pn, pa = model.predict(test, alpha), model.predict(abnormal, alpha)
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
                for key in PRIORITY_KEYS:
                    rank = priority_ranks(q2, key)
                    best_fa = rank[~injected].min() if (~injected).any() else np.inf
                    inj_rows.append(dict(split=sid, alpha=alpha, family=fam, level_value=lv, key=key, injected_cases=int(injected.sum()),
                                         false_alarm_cases=int((~injected).sum()),
                                         injected_below_best_false_alarm=int((rank[injected] > best_fa).sum()) if np.isfinite(best_fa) else 0))
    inj = pd.DataFrame(inj_rows)
    summary = inj.groupby("key").injected_below_best_false_alarm.sum().rename("total_injected_below_best_false_alarm").reset_index()
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
    대회 21/21의 95% 하한. 알림 한 건의 우도비는 (n+1)·TPR을 넘지 못한다(명목 FAR에서 같아진다)."""
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
                                         lr_bound=(n + 1) * tpr, p_anomaly_given_alert=pi * tpr / (pi * tpr + (1 - pi) * far)))
    out = pd.DataFrame(rows)
    out["note"] = "π는 알림 단위당 이상 비율 가정. 교환가능성(같은 운전 조건의 정상) 가정. 주입은 인공 신호라 실제 고장 탐지율이 아니다"
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
    out["note"] = "감시 창 60단위. 전류 전체에 배율 k(analysis/press_dayshift와 같은 모의). A 평가 구간은 가장 조용한 시간대라 알림이 늘지 않는다"
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
    # 2단계 교대 알림의 비사후 추정: 1단계 명목 × 독립 폴드(동결 모델과 보정값이 다른 시간순 폴드) α 5%의 2단계/1단계 비.
    # 2단계 규칙은 대회 오경보를 본 뒤 정해 "관측" 행의 2단계 0건은 표본 내 값이다(post_hoc).
    ind = levels[levels.independent & levels.model.str.startswith("rolling") & levels.alpha.eq(.05)].groupby("level").normal_alerted_segments.sum()
    k2, k1 = int(ind.get(2, 0)), int(ind.get(1, 0))
    ratio, ratio_hi = (k2 / k1, float(stats.beta.ppf(.95, k2 + 1, k1 - k2))) if k1 else (np.nan, np.nan)
    nominal = lv.loc[1, "nominal_alerts_per_8h_elapsed"]
    alerts = {"명목": (nominal, np.nan),
              "비사후 추정(독립 폴드 2/1단계 비)": (nominal, nominal * ratio),
              "비사후 추정 95% 상한": (nominal, nominal * ratio_hi),
              "관측": (lv.loc[1, "alerts_per_8h_elapsed"], lv.loc[2, "alerts_per_8h_elapsed"]),
              "관측 95% 상한": (lv.loc[1, "upper95_alerts_per_8h_elapsed"], lv.loc[2, "upper95_alerts_per_8h_elapsed"])}
    basis = {"비사후 추정(독립 폴드 2/1단계 비)": f"독립 시간순 폴드 α 5%: 2단계 {k2} / 1단계 {k1} = {ratio:.3f}",
             "비사후 추정 95% 상한": f"같은 비의 단측 95% 상한 {ratio_hi:.3f}"}
    detect = (float(inj.level2_detect_2s.min()), .05 ** (1 / 21), 1.0)
    detect_basis = ("E1식 주입 2단계 2초 탐지율 최솟값(B α1%)", "대회 21/21의 95% 하한", "대회 21/21 관측")
    rows = []
    for name, (a1, a2) in alerts.items():
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
                rows.append(dict(alert_scenario=name, post_hoc=name.startswith("관측") and policy == "2단계만 출동",
                                 level2_basis=basis.get(name, "2단계 규칙을 정하기 전에 본 대회 자료(표본 내)" if name.startswith("관측") else ""),
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
        for alpha in ALPHAS:
            fa = m.predict(frame, alpha).groupby("record_id").alarm.max()
            for r, v in fa.items():
                f = feat.loc[r]
                rows.append(dict(model=name, alpha=alpha, absolute_record=int(lo + r), length=int(f.length), current_amp=float(f.current_amp),
                                 vib_sd=float(f.vib_sd), false_alarm=int(v)))
    return pd.DataFrame(rows)


def fp_intensity(normal, models, rolling):
    """평가 단위(적합 × 구간) 분모의 운전 강도·시간 블록별 조건부 오경보율, CI, lift, 단측 Fisher. 고유 구간 기준도 함께.
    사분위 경계는 α 1% 평가 단위(길이 ≥17)의 분포다. 진동 SD 사분위는 크기 성분의 발화 경로와 겹친다."""
    ev = _independent_evaluations(normal, models, rolling)
    base = ev[ev.alpha.eq(.01)]
    amp_q = base[base.length >= 17].current_amp.quantile([.25, .5, .75]).to_numpy()
    vsd_q = base.vib_sd.dropna().quantile([.25, .5, .75]).to_numpy()
    split_b = D.split_normal(normal, D.segments(normal), "B")["train"]
    qb = D.quantize(D.inputs_only(split_b), "matched")
    ftr = _record_features(qb, layout(qb)[1], models["B"])
    b_q75 = float(ftr[ftr.length >= 17].current_amp.quantile(.75))
    rows = []
    for alpha in ALPHAS:
        g = ev[ev.alpha.eq(alpha)].copy()
        g["amp_quartile"] = np.where(g.length < 17, "짧은 기록(<17)", pd.cut(g.current_amp, [-np.inf, *amp_q, np.inf], labels=["Q1", "Q2", "Q3", "Q4"]).astype(str))
        g["vib_sd_quartile"] = pd.cut(g.vib_sd, [-np.inf, *vsd_q, np.inf], labels=["Q1", "Q2", "Q3", "Q4"]).astype(str)
        g["block"] = (g.absolute_record // 60 * 60).astype(str) + "~" + (g.absolute_record // 60 * 60 + 59).astype(str)
        tot_k, tot_n = int(g.false_alarm.sum()), len(g)
        for cond in ("amp_quartile", "vib_sd_quartile", "block"):
            for v, gg in g.groupby(cond):
                k, n = int(gg.false_alarm.sum()), len(gg)
                lo, hi = clopper(k, n)
                pf = stats.fisher_exact([[k, n - k], [tot_k - k, tot_n - n - (tot_k - k)]], alternative="greater").pvalue if n < tot_n else np.nan
                rows.append(dict(unit="평가 단위(적합×구간)", alpha=alpha, condition=cond, value=v, false_alarms=k, denominator=n, rate=k / n,
                                 ci_low=lo, ci_high=hi, lift=(k / n) / (tot_k / tot_n) if tot_k else np.nan, fisher_p_greater=float(pf),
                                 small_sample=tot_k < 5,
                                 note="크기 성분 경보의 발화 경로와 겹친다" if cond == "vib_sd_quartile" else ""))
        u = g.groupby("absolute_record").agg(fa=("false_alarm", "max"), amp=("current_amp", "first"), length=("length", "first"))
        for lab, cut in (("전류 진폭 ≥ 평가 분포 q75", amp_q[2]), ("전류 진폭 ≥ B 정상 학습 q75", b_q75)):
            hi_ = (u.length >= 17) & (u.amp >= cut)
            k1, n1 = int(u[hi_].fa.sum()), int(hi_.sum()); k0, n0 = int(u[~hi_].fa.sum()), int((~hi_).sum())
            lo1, hi1 = clopper(k1, n1)
            pf = stats.fisher_exact([[k1, n1 - k1], [k0, n0 - k0]], alternative="greater").pvalue
            rows.append(dict(unit="고유 구간(300~599, 한 적합이라도 경보)", alpha=alpha, condition="amp_high", value=f"{lab} ({cut:.1f})", false_alarms=k1,
                             denominator=n1, rate=k1 / n1, ci_low=lo1, ci_high=hi1, lift=(k1 / n1) / ((k1 + k0) / (n1 + n0)) if k1 + k0 else np.nan,
                             fisher_p_greater=float(pf), small_sample=(k1 + k0) < 5, note=f"나머지 {k0}/{n0}"))
    out = pd.DataFrame(rows)
    out["post_hoc"] = True
    return out


# ---------- 고장 모양 × 운전 강도 미탐(2회차 평가관 03 R2-02) ----------
FN_FAMILIES = (("vib_noise", 2.0), ("cur_noise", .1), ("cur_offset", .2), ("cur_gain", 1.15), ("cur_gain", 1.3))


def fn_intensity(normal, models, reps=5):
    """E1과 같은 계단 주입(30행 이상 단위의 10행째부터, α 1%, 2초 안)의 단위별 탐지를 주입받은 기록의 운전 강도(전류 진폭·진동 SD)로 나눈다.
    잡음 족은 반복 5회(난수 0~4) 평균이다. E1의 난수와 달라 잡음 족 값은 E1과 소수 둘째 자리에서 다를 수 있다."""
    from recalibrate import inject, unit_layout, T0, WINDOW, MIN_UNIT_ROWS
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
            ra, pa_ = stats.spearmanr(amp, det) if det.std() > 0 else (np.nan, np.nan)
            rv, pv = stats.spearmanr(vsd, det) if det.std() > 0 else (np.nan, np.nan)
            row = dict(split=sid, family=fam, level_value=lv, units=len(el_units), detect_mean=float(det.mean()),
                       spearman_amp=float(ra), p_amp=float(pa_), spearman_vib_sd=float(rv), p_vib_sd=float(pv))
            for qlab in ("Q1", "Q2", "Q3", "Q4"):
                m = np.asarray(amp_q == qlab)
                row[f"detected_amp_{qlab}"] = float(det[m].sum()); row[f"units_amp_{qlab}"] = int(m.sum())
            rows.append(row)
    out = pd.DataFrame(rows)
    out["note"] = "사후 분석. 인공 신호. 사분위는 분할별 주입 대상 단위의 전류 진폭(√2×평균 제거 RMS). 여러 족·분할을 비교했으니 p값은 다중 비교를 고려해 읽는다"
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
        rec.update(comparison=comparison, evidence=evidence, source=source, limitation=limitation)
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
    add("FN", "4σ 미만 진동 이상 × 조용한 운전", "고장 모양 × 운전 강도", "진동 두 센서 2σ 잡음(10행째부터, 반복 5회). 주입 기록의 전류 진폭 Q1(조용함) 대 Q4",
        (round(float(v.loc["A"].units_amp_Q1 - v.loc["A"].detected_amp_Q1), 1), int(v.loc["A"].units_amp_Q1)),
        (round(float(v.loc["B"].units_amp_Q1 - v.loc["B"].detected_amp_Q1), 1), int(v.loc["B"].units_amp_Q1)),
        1 - v.loc["A"].detected_amp_Q4 / v.loc["A"].units_amp_Q4, 1 - v.loc["B"].detected_amp_Q4 / v.loc["B"].units_amp_Q4,
        f"전체 탐지 {v.loc['A'].detect_mean:.1%}·{v.loc['B'].detect_mean:.1%}(4σ는 100%). 탐지와 전류 진폭 Spearman +{v.loc['A'].spearman_amp:.2f}·+{v.loc['B'].spearman_amp:.2f}",
        "주입(E1식) + 사후 층화", _cite(fn_path, fn.family.eq("vib_noise")), "조용한 운전에서 진동형 약한 이상을 놓친다(가설). 2단계 격상은 더 늦다(alert_levels_injection_v2)")
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
        "주입(사후, press_selection)", _cite(SELECTION_INJECTION, (k | k6)), "A 평가 구간은 조용한 시간대라 문턱(max|z| 4.49)이 B(3.77)보다 높다")

    # FP
    ah = fi[fi.condition.eq("amp_high") & fi.value.str.contains("B 정상 학습")]
    hi = {a: ah[ah.alpha.eq(a)].iloc[0] for a in ALPHAS}
    rest = {a: tuple(int(x) for x in hi[a].note.replace("나머지 ", "").split("/")) for a in ALPHAS}
    ev5 = fi[fi.alpha.eq(.05) & fi.condition.eq("vib_sd_quartile") & fi.value.eq("Q4")].iloc[0]
    add("FP", "고부하 운전(전류 진폭 ≥ B 정상 학습 q75)", "운전 강도(부하)", "고유 정상 구간 300~599(독립 적합 5개 중 하나라도 경보), 길이 ≥17. A 열 α 1%, B 열 α 5%",
        (int(hi[.01].false_alarms), int(hi[.01].denominator)), (int(hi[.05].false_alarms), int(hi[.05].denominator)),
        rest[.01][0] / rest[.01][1], rest[.05][0] / rest[.05][1],
        f"나머지 {rest[.01][0]}/{rest[.01][1]}(α 1%, p {hi[.01].fisher_p_greater:.2g}, 표본 부족)·{rest[.05][0]}/{rest[.05][1]}(α 5%, p {hi[.05].fisher_p_greater:.1e}). "
        f"α 3% {int(hi[.03].false_alarms)}/{int(hi[.03].denominator)} 대 {rest[.03][0]}/{rest[.03][1]}. 진동 SD Q4 {int(ev5.false_alarms)}/{int(ev5.denominator)}(크기 경보 경로와 겹침)",
        "관측(사후, 같은 날 77분)", _cite(fi_path, (fi.condition.eq("amp_high") & fi.value.str.contains("B 정상 학습")) | (fi.alpha.eq(.05) & fi.condition.eq("vib_sd_quartile"))),
        "A·B 열은 분할이 아니라 α다. 부하는 신호 대리변수다. 480~539 블록 0/120")
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
        f"B ×1.0 {int(d.loc[1.0].normal_notified_segments)}, ×1.05 {int(d.loc[1.05].normal_notified_segments)}, ×1.5 {int(d.loc[1.5].normal_notified_segments)}/180. 감시 규칙은 ×1.3부터 재보정 검토(monitor_gain_v2)",
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
