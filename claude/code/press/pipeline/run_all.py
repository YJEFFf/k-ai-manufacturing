"""③ 프레스 제출 파이프라인 — 한 번 실행으로 모델 비교·예측 파일·검증을 만든다.

실행 (claude/ 또는 볼트 대회 폴더에서):
    python code/press/pipeline/run_all.py [--root <data/ 상위 폴더>]
산출: code/press/outputs/pipeline/

최종 모델 = fused_acat: 성분 4개(max-z, 5NN, 창 AE, 전류 사인 적합도)의 극값 꼬리 p값을 ACAT로 결합하고,
보정 구간 기록구간 최댓값으로 conformal 보정한다. 사인 창 w는 정상 데이터만으로 고른다(select_w.py).
"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")  # IF·MLP 수치 재현

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analysis  # noqa: E402
import diagnosis  # noqa: E402
import summary  # noqa: E402
from data import DEFAULT_ROOT, SENSORS, inputs_only, load, load_vendor, split_sets  # noqa: E402
from evaluate import conformal_cutoff, conformal_p, evaluate  # noqa: E402
from fusion import Fusion  # noqa: E402
from scores import Scorer  # noqa: E402
from select_w import select_w  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "outputs" / "pipeline"
REF = HERE.parent / "outputs" / "policy_sine_windows" / "policy_metrics_with_sine.csv"
PRED_BUDGET = 0.01          # 예측 파일 경보: 기록구간 단위 conformal 1%
SENS_WINS = (4, 5, 6, 10, 12, 14, 16)   # 창 길이 민감도 (이상 라벨로 평가, 선택에는 쓰지 않음)
FINAL = "fused_acat"


def load_requant():
    spec = importlib.util.spec_from_file_location("rq05", HERE.parent / "05_requantize_audit.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def fused_models(fu, comp_sets, w):
    """융합 모델과 민감도·ablation. comp_sets = (cal, test, abn) 성분 dict."""
    base = ["maxz", "knn5", "ae5", f"sine_{w}"]
    variants = {FINAL: (base, "acat"), "fused_min": (base, "min")}
    for c in base:
        variants[f"ablate_{c.split('_')[0]}"] = ([b for b in base if b != c], "acat")
    return {name: tuple(fu.score(cs, names, how)[0] for cs in comp_sets) for name, (names, how) in variants.items()}


def check_reproduction(metrics):
    """07 결과(w=8, 학습 ECDF, 예준 문턱식)와 일치하는지: 옛 결합과 max-z·5NN·RMS5."""
    if not REF.exists():
        return {"skipped": f"{REF} 없음"}
    ref = pd.read_csv(REF)
    mp = {"max_abs_z": "max_abs_z", "5nn_distance": "5nn_distance", "trailing_rms5": "trailing_rms5",
          "legacy_maxz_plus_sine_8": "maxz_plus_sine_8"}
    m = metrics[(metrics.rule == "cutoff_yj") & metrics.model.isin(mp)].assign(ref_model=lambda d: d.model.map(mp))
    key = ["split", "calibration_unit", "budget"]
    j = m.merge(ref, left_on=key + ["ref_model"], right_on=key + ["model"], suffixes=("", "_ref"))
    assert len(j) == 48, len(j)
    df1 = float((j.f1_all_rows - j.f1_all_rows_ref).abs().max())
    same = bool((j.abnormal_notified_segments == j.abnormal_notified_segments_ref).all()
                and (j.normal_notified_segments == j.normal_notified_segments_ref).all())
    assert df1 < 1e-9 and same, (df1, same)
    return {"rows_compared": len(j), "max_abs_f1_diff": df1, "segment_counts_equal": same}


def predict_stream(scorer, fu, yj, stream, w, cal_max, thr_conf, thr_yj):
    """라벨 없는 입력 스트림(TimeStamp + 센서 3열)에 행별 예측을 만든다."""
    comp, sensor, _ = scorer.components(stream)
    names = ["maxz", "knn5", "ae5", f"sine_{w}"]
    score, p_acat = fu.score(comp, names, "acat")
    lpc = fu.component_logp(comp)
    fired = {n: -np.where(np.isfinite(lpc[n]), lpc[n], 0.0) / np.log(10) > thr_conf for n in names}
    label = {"maxz": "진동/전류 크기", "knn5": "센서 조합", "ae5": "시계열 재구성", f"sine_{w}": "전류 파형"}
    alarm = score > thr_conf
    reason = []
    for i in range(len(score)):
        if not alarm[i]:
            reason.append("")
            continue
        r = [label[n] for n in names if fired[n][i]]
        reason.append("+".join(r) if r else "복합")
    out = dict(score_fused=score, neglog10p_acat=score, p_conformal=conformal_p(cal_max, score),
               alarm=alarm.astype(int), alarm_cutoff_yj=(score > thr_yj).astype(int), alarm_reason=np.array(reason),
               maxz_sensor=sensor)
    for n in names:
        out[f"comp_{n.split('_')[0]}"] = comp[n]
        out[f"neglog10p_{n.split('_')[0]}"] = -lpc[n] / np.log(10)
    return out


def requant_fused(rq, yj, normal, abnormal, w):
    """최종 모델 재양자화 감사: matched / coarse / 정상 전류만 1.192 격자로."""
    rows = []
    variants = {"raw": (None, None), "matched": (rq.VARIANTS["matched"], rq.VARIANTS["matched"]),
                "coarse": (rq.VARIANTS["coarse"], rq.VARIANTS["coarse"]),
                "normal_current_to_grid": ("cur_only", None)}
    for name, (sn, sa) in variants.items():
        if sn is None:
            n2 = normal
        elif sn == "cur_only":
            n2 = normal.copy()
            n2["AI2_Current"] = np.round(n2["AI2_Current"] / rq.Q_CUR) * rq.Q_CUR
        else:
            n2 = rq.quantize(normal, sn)
        a2 = rq.quantize(abnormal, sa) if sa is not None else abnormal
        for split, te, ce in yj.SPLITS:
            tr, cal, test = split_sets(n2, yj, te, ce)
            sc = Scorer(tr, yj.blocks, wins=(w,), baselines=False)
            fu = Fusion(sc.train_components, ["maxz", "knn5", "ae5", f"sine_{w}"])
            s = [fu.score(sc.components(d)[0], None, "acat")[0] for d in (cal, test, a2)]
            M = yj.segment_max(s[0], yj.blocks(cal))
            for b in yj.BUDGETS:
                thr = conformal_cutoff(M, b)
                rows.append(dict(variant=name, split=split, budget=b,
                                 abnormal_segments=int(pd.Series(s[2] > thr).groupby(yj.blocks(a2)).any().sum()),
                                 normal_segments=int(pd.Series(s[1] > thr).groupby(yj.blocks(test)).any().sum()),
                                 abnormal_row_recall=float((s[2] > thr).mean())))
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--skip-lstm", action="store_true", help="LSTM-AE 베이스라인 학습 생략(개발용, 제출 실행에서는 쓰지 않음)")
    args = ap.parse_args()
    yj = load_vendor()
    normal, abnormal = load(args.root)
    args.out.mkdir(parents=True, exist_ok=True)

    metrics, records, wsel, preds, checks = [], [], [], [], {}
    for split, train_end, cal_end in yj.SPLITS:
        train, cal, test = split_sets(normal, yj, train_end, cal_end)
        w, wtable, winfo = select_w(train, yj.blocks)
        wsel.append(wtable.assign(split=split, **{k: v for k, v in winfo.items() if k != "w_rule"}))
        wins = tuple(dict.fromkeys((w, 8) + SENS_WINS))
        scorer = Scorer(train, yj.blocks, wins=wins, baselines=True)
        comp_sets, per = [], []
        for d in (cal, test, abnormal):
            comp, _, z = scorer.components(d)
            comp_sets.append(comp)
            per.append(scorer.models(d, yj, comp, z))
        model_scores = {m: tuple(p[m] for p in per) for m in per[0]}
        fu = Fusion(scorer.train_components, ["maxz", "knn5", "ae5"] + [f"sine_{x}" for x in wins])
        model_scores.update(fused_models(fu, comp_sets, w))
        for x in wins[1:]:  # 창 길이 민감도
            model_scores[f"{FINAL}_w{x}"] = tuple(
                fu.score(cs, ["maxz", "knn5", "ae5", f"sine_{x}"], "acat")[0] for cs in comp_sets)
        m, r = evaluate(yj, split, (cal, test, abnormal), model_scores)
        for row in m:
            row["w_rule"] = w
        metrics += m
        records += r

        # 예측 파일: 최종 모델, 기록구간 conformal 1%
        cal_max = yj.segment_max(model_scores[FINAL][0], yj.blocks(cal))
        thr_conf = conformal_cutoff(cal_max, PRED_BUDGET)
        thr_yj = yj.cutoff_at_budget(cal_max, PRED_BUDGET)
        stream = pd.concat([inputs_only(test), inputs_only(abnormal)], ignore_index=True)
        pred = predict_stream(scorer, fu, yj, stream, w, cal_max, thr_conf, thr_yj)
        src = np.r_[np.repeat("normal_test", len(test)), np.repeat("abnormal", len(abnormal))]
        rid = np.r_[yj.blocks(test), yj.blocks(abnormal)]
        pdf = pd.DataFrame(dict(split=split, source=src, record_uid=[f"{a}_{b}" for a, b in zip(src, rid)],
                                timestamp=stream.TimeStamp))
        for c in SENSORS:
            pdf[c] = stream[c].to_numpy()
        pdf["row_in_record"] = pdf.groupby("record_uid").cumcount()
        for k, v in pred.items():
            pdf[k] = v
        pdf["model"], pdf["w"], pdf["budget"], pdf["threshold"] = FINAL, w, PRED_BUDGET, thr_conf

        # 수용 검사
        assert len(pdf) == len(test) + 600
        assert ((pdf.p_conformal > 0) & (pdf.p_conformal <= 1)).all()
        assert np.allclose(np.r_[model_scores[FINAL][1], model_scores[FINAL][2]], pdf.score_fused)
        rng = np.random.default_rng(0)
        order = rng.permutation(pdf.record_uid.unique())
        perm = np.concatenate([np.flatnonzero(pdf.record_uid.to_numpy() == u) for u in order])
        pred2 = predict_stream(scorer, fu, yj, stream.iloc[perm].reset_index(drop=True), w, cal_max, thr_conf, thr_yj)
        back = np.empty_like(perm)
        back[perm] = np.arange(len(perm))
        shuffle_ok = bool(np.allclose(pred2["score_fused"][back], pred["score_fused"])
                          and (pred2["alarm"][back] == pred["alarm"]).all())
        assert shuffle_ok
        ev = next(x for x in m if x["model"] == FINAL and x["calibration_unit"] == "recording_segments"
                  and x["rule"] == "conformal" and x["budget"] == PRED_BUDGET)
        n_norm = int(pdf[pdf.source == "normal_test"].groupby("record_uid").alarm.max().sum())
        n_abn = int(pdf[pdf.source == "abnormal"].groupby("record_uid").alarm.max().sum())
        assert n_norm == ev["normal_notified_segments"] and n_abn == ev["abnormal_notified_segments"]
        allowed = max(int(np.floor(PRED_BUDGET * (ev["calibration_units"] + 1) - 1 + 1e-12)), 0)
        assert ev["calibration_exceedances"] <= allowed
        top = np.sort(np.r_[model_scores[FINAL][1], model_scores[FINAL][2]])
        top = top[top > thr_conf]
        checks[split] = dict(w_rule=w, alias_freq_hz=winfo["alias_freq_hz"], half_period_obs=winfo["half_period_obs"],
                             pred_rows=len(pdf), shuffle_invariant=shuffle_ok, normal_alarm_segments=n_norm,
                             abnormal_alarm_segments=n_abn,
                             calibration_exceedances_conformal_1pct=int(ev["calibration_exceedances"]),
                             alarm_scores_unique_fraction=float(len(np.unique(top)) / max(len(top), 1)))
        preds.append(pdf)
        print(f"done {split}: w_rule={w}", flush=True)

    mt = pd.DataFrame(metrics)
    checks["reproduction_07"] = check_reproduction(mt)
    checks["vendor_sha256_ok"] = True

    # 재양자화 감사: 기존 3모델(05, 매번 재실행) + 최종 모델
    subprocess.run([sys.executable, str(HERE.parent / "05_requantize_audit.py"),
                    "--audit", str(HERE / "vendor" / "press_policy_audit.py")], check=True, stdout=subprocess.DEVNULL)
    rqf = requant_fused(load_requant(), yj, normal, abnormal, checks[yj.SPLITS[0][0]]["w_rule"])
    rqf.to_csv(args.out / "requant_fused.csv", index=False)
    base = rqf[rqf.variant == "raw"].set_index(["split", "budget"])
    for col in ("abnormal_segments", "normal_segments"):
        checks[f"requant_fused_max_change_{col}"] = int(max(
            (rqf[rqf.variant == v].set_index(["split", "budget"])[col] - base[col]).abs().max()
            for v in rqf.variant.unique()))

    mt.to_csv(args.out / "model_comparison.csv", index=False)
    pd.DataFrame(records).to_csv(args.out / "record_notifications.csv", index=False)
    pd.concat(wsel).to_csv(args.out / "w_selection.csv", index=False)
    pd.concat(preds).to_csv(args.out / "predictions_test.csv", index=False)
    (args.out / "checks.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2, default=float),
                                          encoding="utf-8")
    write_comparison_md(mt, args.out / "model_comparison.md")
    analysis.run(args.out, args.root)
    diagnosis.run(args.out, args.root, yj)
    # 보조 모듈: 가이드북 LSTM-AE 재현 베이스라인, 계측 섭동 곡선, 이상일 전류 원인 증거표
    if not args.skip_lstm:
        import lstm_ae
        lstm_ae.run(args.out, args.root, yj)
    import anomaly_day
    import perturb
    perturb.run(args.out, args.root, yj)
    anomaly_day.run(args.out, args.root, yj)
    summary.run(args.out)
    print(json.dumps(checks, ensure_ascii=False, indent=2, default=float))


def write_comparison_md(mt, path):
    """보고서용 요약표: 규칙·보정단위별, 모델 × (분할, 예산)."""
    mt = mt.copy()
    mt["cell"] = (mt.abnormal_notified_segments.astype(str) + "/21 · " + mt.normal_notified_segments.astype(str)
                  + "/" + mt.normal_recording_segments.astype(str) + " · " + mt.f1_all_rows.round(3).astype(str))
    lines = ["# 모델 비교 (자동 생성)", "",
             "셀 = 이상 탐지 구간 · 정상 알림 구간 · 전체 행 F1. 문턱은 정상 보정 구간에서만 정함.",
             "주 결과는 rule=conformal, 보정 단위=recording_segments.", ""]
    for rule in ["conformal", "cutoff_yj"]:
        for unit in ["recording_segments", "rows"]:
            t = mt[(mt.rule == rule) & (mt.calibration_unit == unit)].pivot_table(
                index="model", columns=["split", "budget"], values="cell", aggfunc="first")
            head = ["model"] + [f"{s} {int(round(b * 100))}%" for s, b in t.columns]
            rows = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
            rows += ["| " + " | ".join([idx] + [str(v) for v in t.loc[idx]]) + " |" for idx in t.index]
            lines += [f"## 규칙 {rule} · 보정 단위 {unit}", ""] + rows + [""]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
