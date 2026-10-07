"""16단계(사후, test 채점 이후): 표본 시각 흔들림 반증과 잠금 모델 v2+R1·Ridge 예측 오차 병행(보고서 2.6·3.6·4.2절 †). 선택·잠금·2단계 규칙 추가에는 쓰지 않는다.

(A) 표본 시각 흔들림 반증: "이상일의 전류 파형 붕괴는 고장이 아니라 수집 시각 문제 아니냐"에 답한다. 04 V5 ②(예준 jitter_stress)와 같은 생성으로
    분할 B test 정상 기록(17행 이상)의 전류 사인 성분을 60.6 Hz 앨리어싱 가정의 시각 흔들림(σ ms)으로 다시 그리고(잔차는 그대로, 반복 5회),
    기록 전체 사인 적합 R²(= 기록 끝 행의 prefix R², cases 특징 cur_sine_r2와 같은 정의) 중앙값, 전류 치우침(절편/진폭) 중앙값,
    v2 파형 성분이 켜진 기록 비율, v2 경보 기록 비율을 잰다. 이상 기록(10행 이상)의 R² 중앙값(보고서 3.1절 0.095)과 같은 코드로 비교한다.
(B) 1단계 병행: 잠금 모델 v2+R1과 14의 Ridge 예측 오차(같은 학습·보정, α 1%)의 행 경보를 OR로 묶는다(Ridge 단독, Ridge+R1 OR도).
    test 실시간 행 F1·정상 오경보 행·기록(01·03과 같은 흐름: 정상 valid→test, 이상 21기록 전체), 분할 B α 5% 고부하 정상 오경보 기록(valid+test, 14와 같은 정의),
    09·14와 같은 인공 주입(전류 파형 강도 1, 진동 단독 대역 잡음 1·감쇠 충격 4)의 기록 단위 탐지율. 주입 탐지의 v2는 09 ablation_injection.csv의 기록별 값을 쓰고
    (v2+R1의 단일 기록 주입 탐지가 v2와 같은지는 04 validation_v1.csv로 확인), Ridge는 14와 같은 주입으로 다시 잰다.
출력: outputs/jitter_ridge_combo.json
실행: python code/press/tvt/16_jitter_ridge_combo.py --repo <팀 레포>
"""
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from evalcore import own_alarm
from lib import CACHE, OUT, PRIMARY_ALPHA, SPLITS, f1_counts, repo_arg, setup, sine_r2, stream_rules, v3_records


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


S01, V04, S14 = _load("tvt_s01", "01_scores.py"), _load("tvt_v04", "04_validation.py"), _load("tvt_s14", "14_baseline_injection_ridge.py")
ALPHA = V04.ALPHA
SIGMAS_MS = (0.0, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0)
ABN_R2 = 0.0947        # 보고서 3.1절 이상 기록(10행 이상) R² 중앙값(cases/outputs/feature_separation.csv)
INJ = (("current_residual", 2, 1.0), ("band_noise", 0, 1.0), ("band_noise", 1, 1.0), ("damped_impulse", 0, 4.0), ("damped_impulse", 1, 4.0))
COMBOS = ("v2+R1", "ridge", "ridge+R1", "v2+R1|ridge", "v2+R1|ridge+R1")


def _fit_offset(x):
    """F0 고정 사인 적합의 (R², 절편/진폭). cases.common.sine_fit과 같은 계산."""
    n = np.arange(len(x))
    F0 = 0.6064 / 10
    X = np.column_stack([np.ones(len(x)), np.sin(2 * np.pi * F0 * n), np.cos(2 * np.pi * F0 * n)])
    b, *_ = np.linalg.lstsq(X, x, rcond=None)
    amp = float(np.hypot(b[1], b[2]))
    return sine_r2(x), (b[0] / amp if amp > 0 else np.nan)


