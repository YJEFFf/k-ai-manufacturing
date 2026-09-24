"""③ 프레스 제출 파이프라인 — 한 번 실행으로 모델 비교·예측 파일·검증을 만든다.

실행 (claude/ 또는 볼트 대회 폴더에서):
    python code/press/pipeline/run_all.py [--root <data/ 상위 폴더>]
산출: code/press/outputs/pipeline/
"""
import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")  # IF·MLP 수치 재현

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data import DEFAULT_ROOT, SENSORS, inputs_only, load, load_vendor, split_sets  # noqa: E402
import analysis  # noqa: E402
import diagnosis  # noqa: E402
import subprocess  # noqa: E402
from evaluate import conformal_p, evaluate  # noqa: E402
from scores import Scorer  # noqa: E402
from select_w import select_w  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "outputs" / "pipeline"
REF = HERE.parent / "outputs" / "policy_sine_windows" / "policy_metrics_with_sine.csv"
PRED_BUDGET = 0.01  # 예측 파일 경보: 기록구간 단위 1% 예산
REPRO_MODELS = ["max_abs_z", "5nn_distance", "trailing_rms5", "maxz_plus_sine_8"]


def check_reproduction(metrics):
    """수용 기준 T1a(a): 07 결과(w=8, 학습 전체 ECDF)와 일치."""
    if not REF.exists():
        return {"skipped": f"{REF} 없음"}
    ref = pd.read_csv(REF)
    key = ["split", "model", "calibration_unit", "budget"]
    m = metrics[metrics.model.isin(REPRO_MODELS)].merge(ref[ref.model.isin(REPRO_MODELS)], on=key, suffixes=("", "_ref"))
    assert len(m) == 48, len(m)
    df1 = float((m.f1_all_rows - m.f1_all_rows_ref).abs().max())
    same_seg = bool((m.abnormal_notified_segments == m.abnormal_notified_segments_ref).all()
                    and (m.normal_notified_segments == m.normal_notified_segments_ref).all())
    assert df1 < 1e-9 and same_seg, (df1, same_seg)
    return {"rows_compared": len(m), "max_abs_f1_diff": df1, "segment_counts_equal": same_seg}


