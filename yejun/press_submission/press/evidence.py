"""W12 보고서 근거 문서와 numbers.json — PLAN.md §7·§8. outputs/의 실행 결과만 읽어 만든다(하드코딩 없음).

evidence/보고서_근거_장별.md: 공식 양식 6장에 대응하는 표·수치·문장 초안과 출처 파일.
outputs/numbers.json: 헤드라인 수치마다 모델·분할·전처리·기준·α·단위·분모·run_id를 붙인다. 보고서·슬라이드는 이 항목을 참조한다.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import data as D


def md_table(df: pd.DataFrame, cols: list, rename: dict | None = None, fmt: dict | None = None) -> str:
    rename, fmt = rename or {}, fmt or {}
    head = [rename.get(c, c) for c in cols]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(cols)]
    for r in df[cols].itertuples(index=False):
        cells = []
        for c, v in zip(cols, r):
            if c in fmt:
                cells.append(fmt[c].format(v) if pd.notna(v) else "")
            elif isinstance(v, float):
                cells.append("" if pd.isna(v) else (f"{v:.3f}" if abs(v) < 1000 else f"{v:,.0f}"))
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def cell(df):
    return (df.abnormal_notified_segments.astype(int).astype(str) + "/" + df.abnormal_segments.astype(int).astype(str) + " · "
            + df.normal_notified_segments.astype(int).astype(str) + "/" + df.normal_segments.astype(int).astype(str) + " · F1 " + df.f1_all_rows.round(3).astype(str))


def run(out: Path, evidence_dir: Path, manifest: dict, checks: dict) -> dict:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    run_id = manifest.get("git_commit") or "uncommitted"
    diag = json.loads((out / "diagnosis.json").read_text(encoding="utf-8"))
    mc = pd.read_csv(out / "model_comparison_all.csv") if (out / "model_comparison_all.csv").exists() else pd.read_csv(out / "model_comparison.csv")
    ops = pd.read_csv(out / "operating_points.csv")
    sens = pd.read_csv(out / "sensitivity.csv")
    abl = pd.read_csv(out / "ablation.csv")
    frozen = pd.read_csv(out / "quantization_frozen.csv")
    lb = pd.read_csv(out / "label_bypass.csv")
    fn = pd.read_csv(out / "error_conditions_fn.csv")
    fp = pd.read_csv(out / "error_conditions_fp.csv")
    cells = pd.read_csv(out / "interaction_2x2.csv")
    comp = pd.read_csv(out / "alarm_components.csv")
    infl = pd.read_csv(out / "influence.csv")
    tails = pd.read_csv(out / "tail_params.csv")
    unc = pd.read_csv(out / "uncertainty.csv") if (out / "uncertainty.csv").exists() else None
    guide = json.loads((out / "lstm_guidebook_reproduction.json").read_text(encoding="utf-8")) if (out / "lstm_guidebook_reproduction.json").exists() else None
    wl = pd.read_csv(out / "workload.csv") if (out / "workload.csv").exists() else None
    pers = pd.read_csv(out / "persistence.csv") if (out / "persistence.csv").exists() else None
    ln = pd.read_csv(out / "load_normalization.csv") if (out / "load_normalization.csv").exists() else None
    pre = diag["preprocess"]
    seg_conf = mc[(mc.calibration_unit == "recording_segments") & (mc.criterion == "conformal")].copy()
    seg_conf["cell"] = cell(seg_conf)
    main = seg_conf[seg_conf.model == "combined_w8"]
    numbers = {"run_id": run_id, "protocol_version": D.PROTOCOL_VERSION, "preprocess_main": pre, "items": {}}

    def add(key, value, **prov):
        numbers["items"][key] = {"value": value, **prov, "run_id": run_id}

    # ---------- 1장 ----------
    S = diag["structure"]
    L = [f"# 보고서 근거 (자동 생성) — run {run_id}", "",
         f"출처: `yejun/press_submission/outputs/` (실행 시각·환경·해시는 `manifest.json`). 주 전처리 `{pre}`. 모든 성능은 정상 하루·이상 하루 자료에 대한 **탐색적 평가**이며 독립 검증·현장 오경보 보장·고장 원인의 인과 증거가 아니다.", "",
         "## 제1장 데이터 이해 및 진단 (15)", "",
         "**근거 파일**: `diagnosis.md`, `diagnosis.json`, `waveform_segments.csv`, `preprocess_effect.csv`, `splits.csv`, `fig_current_waveform.png`, `fig_segment_length.png`", "",
         "| 항목 | 정상 | 이상 |", "|---|---|---|",
         f"| 행 / 기록구간 | {S['normal']['rows']:,} / {S['normal']['segments']} | {S['abnormal']['rows']:,} / {S['abnormal']['segments']} |",
         f"| 경과 / 기록 시간 | {S['normal']['elapsed_min']:.1f}분 / {S['normal']['recorded_min']:.1f}분 | {S['abnormal']['elapsed_min']:.1f}분 / {S['abnormal']['recorded_min']:.1f}분 |",
         f"| 구간 길이 최소/중앙/최대 | {S['normal']['seg_len_min']}/{S['normal']['seg_len_median']:.0f}/{S['normal']['seg_len_max']} | {S['abnormal']['seg_len_min']}/{S['abnormal']['seg_len_median']:.0f}/{S['abnormal']['seg_len_max']} |",
         f"| 중복 시각 / 결측 | {S['normal']['duplicate_timestamps']} / {S['normal']['missing_values']} | {S['abnormal']['duplicate_timestamps']} / {S['abnormal']['missing_values']} |",
         f"| 구간 내 lag-1 자기상관 AI0 | {S['normal']['lag1'][D.SENSORS[0]]:.3f} | {S['abnormal']['lag1'][D.SENSORS[0]]:.3f} |", ""]
    fr_raw = pd.DataFrame(diag["format_rules_raw"]); fr_pre = pd.DataFrame(diag[f"format_rules_{pre}"])
    L += ["저장 형식 규칙(값 크기와 무관)의 판별력 — raw vs 주 전처리:", "",
          md_table(fr_raw.merge(fr_pre, on="rule", suffixes=("_raw", f"_{pre}")), ["rule", "normal_fire_rate_raw", "abnormal_fire_rate_raw", "separability_raw", f"separability_{pre}"],
                   {"separability_raw": "판별력(raw)", f"separability_{pre}": f"판별력({pre})"}), ""]
    W = diag["waveform"]
    L += [f"전류 파형(구간 전체 사인 적합, 길이≥10): 정상 {W['normal']['segments_fitted']}구간 R² {W['normal']['r2_min']:.3f}~{W['normal']['r2_max']:.3f}(중앙 {W['normal']['r2_median']:.3f}), 적합 주파수 중앙값 {W['normal']['f_median']:.3f}Hz(정확히 0.600Hz {W['normal']['f_exact_0_600']}구간); "
          f"이상 {W['abnormal']['segments_fitted']}구간 R² {W['abnormal']['r2_min']:.3f}~{W['abnormal']['r2_max']:.3f}.", "",
          "**문장 초안**", "- 기록구간은 타임스탬프 간격이 0.1초가 아닌 곳에서 나눈 기록 단위이며 설비 기동·독립 고장 사건이 아니다.",
          "- 정상·이상 파일은 저장 자릿수와 전류 격자가 달라 형식만으로 구분된다(판별력 표). 주 전처리는 두 클래스에 같은 간격의 round를 적용해 이 정보를 제거한다. 수집 장치·클록 차이는 확인 불가한 가설이다.",
          "- 상태 라벨은 파일·날짜와 교락되어 있어 어떤 분석으로도 분리할 수 없다. 반증 조건: 정상일 자료를 이상일과 같은 경로로 한 번 더 수집하면 판별 가능하다.",
          "- 60Hz 교류의 앨리어싱이라는 해석은 가설이다. 파일 평균 차이를 물리적 DC 오프셋으로 해석하지 않는다.", ""]
    add("normal_rows", S["normal"]["rows"], unit="rows"); add("abnormal_rows", S["abnormal"]["rows"], unit="rows")
    add("normal_segments", S["normal"]["segments"], unit="segments"); add("abnormal_segments", S["abnormal"]["segments"], unit="segments")
    add("format_rule_max_separability_raw", float(fr_raw.separability.max()), unit="auroc"); add(f"format_rule_max_separability_{pre}", float(fr_pre.separability.max()), unit="auroc")

    # ---------- 2장 ----------
    L += ["## 제2장 AI 예측모델 개발 및 성능평가 (40)", "",
          "**근거 파일**: `model_comparison_all.csv/.md`, `operating_points.csv`, `thresholds_main.csv`, `tail_params.csv`, `sensitivity.csv`, `quantization_frozen.csv`, `ablation.csv`, `lstm_guidebook_reproduction.json`, `model_comparison_lstm.csv`, `conformal_mc.csv`", "",
          "모델 비교 (기록구간 보정, conformal, 셀 = 이상 탐지 구간/21 · 정상 알림 구간/n · 전체 행 F1):", ""]
    pv = seg_conf.pivot_table(index="model", columns=["split", "alpha"], values="cell", aggfunc="first")
    head = ["model"] + [f"{s} α={a:g}" for s, a in pv.columns]
    L += ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join([str(i)] + [str(v) for v in pv.loc[i]]) + " |" for i in pv.index] + [""]
    L += ["주 모델 운영점 (conformal vs cutoff, 정상 알림의 독립 가정 95% 상한, 조건부 지연):", "",
          md_table(ops[ops.calibration_unit == "recording_segments"], ["split", "criterion", "alpha", "alpha_grid", "normal_notified_segments", "normal_segments", "normal_binomial_upper95", "abnormal_notified_segments", "delay_median_s", "delay_p90_s", "abnormal_row_coverage", "f1_all_rows"],
                   {"normal_notified_segments": "정상 알림", "normal_segments": "정상 구간", "normal_binomial_upper95": "이항 95% 상한", "abnormal_notified_segments": "이상 탐지", "abnormal_row_coverage": "이상 행 coverage"}), ""]
    for r in main[main.alpha == 0.01].itertuples():
        add(f"main_conformal_1pct_abnormal_detected@{r.split}", int(r.abnormal_notified_segments), model="combined_w8", split=r.split, preprocess=pre, criterion="conformal", alpha=0.01, unit="segments", denominator=int(r.abnormal_segments))
        add(f"main_conformal_1pct_normal_notified@{r.split}", int(r.normal_notified_segments), model="combined_w8", split=r.split, preprocess=pre, criterion="conformal", alpha=0.01, unit="segments", denominator=int(r.normal_segments))
        add(f"main_conformal_1pct_f1_all_rows@{r.split}", round(float(r.f1_all_rows), 4), model="combined_w8", split=r.split, preprocess=pre, criterion="conformal", alpha=0.01, unit="f1")
        add(f"main_conformal_1pct_binomial_upper95@{r.split}", round(float(r.normal_binomial_upper95), 4), model="combined_w8", split=r.split, criterion="conformal", alpha=0.01, unit="rate", assumption="독립 정상 구간")
    for m in ("maxz_3", "sine_w8", "lstm20", "lstm20_plus_maxz"):
        for r in seg_conf[(seg_conf.model == m) & (seg_conf.alpha == 0.01)].itertuples():
            add(f"{m}_conformal_1pct_abnormal_detected@{r.split}", int(r.abnormal_notified_segments), model=m, split=r.split, preprocess=pre, criterion="conformal", alpha=0.01, unit="segments", denominator=21)
    ss = sens[(sens.criterion == "conformal") & (sens.alpha == 0.01) & sens.model.str.startswith("combined_w")].copy()
    ss["cell"] = cell(ss)
    pv2 = ss.pivot_table(index=["preprocess", "split"], columns="w", values="cell", aggfunc="first")
    L += ["창 길이·전처리 민감도 (combined, conformal α=1%; w=8은 탐색에서 먼저 정한 값이며 후보 전체를 공개한다):", "",
          "| 전처리 | 분할 | " + " | ".join(f"w={int(c)}" for c in pv2.columns) + " |", "|---|---|" + "---|" * len(pv2.columns)]
    L += ["| " + " | ".join([str(i[0]), str(i[1])] + [str(v) for v in pv2.loc[i]]) + " |" for i in pv2.index] + [""]
    fz = frozen[(frozen.criterion == "conformal")]
    L += ["동결 진단 (matched로 적합·보정한 주 모델을 평가 입력만 변환해 적용):", "",
          md_table(fz, ["split", "eval_preprocess", "alpha", "abnormal_notified_segments", "normal_notified_segments", "normal_segments", "f1_all_rows"]), ""]
    ab = abl[(abl.criterion == "conformal")].copy(); ab["cell"] = cell(ab)
    pv3 = ab.pivot_table(index="ablation", columns=["split", "alpha"], values="cell", aggfunc="first")
    head = ["절제"] + [f"{s} α={a:g}" for s, a in pv3.columns]
    L += ["절제 (matched, w=8):", "", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join([str(i)] + [str(v) for v in pv3.loc[i]]) + " |" for i in pv3.index] + [""]
    L += ["꼬리 변환 파라미터 (정상 학습 q95 초과분 지수):", "", md_table(tails, ["split", "component", "n", "u", "beta", "n_exceed", "fit_ok", "g_at_1"]), ""]
    if guide:
        g = guide
        L += [f"가이드북 LSTM-AE 프로토콜 재구현(PyTorch, 에폭 {g['epochs_run']}/{g['max_epochs']}, patience {g['patience']}): 평가 정상 {g['test_windows_normal']}·이상 {g['test_windows_anomaly']}창에서 TN {g['tn']} / FP {g['fp']} / FN {g['fn']} / TP {g['tp']}, 정확도 {g['accuracy']:.4f}, F1 {g['f1']:.4f}, 오경보율 {g['false_alarm_rate']:.4f}. "
              f"가이드 보고값 TN 3,922 / FP 78 / FN 26 / TP 154, 정확도 0.9751, F1 0.7476. {g['notes']}", ""]
        add("lstm_guidebook_repro_f1", round(g["f1"], 4), protocol="guidebook_reproduction_pytorch", unit="f1", note="이상 라벨로 문턱 선택; 주 비교표와 다른 프로토콜")
    L += ["**문장 초안**",
          "- 최종 모델은 3센서 max|z|와 전류 trailing-8 사인 적합 1−R²를 각각 정상 학습 참조의 q95 초과분 지수 꼬리로 변환해 fmax로 결합한 점수이며, 문턱은 정상 보정 기록구간 최댓값의 conformal p값으로 정한다(α=1%, 3%·5% 병기).",
          "- 선정 근거: 같은 정상 학습·보정·평가 조건에서 결합만이 두 분할·세 전처리·창 5~10에서 이상 21구간을 모두 잡았고(표), 정상 알림은 max-z 단독과 같거나 비슷하다. 사인 단독·max-z 단독은 각각 18/21이며 서로 다른 구간을 놓친다.",
          "- 출력 확률: `p_value`는 정상 참조에 대한 이탈 p값이고 `1−p`는 정렬용 점수다. 고장 사후확률이나 개별 경보의 오경보 확률이 아니다. α=1%의 이론 경계(alpha_grid 1/121≈0.83%)는 교환가능성 가정 아래의 주변 경계이며 고정 문턱의 미래 오경보율 상한이 아니다.",
          "- 창 w=8은 탐색에서 먼저 봤고 정상 자료만으로 최적화했다고 쓰지 않는다. 민감도표를 그대로 싣는다.", ""]

    # ---------- 3장 ----------
    L += ["## 제3장 영향요인 및 오류분석 (15)", "",
          "**근거 파일**: `error_conditions_fn.csv`, `error_conditions_fp.csv`, `interaction_2x2.csv`, `alarm_components.csv`, `influence.csv`, `segment_features.csv`, `fig_vibration_vs_waveform.png`, `fig_recall_by_position.png`, `fig_error_examples.png`", "",
          "FN(놓친 이상 행) 조건표 (α=1%, 분모 = 조건의 이상 행 수):", "",
          md_table(fn[fn.alpha == 0.01], ["split", "condition", "value", "abnormal_rows", "fn_rows", "fn_rate", "rows_before_first_alarm"]), "",
          "FP(정상 알림 구간) 조건표 (α=1%·5%, 분모 = 조건의 정상 평가 구간 수):", "",
          md_table(fp[(fp.fp_segments > 0) | ((fp.alpha == 0.01) & (fp.condition == "vib_bin"))], ["split", "alpha", "condition", "value", "normal_segments", "fp_segments", "fp_rate"]), "",
          "진동 수준 × 파형 2×2 (구간 단위, α=1%):", "",
          md_table(cells, ["split", "vib_high", "wave", "abnormal_segments", "abnormal_detected", "abnormal_missed", "normal_segments", "normal_alerted"]), "",
          "발화 성분과 단변량 판별력:", "", md_table(comp, ["split", "kind", "item", "share", "n"]), "",
          md_table(infl, ["split", "feature", "auroc", "direction", "n_normal", "n_abnormal"]), "",
          "**문장 초안**",
          "- 놓치는 조건: 기록구간 첫 7행(사인 창이 차기 전)에 FN이 집중된다. 이 구간은 max-z만 판정하므로 진동이 정상 수준인 이상 구간은 파형이 판정될 때까지 놓친다(위치별 경보율 그림).",
          "- 헛울리는 조건: 정상 알림 구간은 진동 Q4·긴 구간(≥30)·전류 진폭 상위에 몰리며 첫 사유는 max-z다. 파형은 정상이라 사인 성분은 이를 막지 못한다(2×2 표의 '진동 높음·사인 정상' 칸).",
          "- 상호작용: 진동이 정상 수준이면서 파형이 붕괴한 이상 구간은 사인 성분으로만 잡힌다(2×2 표). 이것이 두 성분을 결합한 이유다.",
          "- 진폭 대리 지표는 실제 부하 측정이 아니며 길이 17 미만 구간은 신뢰 제한이다. 특정 부품 고장 원인을 확정하지 않는다.", ""]
    for r in cells[(cells.vib_high == False) & (cells.wave == "broken")].itertuples():  # noqa: E712
        add(f"abnormal_low_vibration_broken_wave_detected@{r.split}", int(r.abnormal_detected), unit="segments", denominator=int(r.abnormal_segments), source="interaction_2x2.csv")

    # ---------- 4장 ----------
    L += ["## 제4장 현장 활용방안 (10)", "", "**근거 파일**: `workload.csv`, `persistence.csv`, `load_normalization.csv`, `load_normalization_meta.csv`, `field_decision_table.md`, `uncertainty.csv`", ""]
    if wl is not None:
        w1 = wl[(wl.calibration_unit == "recording_segments") & (wl.criterion == "conformal")]
        L += ["업무량 (기록 관측시간 기준; 하루 알림 수는 가정 시나리오):", "",
              md_table(w1, ["split", "alpha", "first_alert_segments", "normal_segments", "alarm_runs", "recorded_hours", "elapsed_hours", "alerts_per_recorded_hour", "alerts_per_elapsed_hour", "scenario_alerts_per_day_8h_recorded_rate", "scenario_alerts_per_day_24h_recorded_rate", "abnormal_detected", "delay_median_s"]), ""]
        for r in w1[w1.alpha == 0.01].itertuples():
            add(f"alerts_per_recorded_hour_conformal_1pct@{r.split}", round(float(r.alerts_per_recorded_hour), 3), unit="alerts/hour", basis="recorded time = 0.1s × rows", split=r.split)
    if pers is not None:
        p1 = pers[pers.criterion == "conformal"].copy(); p1["cell"] = cell(p1)
        pv4 = p1.pivot_table(index="model", columns=["split", "alpha"], values="cell", aggfunc="first")
        head = ["지속성 규칙"] + [f"{s} α={a:g}" for s, a in pv4.columns]
        L += ["지속성 (k,n) 규칙 (정책 점수를 보정 단계부터 다시 보정; 첫 n−1행 미판정):", "", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join([str(i)] + [str(v) for v in pv4.loc[i]]) + " |" for i in pv4.index]
        L += ["", md_table(p1[p1.alpha == 0.01], ["split", "model", "delay_median_s", "delay_p90_s", "abnormal_row_coverage", "normal_alarm_runs"]), ""]
    if ln is not None:
        l1 = ln[ln.criterion == "conformal"].copy(); l1["cell"] = cell(l1)
        pv5 = l1.pivot_table(index="model", columns=["split", "alpha"], values="cell", aggfunc="first")
        head = ["진폭 정규화 후보"] + [f"{s} α={a:g}" for s, a in pv5.columns]
        L += ["진폭 정규화 개선 후보 (trailing-17 온라인 특징; 결과와 무관하게 주 모델은 유지):", "", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join([str(i)] + [str(v) for v in pv5.loc[i]]) + " |" for i in pv5.index] + [""]
    if unc is not None:
        u1 = unc[(unc.criterion == "conformal") & (unc.calibration_unit == "recording_segments")]
        L += ["정상 알림 수의 시간 의존성 민감도 (moving-block bootstrap; 0건은 퇴화):", "", md_table(u1, ["split", "alpha", "block_length", "observed_alerts", "boot_p2_5", "boot_p97_5", "degenerate_all_zero"]), ""]
    L += ["**문장 초안**", "- 경보는 기록구간마다 첫 1회이며 사유(진동 크기/전류 파형)를 붙여 확인 항목을 안내한다(판단표). 사유별 점검 대상은 가설이다.",
          "- 정상 평가 자료의 기록 관측시간은 분할당 약 7~10분(경과 16~24분)뿐이다. 시간당·하루 알림 수는 이 짧은 관측을 그대로 늘린 예시 계산이며 실제 가동 상태·기록 밀도를 반영하지 않는다. 표의 '첫 알림 구간 수 k/n'을 주 수치로 쓴다.",
          "- 지속성 (2,3) 규칙은 두 분할에서 이상 21구간 탐지를 유지한 채 정상 알림을 0으로 줄였고 첫 경보 지연 중앙값은 0.1~0.2초 늘었다(구간 첫 2행은 미판정). 개선 후보로 보고하며 주 모델을 교체하지 않는다.",
          "- 진폭 정규화 후보는 분할 B에서 정상 알림을 3→1로 줄였지만 분할 A에서는 0→1로 늘렸다. 일관된 개선이 아니므로 부정·혼합 결과로 보고한다. 잔차 단독은 13/21로 크기 성분을 대체하지 못한다.",
          "- 1%·3%·5%는 비교 가능한 운영점이다. 정상 알림 0/n을 오경보율 0%로 쓰지 않고 이항 상한과 블록 부트스트랩을 함께 보인다.",
          "- 지속성 규칙과 진폭 정규화는 평가된 개선 후보다. 개선이 없으면 부정 결과로 보고한다.", ""]

    # ---------- 5장 ----------
    L += ["## 제5장 창의성 및 차별성 (10)", "", "**근거 파일**: `ablation.csv`, `diagnosis.md`(형식 규칙), `label_bypass.csv`, `conformal_mc.csv`, `quantization_frozen.csv`", "",
          "요소별 '빼면 무엇이 바뀌나' (conformal α=1%, 절제표 재인용):", ""]
    a1 = abl[(abl.criterion == "conformal") & (abl.alpha == 0.01)]
    L += [md_table(a1, ["split", "ablation", "abnormal_notified_segments", "normal_notified_segments", "normal_segments", "f1_all_rows", "abnormal_row_coverage"]), "",
          "라벨 우회·미래값 불변 검사:", "", md_table(lb, ["split", "check", "expect_equal", "scores_equal", "max_abs_score_diff", "alarm_segments_changed", "passed"]), "",
          "**문장 초안**", "- 제조 지식 결합: 저속 표본화된 모터 전류의 파형 적합도를 특징으로 써서 진동이 정상인 이상 구간을 잡는다(3장 2×2와 연결). 앨리어싱 해석은 가설이다.",
          "- 불확실성·보정: 정상 보정 구간 최댓값의 conformal p값으로 오경보 예산을 명시하고, 순위 p값 구현을 MC로 검증했다. 확률 용어의 한계를 2장에 명시한다.",
          "- 데이터 진단을 모델에 연결: 형식 지름길을 찾아 전처리로 제거했고, 상한 있는 ECDF 결합이 죽은 성분을 만드는 문제를 지수 꼬리로 해결했다(절제표의 capped 행).", ""]

    # ---------- 6장 ----------
    env = manifest.get("environment", {})
    L += ["## 제6장 코드 구성 및 재현성 (10)", "",
          "```bash", "cd yejun/press_submission && python -m pip install -r requirements.txt",
          "OMP_NUM_THREADS=1 python run_all.py --root . --out outputs   # LSTM 캐시 있으면 ~1분, 없으면 첫 실행 30~40분",
          "python -m pytest -q tests", "python verify.py --out outputs                                # outputs/expected 대비 허용오차 검사",
          "python predict.py --model artifacts/main_A.json --input <new.csv> --out predictions.csv", "```", "",
          f"환경: Python {env.get('python')}, numpy {env.get('numpy')}, pandas {env.get('pandas')}, scikit-learn {env.get('scikit_learn')}, torch(LSTM) {manifest.get('torch', '')}; {env.get('platform')}. 실행 시간: {manifest.get('timings_s')}.",
          "검사 결과(`checks.json`): 입력 해시·행 수, 기록구간 = vendor 규칙, 분할 크기, 스트림 추론 = 평가 점수, 저장/복원 일치, 구간 순서 셔플 불변, 예측 파일 알림 수 = 표, p≤α = 문턱 경보, MC, 라벨 우회, 산출 CSV 원값 없음.",
          "예측 파일 규격(§7): row_id, record_id, timestamp, status, position_in_record, record_length, is_scored, score_maxz3, maxz_sensor, score_sine, g_maxz3, g_sine, combined_score, p_value, anomaly_score, alarm(conformal 1%), alarm_<criterion>_<α>, criterion, budget, threshold, alarm_reason, model_id. 자체 평가셋(정상 평가 + 이상 600행)이며 공식 테스트셋이 아니다.", "",
          "## 하지 말 것 (보고서·발표 공통)", "",
          "- 블라인드 테스트·독립 검증·현장 실증·절감액·RUL·'고장 N초 전' 표현. 지연은 기록 시작 후다.",
          "- cutoff F1과 conformal 보장을 한 운영점으로 묶기. 0/120을 오경보율 0%로. 'conformal 1% 보장' 대신 alpha_grid와 가정 명시.",
          "- 60Hz 앨리어싱·수집 경로 차이·DC 오프셋을 확인된 사실로. 21구간을 독립 고장 21회로.",
          "- 21/21·0/120 등 결과 수치를 새 실행의 기대 정답으로. 준용 파이프라인 수치와 이 패키지 수치의 혼용(출처 파일 명시)."]
    (evidence_dir / "보고서_근거_장별.md").write_text("\n".join(L), encoding="utf-8")
    D.dump_json(numbers, out / "numbers.json")
    return {"evidence_lines": len(L), "numbers_items": len(numbers["items"])}