# ---------------------------------------------------------------- (A)
def jitter_refutation(M, normal, abnormal):
    D = M["D"]
    sys.path.insert(0, str(M["repo"] / "yejun/analysis/press_evidence"))
    import diagnostic_probes as probes
    from press.diagnosis import sine_fit
    sid = "B"
    sp = D.split_normal(normal, D.segments(normal), sid)
    fin = V04.fit_split(M, sp["train"], sp["cal"])
    test_start = D.SPLITS[sid][2]
    seg_all = D.segments(normal)
    test = normal[seg_all >= test_start].reset_index(drop=True)
    seg = seg_all[seg_all >= test_start]
    x0 = test[D.SENSORS[2]].to_numpy(float)
    lengths = pd.Series(seg).value_counts()
    fits = {}   # 04 V5 ②와 같은 분해: 기록 → (행 번호, 주파수, 사인 계수, 잔차)
    for s in sorted(lengths[lengths >= 17].index):
        idx = np.flatnonzero(seg == s)
        fr = sine_fit(x0[idx])[0]
        coef = probes.tone_coefficients(x0[idx], fr)
        fits[s] = (idx, fr, coef, x0[idx] - probes.tone_design(len(idx), fr) @ coef)
    keep = np.isin(seg, list(fits))
    sub = test[keep].reset_index(drop=True)          # 흔들림을 넣는 기록만 채점한다(기록끼리는 원래 시각 간격으로 떨어져 있다)
    seg_k = seg[keep]
    cp = M["conformal_p"]

    def measure(x_keep):
        frame = sub.copy()
        frame[D.SENSORS[2]] = x_keep
        q = D.quantize(D.inputs_only(frame), "matched")
        cur = q[D.SENSORS[2]].to_numpy(float)
        r2s, offs = zip(*[_fit_offset(cur[seg_k == s]) for s in pd.unique(seg_k)])
        _, lseg = M["guard"].layout(frame)
        comp = fin.model.components(q, lseg)
        pw, pa = cp(fin.model.cal, comp["g_waveform"]), cp(fin.model.cal, comp["score"])
        wave = pd.Series(np.isfinite(pw) & (pw <= ALPHA)).groupby(lseg).max()
        alarm = pd.Series(np.isfinite(pa) & (pa <= ALPHA)).groupby(lseg).max()
        return np.array(r2s), np.array(offs), float(wave.mean()), float(alarm.mean())

    rows = []
    for sigma in SIGMAS_MS:
        rng = np.random.default_rng(probes.JITTER_SEED)
        reps = probes.JITTER_REPEATS if sigma > 0 else 1
        R2, OFF, W, A = [], [], [], []
        for _ in range(reps):
            x = x0.copy()
            for s, (idx, f0, coef, residual) in fits.items():
                phase = 2 * np.pi * f0 * np.arange(len(idx)) * .1
                if sigma > 0:
                    phase = phase + 2 * np.pi * 60.6 * rng.normal(0, sigma / 1e3, len(idx))
                x[idx] = coef[0] * np.cos(phase) + coef[1] * np.sin(phase) + coef[2] + residual
            r2, off, w, a = measure(x[keep])
            R2.append(r2); OFF.append(off); W.append(w); A.append(a)
        R2, OFF = np.concatenate(R2), np.concatenate(OFF)
        rows.append(dict(sigma_ms=sigma, repeats=reps, records=int(len(fits)), r2_median=float(np.median(R2)),
                         r2_q25=float(np.quantile(R2, .25)), r2_below_abn_share=float((R2 <= ABN_R2).mean()),
                         abs_offset_ratio_median=float(np.median(np.abs(OFF))), wave_fired_record_rate=float(np.mean(W)),
                         v2_alarm_record_rate=float(np.mean(A))))
        print(f"  σ {sigma} ms: R² 중앙값 {rows[-1]['r2_median']:.3f}, 파형 켜진 기록 {rows[-1]['wave_fired_record_rate']:.3f}", flush=True)
    # 이상 기록(10행 이상)을 같은 코드로
    qa = D.quantize(D.inputs_only(abnormal), "matched")
    _, aseg = M["guard"].layout(abnormal)
    cur = qa[D.SENSORS[2]].to_numpy(float)
    ab = [_fit_offset(cur[aseg == s]) for s in pd.unique(aseg) if (aseg == s).sum() >= 10]
    ab_r2, ab_off = np.array([a for a, _ in ab]), np.array([b for _, b in ab])
    t = pd.DataFrame(rows)
    hit = t[t.r2_median <= float(np.median(ab_r2))]
    return dict(split=sid, sigmas=rows,
                abnormal=dict(records_ge10=int(len(ab)), r2_median=float(np.median(ab_r2)), abs_offset_ratio_median=float(np.median(np.abs(ab_off)))),
                sigma_ms_reaching_abnormal_r2=(float(hit.sigma_ms.min()) if len(hit) else None),
                sampling_interval_ms=100.0)


