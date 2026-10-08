"""4단계: "다 맞았지만 의심했다". 최종 모델 v2+R1+R2를 예준 v3 방식으로 검증한다(보고서 2.6절 검증표, 3.3절 실패 조건).

판정 기준은 실행 전에 팀 계획 문서(제출본에는 넣지 않음)에 고정했다. 모든 실험은 test 채점 이후에 하고 같은 test 정상 기록을 쓴다.
V5 교락 대조(전류 수준 이동 +81.4·+272.4 / 표본화 시각 흔들림 0.1 ms·60.6 Hz / 이상 기록 평균 제거), V1 단일 기록 주입(예준 core.Generator,
seed 11·29·47; 전류 잔차 → V1, 진동 → V1b), V1a R1 동작·V1a′ R1 비용, V2 진폭 감소, V3 분할 강건성(P2 분 단위 + 시간순 5창).
대상: v2, v2+R1, v2+R1+R2(최종), v3 B1(기록 단위). α 1%. 출력: outputs/validation_*.csv, outputs/validation_summary.json
실행(제출본 루트에서): python code/press/tvt/04_validation.py --repo .
"""
import json
import sys

import numpy as np
import pandas as pd

from lib import OUT, R2_Q, SPLITS, f1_counts, ns_time, prefix_r2, repo_arg, setup, stream_rules, v3_records

ALPHA = 0.01
SEEDS = (11, 29, 47)
SELECTION = {"band_noise": (0.5, 1.0), "damped_impulse": (2.0, 4.0), "current_residual": (0.5, 1.0)}  # 주입 종류 → 강도(예준 selection)
TARGETS = {"band_noise": (0, 1), "damped_impulse": (0, 1), "current_residual": (2,)}  # 주입할 센서 번호(0·1 진동, 2 전류)
LOSS = (0.75, 0.5, 0.25, 0.0)  # V2 진폭 배율
VARIANTS = ("v2", "v2+R1", "v2+R1+R2")


class Final:
    """예준 GuardModel 위에 R1(사건 지속)·R2(교차 확인)를 얹어 행 경보를 낸다. tvt 시험 채점과 같은 계산."""

    def __init__(self, M, model, r2_ref):
        self.M, self.model, self.r2_ref = M, model, r2_ref

    def rows(self, frame):
        """프레임 하나를 채점해 기록 번호·위치·시각과 v2 경보, R2를 거친 자기 경보(own2), 파형 정상 여부를 낸다."""
        D, guard, cp = self.M["D"], self.M["guard"], self.M["conformal_p"]
        frame = frame.reset_index(drop=True)
        _, seg = guard.layout(frame)
        q = D.quantize(D.inputs_only(frame), "matched")
        comp = self.model.components(q, seg)

        def fires(score):
            p = cp(self.model.cal, score)
            return np.isfinite(p) & (p <= ALPHA)

        alarm = fires(comp["score"])
        # 성분도 결합 점수의 보정 분포와 비교한다. 크기만 넘고 파형·동역학은 안 넘은 경보 = 크기 단독
        mag_only = fires(comp["g_magnitude"]) & ~fires(comp["g_waveform"]) & ~fires(comp["g_dynamics"])
        wave_ok = prefix_r2(q[D.SENSORS[2]].to_numpy(float), seg) >= self.r2_ref
        return dict(seg=seg, pos=D.segment_positions(seg)[0], ts=pd.to_datetime(frame.TimeStamp).astype("datetime64[ns]").to_numpy(),
                    v2=alarm, own2=alarm & ~(mag_only & wave_ok), wave_ok=wave_ok)

    @staticmethod
    def alarms(r, variant):
        """변형별 행 경보와 기록별 '이어받은 경보 안 풀림'."""
        if variant == "v2":
            return r["v2"].copy(), {}
        own = r["v2"] if variant == "v2+R1" else r["own2"]
        return stream_rules(r["ts"], r["seg"], own, r["wave_ok"], latch=True)


