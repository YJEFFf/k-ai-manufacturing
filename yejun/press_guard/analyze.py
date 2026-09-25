"""v2 분석용 표·그림 — 통합 모델 비교, 미탐·오경보 조건, 불확실성, 업무량. 보고서 서술은 생성하지 않는다.

    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python yejun/press_guard/analyze.py

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

from model import GuardModel, cases, D, BASE, HERE, ALPHAS
from press.uncertainty import moving_block_bootstrap

ADVANCE = HERE.parent / "analysis" / "press_advance"
V1 = BASE / "outputs"
FINAL, BASELINE = "early6_ar2", "baseline_w8"
POS_BINS = [(0, 0, "0"), (1, 1, "1"), (2, 4, "2–4"), (5, 6, "5–6"), (7, 9, "7–9"), (10, 10**9, "≥10")]
LEN_BINS = [(1, 4, "≤4"), (5, 9, "5–9"), (10, 29, "10–29"), (30, 10**9, "≥30")]
COLOR_V1, COLOR_V2 = "#b07510", "#178cc2"   # dataviz 검증기 통과(색각 이상 분리·대비)
V1_ALARM = {.01: "alarm", .03: "alarm_conformal_0.03", .05: "alarm_conformal_0.05"}


def _bin(v, bins):
    return next(lab for lo, hi, lab in bins if lo <= v <= hi)


def input_hashes_agree(v2_manifest):
    v1 = json.loads((V1 / "manifest.json").read_text())["inputs"]["files"]
    adv = json.loads((ADVANCE / "manifest.json").read_text())["inputs"]["files"]
    v1h, advh = {k: v["sha256"] for k, v in v1.items()}, {k: v["sha256"] for k, v in adv.items()}
    return v1h == advh == v2_manifest["input_hashes"], dict(v1=v1h, advance=advh, v2=v2_manifest["input_hashes"])


# ---------- 통합 모델 비교 ----------
def model_comparison(out):
    v1 = pd.read_csv(V1 / "model_comparison_all.csv"); v1["source"] = "v1_package"
    adv = pd.read_csv(ADVANCE / "metrics.csv"); adv = adv[adv.input_variant.eq("matched")].drop(columns=["input_variant"]); adv["source"] = "v2_candidates"
    adv = adv[~adv.model.eq(BASELINE)]   # baseline_w8은 v1 combined_w8과 같은 점수 함수(수치 동일)라 중복 제외
    both = pd.concat([v1, adv], ignore_index=True, sort=False)
    both["is_final_model"] = both.model.eq(FINAL)
    both["is_main_model"] = both.model.eq("combined_w8")
    both.to_csv(out / "model_comparison_v2.csv", index=False)
    main = both[both.calibration_unit.eq("recording_segments") & both.criterion.eq("conformal") & both.alpha.eq(.01)]
    cols = ["split_id", "model", "source", "abnormal_notified_segments", "normal_notified_segments", "normal_segments", "fn", "fp", "f1_all_rows", "abnormal_row_coverage", "delay_median_s", "delay_max_s"]
    lines = ["# 통합 모델 비교 — 구간 conformal α=1%, matched (분석용 표)", "",
             "v1 패키지 실행(기준모델·LSTM 포함)과 v2 후보 고정 비교를 같은 입력·분할·보정 구간에서 합쳤다. 이미 본 이상 21구간 기준의 탐색 평가다.", "",
             "| 분할 | 모델 | 출처 | 이상 탐지 구간 | 정상 알림 구간 | 미탐 행 | 오경보 행 | F1(전체 행) | 판정 가능 | 첫 경보 중앙값/최대(초) |", "|---|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for r in main.sort_values(["split_id", "f1_all_rows"], ascending=[True, False])[cols].itertuples(index=False):
        lines.append(f"| {r.split_id} | {'**' + r.model + '**' if r.model == FINAL else r.model} | {r.source} | {int(r.abnormal_notified_segments)}/21 | {int(r.normal_notified_segments)}/{int(r.normal_segments)} | {int(r.fn)} | {int(r.fp)} | {r.f1_all_rows:.4f} | {r.abnormal_row_coverage:.2f} | {r.delay_median_s:.1f}/{r.delay_max_s:.1f} |")
    (out / "model_comparison_v2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return both


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
def error_conditions(sid, v1_pair, v2_pairs, feats):
    rows = []
    def add(model, alpha, subset, kind, cond, value, mask, alarm):
        n = int(mask.sum()); err = int(((alarm == 0) if kind == "fn" else (alarm == 1))[mask].sum())
        rows.append(dict(split_id=sid, model=model, alpha=alpha, subset=subset, error=kind, condition=cond, value=value,
                         rows=n, error_rows=err, error_rate=err / n if n else np.nan))
    def conditions(model, alpha, pn, pa):
        for subset, kind, p in (("abnormal", "fn", pa), ("normal", "fp", pn)):
            p = _with_length(p)
            alarm = p.alarm.to_numpy(int)
            pos = p.position.to_numpy(); ln = p.record_length.to_numpy()
            for lo, hi, lab in POS_BINS:
                add(model, alpha, subset, kind, "pos_bin", lab, (pos >= lo) & (pos <= hi), alarm)
            for lo, hi, lab in LEN_BINS:
                add(model, alpha, subset, kind, "len_bin", lab, (ln >= lo) & (ln <= hi), alarm)
            f = feats[subset].set_index("record_id")
            for col, name in (("vib_std", "vib_quartile"), ("amp_proxy", "amp_quartile")):
                q = np.nanpercentile(f[col], [25, 50, 75])
                per_row = p.record_id.map(f[col]).to_numpy(float)
                for lab, m in (("Q1", per_row < q[0]), ("Q2", (per_row >= q[0]) & (per_row < q[1])), ("Q3", (per_row >= q[1]) & (per_row < q[2])), ("Q4", per_row >= q[2]),
                               ("NA", ~np.isfinite(per_row))):   # 길이 1 구간은 진동 표준편차가 없다
                    add(model, alpha, subset, kind, name, lab, m, alarm)
            if model == "v2":
                comp = p[["g_magnitude", "g_waveform", "g_dynamics"]].to_numpy(float)
                strongest = np.where(np.isfinite(comp).any(axis=1), np.array(["magnitude", "waveform", "dynamics"])[np.nan_to_num(comp, nan=-np.inf).argmax(axis=1)], "none")
                for lab in ("magnitude", "waveform", "dynamics", "none"):
                    add(model, alpha, subset, kind, "strongest_component", lab, strongest == lab, alarm)
    conditions("v1", .01, *v1_pair)
    for alpha, (pn, pa) in v2_pairs.items():
        conditions("v2", alpha, pn, pa)
    return pd.DataFrame(rows)


def segment_feature_table(frame, seg):
    v0, v1_, cur = (frame[c].to_numpy(float) for c in D.SENSORS)
    rows = []
    for s in np.unique(seg):
        idx = np.flatnonzero(seg == s); c = cur[idx]
        rows.append(dict(record_id=int(s), length=int(len(idx)), vib_std=float(np.sqrt(v0[idx].var(ddof=1) + v1_[idx].var(ddof=1))) if len(idx) > 1 else np.nan,
                         amp_proxy=float(np.sqrt(2 * np.mean((c - c.mean()) ** 2))), amp_reliable=bool(len(idx) >= 17)))
    return pd.DataFrame(rows)


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
def workload(sid, name, test, metrics):
    t = pd.to_datetime(test[D.TIME]); recorded_h = len(test) * D.DT / 3600; elapsed_h = (t.max() - t.min()).total_seconds() / 3600
    rows = []
    for r in metrics[metrics.split.eq(sid)].itertuples():
        base = dict(split_id=sid, split=name, model=r.model, alpha=r.alpha, normal_segments=r.normal_segments, first_alert_segments=r.normal_notified_segments,
                    alarm_rows=r.fp, recorded_hours=recorded_h, elapsed_hours=elapsed_h,
                    alerts_per_recorded_hour=r.normal_notified_segments / recorded_h, alerts_per_elapsed_hour=r.normal_notified_segments / elapsed_h,
                    abnormal_detected=r.abnormal_notified_segments, abnormal_fn_rows=r.fn, delay_median_s=r.delay_median_s, delay_max_s=r.delay_max_s)
        for h in (8, 16, 24):
            base[f"scenario_alerts_per_day_{h}h_recorded_rate"] = r.normal_notified_segments / recorded_h * h
        rows.append(base)
    return pd.DataFrame(rows)


# ---------- 그림 ----------
def figures(out, cond, records, v2_pairs_by_split):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": ["Apple SD Gothic Neo", "AppleGothic", "Nanum Gothic", "DejaVu Sans"], "axes.unicode_minus": False, "font.size": 9})
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
    fig.suptitle(f"v2 미탐이 가장 많은 이상 구간(A, 구간 {int(worst)}, {len(g)}관측): 위치 0·1은 센서 크기 성분만 존재", fontsize=9)
    fig.tight_layout(); fig.savefig(out / "fig_missed_example_v2.png", dpi=150); plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=HERE / "outputs")
    ap.add_argument("--artifacts", type=Path, default=HERE / "artifacts")
    ap.add_argument("--reps", type=int, default=2000)
    args = ap.parse_args()
    start = time.monotonic()
    manifest = json.loads((args.out / "manifest.json").read_text())
    agree, hashes = input_hashes_agree(manifest)
    if not agree:
        raise SystemExit(f"입력 해시 불일치: {hashes}")
    normal, abnormal, _ = D.load(args.root) if args.root else D.load()
    metrics = pd.read_csv(args.out / "metrics.csv")
    comparison = model_comparison(args.out)
    robust = robustness(args.out)
    cond, recs, unc, work, v2_by_split = [], [], [], [], {}
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
        feats = {"normal": segment_feature_table(split["test"], D.segments(split["test"])), "abnormal": segment_feature_table(abnormal, D.segments(abnormal))}
        cond.append(error_conditions(sid, v1_pair, pairs, feats))
        recs.append(record_table(sid, v1_pair, pairs[.01]))
        unc.append(uncertainty(sid, split["name"], v1_pair, pairs, reps=args.reps))
        work.append(workload(sid, split["name"], split["test"], metrics))
        print(f"{sid}: 조건·불확실성·업무량 집계", flush=True)
    cond, recs, unc, work = (pd.concat(x, ignore_index=True) for x in (cond, recs, unc, work))
    cond.to_csv(args.out / "error_conditions_v2.csv", index=False)
    recs.to_csv(args.out / "records_first_alarm_v2.csv", index=False)
    unc.to_csv(args.out / "uncertainty_v2.csv", index=False)
    work.to_csv(args.out / "workload_v2.csv", index=False)
    figures(args.out, cond, recs, v2_by_split)
    # 검수용 요약: v1과 v2의 위치 0·1 미탐이 같은지(향상이 위치 2~6에 국한되는지)
    early = cond[cond.subset.eq("abnormal") & cond.condition.eq("pos_bin") & cond.value.isin(["0", "1"]) & cond.alpha.eq(.01)].groupby(["split_id", "model"]).error_rows.sum().unstack()
    summary = dict(input_hashes=hashes["v2"], comparison_rows=int(len(comparison)), models=sorted(comparison.model.unique().tolist()),
                   fn_rows_at_position_0_1=early.to_dict(), fn_rows_total={m: {sid: int(recs[recs.split_id.eq(sid)][f"{m}_fn_rows"].sum()) for sid in D.SPLITS} for m in ("v1", "v2")},
                   robustness_rows=int(len(robust)),
                   files=["model_comparison_v2.csv", "model_comparison_v2.md", "robustness_v2.csv", "error_conditions_v2.csv", "records_first_alarm_v2.csv", "uncertainty_v2.csv", "workload_v2.csv",
                          "fig_recall_by_position_v2.png", "fig_first_alarm_v2.png", "fig_missed_example_v2.png"],
                   elapsed_s=round(time.monotonic() - start, 1))
    D.dump_json(summary, args.out / "analysis_summary.json")
    print(json.dumps(D.to_jsonable(summary), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