# ---------------------------------------------------------------- (B)
def ridge_table(M, normal, abnormal, sid, r2):
    """14와 같은 Ridge 학습·보정으로 01 캐시 표에 ridge 열을 붙인다."""
    D = M["D"]
    sp = D.split_normal(normal, D.segments(normal), sid)
    fin = V04.fit_split(M, sp["train"], sp["cal"])
    q_tr, seg_tr, _ = S01.frame_rows(M, sp["train"], "train", "normal")
    ridge = S14.RidgeForecast(fin.model.mean, fin.model.scale).fit(q_tr, seg_tr, D)

    def score(frame):
        frame = frame.reset_index(drop=True)
        _, seg = M["guard"].layout(frame)
        q = D.quantize(D.inputs_only(frame), "matched")
        return ridge.score(q, seg, D), fin.model.components(q, seg)["score"], seg, D.segment_positions(seg)[0]

    t = pd.read_pickle(CACHE / f"rows_{sid}.pkl")
    parts = {"valid_normal": score(sp["cal"]), "test_normal": score(sp["test"]), "abnormal": score(abnormal)}
    v2 = np.concatenate([p[1] for p in parts.values()])
    assert len(v2) == len(t) and np.nanmax(np.abs(v2 - t["v2|score"].to_numpy(float))) < 1e-9, "01 캐시와 행 순서 불일치"
    cal, pf, loo = S01.calibrate(M, parts["valid_normal"][0], parts["valid_normal"][2], {k: v[0] for k, v in parts.items()})
    t["ridge|p_full"] = np.concatenate([pf[k] for k in parts])
    t["ridge|p_loo"] = np.concatenate([loo, np.full(len(t) - len(loo), np.nan)])
    return t, sp, ridge, cal


def stream_alarms(t, alpha, regime, r2, subsets=("normal", "abnormal")):
    """evalcore._streams와 같은 흐름으로 조합별 실시간 경보를 낸다. 반환: subset → (흐름 행 표, 조합 → 경보, 채점 마스크)."""
    parts = ["valid"] if regime == "valid" else ["valid", "test"]
    scored = "valid" if regime == "valid" else "test"
    out = {}
    for subset in subsets:
        stream = ((t.subset == subset) & t.part.isin(parts)).to_numpy()
        sub = t.loc[stream]
        ts, rec, wave = sub.ts.to_numpy(), sub.rec.to_numpy(), sub.prefix_r2.to_numpy() >= r2
        own_v2 = own_alarm(t, stream, "v2", alpha, regime, False, r2)
        own_r = own_alarm(t, stream, "ridge", alpha, regime, False, r2)
        v2r1 = stream_rules(ts, rec, own_v2, wave, True)[0]
        rr1 = stream_rules(ts, rec, own_r, wave, True)[0]
        al = {"v2+R1": v2r1, "ridge": own_r, "ridge+R1": rr1, "v2+R1|ridge": v2r1 | own_r, "v2+R1|ridge+R1": v2r1 | rr1}
        out[subset] = (sub, al, (sub.part == scored).to_numpy())
    return out