def fit_split(M, train, cal):
    """정상 학습·보정 구간으로 v2를 학습하고 R2 파형 기준(학습 prefix R² 0.5% 분위)을 정한다."""
    guard, D = M["guard"], M["D"]
    model = guard.GuardModel.fit(train, cal)
    q = D.quantize(D.inputs_only(train), "matched")
    _, seg = guard.layout(train)
    r2_ref = float(np.nanquantile(prefix_r2(q[D.SENSORS[2]].to_numpy(float), seg), R2_Q))
    return Final(M, model, r2_ref)


def records_of(frame, M):
    """기록별 행 번호 목록."""
    _, seg = M["guard"].layout(frame.reset_index(drop=True))
    return [np.flatnonzero(seg == s) for s in pd.unique(seg)]


def v3_record(M, x, i):
    """배열 하나를 v3 Record로 감싼다(주입기·B1 입력용)."""
    return M["v3"].Record(i, x, 0.0, 0.0, 0.0, (), "test")


def eval_injected(fin, frame, recs, k, x_new, onset, b1):
    """기록 k를 x_new로 바꾸고 직전 기록과 함께 흘려 기록 k의 탐지를 본다. 직전 기록을 넣어야 R1 이어받기가 실제처럼 돈다."""
    S = fin.M["D"].SENSORS
    idx = recs[k]
    parts = ([recs[k - 1]] if k > 0 else []) + [idx]
    sub = frame.iloc[np.concatenate(parts)].reset_index(drop=True).copy()
    sub.loc[len(sub) - len(idx):, S] = x_new
    r = fin.rows(sub)
    mine = np.arange(len(sub)) >= len(sub) - len(idx)
    start = max(onset, 0)  # 주입이 시작된 행. onset < 0 은 기록 전체 주입
    out = {}
    for v in VARIANTS:
        a, _ = Final.alarms(r, v)
        a_k, pos_k = a[mine], r["pos"][mine]
        after = pos_k >= start
        hit = a_k & after
        late = after & (pos_k >= 8)  # 8행 이후 = 파형 성분이 계산되는 구간의 재현율
        out[v] = dict(detected=bool(hit.any()), delay=float((pos_k[hit][0] - start) * 0.1) if hit.any() else np.nan,
                      late_recall=float(hit[late].mean()) if late.any() else np.nan)
    det, calib = b1
    out["v3_B1"] = dict(detected=bool(calib.p(det.score(fin.M["v3"].features([v3_record(fin.M, x_new, k)])))[0] <= ALPHA),
                        delay=np.nan, late_recall=np.nan)
    return out


def v1_injection(M, fin, frame, gen, f_test, b1, sid):
    """V1·V1b: test 정상 기록마다 하나씩 인공 고장을 주입해 탐지율을 잰다. 강도 0은 주입 없는 대조군."""
    recs = records_of(frame, M)
    X = frame[M["D"].SENSORS].to_numpy(float)
    rows = []
    for fam, strengths in SELECTION.items():
        for target in TARGETS[fam]:
            axis = f"v{target}_rms" if target < 2 else "i_residual"
            scale = gen.scales(f_test, axis)
            for strength in (0.0,) + strengths:
                for seed in (SEEDS if strength > 0 else SEEDS[:1]):
                    for k, idx in enumerate(recs):
                        rec, info = gen.inject(v3_record(M, X[idx], k), fam, target, strength, seed, scale[k])
                        if strength > 0 and not info["valid"]:  # 주입기가 이 기록에 주입할 수 없다고 하면 미지원으로 남긴다
                            rows.append(dict(split=sid, family=fam, target=target, strength=strength, seed=seed, record=k, n=len(idx),
                                             supported=False, **{f"{m}|detected": False for m in VARIANTS + ("v3_B1",)}))
                            continue
                        res = eval_injected(fin, frame, recs, k, rec.x, info["onset"], b1)
                        rows.append(dict(split=sid, family=fam, target=target, strength=strength, seed=seed, record=k, n=len(idx),
                                         supported=True, **{f"{m}|{key}": val for m, d in res.items() for key, val in d.items()}))
    return pd.DataFrame(rows)


