"""5단계(사후): 선택된 LSTM과 우리 모델을 같은 인공 주입·교락 시험으로 잰다(PROTOCOL.md 6절 강건성).

준용 tvt/04_validation과 같은 생성기(예준 v3 core.Generator)·강도·시드(11·29·47)·흐름(직전 기록 + 주입 기록)을 쓰고,
한 주입마다 v2·v2+R1·v2+R1+R2와 LSTM(선택)·LSTM+R1을 함께 채점한다. v2 계열 값은 준용 산출물과 대조해 같은 계산인지 확인한다.
- V1 전류 잔차 주입(강도 0.5·1), V1b 진동 단독 주입(대역 잡음 0.5·1, 감쇠 충격 2·4), 강도 0 = 주입 없는 대조
- V2 진폭 감소(0.75·0.5·0.25·0배, 센서별 기록 전체)
- V5 전류 이동(+81.4·+272.4), 표본화 시각 흔들림(60.6Hz, 0.05~2.4ms), 이상 기록 평균 제거
LSTM 가중치: 선택된 설정을 같은 시드로 다시 학습해 cache/models에 저장하고, 오차 요약이 캐시와 같은지(결정성) 확인한다.
출력: outputs/05_v1.csv, 05_v1_pod.csv, 05_v2_loss.csv, 05_v5.csv, 05_robustness.json
실행: PYTHONDONTWRITEBYTECODE=1 python 05_robustness.py --workers 7
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import multiprocessing as mp
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import lx_harness as H  # noqa: E402
import lx_lstm as L  # noqa: E402
import lx_scoring as X  # noqa: E402

START = ("W20-none-64x32-e300p30", "raw-last")   # 출발점 lstm20과 같은 설정


def m04():
    H.tvt()
    spec = importlib.util.spec_from_file_location("tvt_s04", H.TVT / "04_validation.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def selected_specs() -> list[dict]:
    """강건성에 넣을 LSTM: 잠근 설정의 새 시드 앙상블(e345, 주 결과)과 출발점 lstm20 설정의 시드 0·1·2 앙상블."""
    sel = json.loads((H.OUT / "02_selection.json").read_text(encoding="utf-8"))
    return [dict(label="L:e345", cfg=sel["track_L"]["cfg"], scoring=sel["track_L"]["scoring"], seeds=(3, 4, 5)),
            dict(label="start:e012", cfg=START[0], scoring=START[1], seeds=(0, 1, 2))]


def retrain_jobs(specs) -> list[dict]:
    """가중치가 없는 실행(1단계 초기 학습분)은 같은 시드로 다시 학습해 가중치를 얻고 결정성을 확인한다."""
    jobs = []
    for s in specs:
        for sid in H.SPLITS:
            for seed in s["seeds"]:
                run = X.load_run(H.CACHE / "runs" / f"{sid}_{s['cfg']}_s{seed}.npz")
                mp_ = H.CACHE / "models" / f"{sid}_{s['cfg']}_s{seed}.pt"
                if mp_.exists():
                    continue
                jobs.append(dict(sid=sid, cfg=s["cfg"], W=int(run["W"]), warm=str(run["warm"]), h1=int(run["h1"]), h2=int(run["h2"]),
                                 epochs=int(run["epochs"]), patience=int(run["patience"]), data=X.parse_cfg(s["cfg"])["data"], seed=seed,
                                 inputs=str(H.CACHE / f"inputs_{sid}.npz"), path=str(H.CACHE / "runs" / f"{sid}_{s['cfg']}_s{seed}.npz"),
                                 model_path=str(mp_), check_only=True))
    return jobs


def check_determinism(job_result: dict) -> dict:
    """다시 학습한 오차 요약이 캐시(1·2단계 학습)와 비트 단위로 같은지."""
    cached = X.load_run(H.CACHE / "runs" / f"{job_result['sid']}_{job_result['cfg']}_s{job_result['seed']}.npz")
    same = all(np.array_equal(job_result["arrays"][f"F_{k}"], cached[f"F_{k}"], equal_nan=True) for k in X.FRAMES)
    return dict(sid=job_result["sid"], cfg=job_result["cfg"], seed=job_result["seed"], identical=bool(same),
                epochs_run=job_result["epochs_run"], epochs_cached=int(cached["epochs_run"]))


class LSTMDet:
    """LSTM 변형 하나(단일 시드 또는 시드 앙상블)의 행 경보. 보정은 01_scores.calibrate와 같은 valid 정상 기록별 최대 점수."""

    def __init__(self, sid, s, seeds, label):
        self.label = label
        self.runs = [X.load_run(H.CACHE / "runs" / f"{sid}_{s['cfg']}_s{k}.npz") for k in seeds]
        r0 = self.runs[0]
        self.W, self.warm, self.scoring = int(r0["W"]), str(r0["warm"]), s["scoring"]
        self.models = [L.load_model(H.CACHE / "models" / f"{sid}_{s['cfg']}_s{k}.pt", int(r0["h1"]), int(r0["h2"])) for k in seeds]
        inp = np.load(H.CACHE / f"inputs_{sid}.npz")
        self.mean, self.scale = inp["mean"], inp["scale"]
        sv = np.mean([X.score_rows(r, self.scoring)["valid_normal"] for r in self.runs], axis=0)
        seg_vn = inp["seg_valid_normal"]
        self.cal = pd.Series(np.where(np.isfinite(sv), sv, -np.inf)).groupby(seg_vn).max().to_numpy()

    def own(self, q, seg, cp, alpha):
        z = (q[H.setup()["D"].SENSORS].to_numpy(float) - self.mean) / self.scale
        pos = np.arange(len(seg)) - L.record_starts(np.asarray(seg))
        s = np.mean([X.apply_scoring(L.frame_features(m, z, np.asarray(seg), self.W, self.warm), pos, r, self.scoring)
                     for m, r in zip(self.models, self.runs)], axis=0)
        p = cp(self.cal, s)
        return np.isfinite(p) & (p <= alpha)


def all_alarms(M, V, fin, dets, frame):
    """한 구간의 모델별 행 경보(v2 계열 + LSTM + LSTM+R1)와 기록 번호·위치."""
    lib, _, _ = H.tvt()
    r = fin.rows(frame)
    out = {v: V.Final.alarms(r, v)[0] for v in V.VARIANTS}
    q = M["D"].quantize(M["D"].inputs_only(frame.reset_index(drop=True)), "matched")
    for d in dets:
        own = d.own(q, r["seg"], M["conformal_p"], V.ALPHA)
        out[d.label] = own
        out[d.label + "+R1"] = lib.stream_rules(r["ts"], r["seg"], own, r["wave_ok"], latch=True)[0]
    return r, out


def build(sid):
    M = H.setup()
    V = m04()
    D, v3 = M["D"], M["v3"]
    M["repo"] = H.REPO
    sp = D.split_normal(M["normal"], D.segments(M["normal"]), sid)
    fin = V.fit_split(M, sp["train"], sp["cal"])
    dets = [LSTMDet(sid, s, s["seeds"], s["label"]) for s in selected_specs()]
    lib, _, _ = H.tvt()
    q_tr = D.quantize(D.inputs_only(sp["train"]), "matched")
    fit_feat = v3.features(lib.v3_records(M, q_tr, "train"))
    gen = v3.Generator(fit_feat, sid)
    test = sp["test"].reset_index(drop=True)
    recs = V.records_of(test, M)
    Xs = test[D.SENSORS].to_numpy(float)
    f_test = v3.features([V.v3_record(M, Xs[idx], k) for k, idx in enumerate(recs)])
    return M, V, sp, fin, dets, gen, test, recs, Xs, f_test


def injected(M, V, fin, dets, test, recs, k, x_new, onset):
    """기록 k를 x_new로 바꾸고 직전 기록과 함께 흘려(04_validation.eval_injected와 같은 흐름) 모델별 탐지를 본다."""
    S = M["D"].SENSORS
    idx = recs[k]
    parts = ([recs[k - 1]] if k > 0 else []) + [idx]
    sub = test.iloc[np.concatenate(parts)].reset_index(drop=True).copy()
    sub.loc[len(sub) - len(idx):, S] = x_new
    r, al = all_alarms(M, V, fin, dets, sub)
    mine = np.arange(len(sub)) >= len(sub) - len(idx)
    after = r["pos"][mine] >= max(onset, 0)
    return {m: bool((a[mine] & after).any()) for m, a in al.items()}


def job_v1(sid, family):
    M, V, sp, fin, dets, gen, test, recs, Xs, f_test = build(sid)
    rows = []
    for target in V.TARGETS[family]:
        axis = f"v{target}_rms" if target < 2 else "i_residual"
        scale = gen.scales(f_test, axis)
        for strength in (0.0,) + V.SELECTION[family]:
            for seed in (V.SEEDS if strength > 0 else V.SEEDS[:1]):
                for k, idx in enumerate(recs):
                    rec, info = gen.inject(V.v3_record(M, Xs[idx], k), family, target, strength, seed, scale[k])
                    if strength > 0 and not info["valid"]:
                        rows.append(dict(split=sid, family=family, target=target, strength=strength, seed=seed, record=k, supported=False))
                        continue
                    det = injected(M, V, fin, dets, test, recs, k, rec.x, info["onset"])
                    rows.append(dict(split=sid, family=family, target=target, strength=strength, seed=seed, record=k, supported=True,
                                     **{f"{m}|detected": v for m, v in det.items()}))
    return "v1", pd.DataFrame(rows)


def job_v2(sid):
    M, V, sp, fin, dets, gen, test, recs, Xs, f_test = build(sid)
    rows = []
    for target in (0, 1, 2):
        for mult in V.LOSS:
            for k, idx in enumerate(recs):
                rec, _ = gen.inject(V.v3_record(M, Xs[idx], k), "amplitude_decrease", target, mult, V.SEEDS[0], 1.0)
                det = injected(M, V, fin, dets, test, recs, k, rec.x, -1)
                rows.append(dict(split=sid, target=target, multiplier=mult, record=k, **{f"{m}|detected": v for m, v in det.items()}))
    return "loss", pd.DataFrame(rows)


def rate_rows(M, V, fin, dets, frame, keep=None):
    r, al = all_alarms(M, V, fin, dets, frame)
    seg = np.asarray(r["seg"])
    m = np.ones(len(seg), bool) if keep is None else keep
    return {k: (int(pd.Series(a[m]).groupby(seg[m]).max().sum()), int(len(np.unique(seg[m])))) for k, a in al.items()}


def job_v5(sid):
    """04_validation.v5_confound와 같은 생성(전류 이동, 60.6Hz 시각 흔들림 같은 난수 순서, 이상 평균 제거)."""
    M, V, sp, fin, dets, gen, test, recs, Xs, f_test = build(sid)
    D = M["D"]
    rows = []
    for shift in (0.0, 81.4, 272.4):
        f = test.copy()
        f[D.SENSORS[2]] = f[D.SENSORS[2]] + shift
        for mname, (hit, n) in rate_rows(M, V, fin, dets, f).items():
            rows.append(dict(split=sid, test="current_shift", level=shift, model=mname, alerted=hit, records=n, rate=hit / n))
    sys.path.insert(0, str(H.REPO / "yejun/analysis/press_evidence"))
    import diagnostic_probes as probes
    from press.diagnosis import sine_fit
    seg_all = D.segments(M["normal"])
    test_start = D.SPLITS[sid][2]
    tst = M["normal"][seg_all >= test_start].reset_index(drop=True)
    seg = seg_all[seg_all >= test_start]
    x0 = tst[D.SENSORS[2]].to_numpy(float)
    lengths = pd.Series(seg).value_counts()
    fits = {}
    for s in sorted(lengths[lengths >= 17].index):
        idx = np.flatnonzero(seg == s)
        fr = sine_fit(x0[idx])[0]
        coef = probes.tone_coefficients(x0[idx], fr)
        fits[s] = (idx, fr, coef, x0[idx] - probes.tone_design(len(idx), fr) @ coef)
    keep_rows = np.isin(seg, list(fits))
    for frequency_hz, sigma_ms in probes.JITTER_CONDITIONS:
        if frequency_hz not in (None, 60.6):
            continue
        rng = np.random.default_rng(probes.JITTER_SEED)
        repeats = probes.JITTER_REPEATS if sigma_ms > 0 else 1
        counts = {}
        for _ in range(repeats):
            x = x0.copy()
            for s, (idx, f0, coef, residual) in fits.items():
                phase = 2 * np.pi * f0 * np.arange(len(idx)) * .1
                if sigma_ms > 0:
                    phase = phase + 2 * np.pi * frequency_hz * rng.normal(0, sigma_ms / 1e3, len(idx))
                x[idx] = coef[0] * np.cos(phase) + coef[1] * np.sin(phase) + coef[2] + residual
            frame = tst.copy()
            frame[D.SENSORS[2]] = x
            for mname, (hit, n) in rate_rows(M, V, fin, dets, frame, keep_rows).items():
                c = counts.setdefault(mname, [0, 0])
                c[0] += hit
                c[1] += n
        for mname, (hit, n) in counts.items():
            rows.append(dict(split=sid, test="jitter_60.6Hz", level=sigma_ms, model=mname, alerted=hit, records=n, rate=hit / n))
    _, aseg = M["guard"].layout(M["abnormal"])
    for mode, cols in (("none", []), ("current_mean_removed", [D.SENSORS[2]]), ("all_means_removed", D.SENSORS)):
        f = M["abnormal"].copy()
        for c in cols:
            f[c] = f[c] - f.groupby(aseg)[c].transform("mean")
        for mname, (hit, n) in rate_rows(M, V, fin, dets, f).items():
            rows.append(dict(split=sid, test="abnormal_mean_removal", level=mode, model=mname, alerted=hit, records=n, rate=hit / n))
    return "v5", pd.DataFrame(rows)


def run_job(args):
    kind, sid, fam = args
    if kind == "v1":
        return job_v1(sid, fam)
    if kind == "v2":
        return job_v2(sid)
    return job_v5(sid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=7)
    a = ap.parse_args()
    t0 = time.time()
    specs = selected_specs()
    print("강건성 대상 LSTM:", specs, flush=True)
    det_check = []
    jobs = retrain_jobs(specs)
    if jobs:
        with ProcessPoolExecutor(max_workers=a.workers, mp_context=mp.get_context("spawn")) as ex:
            for f in as_completed([ex.submit(L.run, j) for j in jobs]):
                det_check.append(check_determinism(f.result()))
        print("재학습 결정성:", det_check, flush=True)
    work = [("v1", s, fam) for s in H.SPLITS for fam in ("band_noise", "damped_impulse", "current_residual")] + \
           [("v2", s, None) for s in H.SPLITS] + [("v5", s, None) for s in H.SPLITS]
    res = {"v1": [], "loss": [], "v5": []}
    with ProcessPoolExecutor(max_workers=a.workers, mp_context=mp.get_context("spawn")) as ex:
        futs = {ex.submit(run_job, w): w for w in work}
        for f in as_completed(futs):
            kind, df = f.result()
            res[kind].append(df)
            print("완료", futs[f], f"{time.time() - t0:.0f}s", flush=True)
    v1 = pd.concat(res["v1"], ignore_index=True)
    loss = pd.concat(res["loss"], ignore_index=True)
    v5 = pd.concat(res["v5"], ignore_index=True)
    v1.to_csv(H.OUT / "05_v1.csv", index=False)
    loss.to_csv(H.OUT / "05_v2_loss.csv", index=False)
    v5.to_csv(H.OUT / "05_v5.csv", index=False)
    det_cols = [c for c in v1.columns if c.endswith("|detected")]
    sup = v1[v1.supported]
    pod = sup.groupby(["split", "family", "target", "strength"])[det_cols].mean().reset_index()
    pod.to_csv(H.OUT / "05_v1_pod.csv", index=False)
    lpod = loss.groupby(["split", "target", "multiplier"])[[c for c in loss.columns if c.endswith("|detected")]].mean().reset_index()
    # v2 계열이 준용 04 산출물과 같은 계산인지
    ref_pod = pd.read_csv(H.TVT / "outputs/validation_v1_pod.csv")
    chk = pod.merge(ref_pod, on=["split", "family", "target", "strength"], suffixes=("", "_ref"))
    v2_same = {v: bool(np.allclose(chk[f"{v}|detected"], chk[f"{v}|detected_ref"])) for v in ("v2", "v2+R1", "v2+R1+R2")}
    ref_v5 = pd.read_csv(H.TVT / "outputs/validation_v5.csv")
    m5 = v5[v5.model.isin(["v2", "v2+R1", "v2+R1+R2"])].merge(ref_v5.rename(columns={"variant": "model"}),
                                                                on=["split", "test", "level", "model"], suffixes=("", "_ref"))
    v5_same = bool((m5.alerted == m5.alerted_ref).all()) if len(m5) else None
    summary = dict(specs=specs, determinism=det_check, v2_matches_tvt_validation=dict(v1_pod=v2_same, v5=v5_same, v5_cells=int(len(m5))),
                   v2_loss_pod=lpod.round(4).to_dict("records"), seconds=round(time.time() - t0, 1))
    H.dump(summary, H.OUT / "05_robustness.json")
    pd.set_option("display.width", 260)
    print(json.dumps({k: summary[k] for k in ("determinism", "v2_matches_tvt_validation")}, ensure_ascii=False, indent=1, default=str))
    print(pod.round(3).to_string(index=False))
    print(lpod.round(3).to_string(index=False))
    print(v5.round(4).to_string(index=False))
    print(f"{summary['seconds']}s")


if __name__ == "__main__":
    main()
