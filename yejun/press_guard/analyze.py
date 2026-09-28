"""v2 분석용 표·그림 — 통합 모델 비교, 미탐·오경보 조건, 불확실성, 업무량. 보고서 서술은 생성하지 않는다.

    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python yejun/press_guard/analyze.py

산출: 통합 비교, 입력 정밀도 스트레스(robustness), 전처리별 재적합 민감도(sensitivity), 성분 절제(ablation), 행/구간 단위 미탐·오경보 조건표,
진동×파형 2×2, 구간별 첫 경보, 불확실성, 업무량, 그림.
입력: press_guard/outputs(train.py 결과), press_guard/artifacts, press_submission/outputs(v1 패키지 실행 결과),
analysis/press_advance(후보 고정 비교). 세 실행의 입력 자료 해시가 같아야 표를 합친다.
모든 결과는 이미 본 이상 21구간을 재사용한 탐색 평가다. 위치는 기록구간 시작 기준이며 실제 고장 시각이 아니다.
"""
from pathlib import Path
import argparse
import json
import time

import numpy as np
import pandas as pd

from model import GuardModel, cases, D, BASE, HERE, ALPHAS, DECISION_TABLE, ALERT_UNIT_ROWS
from press.uncertainty import moving_block_bootstrap
from press.diagnosis import MIN_FIT_LEN, sine_fit
from press.scores import Scorer, ExpTail, window_index
from press.evaluate import evaluate_models
from contracts import training_errors, training_fingerprint, ANALYSIS_FILES, SOURCES, check_files, INSIGHT_FILES
import runtime
E1_SUMMARY = HERE.parent / "analysis" / "press_supplement" / "e1_summary.csv"   # 라벨 없는 확률 환산의 주입 탐지율(E1)
DAYSHIFT = HERE.parent / "analysis" / "press_dayshift" / "v2_current_scale.csv"   # 전류 배율 스트레스(오경보 조건 요약)

ADVANCE = HERE.parent / "analysis" / "press_advance"
V1 = BASE / "outputs"
FINAL, BASELINE = "early6_ar2", "baseline_w8"
POS_BINS = [(0, 0, "0"), (1, 1, "1"), (2, 4, "2–4"), (5, 6, "5–6"), (7, 9, "7–9"), (10, 10**9, "≥10")]
LEN_BINS = [(1, 4, "≤4"), (5, 9, "5–9"), (10, 29, "10–29"), (30, 10**9, "≥30")]
COLOR_V1, COLOR_V2 = "#b07510", "#178cc2"   # dataviz 검증기 통과(색각 이상 분리·대비)
V1_ALARM = {.01: "alarm", .03: "alarm_conformal_0.03", .05: "alarm_conformal_0.05"}
# 모델별 입력 조건(비교 공정성: v2와 입력이 다른 기준모델을 구분한다. 같은 특징 대안은 analysis/press_selection)
INPUT_FEATURES = {
    "early6_ar2": "v2 세 성분: 센서 크기 max|z| + 전류 사인 1−R²(6→8행 창) + AR(2) 전류 예측 오차",
    "early_w6_to_w8": "센서 크기 + 전류 사인 1−R²(6→8행 창)", "maxz_ar2": "센서 크기 + AR(2) 전류 예측 오차",
    "combined_w8": "센서 크기 + 전류 사인 1−R²(8행 창)(v1)", "sine_w8": "전류 사인 1−R²(8행 창)", "ar2_only": "AR(2) 전류 예측 오차",
    "maxz_3": "센서 3개 z의 max|z|(한 행)", "maxz_vib2": "진동 2개 z의 max|z|(한 행)",
    "isolation_forest": "센서 3개 z(한 행)", "5nn_distance": "센서 3개 z(한 행)",
    "mlp_ae_w5": "센서 3개 z 5행 창", "trailing_rms5": "센서 3개 z 5행 창 RMS",
    "lstm20": "센서 3개 20행 창(LSTM-AE)", "lstm20_plus_maxz": "센서 3개 20행 창(LSTM-AE) + max|z|",
}


def _bin(v, bins):
    return next(lab for lo, hi, lab in bins if lo <= v <= hi)


def input_hashes_agree(v2_manifest):
    v1 = json.loads((V1 / "manifest.json").read_text(encoding="utf-8"))["inputs"]["files"]
    adv = json.loads((ADVANCE / "manifest.json").read_text(encoding="utf-8"))["inputs"]["files"]
    v1h, advh = {k: v["sha256"] for k, v in v1.items()}, {k: v["sha256"] for k, v in adv.items()}
    return v1h == advh == v2_manifest["input_hashes"], dict(v1=v1h, advance=advh, v2=v2_manifest["input_hashes"])