def v1a_chain(M, fin, frame, gen, f_test, sid):
    """V1a: 60초 안에 이어지는 기록 3개에 같은 주입. V1a′: 기록 k만 주입하고 뒤 정상 기록(최대 5개)으로 이어진 오경보."""
    recs = records_of(frame, M)
    X = frame[M["D"].SENSORS].to_numpy(float)
    ts = pd.to_datetime(frame.TimeStamp).astype("datetime64[ns]").to_numpy()
    gap = lambda a, b: (ts[recs[b][0]] - ts[recs[a][-1]]) / np.timedelta64(1, "s")  # 기록 a 끝 → 기록 b 시작(초)
    S = M["D"].SENSORS
    chain_rows, cost_rows = [], []
    for fam, strengths in SELECTION.items():
        for target in TARGETS[fam]:
            axis = f"v{target}_rms" if target < 2 else "i_residual"
            scale = gen.scales(f_test, axis)
            for strength in strengths:
                for seed in SEEDS:
                    # V1a: 겹치지 않는 3기록 묶음. 사이 공백이 60초를 넘으면 R1이 이어지지 않으므로 뺀다
                    for k in range(0, len(recs) - 2, 3):
                        if gap(k, k + 1) > 60 or gap(k + 1, k + 2) > 60:
                            continue
                        sub = frame.iloc[np.concatenate(recs[k:k + 3])].reset_index(drop=True).copy()
                        start = 0
                        for j in range(3):
                            rec, _ = gen.inject(v3_record(M, X[recs[k + j]], k + j), fam, target, strength, seed, scale[k + j])
                            sub.loc[start:start + len(recs[k + j]) - 1, S] = rec.x
                            start += len(recs[k + j])
                        r = fin.rows(sub)
                        for v in VARIANTS:
                            a, _ = Final.alarms(r, v)
                            for j, s in enumerate(pd.unique(r["seg"])):
                                chain_rows.append(dict(split=sid, family=fam, target=target, strength=strength, seed=seed, chain=k,
                                                       order=j, variant=v, detected=bool(a[r["seg"] == s].any())))
                    # V1a′: 기록 k만 주입하고 60초 안에 이어지는 뒤 정상 기록(최대 5개)까지 흘린다
                    for k in range(len(recs) - 1):
                        last = k
                        while last + 1 < len(recs) and last - k < 5 and gap(last, last + 1) <= 60:
                            last += 1
                        if last == k:
                            continue
                        sub = frame.iloc[np.concatenate(recs[k:last + 1])].reset_index(drop=True).copy()
                        rec, _ = gen.inject(v3_record(M, X[recs[k]], k), fam, target, strength, seed, scale[k])
                        sub.loc[:len(recs[k]) - 1, S] = rec.x
                        r = fin.rows(sub)
                        segs = pd.unique(r["seg"])
                        first = r["seg"] == segs[0]
                        a, _ = Final.alarms(r, "v2+R1+R2")
                        latched = r["own2"][first].sum() >= 2  # 주입 기록이 '확인된 이상'이 됐을 때만 비용을 잰다
                        if not latched:
                            continue
                        extra = a & ~r["own2"] & ~first            # 이어받은 경보로만 켜진 뒤 기록의 행
                        chain_records = int(sum(extra[r["seg"] == s].any() for s in segs[1:]))
                        first_next = r["seg"] == segs[1]
                        cost_rows.append(dict(split=sid, family=fam, target=target, strength=strength, seed=seed, record=k,
                                              next_len=int(first_next.sum()), latched_rows_next=int(extra[first_next].sum()),
                                              chain_records=chain_records, chain_rows=int(extra.sum()),
                                              next_short=bool(first_next.sum() < 8)))
    return pd.DataFrame(chain_rows), pd.DataFrame(cost_rows)


def v2_loss(M, fin, frame, gen, b1, sid):
    """V2: 센서별로 기록 전체 진폭을 LOSS 배율로 줄였을 때의 탐지(줄어드는 고장·센서 끊김)."""
    recs = records_of(frame, M)
    X = frame[M["D"].SENSORS].to_numpy(float)
    rows = []
    for target in (0, 1, 2):
        for mult in LOSS:
            for k, idx in enumerate(recs):
                rec, _ = gen.inject(v3_record(M, X[idx], k), "amplitude_decrease", target, mult, SEEDS[0], 1.0)
                res = eval_injected(fin, frame, recs, k, rec.x, -1, b1)
                rows.append(dict(split=sid, target=target, multiplier=mult, record=k,
                                 **{f"{m}|detected": d["detected"] for m, d in res.items()}))
    return pd.DataFrame(rows)