def test_metrics(t, r2):
    st = stream_alarms(t, PRIMARY_ALPHA, "test", r2)
    res = {}
    for c in COMBOS:
        y = np.concatenate([st[s][0].label.to_numpy()[st[s][2]] == 1 for s in st])
        a = np.concatenate([st[s][1][c][st[s][2]] for s in st])
        f = f1_counts(y, a)
        sub, al, keep = st["normal"]
        fa_rec = int(pd.Series(al[c][keep]).groupby(sub.rec.to_numpy()[keep]).max().sum())
        res[c] = dict(test_f1=f["f1"], miss_rows=f["fn"], fa_rows=f["fp"], fa_records=fa_rec, normal_records=int(sub.rec[keep].nunique()))
    return res


def high_load(t, r2):
    """14 high_load_fa와 같은 정의(분할 B, α 5%, valid+test 정상, 06의 busy_high)."""
    st_map = pd.read_csv(S14.REGIME_CSV, encoding="utf-8-sig").set_index("rec").state
    tr_end, va_end = SPLITS["B"]
    hit = {c: [] for c in COMBOS}
    for regime in ("valid", "test"):
        sub, al, keep = stream_alarms(t, 0.05, regime, r2, subsets=("normal",))["normal"]
        rec = sub.rec.to_numpy()[keep]
        for c in COMBOS:
            for r, a in pd.Series(al[c][keep]).groupby(rec).max().items():
                part, _, k = r.split(":")
                hit[c].append((int(k) + (tr_end if part == "valid" else va_end), bool(a)))
    out = {}
    for c, h in hit.items():
        h = pd.DataFrame(h, columns=["rec", "alarm"]).assign(state=lambda d: d.rec.map(st_map))
        hi = h[h.state == "busy_high"]
        out[c] = dict(fa_records=int(hi.alarm.sum()), records=int(len(hi)), all_fa_records=int(h.alarm.sum()), all_records=int(len(h)))
    return out


def injection(M, sp, ridge, cal, sid):
    """14와 같은 주입으로 Ridge 기록 탐지를 다시 재고, 09의 v2 기록 탐지와 기록별로 OR한다."""
    D, v3 = M["D"], M["v3"]
    test = sp["test"].reset_index(drop=True)
    recs = V04.records_of(test, M)
    S = D.SENSORS
    X = test[S].to_numpy(float)
    q_tr = D.quantize(D.inputs_only(sp["train"]), "matched")
    gen = v3.Generator(v3.features(v3_records(M, q_tr, "train")), sid)
    f_test = v3.features([V04.v3_record(M, X[idx], k) for k, idx in enumerate(recs)])
    rows = []
    for fam, target, smax in ((INJ[0][0], INJ[0][1], 0.0),) + INJ:
        axis = f"v{target}_rms" if target < 2 else "i_residual"
        scale = gen.scales(f_test, axis)
        for seed in (V04.SEEDS if smax > 0 else V04.SEEDS[:1]):
            Xn, onset, ok = X.copy(), np.zeros(len(recs), int), np.ones(len(recs), bool)
            for k, idx in enumerate(recs):
                rec, info = gen.inject(V04.v3_record(M, X[idx], k), fam, target, smax, seed, scale[k])
                if smax > 0 and not info["valid"]:
                    ok[k] = False
                    continue
                Xn[idx], onset[k] = rec.x, max(info["onset"], 0)
            frame = test.copy()
            frame[S] = Xn
            _, seg = M["guard"].layout(frame)
            q = D.quantize(D.inputs_only(frame), "matched")
            pos = D.segment_positions(seg)[0]
            p = M["conformal_p"](cal, ridge.score(q, seg, D))
            a = np.isfinite(p) & (p <= ALPHA)
            rows += [dict(split=sid, family=fam, target=target, strength=smax, seed=seed, record=k,
                          ridge=bool(ok[k] and (a[idx] & (pos[idx] >= onset[k])).any())) for k, idx in enumerate(recs)]
    return pd.DataFrame(rows)


