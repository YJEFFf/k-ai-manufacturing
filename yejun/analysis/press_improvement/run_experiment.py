"""고정된 소수 후보의 탐색 실험. 기존 주 모델·동결 기대값·artifact는 변경하지 않는다.

정상 자료로만 적합·보정한다. 이미 본 이상 자료를 재평가하므로 독립 검증이 아니다.
실행: OMP_NUM_THREADS=1 python analysis/press_improvement/run_experiment.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

os.environ.setdefault("OMP_NUM_THREADS", "1")
HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parents[1] / "press_submission"
sys.path.insert(0, str(PACKAGE))

import numpy as np
import pandas as pd

from press import data as D
from press.calibrate import ALPHAS, conformal_p, segment_max, thresholds_for
from press.evaluate import evaluate_models
from press.field import LoadNormalizer, persistence_score
from press.scores import ExpTail, Scorer
from press.validation import code_sha256


PROTOCOL = "exploratory-performance-v1"
CANDIDATES = {
    "baseline_w8": "기존: max(g_maxz3, g_sine8)",
    "loadnorm_w8": "기존: max(17관측 진폭 보정, 부족한 행은 max-z로 보완, g_sine8)",
    "baseline_persist2of3": "기존: 기본 결합 점수의 최근 3점 중 두 번째 큰 값으로 재보정",
    "loadnorm_persist2of3": "진폭 보정 결합 점수의 최근 3점 중 두 번째 큰 값으로 재보정",
    "magnitude_persist2of3": "max(최근 3점 중 두 번째 큰 g_maxz3, g_sine8)",
    "loadnorm_magnitude_persist2of3": "max(최근 3점 중 두 번째 큰 진폭 보정 크기 성분, g_sine8)",
    "early_w5_to_w8": "구간 위치 0~6에는 g_sine5, 위치 7부터는 g_sine8을 max-z와 결합",
    "early_w6_to_w8": "구간 위치 0~6에는 g_sine6, 위치 7부터는 g_sine8을 max-z와 결합",
}


class CandidateScorer:
    def __init__(self, train, seg, vendor):
        self.base = Scorer(train, seg, vendor, wins=(5, 6, 8), baselines=False)
        self.load = LoadNormalizer(train, seg)
        self.load_tail = ExpTail(self.load.ref)
        assert self.load_tail.ok and self.base.tail_z3.ok
        assert all(tail.ok for tail in self.base.tail_sine.values())

    def score(self, frame, seg):
        comp, _ = self.base.components(frame, seg)
        gz, gs = comp["g_maxz3"], comp["g_sine_8"]
        residual = self.load_tail(self.load.score(frame, seg))
        magnitude = np.where(np.isfinite(residual), residual, gz)
        basic, normalized = np.fmax(gz, gs), np.fmax(magnitude, gs)
        p23 = lambda x: persistence_score(x, seg, 2, 3)
        pos, _ = D.segment_positions(seg)
        result = {
            "baseline_w8": basic,
            "loadnorm_w8": normalized,
            "baseline_persist2of3": p23(basic),
            "loadnorm_persist2of3": p23(normalized),
            "magnitude_persist2of3": np.fmax(p23(gz), gs),
            "loadnorm_magnitude_persist2of3": np.fmax(p23(magnitude), gs),
            **{f"early_w{w}_to_w8": np.fmax(gz, np.where(pos < 7, comp[f"g_sine_{w}"], gs))
               for w in (5, 6)},
        }
        assert result.keys() == CANDIDATES.keys()
        return result


def independent_check(metrics, model_scores, segs):
    for r in metrics[metrics.criterion.eq("conformal")].itertuples():
        sc = model_scores[r.model]
        normal = np.isfinite(sc["test"]) & (sc["test"] > r.threshold)
        abnormal = np.isfinite(sc["abn"]) & (sc["abn"] > r.threshold)
        nn = sum(bool(normal[segs["test"] == s].any()) for s in np.unique(segs["test"]))
        na = sum(bool(abnormal[segs["abn"] == s].any()) for s in np.unique(segs["abn"]))
        fp, tp, fn = int(normal.sum()), int(abnormal.sum()), int((~abnormal).sum())
        assert (nn, na, fp, tp, fn) == (r.normal_notified_segments, r.abnormal_notified_segments, r.fp, r.tp, r.fn)
        assert abs(2 * tp / (2 * tp + fp + fn) - r.f1_all_rows) < 1e-12
        for part, alarm in (("test", normal), ("abn", abnormal)):
            p = conformal_p(segment_max(sc["cal"], segs["cal"]), sc[part])
            assert np.array_equal(np.nan_to_num(p, nan=1.0) <= r.alpha, alarm)


def snapshot(root):
    return {str(p.relative_to(root)): D.sha256_file(p) for p in sorted(root.rglob("*")) if p.is_file()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=PACKAGE)
    ap.add_argument("--out", type=Path, default=HERE)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    source_hashes = {name: snapshot(PACKAGE / name) for name in ("outputs", "artifacts")}
    config = dict(protocol=PROTOCOL, candidates=CANDIDATES, fit_preprocess="matched",
                  eval_preprocess=["matched", "raw", "coarse"], alpha=list(ALPHAS),
                  calibration="normal recording-segment maxima, separately calibrated per candidate",
                  new_candidate_count=5, reference_candidate_count=3,
                  exploration_only=True, baseline_not_replaced=True)
    # 평가 전에 후보 집합을 기록하고 실행 도중 추가하거나 바꾸지 않는다.
    D.dump_json(config, args.out / "config.json")
    normal, abnormal, load_report = D.load(args.root)
    vendor = D.load_vendor()
    seg_n = D.segments(normal)
    metrics_list, checks = [], {"prefix_invariant": {}, "reference_tables_equal": {}}
    for sid in D.SPLITS:
        split = D.split_normal(normal, seg_n, sid)
        train = D.quantize(split["train"], "matched")
        model = CandidateScorer(train, D.segments(train), vendor)
        frames = {part: D.quantize(split[part], "matched") for part in ("cal", "test")}
        frames["abn"] = D.quantize(abnormal, "matched")
        segs = {part: D.segments(frame) for part, frame in frames.items()}
        scores = {part: model.score(frame, segs[part]) for part, frame in frames.items()}
        by_model = {name: {part: scores[part][name] for part in frames} for name in CANDIDATES}
        # 모든 후보에서 미래 행이 기존 점수에 섞이지 않는지 실제 추론 경로로 확인한다.
        prefix = frames["abn"].iloc[:40].copy()
        prefix_scores = model.score(prefix, D.segments(prefix))
        for name in CANDIDATES:
            np.testing.assert_allclose(prefix_scores[name], scores["abn"][name][:40], rtol=0, atol=1e-12, equal_nan=True)
        checks["prefix_invariant"][sid] = True
        frozen = {(name, "recording_segments"): thresholds_for(segment_max(sc["cal"], segs["cal"]), "recording_segments")
                  for name, sc in by_model.items()}
        for variant in config["eval_preprocess"]:
            if variant == "matched":
                current_frames, current_scores = frames, by_model
            else:
                current_frames = dict(frames, test=D.quantize(split["test"], variant), abn=D.quantize(abnormal, variant))
                changed = {part: model.score(current_frames[part], segs[part]) for part in ("test", "abn")}
                current_scores = {name: dict(cal=by_model[name]["cal"], **{part: changed[part][name] for part in changed})
                                  for name in CANDIDATES}
            metrics, _ = evaluate_models(vendor, split["name"], "matched", current_scores,
                                         current_frames, segs, threshold_override=frozen, units=("recording_segments",))
            independent_check(metrics, current_scores, segs)
            metrics["split_id"], metrics["eval_preprocess"] = sid, variant
            metrics_list.append(metrics)
        print(f"split {sid}: {len(CANDIDATES)} candidates × 3 input variants done", flush=True)

    all_metrics = pd.concat(metrics_list, ignore_index=True)
    for name, (file, original_model) in {
        "baseline_w8": ("operating_points.csv", "combined_w8"),
        "loadnorm_w8": ("load_normalization.csv", "loadnorm_resid_plus_sine"),
        "baseline_persist2of3": ("persistence.csv", "persist_k2n3"),
    }.items():
        expected = pd.read_csv(PACKAGE / "outputs" / file)
        expected = expected[expected.model.eq(original_model) & expected.calibration_unit.eq("recording_segments")]
        actual = all_metrics[all_metrics.model.eq(name) & all_metrics.eval_preprocess.eq("matched")]
        keys = ["split", "criterion", "alpha"]
        columns = ["normal_notified_segments", "abnormal_notified_segments", "fp", "fn", "tp", "tn", "f1_all_rows",
                   "threshold", "abnormal_row_coverage", "normal_row_coverage", "delay_median_s", "delay_p90_s", "delay_max_s"]
        pd.testing.assert_frame_equal(actual.sort_values(keys)[keys + columns].reset_index(drop=True),
                                      expected.sort_values(keys)[keys + columns].reset_index(drop=True),
                                      check_dtype=False, rtol=0, atol=1e-8)
        checks["reference_tables_equal"][name] = True
    checks["independent_counts_and_pvalues"] = True
    checks["source_outputs_and_artifacts_unchanged"] = all(snapshot(PACKAGE / n) == h for n, h in source_hashes.items())
    assert checks["source_outputs_and_artifacts_unchanged"]
    all_metrics.to_csv(args.out / "candidate_metrics.csv", index=False)
    selected = all_metrics[all_metrics.criterion.eq("conformal") & all_metrics.alpha.eq(.01)].copy()
    selected.to_csv(args.out / "conformal_1pct.csv", index=False)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=HERE, text=True).strip()
    D.dump_json(dict(config=config, baseline_commit=head, package_code_sha256=code_sha256(),
                     script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                     inputs=load_report, environment=D.environment(), elapsed_s=round(time.monotonic() - started, 2),
                     checks=checks,
                     outputs={n: D.sha256_file(args.out / n) for n in ("config.json", "candidate_metrics.csv", "conformal_1pct.csv")}),
                args.out / "experiment_manifest.json")
    display = selected[selected.eval_preprocess.eq("matched")]
    print(display[["split_id", "model", "normal_notified_segments", "abnormal_notified_segments", "fp", "fn",
                   "f1_all_rows", "abnormal_row_coverage", "delay_median_s", "delay_max_s"]].to_string(index=False))


if __name__ == "__main__":
    main()