# ---------- 통합 모델 비교 ----------
def model_comparison(out):
    v1 = pd.read_csv(V1 / "model_comparison_all.csv"); v1["source"] = "v1_package"
    adv = pd.read_csv(ADVANCE / "metrics.csv"); adv = adv[adv.input_variant.eq("matched")].drop(columns=["input_variant"]); adv["source"] = "v2_candidates"
    adv = adv[~adv.model.eq(BASELINE)]   # baseline_w8은 v1 combined_w8과 같은 점수 함수(수치 동일)라 중복 제외
    both = pd.concat([v1, adv], ignore_index=True, sort=False)
    both["input_features"] = both.model.map(INPUT_FEATURES).fillna("")
    both["is_final_model"] = both.model.eq(FINAL)
    both["is_main_model"] = both.model.eq("combined_w8")
    both.to_csv(out / "model_comparison_v2.csv", index=False)
    main = both[both.calibration_unit.eq("recording_segments") & both.criterion.eq("conformal") & both.alpha.eq(.01)]
    cols = ["split_id", "model", "input_features", "source", "abnormal_notified_segments", "normal_notified_segments", "normal_segments", "fn", "fp", "f1_all_rows", "abnormal_row_coverage", "delay_median_s", "delay_max_s"]
    lines = ["# 통합 모델 비교 — 구간 conformal α=1%, matched (분석용 표)", "",
             "v1 패키지 실행(기준모델·LSTM 포함)과 v2 후보 고정 비교를 같은 입력·분할·보정 구간에서 합쳤다. 이미 본 이상 21구간 기준의 탐색 평가다.", "",
             "모델마다 입력이 다르다(입력 조건 열). v2와 같은 세 성분을 넣은 대안(5NN·합·Fisher 등)은 analysis/press_selection에 있다.", "",
             "| 분할 | 모델 | 입력 조건 | 출처 | 이상 탐지 구간 | 정상 알림 구간 | 미탐 행 | 오경보 행 | F1(전체 행) | 판정 가능 | 첫 경보 중앙값/최대(초) |", "|---|---|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for r in main.sort_values(["split_id", "f1_all_rows"], ascending=[True, False])[cols].itertuples(index=False):
        lines.append(f"| {r.split_id} | {'**' + r.model + '**' if r.model == FINAL else r.model} | {r.input_features} | {r.source} | {int(r.abnormal_notified_segments)}/21 | {int(r.normal_notified_segments)}/{int(r.normal_segments)} | {int(r.fn)} | {int(r.fp)} | {r.f1_all_rows:.4f} | {r.abnormal_row_coverage:.2f} | {r.delay_median_s:.1f}/{r.delay_max_s:.1f} |")
    (out / "model_comparison_v2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return both


def source_hashes():
    """v1 행별 예측·기준모델 표의 실행 출처와 후보 코드를 확인한다."""
    v1=json.loads((V1/"manifest.json").read_text(encoding="utf-8"))
    expected=json.loads((V1/"expected"/"manifest.json").read_text(encoding="utf-8"))
    bad=check_files(V1,v1.get("outputs"),("predictions_A.csv","predictions_B.csv"))
    # v1 비교표는 v1 verify와 같은 허용오차(LSTM 1e-3 등)로 동결값과 대조한다. 바이트 일치를 요구하면 LSTM을 다시 학습한
    # 다른 기기에서 원본부터 다시 만드는 경로가 끊긴다(루브릭 사이클2 평가관 06 R9).
    import importlib.util
    spec=importlib.util.spec_from_file_location("press_v1_verify",BASE/"verify.py")
    v1verify=importlib.util.module_from_spec(spec); spec.loader.exec_module(v1verify)
    table=V1/"model_comparison_all.csv"
    if not table.is_file():
        bad.append("model_comparison_all.csv: 없음")
    else:
        cmp=v1verify.compare_csv(table,V1/"expected"/"model_comparison_all.csv")
        if not cmp["ok"]: bad.append(f"model_comparison_all.csv: v1 동결값과 허용오차 밖({cmp['reason']})")
    if {k:v["sha256"] for k,v in expected["inputs"]["files"].items()}!=D.EXPECTED_SHA256:
        bad.append("v1 기준모델 표 입력 해시 불일치")
    adv=json.loads((ADVANCE/"manifest.json").read_text(encoding="utf-8"))
    if adv.get("script_sha256")!=D.sha256_file(ADVANCE/"run_experiment.py"):
        bad.append("후보 탐색 코드가 실행 당시와 다름")
    if bad: raise ValueError(f"분석 원본 무결성 오류: {bad}. v1 선행 단계를 먼저 실행한다: "
                             "python press_submission/run_all.py --steps 2 --no-baselines (또는 한 명령 재현: python press_guard/reproduce.py)")
    return {n:D.sha256_file(HERE.parent/n) for n in SOURCES}


# ---------- 입력 정밀도 강건성 (v1 3단계 형식) ----------
def robustness(out):
    """matched로 적합·보정한 상태를 고정하고 평가 입력만 raw/coarse로 바꾼 결과(press_advance). 재학습·재보정 없음."""
    m = pd.read_csv(ADVANCE / "metrics.csv")
    r = m[m.model.isin([FINAL, BASELINE]) & m.calibration_unit.eq("recording_segments")].copy()
    r["version"] = np.where(r.model.eq(FINAL), "v2", "v1")
    cols = ["split_id", "split", "version", "model", "input_variant", "criterion", "alpha", "normal_notified_segments", "normal_segments", "abnormal_notified_segments",
            "fn", "fp", "f1_all_rows", "abnormal_row_coverage", "delay_median_s", "delay_max_s"]
    r = r[cols].sort_values(["split_id", "input_variant", "criterion", "alpha", "version"]).reset_index(drop=True)
    r.to_csv(out / "robustness_v2.csv", index=False)
    return r


# ---------- 행별 예측 로드 ----------
def load_v1(sid):
    p = pd.read_csv(V1 / f"predictions_{sid}.csv")
    p = p.rename(columns={"position_in_record": "position"})
    pn, pa = p[p.source.eq("normal_test")].reset_index(drop=True), p[p.source.eq("abnormal")].reset_index(drop=True)
    pa["record_id"] -= pa.record_id.min()   # v1 예측 파일은 정상 평가 뒤에 이어 붙인 번호라 이상 구간을 0부터 다시 센다(v2와 같은 기준)
    return pn, pa


def v2_predictions(model, normal_test, abnormal):
    out = {}
    for alpha in ALPHAS:
        out[alpha] = (model.predict(normal_test, alpha), model.predict(abnormal, alpha))
    return out


def _with_length(p):
    p = p.copy()
    p["record_length"] = p.groupby("record_id").position.transform("size")
    return p


# ---------- 미탐·오경보 조건 ----------
AMP_MIN_LEN = 17
QUARTILE_LABELS = ("Q1(<q25)", "Q2", "Q3", "Q4(≥q75)")


def segment_feature_table(frame, seg, mean, scale):
    """구간 특징(사후 기술 통계): 길이, 진동 산포, 전류 진폭 대리 지표(길이≥17만 신뢰), 사인 R²(길이≥10), 진동 두 센서 max|z|."""
    v0, v1_, cur = (frame[c].to_numpy(float) for c in D.SENSORS)
    zvib = np.abs((frame[D.SENSORS[:2]].to_numpy(float) - mean[:2]) / scale[:2]).max(1)
    rows = []
    for s_ in np.unique(seg):
        idx = np.flatnonzero(seg == s_); c = cur[idx]
        rows.append(dict(record_id=int(s_), length=int(len(idx)),
                         vib_std=float(np.sqrt(v0[idx].var(ddof=1) + v1_[idx].var(ddof=1))) if len(idx) > 1 else np.nan,
                         amp_proxy=float(np.sqrt(2 * np.mean((c - c.mean()) ** 2))), amp_reliable=bool(len(idx) >= AMP_MIN_LEN),
                         r2_segment=float(sine_fit(c)[1]) if len(idx) >= MIN_FIT_LEN else np.nan, vibz_max=float(zvib[idx].max())))
    return pd.DataFrame(rows)


def condition_bounds(train_feats):
    """정상 학습 구간 기준의 공통 경계(v1 analysis와 같은 정의). 정상·이상 평가에 같은 경계를 적용한다."""
    return dict(vib=tuple(train_feats.vib_std.dropna().quantile([.25, .5, .75]).to_numpy()),
                amp=tuple(train_feats[train_feats.amp_reliable].amp_proxy.quantile([.25, .5, .75]).to_numpy()),
                vib_high=float(train_feats.vibz_max.quantile(.95)), r2_low=float(train_feats.r2_segment.dropna().quantile(.05)))


def _quartile(values, q):
    v = np.asarray(values, float)
    lab = np.full(len(v), "NA", dtype=object)
    ok = np.isfinite(v)
    lab[ok & (v < q[0])] = QUARTILE_LABELS[0]; lab[ok & (v >= q[0]) & (v < q[1])] = QUARTILE_LABELS[1]
    lab[ok & (v >= q[1]) & (v < q[2])] = QUARTILE_LABELS[2]; lab[ok & (v >= q[2])] = QUARTILE_LABELS[3]
    return lab


def _wave(feats, bounds):
    return np.where(feats.r2_segment.isna(), "unfittable(<10)", np.where(feats.r2_segment < bounds["r2_low"], "broken", "sine-like"))


def error_conditions(sid, v1_pair, v2_pairs, feats, bounds):
    """행 단위 조건표. 사분위 경계는 정상 학습 구간 기준(열에 저장). 진폭 조건에는 신뢰 제한(길이<17) 행 수를 함께 적는다.
    *_pos_ge2 열은 같은 조건을 위치 2 이상 행으로만 다시 센 값이다. 위치 0·1에는 크기 성분만 있어 미탐이 몰리므로(초반 창),
    길이·진폭·진동 조건의 미탐률을 비교할 때는 이 열을 본다(루브릭 사이클2 평가관 03 E2)."""
    rows = []
    def add(model, alpha, subset, kind, cond, value, mask, alarm, extra=None, pos=None):
        wrong = (alarm == 0) if kind == "fn" else (alarm == 1)
        n = int(mask.sum()); err = int(wrong[mask].sum())
        row = dict(split_id=sid, model=model, alpha=alpha, subset=subset, error=kind, condition=cond, value=value,
                   rows=n, error_rows=err, error_rate=err / n if n else np.nan, **(extra or {}))
        if pos is not None:
            m2 = mask & (pos >= 2); n2 = int(m2.sum()); e2 = int(wrong[m2].sum())
            row.update(rows_pos_ge2=n2, error_rows_pos_ge2=e2, error_rate_pos_ge2=e2 / n2 if n2 else np.nan)
        rows.append(row)
    def conditions(model, alpha, pn, pa):
        for subset, kind, p in (("abnormal", "fn", pa), ("normal", "fp", pn)):
            p = _with_length(p)
            alarm = p.alarm.to_numpy(int)
            pos = p.position.to_numpy(); ln = p.record_length.to_numpy()
            for lo, hi, lab in POS_BINS:
                add(model, alpha, subset, kind, "pos_bin", lab, (pos >= lo) & (pos <= hi), alarm, pos=pos)
            for lo, hi, lab in LEN_BINS:
                add(model, alpha, subset, kind, "len_bin", lab, (ln >= lo) & (ln <= hi), alarm, pos=pos)
            f = feats[subset].set_index("record_id")
            reliable = p.record_id.map(f.amp_reliable).to_numpy(bool)
            for col, name, q in (("vib_std", "vib_quartile", bounds["vib"]), ("amp_proxy", "amp_quartile", bounds["amp"])):
                lab = _quartile(p.record_id.map(f[col]).to_numpy(float), q)
                for value in QUARTILE_LABELS + ("NA",):
                    m = lab == value
                    if not m.any() and value == "NA":
                        continue
                    extra = dict(q25=q[0], q50=q[1], q75=q[2], boundary_source="normal_train_segments")
                    if name == "amp_quartile":
                        extra["unreliable_amp_rows"] = int((m & ~reliable).sum())
                    add(model, alpha, subset, kind, name, value, m, alarm, extra, pos=pos)
            if model == "v2":
                comp = p[["g_magnitude", "g_waveform", "g_dynamics"]].to_numpy(float)
                strongest = np.where(np.isfinite(comp).any(axis=1), np.array(["magnitude", "waveform", "dynamics"])[np.nan_to_num(comp, nan=-np.inf).argmax(axis=1)], "none")
                for lab in ("magnitude", "waveform", "dynamics", "none"):
                    add(model, alpha, subset, kind, "strongest_component", lab, strongest == lab, alarm, pos=pos)
    conditions("v1", .01, *v1_pair)
    for alpha, (pn, pa) in v2_pairs.items():
        conditions("v2", alpha, pn, pa)
    return pd.DataFrame(rows)


def segment_conditions(sid, v1_pair, v2_pairs, feats, bounds):
    """구간 단위 조건표(PLAN §5.3의 구간 분모): 이상은 탐지/미탐 구간, 정상은 알림 구간. 진폭 조건에 신뢰 제한 구간 수."""
    rows = []
    def per(model, alpha, pn, pa):
        for subset, p in (("abnormal", pa), ("normal", pn)):
            f = feats[subset].copy()
            f["alerted"] = f.record_id.map(p.groupby("record_id").alarm.max()).fillna(0).astype(int)
            f["len_bin"] = [_bin(n, LEN_BINS) for n in f.length]
            f["vib_quartile"] = _quartile(f.vib_std, bounds["vib"]); f["amp_quartile"] = _quartile(f.amp_proxy, bounds["amp"])
            f["vib_high"] = np.where(f.vibz_max > bounds["vib_high"], "high(>q95 train)", "normal-range")
            f["wave"] = _wave(f, bounds)
            for cond in ("len_bin", "vib_quartile", "amp_quartile", "vib_high", "wave"):
                for value, g in f.groupby(cond, sort=False):
                    err = int((g.alerted == 0).sum()) if subset == "abnormal" else int(g.alerted.sum())
                    rows.append(dict(split_id=sid, model=model, alpha=alpha, subset=subset, error="missed_segments" if subset == "abnormal" else "alerted_segments",
                                     condition=cond, value=value, segments=len(g), error_segments=err, error_rate=err / len(g),
                                     unreliable_amp_segments=int((~g.amp_reliable).sum()) if cond == "amp_quartile" else None))
    per("v1", .01, *v1_pair)
    for alpha, (pn, pa) in v2_pairs.items():
        per("v2", alpha, pn, pa)
    return pd.DataFrame(rows)


def interaction_2x2(sid, v1_pair, v2_pairs, feats, bounds):
    """진동 수준(진동 두 센서 max|z| > 정상 학습 q95) × 전류 파형(사인 R² < 정상 학습 q05) 교차표. v1 analysis와 같은 정의, 경보는 각 모델의 것."""
    rows = []
    def per(model, alpha, pn, pa):
        for subset, p in (("abnormal", pa), ("normal", pn)):
            f = feats[subset].copy()
            f["alerted"] = f.record_id.map(p.groupby("record_id").alarm.max()).fillna(0).astype(int)
            f["vib_high"] = f.vibz_max > bounds["vib_high"]; f["wave"] = _wave(f, bounds)
            for (vh, wv), g in f.groupby(["vib_high", "wave"]):
                rows.append(dict(split_id=sid, model=model, alpha=alpha, subset=subset, vib_high=bool(vh), wave=wv, segments=len(g),
                                 alerted_segments=int(g.alerted.sum()), missed_segments=int((g.alerted == 0).sum()) if subset == "abnormal" else None,
                                 vib_threshold=f"segment max|z| of AI0/AI1 > q95 of normal-train ({bounds['vib_high']:.2f})",
                                 wave_threshold=f"segment R² < q05 of normal-train ({bounds['r2_low']:.3f})"))
    per("v1", .01, *v1_pair)
    for alpha, (pn, pa) in v2_pairs.items():
        per("v2", alpha, pn, pa)
    return pd.DataFrame(rows)


# ---------- 재적합 민감도·절제 (PLAN §5.2 ①을 최종 v2에 적용) ----------
def _ar2_fit(train, seg):
    x = train[D.SENSORS[2]].to_numpy(float); idx = window_index(seg, 3)
    coef = np.linalg.lstsq(np.column_stack([np.ones(len(idx)), x[idx - 1], x[idx - 2]]), x[idx], rcond=None)[0]
    return coef, ExpTail(_ar2_residual(train, seg, coef))


def _ar2_residual(frame, seg, coef):
    x = frame[D.SENSORS[2]].to_numpy(float); idx = window_index(seg, 3)
    out = np.full(len(x), np.nan); out[idx] = np.abs(x[idx] - coef[0] - coef[1] * x[idx - 1] - coef[2] * x[idx - 2])
    return out


def _v2_scores(base, ar2, frame, seg):
    comp, _ = base.components(frame, seg)
    pos, _ = D.segment_positions(seg)
    gz, s6, s8 = comp["g_maxz3"], comp["g_sine_6"], comp["g_sine_8"]
    switch = np.where(pos < 7, s6, s8)
    gd = ar2[1](_ar2_residual(frame, seg, ar2[0]))
    return dict(v2=np.fmax(np.fmax(gz, switch), gd), v1_combined_w8=np.fmax(gz, s8),
                no_magnitude=np.fmax(switch, gd), no_waveform=np.fmax(gz, gd), no_dynamics=np.fmax(gz, switch), no_early_switch=np.fmax(np.fmax(gz, s8), gd))


def refit_experiments(normal, abnormal, vendor, metrics):
    """① 전처리별로 학습·보정·평가를 다시 실행(재적합 민감도). ② matched 재적합에서 성분 절제. 결과 산식·기대값은 바꾸지 않는다."""
    sens, abl = [], []
    for sid in D.SPLITS:
        split = D.split_normal(normal, D.segments(normal), sid)
        for variant in ("raw", "matched", "coarse"):
            q = {k: D.quantize(split[k], variant) for k in ("train", "cal", "test")}; q["abn"] = D.quantize(abnormal, variant)
            segs = {k: D.segments(v) for k, v in q.items()}
            base = Scorer(q["train"], segs["train"], vendor, wins=(6, 8), baselines=False)
            ar2 = _ar2_fit(q["train"], segs["train"])
            ss = {k: _v2_scores(base, ar2, q[k], segs[k]) for k in ("cal", "test", "abn")}
            frames = dict(cal=q["cal"], test=q["test"], abn=q["abn"])
            by_model = {m: {k: ss[k][m] for k in frames} for m in ("v2", "v1_combined_w8")}
            mt, _ = evaluate_models(vendor, split["name"], variant, by_model, frames, segs, units=("recording_segments",))
            mt["split_id"], mt["fit_variant"], mt["ar2_coefficients"] = sid, variant, str(np.round(ar2[0], 6).tolist())
            sens.append(mt)
            if variant == "matched":
                by_model = {m: {k: ss[k][m] for k in frames} for m in ("v2", "no_magnitude", "no_waveform", "no_dynamics", "no_early_switch")}
                ma, _ = evaluate_models(vendor, split["name"], variant, by_model, frames, segs, units=("recording_segments",))
                ma["split_id"] = sid; abl.append(ma)
                row = ma[ma.model.eq("v2") & ma.criterion.eq("conformal") & ma.alpha.eq(.01)].iloc[0]
                got = metrics[metrics.split.eq(sid) & metrics.model.eq("guard_v2") & metrics.alpha.eq(.01)].iloc[0]
                assert (int(row.tp), int(row.fp), int(row.fn)) == (int(got.tp), int(got.fp), int(got.fn)), ("matched 재적합이 저장 모델 결과와 다름", sid)
        print(f"{sid}: 재적합 민감도·절제", flush=True)
    return pd.concat(sens, ignore_index=True), pd.concat(abl, ignore_index=True)


# ---------- 기록구간별 첫 경보 ----------
def record_table(sid, v1_pair, v2_pair):
    _, a1 = v1_pair; _, a2 = v2_pair
    rows = []
    for rid, g2 in a2.groupby("record_id", sort=True):
        g1 = a1[a1.record_id.eq(rid)]
        f1 = g1[g1.alarm.eq(1)].position.min() if g1.alarm.any() else np.nan
        f2 = g2[g2.alarm.eq(1)].position.min() if g2.alarm.any() else np.nan
        first2 = g2[g2.alarm.eq(1)].iloc[0] if g2.alarm.any() else None
        rows.append(dict(split_id=sid, record_id=int(rid), rows=len(g2), v1_first_alarm_position=f1, v2_first_alarm_position=f2,
                         v1_first_alarm_s=f1 * D.DT if np.isfinite(f1) else np.nan, v2_first_alarm_s=f2 * D.DT if np.isfinite(f2) else np.nan,
                         v1_fn_rows=int((g1.alarm == 0).sum()), v2_fn_rows=int((g2.alarm == 0).sum()),
                         v2_first_alarm_reason=first2.reason if first2 is not None else "", v2_fn_positions=" ".join(map(str, g2[g2.alarm.eq(0)].position.tolist()))))
    return pd.DataFrame(rows)


# ---------- 불확실성 ----------
def uncertainty(sid, name, v1_pair, v2_pairs, reps=2000):
    rows = []
    def both_sides(model, alpha, pn, pa):
        x = pn.groupby("record_id").alarm.max().sort_index().to_numpy(int)
        for b in (5, 10, 20):
            c = moving_block_bootstrap(x, b, reps=reps, seed=0)
            rows.append(dict(split_id=sid, split=name, model=model, alpha=alpha, side="normal", statistic="notified_segments", block_length=b, n_segments=len(x),
                             observed=int(x.sum()), boot_mean=float(c.mean()), boot_p2_5=float(np.percentile(c, 2.5)), boot_p97_5=float(np.percentile(c, 97.5)), degenerate_all_zero=bool(x.sum() == 0), reps=reps))
        g = pa.groupby("record_id", sort=True)
        for stat, x in (("fn_rows", (g.alarm.apply(lambda s: int((s == 0).sum()))).to_numpy()), ("detected_segments", g.alarm.max().to_numpy(int))):
            for b in (3, 5):
                c = moving_block_bootstrap(x, b, reps=reps, seed=0)
                rows.append(dict(split_id=sid, split=name, model=model, alpha=alpha, side="abnormal", statistic=stat, block_length=b, n_segments=len(x),
                                 observed=int(x.sum()), boot_mean=float(c.mean()), boot_p2_5=float(np.percentile(c, 2.5)), boot_p97_5=float(np.percentile(c, 97.5)), degenerate_all_zero=bool(x.sum() == 0), reps=reps))
    pn1, pa1 = v1_pair
    for alpha, col in V1_ALARM.items():
        both_sides("v1", alpha, pn1.assign(alarm=pn1[col]), pa1.assign(alarm=pa1[col]))
    for alpha, (pn, pa) in v2_pairs.items():
        both_sides("v2", alpha, pn, pa)
    return pd.DataFrame(rows)


# ---------- 업무량 ----------
def workload(sid, name, test, metrics, n_cal):
    """α별 정상 알림 업무량. α는 시간 비율이 아니라 보정·알림 단위(기록구간, 최대 50행)당 비율이다.

    경과시간 기준 교대(8시간)당 건수를 보정 격자 명목값, 관측값, 관측 비율의 이항 단측 95% 상한으로 나란히 둔다.
    같은 날 간헐 수집 밀도(경과 1시간당 기록구간 수)를 가정한 환산이며 다른 날짜·설비의 보장이 아니다.
    """
    from scipy import stats
    t = pd.to_datetime(test[D.TIME]); recorded_h = len(test) * D.DT / 3600; elapsed_h = (t.max() - t.min()).total_seconds() / 3600
    rows = []
    for r in metrics[metrics.split.eq(sid)].itertuples():
        base = dict(split_id=sid, split=name, model=r.model, alpha=r.alpha, normal_segments=r.normal_segments, first_alert_segments=r.normal_notified_segments,
                    alarm_rows=r.fp, recorded_hours=recorded_h, elapsed_hours=elapsed_h,
                    alerts_per_recorded_hour=r.normal_notified_segments / recorded_h, alerts_per_elapsed_hour=r.normal_notified_segments / elapsed_h,
                    abnormal_detected=r.abnormal_notified_segments, abnormal_fn_rows=r.fn, delay_median_s=r.delay_median_s, delay_max_s=r.delay_max_s)
        for h in (8, 16, 24):
            base[f"scenario_alerts_per_day_{h}h_recorded_rate"] = r.normal_notified_segments / recorded_h * h
        units_per_hour = r.normal_segments / elapsed_h
        grid = np.floor(r.alpha * (n_cal + 1) + 1e-9) / (n_cal + 1)   # p ≤ α가 실제로 허용하는 명목 비율
        upper = float(stats.beta.ppf(.95, r.normal_notified_segments + 1, r.normal_segments - r.normal_notified_segments))
        base.update(alert_unit_max_rows=ALERT_UNIT_ROWS, units_per_elapsed_hour=units_per_hour, alpha_grid_rate=grid,
                    nominal_alerts_per_8h_elapsed=grid * units_per_hour * 8,
                    observed_alerts_per_8h_elapsed=r.normal_notified_segments / elapsed_h * 8,
                    observed_rate_upper95=upper, upper95_alerts_per_8h_elapsed=upper * units_per_hour * 8)
        rows.append(base)
    return pd.DataFrame(rows)


# ---------- 그림 ----------
def figures(out, cond, records, v2_pairs_by_split, model_a=None, vib_q95_a=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": runtime.korean_fonts(), "axes.unicode_minus": False, "font.size": 9})
    # 1) 위치별 이상 행 재현율 v1 vs v2
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.2), sharey=True)
    for ax, sid in zip(axes, ("A", "B")):
        c = cond[cond.split_id.eq(sid) & cond.subset.eq("abnormal") & cond.condition.eq("pos_bin") & cond.alpha.eq(.01)]
        labels = [lab for _, _, lab in POS_BINS]
        x = np.arange(len(labels)); w = .38
        for k, (model, color) in enumerate((("v1", COLOR_V1), ("v2", COLOR_V2))):
            g = c[c.model.eq(model)].set_index("value").reindex(labels)
            rec = 1 - g.error_rate
            ax.bar(x + (k - .5) * w, rec, w, color=color, label=f"{model} ({'기존 결합' if model == 'v1' else '정상 동역학 결합'})", linewidth=0)
            for xi, v, n in zip(x + (k - .5) * w, rec, g.rows):
                ax.text(xi, v + .02, f"{v:.2f}\n(n={int(n)})", ha="center", va="bottom", fontsize=6.5, color="#334")
        ax.set_xticks(x); ax.set_xticklabels(labels); ax.set_ylim(0, 1.18); ax.set_title(f"정상 기준 {sid} · 이상 600행", fontsize=9)
        ax.set_xlabel("기록구간 내 위치(관측 번호, 0.1초 간격)"); ax.spines[["top", "right"]].set_visible(False); ax.grid(axis="y", color="#eef1f2")
    axes[0].set_ylabel("행 재현율(경보 비율)"); axes[0].legend(frameon=False, fontsize=8, loc="lower right")
    fig.suptitle("위치별 이상 행 재현율 — conformal α=1%, matched (이미 본 이상 자료의 탐색 평가)", fontsize=9)
    fig.tight_layout(); fig.savefig(out / "fig_recall_by_position_v2.png", dpi=150); plt.close(fig)
    # 2) 기록구간별 첫 경보 위치 v1 vs v2
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.2), sharey=True)
    for ax, sid in zip(axes, ("A", "B")):
        r = records[records.split_id.eq(sid)].sort_values("record_id")
        y = np.arange(len(r))
        ax.hlines(y, r.v2_first_alarm_s, r.v1_first_alarm_s, color="#c9d3d6", linewidth=2)
        ax.scatter(r.v1_first_alarm_s, y, color=COLOR_V1, s=22, label="v1 첫 경보", zorder=3)
        ax.scatter(r.v2_first_alarm_s, y, color=COLOR_V2, s=22, label="v2 첫 경보", zorder=4, marker="D")
        ax.set_yticks(y); ax.set_yticklabels([f"구간 {int(i)}" for i in r.record_id], fontsize=6.5)
        ax.set_xlabel("기록 시작 후 첫 경보(초)"); ax.set_title(f"정상 기준 {sid}", fontsize=9); ax.set_xlim(-.05, .95)
        ax.spines[["top", "right"]].set_visible(False); ax.grid(axis="x", color="#eef1f2")
    axes[0].legend(frameon=False, fontsize=8, loc="lower right")
    fig.suptitle("이상 기록구간 21개의 첫 경보 시점 — 기록 시작 기준(실제 고장 시각 아님)", fontsize=9)
    fig.tight_layout(); fig.savefig(out / "fig_first_alarm_v2.png", dpi=150); plt.close(fig)
    # 3) 미탐이 남는 구간 예시: v2 미탐 행이 가장 많은 구간(A)의 전류·성분 점수
    pn, pa = v2_pairs_by_split["A"][.01]
    worst = pa.groupby("record_id").alarm.apply(lambda s: int((s == 0).sum())).idxmax()
    g = pa[pa.record_id.eq(worst)].reset_index(drop=True)
    fig, axes = plt.subplots(2, 1, figsize=(8, 4.4), sharex=True)
    t = g.position * D.DT
    axes[0].plot(t, g.AI2_Current if "AI2_Current" in g else g.magnitude, color="#3b4a50", linewidth=1.6)
    axes[0].set_ylabel("전류(원값)" if "AI2_Current" in g else "센서 크기 max|z|")
    for key, name, color, ls in (("g_dynamics", "전류 예측 오차", "#6d55c9", "-"), ("g_waveform", "전류 파형", "#178cc2", "--"), ("g_magnitude", "센서 크기", "#b07510", ":")):
        axes[1].plot(t, g[key], color=color, linewidth=1.8, linestyle=ls, label=name)
    thr = pn.attrs.get("threshold")
    if thr is not None:
        axes[1].axhline(thr, color="#b3412e", linewidth=1, linestyle="--"); axes[1].text(t.iloc[-1], thr, f" 경보 문턱 {thr:.2f}", color="#b3412e", va="bottom", ha="right", fontsize=7)
    miss = g[g.alarm.eq(0)]
    axes[1].scatter(miss.position * D.DT, np.zeros(len(miss)), marker="x", color="#b3412e", s=30, label="미탐 행", zorder=5)
    axes[1].legend(frameon=False, fontsize=7.5, ncol=4); axes[1].set_xlabel("기록 시작 후 시간(초)"); axes[1].set_ylabel("정상 기준 대비 편차")
    for ax in axes: ax.spines[["top", "right"]].set_visible(False); ax.grid(color="#eef1f2")
    vib_note = ""
    if model_a is not None and vib_q95_a is not None and "AI0_Vibration" in g:
        vz = float(np.abs((g[list(D.SENSORS[:2])].to_numpy(float) - model_a.mean[:2]) / model_a.scale[:2]).max())
        vib_note = (f" · 진동 정상 범위 구간(진동 max|z| {vz:.2f} ≤ 정상 학습 q95 {vib_q95_a:.2f})" if vz <= vib_q95_a
                    else f" · 진동 높은 구간(진동 max|z| {vz:.2f} > q95 {vib_q95_a:.2f})")
    fig.suptitle(f"v2 미탐이 가장 많은 이상 구간(A, 구간 {int(worst)}, {len(g)}관측): 위치 0·1은 센서 크기 성분만 존재{vib_note}", fontsize=8.5)
    fig.tight_layout(); fig.savefig(out / "fig_missed_example_v2.png", dpi=150); plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=HERE / "outputs")
    ap.add_argument("--artifacts", type=Path, default=HERE / "artifacts")
    ap.add_argument("--reps", type=int, default=2000)
    args = ap.parse_args()
    runtime.setup()
    start = time.monotonic()
    manifest = json.loads((args.out / "manifest.json").read_text(encoding="utf-8"))
    bad=training_errors(manifest,args.out,args.artifacts)
    if bad: raise SystemExit(f"학습 실행 무결성 오류: {bad}")
    sources=source_hashes()
    agree, hashes = input_hashes_agree(manifest)
    if not agree:
        raise SystemExit(f"입력 해시 불일치: {hashes}")
    normal, abnormal, _ = D.load(args.root) if args.root else D.load()
    vendor = D.load_vendor()
    metrics = pd.read_csv(args.out / "metrics.csv")
    comparison = model_comparison(args.out)
    robust = robustness(args.out)
    sens, abl = refit_experiments(normal, abnormal, vendor, metrics)
    sens.to_csv(args.out / "sensitivity_v2.csv", index=False); abl.to_csv(args.out / "ablation_v2.csv", index=False)
    cond, segc, inter, recs, unc, work, v2_by_split, bounds_used = [], [], [], [], [], [], {}, {}
    from serve import score_threshold
    for sid in D.SPLITS:
        model = GuardModel.load(args.artifacts / f"guard_{sid}.json")
        split = D.split_normal(normal, D.segments(normal), sid)
        v1_pair = load_v1(sid)
        pairs = v2_predictions(model, split["test"], abnormal)
        for alpha, (pn, pa) in pairs.items():
            for p in (pn, pa):
                for c in D.SENSORS:
                    p[c] = pd.to_numeric((split["test"] if p is pn else abnormal)[c], errors="coerce").to_numpy()
            pn.attrs["threshold"] = score_threshold(model.cal, alpha)
        v2_by_split[sid] = pairs
        q = {k: D.quantize(D.inputs_only(f), "matched") for k, f in (("train", split["train"]), ("test", split["test"]), ("abn", abnormal))}
        feats = {"normal": segment_feature_table(q["test"], D.segments(q["test"]), model.mean, model.scale), "abnormal": segment_feature_table(q["abn"], D.segments(q["abn"]), model.mean, model.scale)}
        bounds = condition_bounds(segment_feature_table(q["train"], D.segments(q["train"]), model.mean, model.scale)); bounds_used[sid] = bounds
        cond.append(error_conditions(sid, v1_pair, pairs, feats, bounds))
        segc.append(segment_conditions(sid, v1_pair, pairs, feats, bounds))
        inter.append(interaction_2x2(sid, v1_pair, pairs, feats, bounds))
        recs.append(record_table(sid, v1_pair, pairs[.01]))
        unc.append(uncertainty(sid, split["name"], v1_pair, pairs, reps=args.reps))
        work.append(workload(sid, split["name"], split["test"], metrics, len(model.cal)))
        print(f"{sid}: 조건·불확실성·업무량 집계", flush=True)
    cond, segc, inter, recs, unc, work = (pd.concat(x, ignore_index=True) for x in (cond, segc, inter, recs, unc, work))
    # 루브릭 사이클2 보강: 이상 확률 층 평가, 2단계 경보, 업무량 사후 상한, 대기열 순위, 센서 중요도·상호작용·오경보 사건
    import insights
    models = {sid: GuardModel.load(args.artifacts / f"guard_{sid}.json") for sid in D.SPLITS}
    work = insights.workload_extras(work, models)
    extra = {}
    extra["probability_eval_v2.csv"], extra["probability_reliability_v2.csv"], extra["probability_conversion_v2.csv"] = insights.probability_evaluation(normal, abnormal, models)
    rolling = insights.rolling_models(normal)
    extra["alert_levels_v2.csv"] = insights.alert_level_evaluation(normal, abnormal, models, rolling)
    extra["alert_levels_injection_v2.csv"] = insights.alert_level_injection(normal, models)
    extra["alert_budget_design_v2.csv"] = insights.alert_budget_design(float(work[work.model.eq("guard_v2")].units_per_elapsed_hour.mean()))
    extra["queue_mixed_ranks_v2.csv"], extra["queue_injection_ranks_v2.csv"], extra["queue_key_selection_v2.csv"] = insights.queue_rankings(normal, abnormal, models)
    extra["sensor_importance_v2.csv"] = insights.sensor_importance(normal, abnormal, vendor, metrics, models)
    extra["position_vibration_misses_v2.csv"] = insights.position_vibration_misses(normal, abnormal, models)
    fa_records = {sid: sorted(v2_by_split[sid][.01][0].query("alarm == 1").record_id.unique().tolist()) for sid in D.SPLITS}
    extra["coupling_fit_v2.csv"], extra["coupling_records_v2.csv"] = insights.coupling(normal, abnormal, models, fa_records)
    extra["fp_events_v2.csv"] = insights.false_alarm_events(normal, abnormal, models, rolling)
    extra["quality_windows_v2.csv"] = insights.quality_windows(normal, abnormal, models)
    g2 = work[work.model.eq("guard_v2")]
    observed = {(r.split_id, r.alpha): (int(r.first_alert_segments), int(r.normal_segments)) for r in g2.itertuples()}
    extra["label_free_alert_probability_v2.csv"] = insights.label_free_alert_probability(models, E1_SUMMARY, observed)
    extra["monitor_gain_v2.csv"] = insights.monitor_gain(normal, models)
    extra["expected_effect_v2.csv"] = insights.expected_effect(extra["alert_levels_v2.csv"], extra["alert_levels_injection_v2.csv"])
    extra["fp_intensity_v2.csv"] = insights.fp_intensity(normal, models, rolling)
    extra["fn_intensity_v2.csv"] = insights.fn_intensity(normal, models)
    extra["incident_summary_v2.csv"] = insights.incident_summary(normal, abnormal, models)
    extra["near_miss_v2.csv"], extra["near_miss_corr_v2.csv"] = insights.near_miss(normal, models)
    extra["error_conditions_stats_v2.csv"] = insights.condition_stats(segc)
    for name, table in extra.items():
        table.to_csv(args.out / name, index=False)
    # 위 표들과 E1·전류 배율 모의에서 FN·FP 집중 조건을 모은 요약(파일:행 인용)
    insights.error_condition_summary(args.out, E1_SUMMARY, DAYSHIFT).to_csv(args.out / "error_condition_summary_v2.csv", index=False)
    insights.insight_figures(args.out, extra["sensor_importance_v2.csv"], extra["coupling_fit_v2.csv"], extra["coupling_records_v2.csv"],
                             extra["probability_reliability_v2.csv"], extra["fp_events_v2.csv"], normal, models, extra["position_vibration_misses_v2.csv"])
    print("사이클2 보강 표·그림", flush=True)
    cond.to_csv(args.out / "error_conditions_v2.csv", index=False)
    segc.to_csv(args.out / "error_conditions_segments_v2.csv", index=False)
    inter.to_csv(args.out / "interaction_2x2_v2.csv", index=False)
    recs.to_csv(args.out / "records_first_alarm_v2.csv", index=False)
    unc.to_csv(args.out / "uncertainty_v2.csv", index=False)
    work.to_csv(args.out / "workload_v2.csv", index=False)
    pd.DataFrame(DECISION_TABLE).to_csv(args.out / "decision_table_v2.csv", index=False)   # 조치 규칙(model.action_for)과 같은 원천
    pv = extra["position_vibration_misses_v2.csv"]
    figures(args.out, cond, recs, v2_by_split, models["A"], float(pv[pv.split.eq("A")].vib_threshold_train_q95.iloc[0]))
    # 검수용 요약: v1과 v2의 위치 0·1 미탐이 같은지(향상이 위치 2~6에 국한되는지)
    early = cond[cond.subset.eq("abnormal") & cond.condition.eq("pos_bin") & cond.value.isin(["0", "1"]) & cond.alpha.eq(.01)].groupby(["split_id", "model"]).error_rows.sum().unstack()
    summary = dict(input_hashes=hashes["v2"], comparison_rows=int(len(comparison)), models=sorted(comparison.model.unique().tolist()),
                   fn_rows_at_position_0_1=early.to_dict(), fn_rows_total={m: {sid: int(recs[recs.split_id.eq(sid)][f"{m}_fn_rows"].sum()) for sid in D.SPLITS} for m in ("v1", "v2")},
                   robustness_rows=int(len(robust)), sensitivity_rows=int(len(sens)), ablation_rows=int(len(abl)),
                   condition_bounds={sid: {k: (list(np.round(v, 6)) if isinstance(v, tuple) else round(v, 6)) for k, v in b.items()} for sid, b in bounds_used.items()},
                   files=["model_comparison_v2.csv", "model_comparison_v2.md", "robustness_v2.csv", "sensitivity_v2.csv", "ablation_v2.csv", "error_conditions_v2.csv",
                          "error_conditions_segments_v2.csv", "interaction_2x2_v2.csv", "records_first_alarm_v2.csv", "uncertainty_v2.csv", "workload_v2.csv",
                          "decision_table_v2.csv", "fig_recall_by_position_v2.png", "fig_first_alarm_v2.png", "fig_missed_example_v2.png"] + INSIGHT_FILES,
                   external_inputs={"analysis/press_supplement/e1_summary.csv": D.sha256_file(E1_SUMMARY),
                                    "analysis/press_dayshift/v2_current_scale.csv": D.sha256_file(DAYSHIFT)},
                   elapsed_s=round(time.monotonic() - start, 1))
    D.dump_json(summary, args.out / "analysis_summary.json")
    manifest["analysis"]=dict(training_fingerprint=training_fingerprint(manifest),config={"reps":args.reps},
                              sources=sources,outputs={n:D.sha256_file(args.out/n) for n in ANALYSIS_FILES})
    manifest.pop("audit_sha256",None)
    D.dump_json(manifest,args.out/"manifest.json")
    print(json.dumps(D.to_jsonable(summary), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