def main():
    t0 = time.time()
    repo = repo_arg()
    M = setup(repo)
    M["repo"] = repo
    normal, abnormal, _ = M["D"].load(repo / "yejun/press_submission")
    smeta = json.loads((OUT / "tvt_scores_meta.json").read_text(encoding="utf-8"))
    r2 = {s: smeta[s]["r2_ref"] for s in SPLITS}
    print("(A) 표본 시각 흔들림 …", flush=True)
    res = {"A_jitter": jitter_refutation(M, normal, abnormal)}
    print("(B) v2+R1 · Ridge 병행 …", flush=True)
    ref = json.loads((OUT / "ridge_baseline.json").read_text(encoding="utf-8"))["ridge"]
    abl = pd.read_csv(OUT / "ablation_injection.csv")
    v1 = pd.read_csv(OUT / "validation_v1.csv")
    met, inj, tables = {}, [], {}
    for sid in SPLITS:
        t, sp, ridge, cal = ridge_table(M, normal, abnormal, sid, r2[sid])
        tables[sid] = t
        met[sid] = test_metrics(t, r2[sid])
        # 확인: 14·03과 같은 값
        assert abs(met[sid]["ridge"]["test_f1"] - ref[sid]["ridge"]["test_f1"]) < 1e-12, (sid, "Ridge F1이 14와 다름")
        assert abs(met[sid]["ridge+R1"]["test_f1"] - ref[sid]["ridge+R1"]["test_f1"]) < 1e-12, (sid, "Ridge+R1 F1이 14와 다름")
        inj.append(injection(M, sp, ridge, cal, sid))
        print(sid, "완료", {c: round(v["test_f1"], 4) for c, v in met[sid].items()}, flush=True)
    assert abs(met["A"]["v2+R1"]["test_f1"] - 1.0) < 1e-12 and met["B"]["v2+R1"]["fa_rows"] == 3, "잠금 모델 값이 03과 다름"
    hl = high_load(tables["B"], r2["B"])
    assert (hl["v2+R1"]["records"], hl["ridge"]["fa_records"]) == (53, 2), hl
    # 주입: v2(09 기록별) OR Ridge. v2+R1의 단일 기록 주입 탐지가 v2와 같은지 04로 확인
    inj = pd.concat(inj, ignore_index=True)
    key = ["split", "family", "target", "strength", "seed", "record"]
    m = inj.merge(abl[key + ["v2"]], on=key, how="left")
    assert m.v2.notna().all(), "09 기록과 짝이 안 맞음"
    vv = v1.merge(inj[key], on=key)
    same_r1 = int((vv["v2|detected"] == vv["v2+R1|detected"]).sum())
    m["v2+R1|ridge"] = m.v2.astype(bool) | m.ridge
    rate = m.groupby(["split", "family", "target", "strength"])[["v2", "ridge", "v2+R1|ridge"]].mean().round(4).reset_index()
    bi = pd.read_csv(OUT / "baseline_injection.csv")
    chk = rate.merge(bi[["split", "family", "target", "strength", "ridge"]], on=["split", "family", "target", "strength"], suffixes=("", "_14"))
    assert (chk.ridge - chk.ridge_14).abs().max() < 1e-4, "Ridge 주입 탐지가 14와 다름"
    res["B_combo"] = dict(test=met, high_load_B_a5_valid_test=hl, injection=rate.to_dict("records"),
                          v2_vs_v2R1_single_record_injection=dict(records=int(len(vv)), same=same_r1))
    res["runtime_s"] = round(time.time() - t0, 1)
    (OUT / "jitter_ridge_combo.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