def record_rate(fin, frame, variant):
    """경보가 한 번이라도 난 기록의 비율·수·전체 기록 수."""
    r = fin.rows(frame)
    a, _ = Final.alarms(r, variant)
    s = pd.Series(a).groupby(r["seg"]).max()
    return float(s.mean()), int(s.sum()), int(len(s))


def v5_confound(M, fin, test_n, abnormal, sid, test_start):
    """V5: 고장이 아니라 수집 조건 차이를 잡는지 본다. ① 전류 수준 이동 ② 표본화 시각 흔들림 ③ 이상 기록 평균 제거."""
    D = M["D"]
    rows = []
    for shift in (0.0, 81.4, 272.4):
        f = test_n.copy()
        f[D.SENSORS[2]] = f[D.SENSORS[2]] + shift
        for v in VARIANTS:
            rate, hit, n = record_rate(fin, f, v)
            rows.append(dict(split=sid, test="current_shift", level=shift, variant=v, alerted=hit, records=n, rate=rate))
    # ② 예준 jitter_stress와 같은 생성(같은 난수 순서). 길이 17행 이상 기록만 바꾸고 그 기록만 센다
    sys.path.insert(0, str(M["repo"] / "yejun/analysis/press_evidence"))
    import diagnostic_probes as probes
    from press.diagnosis import sine_fit
    seg_all = D.segments(M["normal"])
    test = M["normal"][seg_all >= test_start].reset_index(drop=True)
    seg = seg_all[seg_all >= test_start]
    x0 = test[D.SENSORS[2]].to_numpy(float)
    lengths = pd.Series(seg).value_counts()
    fits = {}  # 기록 → (행 번호, 주파수, 사인 계수, 잔차). 흔들린 시각으로 사인만 다시 그리고 잔차는 그대로 더한다
    for s in sorted(lengths[lengths >= 17].index):
        idx = np.flatnonzero(seg == s)
        fr = sine_fit(x0[idx])[0]
        coef = probes.tone_coefficients(x0[idx], fr)
        fits[s] = (idx, fr, coef, x0[idx] - probes.tone_design(len(idx), fr) @ coef)
    keep = np.isin(seg, list(fits))
    for frequency_hz, sigma_ms in probes.JITTER_CONDITIONS:
        if frequency_hz not in (None, 60.6):  # 판정 셀(60.6 Hz)과 흔들림 0 대조만 돌린다
            continue
        rng = np.random.default_rng(probes.JITTER_SEED)
        repeats = probes.JITTER_REPEATS if sigma_ms > 0 else 1
        counts = {v: [0, 0] for v in VARIANTS}  # 변형 → [경보 기록 수, 기록 수] (반복 합)
        for _ in range(repeats):
            x = x0.copy()
            for s, (idx, f0, coef, residual) in fits.items():
                phase = 2 * np.pi * f0 * np.arange(len(idx)) * .1
                if sigma_ms > 0:
                    phase = phase + 2 * np.pi * frequency_hz * rng.normal(0, sigma_ms / 1e3, len(idx))
                x[idx] = coef[0] * np.cos(phase) + coef[1] * np.sin(phase) + coef[2] + residual
            frame = test.copy()
            frame[D.SENSORS[2]] = x
            r = fin.rows(frame)
            for v in VARIANTS:
                a, _ = Final.alarms(r, v)
                per = pd.Series(a[keep]).groupby(seg[keep]).max()
                counts[v][0] += int(per.sum()); counts[v][1] += int(len(per))
        for v in VARIANTS:
            rows.append(dict(split=sid, test="jitter_60.6Hz", level=sigma_ms, variant=v, alerted=counts[v][0], records=counts[v][1],
                             rate=counts[v][0] / counts[v][1]))
    # ③ 이상 기록 평균 제거: 이상이 평균 수준 차이뿐이라면 평균을 지운 뒤에는 못 잡는다
    _, aseg = M["guard"].layout(abnormal)
    for mode, cols in (("none", []), ("current_mean_removed", [D.SENSORS[2]]), ("all_means_removed", D.SENSORS)):
        f = abnormal.copy()
        for c in cols:
            f[c] = f[c] - f.groupby(aseg)[c].transform("mean")
        for v in VARIANTS:
            rate, hit, n = record_rate(fin, f, v)
            rows.append(dict(split=sid, test="abnormal_mean_removal", level=mode, variant=v, alerted=hit, records=n, rate=rate))
    return pd.DataFrame(rows)


