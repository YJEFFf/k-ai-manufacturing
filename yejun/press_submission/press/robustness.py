"""W5 강건성·민감도·절제·라벨 우회 검사 — PLAN.md §5.2·§9.

- 전처리 raw/matched/coarse × 분할 A/B × 창 {5,6,8,10,12,15,20}: 학습·보정·평가를 전부 다시 실행한다(sensitivity.csv).
- 동결 진단: matched로 적합·보정한 주 모델을 raw/coarse로 변환한 평가 입력에 그대로 적용해 입력 변화와 재적합 효과를 구분한다(quantization_frozen.csv).
- 절제(matched, w=8): 사인 제거(=maxz_3), 크기 제거(=sine_w8), 초기 max-z 보완 제거, 지수 꼬리 제거(capped), 행 보정(모델 비교표의 rows 단위)(ablation.csv).
- 라벨 우회: 날짜 이동, 불필요한 열 추가, 6자리 재직렬화(스트레스, 변화량 보고), 미래 행 추가(label_bypass.csv).
성능이 낮아도 그대로 저장한다. 어떤 결과도 기대 정답으로 두지 않는다.
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd

from . import data as D
from .calibrate import ALPHAS, segment_max, thresholds_for
from .evaluate import evaluate_models
from .scores import MAIN_W, MainModel, Scorer

WINS = (5, 6, 8, 10, 12, 15, 20)


def _prepare(normal, abnormal, seg_n, seg_a, sid, pre):
    sp = D.split_normal(normal, seg_n, sid)
    q = {k: D.quantize(sp[k], pre) for k in ("train", "cal", "test")}
    segs = {k: D.segments(q[k]) for k in ("train", "cal", "test")}
    segs["abn"] = seg_a
    frames = {"cal": q["cal"], "test": q["test"], "abn": D.quantize(abnormal, pre)}
    return sp["name"], q["train"], segs, frames


def _fit_score(vendor, train, segs, frames, wins, tail="exp"):
    scorer = Scorer(train, segs["train"], vendor, wins=wins, baselines=False, tail=tail)
    per = {k: scorer.score(frames[k], segs[k]) for k in ("cal", "test", "abn")}
    model_scores = {m: {k: per[k][0][m] for k in per} for m in per["cal"][0]}
    comps = {k: per[k][1] for k in per}
    bounds = {f"combined_w{w}": float(scorer.tail_sine[w](np.array([1.0]))[0]) for w in wins}
    return scorer, model_scores, comps, bounds


def sensitivity(vendor, normal, abnormal, seg_n, seg_a, preprocesses=("raw", "matched", "coarse"), wins=WINS, log=print):
    """전처리 × 분할 × 창 전수 재실행. 구간 단위(conformal·cutoff)만 집계한다."""
    out, params = [], []
    for pre in preprocesses:
        for sid in D.SPLITS:
            name, train, segs, frames = _prepare(normal, abnormal, seg_n, seg_a, sid, pre)
            scorer, ms, _, bounds = _fit_score(vendor, train, segs, frames, wins)
            keep = {m: v for m, v in ms.items() if m.startswith(("combined_w", "sine_w", "maxz_3"))}
            mt, _ = evaluate_models(vendor, name, pre, keep, frames, segs, bounds, units=("recording_segments",))
            mt["split_id"] = sid
            mt["w"] = mt.model.str.extract(r"_w(\d+)$").astype(float)
            out.append(mt)
            for w in wins:
                st = scorer.tail_sine[w].state()
                params.append(dict(preprocess=pre, split=name, component=f"sine_w{w}", n=st["n"], u=st["u"], beta=st["beta"],
                                   fit_ok=st["ok"], g_at_1=bounds[f"combined_w{w}"],
                                   cal_seg_max_max=float(np.max(segment_max(ms[f"combined_w{w}"]["cal"], segs["cal"])))))
            st = scorer.tail_z3.state()
            params.append(dict(preprocess=pre, split=name, component="maxz3", n=st["n"], u=st["u"], beta=st["beta"], fit_ok=st["ok"],
                               g_at_1=np.nan, cal_seg_max_max=float(np.max(segment_max(ms["maxz_3"]["cal"], segs["cal"])))))
            log(f"  sensitivity {pre} {sid} done")
    return pd.concat(out, ignore_index=True), pd.DataFrame(params)


def frozen_quantization(vendor, normal, abnormal, seg_n, seg_a, main_pre="matched", others=("raw", "coarse")):
    """matched로 적합·보정한 주 모델과 문턱을 동결하고 평가 입력만 다른 변환으로 바꾼다."""
    rows = []
    for sid in D.SPLITS:
        name, train, segs, frames = _prepare(normal, abnormal, seg_n, seg_a, sid, main_pre)
        scorer, ms, _, bounds = _fit_score(vendor, train, segs, frames, (MAIN_W,))
        key = f"combined_w{MAIN_W}"
        cal_seg_max = segment_max(ms[key]["cal"], segs["cal"])
        override = {(key, "recording_segments"): thresholds_for(cal_seg_max, "recording_segments")}
        for pre in (main_pre,) + tuple(others):
            _, _, _, fr2 = _prepare(normal, abnormal, seg_n, seg_a, sid, pre)
            f2 = {"cal": frames["cal"], "test": fr2["test"], "abn": fr2["abn"]}   # 보정은 동결(matched), 평가만 변환
            sc = {key: {"cal": ms[key]["cal"], "test": scorer.score(f2["test"], segs["test"])[0][key],
                        "abn": scorer.score(f2["abn"], segs["abn"])[0][key]}}
            mt, _ = evaluate_models(vendor, name, f"fit_{main_pre}_eval_{pre}", sc, f2, segs, {key: bounds[key]}, override,
                                    units=("recording_segments",))
            mt["split_id"], mt["eval_preprocess"], mt["fit_preprocess"] = sid, pre, main_pre
            rows.append(mt)
    return pd.concat(rows, ignore_index=True)


def ablation(vendor, normal, abnormal, seg_n, seg_a, pre="matched"):
    """matched, w=8 절제. 각 절제는 그 변경 외 조건을 고정한다."""
    rows = []
    for sid in D.SPLITS:
        name, train, segs, frames = _prepare(normal, abnormal, seg_n, seg_a, sid, pre)
        sc_exp, ms, comps, bounds = _fit_score(vendor, train, segs, frames, (MAIN_W,), tail="exp")
        sc_cap, ms_cap, _, bounds_cap = _fit_score(vendor, train, segs, frames, (MAIN_W,), tail="capped")
        key = f"combined_w{MAIN_W}"
        no_fill = {k: np.where(np.isfinite(comps[k][f"g_sine_{MAIN_W}"]), np.fmax(comps[k]["g_maxz3"], comps[k][f"g_sine_{MAIN_W}"]), np.nan) for k in comps}
        variants = {
            "full": (ms[key], bounds[key]),
            "no_sine(=maxz_3)": (ms["maxz_3"], None),
            "no_magnitude(=sine_w8)": (ms[f"sine_w{MAIN_W}"], None),
            "no_initial_maxz_fill": (no_fill, bounds[key]),
            "capped_tail(legacy_ecdf)": (ms_cap[key], bounds_cap[key]),
        }
        model_scores = {v: s for v, (s, _) in variants.items()}
        cb = {v: b for v, (_, b) in variants.items() if b is not None}
        mt, _ = evaluate_models(vendor, name, pre, model_scores, frames, segs, cb, units=("recording_segments",))
        mt = mt.rename(columns={"model": "ablation"})
        mt["split_id"] = sid
        rows.append(mt)
    return pd.concat(rows, ignore_index=True)


def label_bypass(artifact_state: dict, stream: pd.DataFrame, split_name: str) -> pd.DataFrame:
    """주 모델 artifact로 라벨 우회·미래값 불변·재직렬화 스트레스를 검사한다. 입력은 평가 스트림(TimeStamp+센서 3열)."""
    mm = MainModel(artifact_state)
    thr = next(t["threshold"] for t in artifact_state["calibration"]["thresholds"] if t["criterion"] == "conformal" and t["alpha"] == 0.01)
    seg = D.segments(stream)
    base = mm.score(stream, seg)["combined"]
    base_alarm = np.isfinite(base) & (base > thr)

    def compare(check, frame, expect_equal, n_keep=None):
        s2 = mm.score(frame, D.segments(frame))["combined"]
        if n_keep is not None:
            s2 = s2[:n_keep]
        a2 = np.isfinite(s2) & (s2 > thr)
        diff = np.nanmax(np.abs(s2 - base)) if np.isfinite(s2).any() else np.nan
        seg_changed = int((pd.Series(a2).groupby(seg).max() != pd.Series(base_alarm).groupby(seg).max()).sum())
        equal = bool(np.allclose(s2, base, equal_nan=True))
        return dict(split=split_name, check=check, expect_equal=expect_equal, scores_equal=equal,
                    max_abs_score_diff=float(diff), alarm_rows_changed=int((a2 != base_alarm).sum()),
                    alarm_segments_changed=seg_changed, passed=(equal if expect_equal else True))

    rows = []
    shifted = stream.copy()
    shifted[D.TIME] = (pd.to_datetime(shifted[D.TIME]) + pd.Timedelta(days=5)).dt.strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3]
    rows.append(compare("timestamps_shifted_5_days", shifted, True))
    extra = stream.copy()
    extra.insert(0, "Unnamed: 0", np.arange(len(extra)))
    extra["Equipment_state"] = 1
    extra["random_column"] = np.random.default_rng(0).standard_normal(len(extra))
    rows.append(compare("extra_columns_index_label_random", extra, True))
    buf = io.StringIO()
    stream.to_csv(buf, index=False, float_format="%.6f")
    reser = pd.read_csv(io.StringIO(buf.getvalue()))
    rows.append(compare("reserialized_6_decimals(stress)", reser, False))
    longer = pd.concat([stream, stream.tail(40)], ignore_index=True)
    rows.append(compare("future_rows_appended", longer, True, n_keep=len(stream)))
    return pd.DataFrame(rows)


def run(out, vendor, normal, abnormal, seg_n, seg_a, artifacts: dict, streams: dict, log=print):
    """artifacts[sid] = state dict, streams[sid] = 평가 스트림. 산출 CSV를 out에 쓰고 요약 dict를 돌려준다."""
    sens, params = sensitivity(vendor, normal, abnormal, seg_n, seg_a, log=log)
    sens.to_csv(out / "sensitivity.csv", index=False)
    params.to_csv(out / "sensitivity_params.csv", index=False)
    frozen = frozen_quantization(vendor, normal, abnormal, seg_n, seg_a)
    frozen.to_csv(out / "quantization_frozen.csv", index=False)
    abl = ablation(vendor, normal, abnormal, seg_n, seg_a)
    abl.to_csv(out / "ablation.csv", index=False)
    lb = pd.concat([label_bypass(artifacts[sid], streams[sid], D.SPLITS[sid][0]) for sid in artifacts], ignore_index=True)
    lb.to_csv(out / "label_bypass.csv", index=False)
    main = sens[(sens.criterion == "conformal") & (sens.alpha == 0.01) & sens.model.str.startswith("combined_w")]
    summary = {
        "label_bypass_all_passed": bool(lb.passed.all()),
        "reserialization_alarm_segments_changed": int(lb[lb.check.str.startswith("reserialized")].alarm_segments_changed.sum()),
        "dead_component_cases": int((~sens.waveform_only_alarm_possible.fillna(True).astype(bool)).sum()) if "waveform_only_alarm_possible" in sens else None,
        "tail_fit_failures": int((~params.fit_ok).sum()),
        "combined_conformal_1pct_abnormal_detected_range": [int(main.abnormal_notified_segments.min()), int(main.abnormal_notified_segments.max())],
        "combined_conformal_1pct_normal_notified_range": [int(main.normal_notified_segments.min()), int(main.normal_notified_segments.max())],
    }
    return summary
