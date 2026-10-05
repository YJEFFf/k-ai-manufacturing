"""보고서 장별 수치 요약(summary.md) 자동 생성. 모든 숫자는 outputs/pipeline/ 의 CSV·JSON에서 읽는다.

선택 산출물(lstm_ae_metrics.csv, perturb_curve.csv, anomaly_day_*.csv)이 없으면 해당 절을 건너뛴다.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

FINAL = "fused_acat"
SPLITS = ["normal_60_20_20", "normal_50_20_30"]


def _table(df, cols, headers=None):
    headers = headers or cols
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for _, r in df.iterrows():
        out.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return out


def _cell(r):
    return f"{int(r.abnormal_notified_segments)}/21 · {int(r.normal_notified_segments)}/{int(r.normal_recording_segments)} · {r.f1_all_rows:.3f}"


def run(out: Path):
    mt = pd.read_csv(out / "model_comparison.csv")
    lstm = out / "lstm_ae_metrics.csv"
    if lstm.exists():
        lm = pd.read_csv(lstm)
        if "rule" in lm.columns:
            mt = pd.concat([mt, lm[lm.model.str.startswith("lstm")]], ignore_index=True)
    checks = json.loads((out / "checks.json").read_text(encoding="utf-8"))
    main = mt[(mt.rule == "conformal") & (mt.calibration_unit == "recording_segments")]
    L = ["# 결과 요약 (자동 생성 — 손으로 고치지 말 것)", "",
         "주 결과 = conformal 규칙(보정 초과 ≤ ⌊α(n+1)⌋−1), 기록구간 보정. 셀 = 이상 탐지 구간 · 정상 알림 구간 · 전체 행 F1", ""]

    # 2장: 모델 비교
    order = ["max_abs_z", "isolation_forest", "autoencoder_w5", "lstm_ae_guide", "lstm_ae_segment", "5nn_distance",
             "trailing_rms5", "sine_r2_8", FINAL]
    names = {"max_abs_z": "max-z (베이스라인)", "isolation_forest": "Isolation Forest", "autoencoder_w5": "창 AE(5관측)",
             "lstm_ae_guide": "LSTM-AE (가이드북 재현, 공백 무시)", "lstm_ae_segment": "LSTM-AE (기록구간 준수)",
             "5nn_distance": "5NN 거리", "trailing_rms5": "RMS5", "sine_r2_8": "전류 사인 1−R² 단독 (w=8)",
             FINAL: "**최종: 4성분 ACAT 융합**"}
    rows = []
    for m in order:
        g = main[main.model == m]
        if g.empty:
            continue
        row = {"모델": names[m]}
        for s in SPLITS:
            for b in (0.01, 0.05):
                r = g[(g.split == s) & (g.budget == b)]
                row[f"{s[7:]} {int(b * 100)}%"] = _cell(r.iloc[0]) if len(r) else "-"
        rows.append(row)
    t = pd.DataFrame(rows)
    L += ["## 2장. 모델 비교", ""] + _table(t, list(t.columns)) + [""]

    # ablation
    rows = []
    for m in [FINAL] + sorted(x for x in main.model.unique() if x.startswith("ablate_")) + ["fused_min"]:
        r = main[(main.model == m) & (main.budget == 0.01)]
        rows.append({"모델": m, **{s[7:]: _cell(r[r.split == s].iloc[0]) for s in SPLITS}})
    t = pd.DataFrame(rows)
    L += ["### 성분 ablation (1%)", ""] + _table(t, list(t.columns)) + [""]

    # 창 길이 민감도
    rows = []
    for m in sorted([x for x in main.model.unique() if x.startswith(f"{FINAL}_w")], key=lambda x: int(x.split("_w")[1])) + [FINAL]:
        r = main[(main.model == m) & (main.budget == 0.01)]
        rows.append({"창": m.replace(f"{FINAL}_", "") if m != FINAL else f"w{checks[SPLITS[0]]['w_rule']} (규칙 선택)",
                     **{s[7:]: _cell(r[r.split == s].iloc[0]) for s in SPLITS}})
    t = pd.DataFrame(rows)
    L += ["### 창 길이 민감도 (1%, 이상 라벨로 평가 — 선택에는 쓰지 않음)", ""] + _table(t, list(t.columns)) + [""]

    # 규칙 비교
    rows = []
    for rule in ("conformal", "cutoff_yj"):
        g = mt[(mt.model == FINAL) & (mt.rule == rule) & (mt.calibration_unit == "recording_segments")]
        for s in SPLITS:
            rows.append({"규칙": rule, "분할": s[7:], **{f"{int(b * 100)}%": _cell(g[(g.split == s) & (g.budget == b)].iloc[0])
                                                        for b in (0.01, 0.03, 0.05)}})
    t = pd.DataFrame(rows)
    L += ["### 경보 규칙 비교 (최종 모델)", ""] + _table(t, list(t.columns)) + [""]

    # 창 규칙
    ws = pd.read_csv(out / "w_selection.csv")
    w0 = ws[ws.split == SPLITS[0]]
    L += ["### 창 길이 규칙 (정상 데이터만)", "",
          f"- 선택: w={checks[SPLITS[0]]['w_rule']} (두 분할 모두 {checks[SPLITS[1]]['w_rule']}), "
          f"정상 학습 앨리어싱 {checks[SPLITS[0]]['alias_freq_hz']:.3f}Hz → 반주기 {checks[SPLITS[0]]['half_period_obs']:.1f}관측", ""]
    L += _table(w0.round(3), ["w", "normal_misfit_q99", "noise_misfit_median", "noise_reject_rate"],
                ["w", "정상 1−R² 99분위", "잡음 1−R² 중앙", "잡음 기각률"]) + [""]

    # 3장: 영향요인·오류
    inf = pd.read_csv(out / "influence.csv")
    au = inf[inf.kind == "univariate_auroc"].pivot_table(index="item", columns="split", values="value").round(3)
    au = au.reset_index().sort_values(SPLITS[0], ascending=False)
    L += ["## 3장. 영향요인·오류", "", "### 구간 특징 단변량 AUROC (정상 평가 vs 이상)", ""]
    L += _table(au, ["item"] + SPLITS) + [""]
    rs = inf[(inf.kind == "alarm_reason") & (inf.source == "abnormal")]
    for s in SPLITS:
        top = rs[rs.split == s].sort_values("value", ascending=False).head(4)
        L.append(f"- 이상 경보 사유 상위({s[7:]}): " + ", ".join(f"{r.item} {r.value:.0%}" for _, r in top.iterrows()))
    ms = inf[(inf.kind == "maxz_sensor") & (inf.source == "abnormal")]
    L.append("- 크기 성분 경보의 센서: " + ", ".join(f"{r.split[7:]} {r.item} {r.value:.0%}" for _, r in ms.iterrows()))
    er = pd.read_csv(out / "error_conditions.csv")
    L += ["", "### FN (놓친 이상 행)", ""]
    L += _table(er.round(3), ["split", "budget", "fn_rows", "fn_in_sine_warmup", "recall_warmup", "recall_after_warmup"],
                ["분할", "예산", "FN 행", "창 준비 중 FN", "준비 중 재현율", "창 찬 뒤 재현율"]) + [""]
    fp = pd.read_csv(out / "fp_segments.csv")
    L += ["### FP (정상 알림 구간 — 사례가 적어 일반화하지 않음)", ""]
    L += _table(fp.round(3), ["split", "budget", "record_uid", "reasons", "current_amp", "current_amp_normal_median",
                              "vib0_std", "vib0_std_normal_median"],
                ["분할", "예산", "구간", "사유", "전류 진폭", "정상 중앙", "상부진동 std", "정상 중앙"]) + [""]

    # 강건성
    rq = pd.read_csv(out / "requant_fused.csv")
    base = rq[rq.variant == "raw"].set_index(["split", "budget"])
    dmax = {c: int(max((rq[rq.variant == v].set_index(["split", "budget"])[c] - base[c]).abs().max()
                       for v in rq.variant.unique())) for c in ("abnormal_segments", "normal_segments")}
    L += ["## 강건성", "",
          f"- 최종 모델 재양자화(matched·coarse·정상 전류만 1.192 격자): 이상 탐지 구간 변화 최대 "
          f"{dmax['abnormal_segments']}, 정상 알림 구간 변화 최대 {dmax['normal_segments']}"]
    pc = out / "perturb_curve.csv"
    if pc.exists():
        L += ["- 계측 섭동 곡선: `perturb_curve.csv`, 그림 `fig_perturb_jitter.png`"]
    L.append("")

    # 재현성
    L += ["## 6장. 재현성 검사 (checks.json)", ""]
    for s in SPLITS:
        c = checks[s]
        L.append(f"- {s}: 예측 {c['pred_rows']}행, 순서 섞기 불변 {c['shuffle_invariant']}, 보정 초과 {c['calibration_exceedances_conformal_1pct']}, "
                 f"경보 점수 고유 비율 {c['alarm_scores_unique_fraction']:.2f}")
    rep = checks["reproduction_07"]
    L.append(f"- 07 결과 재현: {rep.get('rows_compared')}행, F1 최대 차 {rep.get('max_abs_f1_diff', float('nan')):.1e}")
    (out / "summary.md").write_text("\n".join(L), encoding="utf-8")
    return L


if __name__ == "__main__":
    run(Path(__file__).resolve().parent.parent / "outputs" / "pipeline")