def v3_splits(M, normal, abnormal):
    """V3: 정상 분할을 바꿔(P2 분 단위 + 시간순 5창) 다시 학습해도 결과가 버티는지 본다."""
    D = M["D"]
    out = []
    seg_all = D.segments(normal)
    ts = pd.to_datetime(normal.TimeStamp)
    minutes = (ts - ts.iloc[0]).dt.total_seconds() / 60
    rec_start = minutes.groupby(seg_all).transform("min").to_numpy()
    rec_end = minutes.groupby(seg_all).transform("max").to_numpy()
    # 분 단위 분할은 기록이 경계에 걸치지 않게 기록 시작·끝 시각으로 나눈다
    folds = {"P2(분 0~40/40~60/60~)": ((rec_end < 40), (rec_start >= 40) & (rec_end < 60), rec_start >= 60)}
    for end in (180, 240, 300, 360, 420):
        folds[f"rolling 학습<{end}·보정~{end + 119}·평가{end + 120}~{end + 179}"] = (
            seg_all < end, (seg_all >= end) & (seg_all < end + 120), (seg_all >= end + 120) & (seg_all < end + 180))
    for name, (tr, ca, te) in folds.items():
        fin = fit_split(M, normal[tr].reset_index(drop=True), normal[ca].reset_index(drop=True))
        rn, ra = fin.rows(normal[te].reset_index(drop=True)), fin.rows(abnormal)
        for v in VARIANTS:
            an, _ = Final.alarms(rn, v)
            aa, _ = Final.alarms(ra, v)
            m = f1_counts(np.r_[np.zeros(len(an)), np.ones(len(aa))].astype(bool), np.r_[an, aa])
            norm_rec = pd.Series(an).groupby(rn["seg"]).max()
            abn_rec = pd.Series(aa).groupby(ra["seg"]).max()
            out.append(dict(fold=name, variant=v, f1=m["f1"], tp=m["tp"], fp=m["fp"], fn=m["fn"],
                            normal_alerted_records=int(norm_rec.sum()), normal_records=int(len(norm_rec)),
                            abnormal_detected_records=int(abn_rec.sum()), abnormal_records=int(len(abn_rec))))
    return pd.DataFrame(out)


def judge(v1, cost, v5):
    """실행 전에 정한 기준으로 판정한다. 반환 (주입 탐지율 표, 판정 dict)."""
    sel = v1[v1.strength > 0]
    pod = sel.groupby(["split", "family", "target", "strength"])[[f"{m}|detected" for m in VARIANTS + ("v3_B1",)]].mean().reset_index()
    j = {}
    # V1: 전류 잔차 주입에서 최종 모델 탐지율이 v2보다 5%p 넘게 낮지 않아야 한다
    d3 = pod[pod.family == "current_residual"]
    j["V1_current_residual_rules_do_not_hurt"] = bool(((d3["v2+R1+R2|detected"] - d3["v2|detected"]) >= -0.05).all())
    # V1b: 진동 주입에서 R2가 깎는 탐지율(v2+R1 − 최종)이 5%p 이내인지
    vib = pod[pod.family != "current_residual"]
    loss = vib["v2+R1|detected"] - vib["v2+R1+R2|detected"]
    j["V1b_R2_cost_within_5pp"] = bool((loss <= 0.05).all())
    j["V1b_max_cost_pp"] = round(float(loss.max() * 100), 2)
    # V1a′: 다음 기록에서 이어받은 오경보가 8행 이하인 경우가 90% 이상인지
    if len(cost):
        share = float((cost.latched_rows_next <= 8).mean())
        j["V1a_prime_latch_cost_limited"] = share >= 0.9
        j["V1a_prime_release_within_8_share"] = round(share, 4)
        j["V1a_prime_cases"] = int(len(cost))
    # V5: 전류 이동·시각 흔들림에 정상 경보율이 2α 이하로 버티는지, 평균을 지워도 이상 20기록 이상을 잡는지
    fin = v5[v5.variant == "v2+R1+R2"]
    sh = fin[fin.test == "current_shift"]
    j["V5_shift_insensitive"] = {f"{r.split} +{r.level}": bool(r.rate <= 2 * ALPHA) for r in sh[sh.level > 0].itertuples()}
    jt = fin[(fin.test == "jitter_60.6Hz") & (fin.level == 0.1)]
    j["V5_jitter_0.1ms_insensitive"] = {r.split: bool(r.rate <= 2 * ALPHA) for r in jt.itertuples()}
    mr = fin[(fin.test == "abnormal_mean_removal") & (fin.level != "none")]
    j["V5_mean_removal_still_detects"] = {f"{r.split} {r.level}": bool(r.alerted >= 20) for r in mr.itertuples()}
    return pod, j


