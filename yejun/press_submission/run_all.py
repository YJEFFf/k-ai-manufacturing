"""③ 프레스 제출 패키지 — 한 명령 실행 (PLAN.md §7·§8).

    OMP_NUM_THREADS=1 python run_all.py --root . --out outputs [--preprocess matched] [--no-verify] [--no-baselines]

1단계: 데이터 검증·기록구간·분할·전처리 효과·진단·manifest.
2단계: 주 전처리에서 분할 A/B마다 정상 학습 적합 → 보정 → 평가(모델 × 보정 단위 × 기준 × α) → 주 모델 artifact·예측 파일·검사.
3단계 이후는 checks.json의 pending_steps에 표시한다.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from press import data as D  # noqa: E402
from press import analysis, diagnosis, robustness  # noqa: E402
from press.artifact import Artifact  # noqa: E402
from press.calibrate import ALPHAS, conformal_p, mc_check_conformal, segment_max, thresholds_for  # noqa: E402
from press.evaluate import comparison_markdown, evaluate_models  # noqa: E402
from press.scores import MAIN_W, MainModel, Scorer  # noqa: E402

PENDING = ["baselines_lstm_uncertainty(4단계)",
           "field_persistence_evidence(5단계)", "freeze_env_clean_repro_zip(6단계)"]
MAIN_ALPHA = 0.01


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True,
                              cwd=Path(__file__).resolve().parent).stdout.strip()
    except Exception:
        return None


def scan_outputs_for_raw_values(out: Path) -> dict:
    """산출 CSV에 센서 원값 열이 없는지 확인한다(행 단위 원값은 Git 제외 대상)."""
    hits = {}
    for p in out.rglob("*.csv"):
        if p.name.startswith("predictions") or p.name.startswith("records"):
            continue
        cols = pd.read_csv(p, nrows=0).columns.tolist()
        bad = [c for c in cols if c in D.SENSORS]
        if bad:
            hits[str(p.relative_to(out))] = bad
    return hits


def step1(args, out):
    normal, abnormal, load_report = D.load(args.root, verify=not args.no_verify)
    checks = {"input_hash_ok": all(v["sha256_ok"] for v in load_report["files"].values()),
              "input_rows_ok": all(v["rows_ok"] for v in load_report["files"].values())}
    status_n, status_a = D.validate_rows(normal), D.validate_rows(abnormal)
    seg_n, seg_a = D.segments(normal, status_n), D.segments(abnormal, status_a)
    vendor = D.load_vendor()
    checks["segments_equal_vendor_blocks"] = bool((seg_n == vendor.blocks(normal)).all() and (seg_a == vendor.blocks(abnormal)).all())
    checks["segment_counts"] = {"normal": int(len(np.unique(seg_n))), "abnormal": int(len(np.unique(seg_a)))}
    checks["segment_counts_ok"] = checks["segment_counts"] == D.EXPECTED_SEGMENTS if not args.no_verify else None
    checks["bad_rows"] = {"normal": int((status_n != "ok").sum()), "abnormal": int((status_a != "ok").sum())}
    rows = []
    for sid in D.SPLITS:
        sp = D.split_normal(normal, seg_n, sid)
        for part in ("train", "cal", "test"):
            rows.append(dict(split_id=sid, split=sp["name"], part=part, rows=len(sp[part]), segments=sp["segments"][part]))
        rows.append(dict(split_id=sid, split=sp["name"], part="abnormal_test", rows=len(abnormal), segments=int(len(np.unique(seg_a)))))
    pd.DataFrame(rows).to_csv(out / "splits.csv", index=False)
    eff = []
    for name in D.QUANTIZATION:
        for lab, df in (("normal", normal), ("abnormal", abnormal)):
            q = D.quantize(df, name)
            for c in D.SENSORS:
                diff = (q[c] - df[c]).abs().to_numpy()
                eff.append(dict(preprocess=name, set=lab, sensor=c, changed_fraction=float((diff > 0).mean()),
                                mean_abs_change=float(diff.mean()), max_abs_change=float(diff.max())))
    pd.DataFrame(eff).to_csv(out / "preprocess_effect.csv", index=False)
    numbers = diagnosis.run(out, args.root, normal, abnormal, seg_n, seg_a, status_n, status_a, args.preprocess)
    D.dump_json(numbers, out / "diagnosis.json")
    checks["diagnosis_generated"] = (out / "diagnosis.md").exists()
    checks["format_rules_after_preprocess_max_separability"] = float(pd.DataFrame(numbers[f"format_rules_{args.preprocess}"]).separability.max())
    return dict(normal=normal, abnormal=abnormal, seg_n=seg_n, seg_a=seg_a, vendor=vendor, load_report=load_report), checks


def build_predictions(mm: MainModel, stream: pd.DataFrame, seg: np.ndarray, cal_seg_max: np.ndarray, thresholds: list[dict], model_id: str):
    """행별 예측 파일(PLAN §7 계약). 주 열은 conformal α=1%, 다른 운영점은 alarm_<criterion>_<α> 열."""
    r = mm.score(stream, seg)
    p = conformal_p(cal_seg_max, r["combined"])
    pos, length = D.segment_positions(seg)
    df = pd.DataFrame(dict(row_id=np.arange(len(stream)), record_id=seg, timestamp=stream[D.TIME].astype(str),
                           status="ok", position_in_record=pos, record_length=length,
                           is_scored=np.isfinite(r["combined"]).astype(int), sine_scored=np.isfinite(r["sine"]).astype(int),
                           score_maxz3=r["maxz3"], maxz_sensor=r["maxz_sensor"], score_sine=r["sine"],
                           g_maxz3=r["g_maxz3"], g_sine=r["g_sine"], combined_score=r["combined"],
                           p_value=p, anomaly_score=1 - p))
    main = next(t for t in thresholds if t["criterion"] == "conformal" and t["alpha"] == MAIN_ALPHA)
    for t in thresholds:
        thr = t["threshold"]
        col = "alarm" if t is main else f"alarm_{t['criterion']}_{t['alpha']:g}"
        df[col] = (np.isfinite(r["combined"]) & (r["combined"] > thr)).astype(int)
    thr = main["threshold"]
    zf, sf = r["g_maxz3"] > thr, np.nan_to_num(r["g_sine"], nan=-np.inf) > thr
    reason = np.where(zf & sf, "both", np.where(zf, "maxz", np.where(sf, "sine", "")))
    df["criterion"], df["budget"], df["threshold"] = "conformal", MAIN_ALPHA, thr
    df["alarm_reason"] = np.where(df.alarm.to_numpy() == 1, reason, "")
    df["model_id"] = model_id
    return df, r


def step2(args, out, art_dir, ctx, checks):
    vendor, normal, abnormal, seg_a = ctx["vendor"], ctx["normal"], ctx["abnormal"], ctx["seg_a"]
    pre = args.preprocess
    abn_q = D.quantize(abnormal, pre)
    all_metrics, tails, ops, mc = [], [], [], mc_check_conformal()
    checks["conformal_mc_within_4se"] = all(abs(m["realized"] - m["alpha_grid"]) <= 4 * m["mc_se"] for m in mc)
    pd.DataFrame(mc).to_csv(out / "conformal_mc.csv", index=False)
    step_checks, ctx2 = {}, {}
    for sid in D.SPLITS:
        t0 = time.time()
        sp = D.split_normal(normal, ctx["seg_n"], sid)
        q = {k: D.quantize(sp[k], pre) for k in ("train", "cal", "test")}
        segs = {k: D.segments(q[k]) for k in ("train", "cal", "test")}
        segs["abn"] = seg_a
        frames = {"cal": q["cal"], "test": q["test"], "abn": abn_q}
        scorer = Scorer(q["train"], segs["train"], vendor, wins=(MAIN_W,), baselines=not args.no_baselines)
        per = {k: scorer.score(frames[k], segs[k])[0] for k in ("cal", "test", "abn")}
        model_scores = {m: {k: per[k][m] for k in per} for m in per["cal"]}
        for name, tail in (("maxz3", scorer.tail_z3), (f"sine_w{MAIN_W}", scorer.tail_sine[MAIN_W])):
            st = tail.state()
            tails.append(dict(split=sp["name"], preprocess=pre, component=name, n=st["n"], u=st["u"], beta=st["beta"],
                              n_exceed=st["n_exceed"], fit_ok=st["ok"], g_at_1=float(tail(np.array([1.0]))[0]) if name.startswith("sine") else np.nan))
        degenerate = not scorer.tail_sine[MAIN_W].ok
        main_model = f"combined_w{MAIN_W}"
        if degenerate:   # PLAN §4.1: 사인 적합 불가 → maxz_only_degenerate로 명시
            model_scores["maxz_only_degenerate"] = {k: scorer.components(frames[k], segs[k])[0]["g_maxz3"] for k in frames}
            main_model = "maxz_only_degenerate"
        if not scorer.tail_z3.ok and degenerate:
            raise RuntimeError("두 성분 모두 꼬리 적합 불가: 실행 실패 (PLAN §4.1)")
        comp_bounds = {f"combined_w{MAIN_W}": float(scorer.tail_sine[MAIN_W](np.array([1.0]))[0])}
        mt, rec = evaluate_models(vendor, sp["name"], pre, model_scores, frames, segs, comp_bounds)
        mt["split_id"], mt["is_main_model"] = sid, mt.model == main_model
        all_metrics.append(mt)
        rec[rec.model == main_model].to_csv(out / f"records_main_{sid}.csv", index=False)

        # 주 모델 artifact (학습 상태 + 보정 상태)
        cal_seg_max = segment_max(model_scores[main_model]["cal"], segs["cal"])
        thr_rows = thresholds_for(cal_seg_max, "recording_segments")
        state = scorer.main_state(MAIN_W)
        state.update(degenerate=degenerate, preprocess_spec=D.QUANTIZATION[pre], segment_rule={"dt": D.DT, "tol": D.GAP_TOL},
                     calibration={"unit": "recording_segments", "split": sp["name"], "segment_max": cal_seg_max,
                                  "n": int(len(cal_seg_max)), "thresholds": thr_rows})
        art = Artifact(model_id=f"{main_model}_{pre}_{sid}", split=sp["name"], preprocess=pre, w=MAIN_W,
                       input_sha256={k: v["sha256"] for k, v in ctx["load_report"]["files"].items()}, state=state)
        art_path = art.save(art_dir / f"main_{sid}.json")

        # 예측 파일: 평가 스트림(정상 평가 + 이상)에 artifact만으로 추론
        mm = MainModel(Artifact.load(art_path).state)
        stream = pd.concat([D.inputs_only(frames["test"]), D.inputs_only(frames["abn"])], ignore_index=True)
        seg_stream = D.segments(stream)
        pred, r = build_predictions(mm, stream, seg_stream, cal_seg_max, thr_rows, art.model_id)
        src = np.r_[np.repeat("normal_test", len(frames["test"])), np.repeat("abnormal", len(frames["abn"]))]
        pred.insert(1, "source", src)   # 평가용 메타데이터(입력 아님)
        pred.to_csv(out / f"predictions_{sid}.csv", index=False)

        # 검사: 스트림 추론 == 평가 점수, 저장/불러오기 일치, 순서 셔플 불변, 예측 파일 알림 수 == 표, p≤α == 문턱
        eval_comb = np.r_[model_scores[main_model]["test"], model_scores[main_model]["abn"]]
        c_stream = bool(np.allclose(r["combined"], eval_comb, equal_nan=True))
        rng = np.random.default_rng(0)
        order = rng.permutation(np.unique(seg_stream))
        perm = np.concatenate([np.flatnonzero(seg_stream == u) for u in order])
        shuf = stream.iloc[perm].reset_index(drop=True)
        r2 = mm.score(shuf, D.segments(shuf))
        back = np.empty_like(perm); back[perm] = np.arange(len(perm))
        c_shuffle = bool(np.allclose(r2["combined"][back], r["combined"], equal_nan=True))
        ev = mt[(mt.model == main_model) & (mt.calibration_unit == "recording_segments") & (mt.criterion == "conformal") & (mt.alpha == MAIN_ALPHA)].iloc[0]
        n_norm = int(pred[pred.source == "normal_test"].groupby("record_id").alarm.max().sum())
        n_abn = int(pred[pred.source == "abnormal"].groupby("record_id").alarm.max().sum())
        c_counts = n_norm == ev.normal_notified_segments and n_abn == ev.abnormal_notified_segments
        c_p = bool(mt[(mt.calibration_unit == "recording_segments") & (mt.criterion == "conformal")].conformal_p_alarm_rows_equal_threshold_rows.all())
        step_checks[sid] = dict(main_model=main_model, degenerate=degenerate, stream_equals_evaluation=c_stream,
                                shuffle_invariant=c_shuffle, prediction_alarm_counts_equal_table=bool(c_counts),
                                conformal_p_equals_threshold_alarms=c_p, artifact=str(art_path.name),
                                normal_notified=n_norm, abnormal_notified=n_abn, seconds=round(time.time() - t0, 1))
        for t in thr_rows:
            ops.append(dict(split=sp["name"], model=main_model, **t))
        ctx2[sid] = dict(name=sp["name"], train=q["train"], seg_train=segs["train"], stream=stream, seg_stream=seg_stream, pred=pred, state=state)
        print(f"split {sid} done in {time.time() - t0:.1f}s: {main_model} conformal 1% → normal {n_norm}/{ev.normal_segments}, abnormal {n_abn}/21", flush=True)
    mt = pd.concat(all_metrics, ignore_index=True)
    mt.to_csv(out / "model_comparison.csv", index=False)
    comparison_markdown(mt, out / "model_comparison.md", "recording_segments", "conformal")
    comparison_markdown(mt, out / "model_comparison_cutoff.md", "recording_segments", "cutoff")
    mt[mt.is_main_model].to_csv(out / "operating_points.csv", index=False)
    pd.DataFrame(tails).to_csv(out / "tail_params.csv", index=False)
    pd.DataFrame(ops).to_csv(out / "thresholds_main.csv", index=False)
    checks["step2"] = step_checks
    checks["step2_all_ok"] = all(v["stream_equals_evaluation"] and v["shuffle_invariant"] and v["prediction_alarm_counts_equal_table"]
                                 and v["conformal_p_equals_threshold_alarms"] for v in step_checks.values())
    return ctx2


def step3(args, out, ctx, ctx2, checks):
    vendor, normal, abnormal = ctx["vendor"], ctx["normal"], ctx["abnormal"]
    log = lambda m: print(m, flush=True)  # noqa: E731
    rob = robustness.run(out, vendor, normal, abnormal, ctx["seg_n"], ctx["seg_a"],
                         {sid: c["state"] for sid, c in ctx2.items()}, {sid: c["stream"] for sid, c in ctx2.items()}, log=log)
    checks["step3_robustness"] = rob
    checks["step3_analysis"] = analysis.run(out, ctx2, MAIN_W, log=log)
    checks["step3_label_bypass_ok"] = rob["label_bypass_all_passed"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=D.PACKAGE_DIR, help="data/3_소성가공_예지보전/ 를 포함하는 폴더")
    ap.add_argument("--out", type=Path, default=D.PACKAGE_DIR / "outputs")
    ap.add_argument("--artifacts", type=Path, default=None, help="기본: <out>/../artifacts")
    ap.add_argument("--preprocess", choices=list(D.QUANTIZATION), default="matched")
    ap.add_argument("--no-verify", action="store_true", help="입력 해시·행 수 검증을 건너뛴다(다른 자료로 실행할 때)")
    ap.add_argument("--no-baselines", action="store_true", help="5NN·RMS5·IF·MLP-AE 생략(빠른 확인용)")
    ap.add_argument("--steps", type=int, default=3, help="실행할 단계 수 (1: 진단만, 2: 주 모델까지, 3: 강건성·오류 분석까지)")
    args = ap.parse_args(argv)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    art_dir = args.artifacts or out.parent / "artifacts"
    t0 = time.time()
    timings = {}
    ctx, checks = step1(args, out)
    timings["step1_s"] = round(time.time() - t0, 2)
    if args.steps >= 2:
        t1 = time.time()
        ctx2 = step2(args, out, art_dir, ctx, checks)
        timings["step2_s"] = round(time.time() - t1, 2)
    if args.steps >= 3:
        t2 = time.time()
        step3(args, out, ctx, ctx2, checks)
        timings["step3_s"] = round(time.time() - t2, 2)
    raw_hits = scan_outputs_for_raw_values(out)
    checks["outputs_free_of_raw_sensor_columns"] = not raw_hits
    checks["raw_column_hits"] = raw_hits
    checks["pending_steps"] = PENDING
    timings["total_s"] = round(time.time() - t0, 2)
    manifest = dict(protocol_version=D.PROTOCOL_VERSION, git_commit=git_commit(), args={k: str(v) for k, v in vars(args).items()},
                    environment=D.environment(), omp_num_threads=os.environ.get("OMP_NUM_THREADS"),
                    inputs=ctx["load_report"], timings_s=timings,
                    outputs={str(p.relative_to(out)): D.sha256_file(p) for p in sorted(out.rglob("*")) if p.is_file() and p.name != "manifest.json"})
    D.dump_json(manifest, out / "manifest.json")
    D.dump_json(checks, out / "checks.json")
    print(json.dumps(D.to_jsonable(checks), ensure_ascii=False, indent=2))
    return checks


if __name__ == "__main__":
    main()