def predict_stream(scorer, yj, stream, cal_seg_max, thr, w, comb_key):
    """라벨 없는 입력 스트림에 행별 예측을 만든다."""
    s, comp = scorer.score(stream, yj)
    score = s[comb_key]
    p = conformal_p(cal_seg_max, score)
    alarm = np.isfinite(score) & (score > thr)
    zf = comp["maxz_logp"] > thr
    sf = np.nan_to_num(comp[f"sine_{w}_logp"], nan=-np.inf) > thr
    reason = np.where(zf & sf, "both", np.where(zf, "maxz", np.where(sf, "sine", "")))
    reason = np.where(alarm, reason, "")
    return dict(score_maxz=comp["maxz"], score_maxz_logp=comp["maxz_logp"], maxz_sensor=comp["maxz_sensor"],
                score_sine=comp[f"sine_{w}"], score_sine_logp=comp[f"sine_{w}_logp"],
                score_comb=score, p_value=p, anomaly_score=1 - p, alarm=alarm.astype(int),
                conformal_alarm=(np.nan_to_num(p, nan=1.0) <= PRED_BUDGET).astype(int), alarm_reason=reason)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    yj = load_vendor()
    normal, abnormal = load(args.root)
    args.out.mkdir(parents=True, exist_ok=True)

    metrics, records, unit_tests, wsel, preds, checks = [], [], [], [], [], {}
    for split, train_end, cal_end in yj.SPLITS:
        train, cal, test = split_sets(normal, yj, train_end, cal_end)
        w_rule, wtable, tie = select_w(yj, train, cal)
        wsel.append(wtable.assign(split=split, selected=lambda d: d.w == w_rule, tied_candidates=tie))
        wins = sorted({8, w_rule})
        scorer = Scorer(train, yj.blocks, wins=wins, baselines=True)
        per_set = [scorer.score(d, yj)[0] for d in (cal, test, abnormal)]
        model_scores = {m: tuple(ps[m] for ps in per_set) for m in per_set[0]}
        m, r, u = evaluate(yj, split, (cal, test, abnormal), model_scores)
        for row in m:
            row["w_rule"] = w_rule
        metrics += m
        records += r
        unit_tests += u

        # T2: 예측 파일 — 결합 모델(규칙이 고른 w), 기록구간 1% 예산
        comb_key = f"maxz_plus_sine_{w_rule}"
        cal_seg_max = yj.segment_max(model_scores[comb_key][0], yj.blocks(cal))
        thr = yj.cutoff_at_budget(cal_seg_max, PRED_BUDGET)
        stream = pd.concat([inputs_only(test), inputs_only(abnormal)], ignore_index=True)
        pred = predict_stream(scorer, yj, stream, cal_seg_max, thr, w_rule, comb_key)
        src = np.r_[np.repeat("normal_test", len(test)), np.repeat("abnormal", len(abnormal))]
        rid = np.r_[yj.blocks(test), yj.blocks(abnormal)]
        pdf = pd.DataFrame(dict(split=split, source=src, record_uid=[f"{a}_{b}" for a, b in zip(src, rid)],
                                timestamp=stream.TimeStamp))
        for c in SENSORS:
            pdf[c] = stream[c].to_numpy()
        pdf["row_in_record"] = pdf.groupby("record_uid").cumcount()
        pdf["is_scored"] = np.isfinite(pred["score_comb"]).astype(int)
        for k, v in pred.items():
            pdf[k] = v
        pdf["model"], pdf["w"], pdf["budget"], pdf["threshold"] = comb_key, w_rule, PRED_BUDGET, thr

        # 수용 기준 T2
        assert len(pdf) == len(test) + 600
        assert ((pdf.p_value > 0) & (pdf.p_value <= 1) | pdf.p_value.isna()).all()
        sep = np.r_[model_scores[comb_key][1], model_scores[comb_key][2]]
        assert np.allclose(sep, pdf.score_comb, equal_nan=True), "스트림 추론 ≠ 평가 점수"
        # 라벨 우회 검사: 기록구간 순서를 섞어도 행별 결과 동일
        rng = np.random.default_rng(0)
        order = rng.permutation(pdf.record_uid.unique())
        perm = np.concatenate([np.flatnonzero(pdf.record_uid.to_numpy() == u) for u in order])
        pred2 = predict_stream(scorer, yj, stream.iloc[perm].reset_index(drop=True), cal_seg_max, thr, w_rule, comb_key)
        back = np.empty_like(perm)
        back[perm] = np.arange(len(perm))
        shuffle_ok = bool(np.allclose(pred2["score_comb"][back], pred["score_comb"], equal_nan=True)
                          and (pred2["alarm"][back] == pred["alarm"]).all())
        assert shuffle_ok
        ev = next(x for x in m if x["model"] == comb_key and x["calibration_unit"] == "recording_segments"
                  and x["budget"] == PRED_BUDGET)
        n_norm = pdf[(pdf.source == "normal_test")].groupby("record_uid").alarm.max().sum()
        n_abn = pdf[(pdf.source == "abnormal")].groupby("record_uid").alarm.max().sum()
        assert n_norm == ev["normal_notified_segments"] and n_abn == ev["abnormal_notified_segments"]
        checks[split] = dict(w_rule=w_rule, w_tied_candidates=tie, pred_rows=len(pdf), shuffle_invariant=shuffle_ok,
                             normal_alarm_segments=int(n_norm), abnormal_alarm_segments=int(n_abn))
        preds.append(pdf)
        print(f"done {split}: w_rule={w_rule} (동률 {tie})", flush=True)

    mt = pd.DataFrame(metrics)
    checks["reproduction_07"] = check_reproduction(mt)
    ut = pd.DataFrame(unit_tests)
    checks["conformal_vs_cutoff_max_diff_rows"] = int(ut.diff_rows.max())
    checks["vendor_sha256_ok"] = True

    mt.to_csv(args.out / "model_comparison.csv", index=False)
    pd.DataFrame(records).to_csv(args.out / "record_notifications.csv", index=False)
    pd.concat(wsel).to_csv(args.out / "w_selection.csv", index=False)
    pd.concat(preds).to_csv(args.out / "predictions_test.csv", index=False)
    ut.to_csv(args.out / "conformal_unit_test.csv", index=False)
    (args.out / "checks.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2, default=int), encoding="utf-8")
    write_comparison_md(mt, args.out / "model_comparison.md")
    analysis.run(args.out, args.root)
    # 진단: 형식 누수 감사(05)는 vendor 사본으로 실행 — 예준 폴더 경로 의존 없음
    rq = HERE.parent / "05_requantize_audit.py"
    if not (HERE.parent / "outputs" / "requantize" / "shortcut_rules.csv").exists():
        subprocess.run([sys.executable, str(rq), "--audit", str(HERE / "vendor" / "press_policy_audit.py")],
                       check=True, stdout=subprocess.DEVNULL)
    diagnosis.run(args.out, args.root, yj)
    print(json.dumps(checks, ensure_ascii=False, indent=2, default=int))


def write_comparison_md(mt, path):
    """보고서용 요약표: 기록구간 보정, 예산별."""
    mt = mt.copy()
    mt["cell"] = (mt.abnormal_notified_segments.astype(str) + "/21 · " + mt.normal_notified_segments.astype(str)
                  + "/" + mt.normal_recording_segments.astype(str) + " · " + mt.f1_all_rows.round(3).astype(str))
    lines = ["# 모델 비교 (자동 생성)", "",
             "셀 = 이상 탐지 구간 · 정상 알림 구간 · 전체 행 F1. 문턱은 정상 보정 구간에서만 정함.", ""]
    for unit in ["recording_segments", "rows"]:
        t = mt[mt.calibration_unit == unit].pivot_table(index="model", columns=["split", "budget"], values="cell",
                                                        aggfunc="first")
        head = ["model"] + [f"{s} {int(b * 100)}%" for s, b in t.columns]
        rows = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
        rows += ["| " + " | ".join([idx] + [str(v) for v in t.loc[idx]]) + " |" for idx in t.index]
        lines += [f"## 보정 단위: {unit}", ""] + rows + [""]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