def main():
    repo = repo_arg()
    M = setup(repo)
    M["repo"] = repo
    D, v3 = M["D"], M["v3"]
    normal, abnormal, _ = D.load(repo / "yejun/press_submission")
    M["normal"] = normal
    out = {k: [] for k in ("v1", "chain", "cost", "loss", "v5")}
    for sid in SPLITS:
        sp = D.split_normal(normal, D.segments(normal), sid)
        fin = fit_split(M, sp["train"], sp["cal"])
        # v3 주입기·B1은 정상 학습 기록 특징으로 맞추고, B1 문턱은 정상 보정 기록으로 정한다
        q_tr = D.quantize(D.inputs_only(sp["train"]), "matched")
        fit_feat = v3.features(v3_records(M, q_tr, "train"))
        gen = v3.Generator(fit_feat, sid)
        det = v3.Detector("B1").fit(fit_feat)
        q_va = D.quantize(D.inputs_only(sp["cal"]), "matched")
        calib = v3.RankCalibration().fit(det.score(v3.features(v3.records_from_frame(ns_time(q_va))[0])))
        test = sp["test"].reset_index(drop=True)
        X = test[D.SENSORS].to_numpy(float)
        f_test = v3.features([v3_record(M, X[idx], k) for k, idx in enumerate(records_of(test, M))])
        print(sid, "V5 교락 대조 …", flush=True)
        out["v5"].append(v5_confound(M, fin, test, abnormal, sid, D.SPLITS[sid][2]))
        print(sid, "V1 주입 …", flush=True)
        out["v1"].append(v1_injection(M, fin, test, gen, f_test, (det, calib), sid))
        print(sid, "V1a·V1a′ …", flush=True)
        c, k = v1a_chain(M, fin, test, gen, f_test, sid)
        out["chain"].append(c); out["cost"].append(k)
        print(sid, "V2 손실 …", flush=True)
        out["loss"].append(v2_loss(M, fin, test, gen, (det, calib), sid))
    tables = {k: pd.concat(v, ignore_index=True) for k, v in out.items()}
    print("V3 분할 강건성 …", flush=True)
    tables["v3split"] = v3_splits(M, normal, abnormal)
    for k, t in tables.items():
        t.to_csv(OUT / f"validation_{k}.csv", index=False)
    pod, j = judge(tables["v1"], tables["cost"], tables["v5"])
    pod.to_csv(OUT / "validation_v1_pod.csv", index=False)
    chain = tables["chain"].groupby(["family", "order", "variant"]).detected.mean().unstack("variant")
    loss = tables["loss"].groupby(["split", "target", "multiplier"])[[c for c in tables["loss"].columns if c.endswith("|detected")]].mean()
    summary = dict(judgments=j, v1a_chain_pod=chain.round(4).reset_index().to_dict("records"),
                   v2_loss_pod=loss.round(4).reset_index().to_dict("records"))
    (OUT / "validation_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    pd.set_option("display.width", 220)
    print(json.dumps(j, ensure_ascii=False, indent=1))
    print(pod.round(3).to_string(index=False))
    print(tables["v5"].round(4).to_string(index=False))
    print(tables["v3split"].to_string(index=False))
    print(chain.round(3).to_string())
    print(loss.round(3).to_string())


if __name__ == "__main__":
    main()
