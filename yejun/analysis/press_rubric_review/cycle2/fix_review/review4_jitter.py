"""review4 주장 3 독립 재계산: 표본화 시각 흔들림 스트레스(팀 함수 미사용, 같은 시드·추출 순서).

(1) 팀 CSV 재현 (2) 흔들림 0 복원 (3) 다른 시드 5개로 몬테카를로 변동 (4) 흔들린 정상 기록과 이상 기록의 다른 파형 지표 비교.
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import review4_indep as I  # noqa: E402

pd.set_option("display.width", 250)
SEED, REPEATS = 20260929, 5
CONDS = ((None, 0.0), (60.6, .05), (60.6, .1), (60.6, .2), (60.6, .5), (60.6, 2.4), (50.6, .1), (50.6, .2), (0.6, 2.4))
SPL = {"A": 480, "B": 420}
t0 = time.time()
n, a = I.load_raw()
rec_all = I.records(n.TimeStamp)


def prepare(sid, min_len=17):
    mask = rec_all >= SPL[sid]
    test = n[mask].reset_index(drop=True)
    seg = rec_all[mask]
    x0 = test.AI2_Current.to_numpy(float)
    lengths = pd.Series(seg).value_counts()
    fits = {}
    for s in sorted(lengths[lengths >= min_len].index):
        idx = np.flatnonzero(seg == s)
        f = I.best_sine(x0[idx])[0]
        coef, resid = I.ls_tone(x0[idx], f)
        fits[s] = (idx, f, coef, resid)
    return test, seg, x0, fits


def jittered(x0, fits, fhz, sigma, rng):
    x = x0.copy()
    for s, (idx, f, coef, resid) in fits.items():
        ph = 2 * np.pi * f * np.arange(len(idx)) * .1
        if sigma > 0:
            ph = ph + 2 * np.pi * fhz * rng.normal(0, sigma / 1e3, len(idx))
        x[idx] = coef[0] * np.cos(ph) + coef[1] * np.sin(ph) + coef[2] + resid
    return x


def run(sid, model, prep, conds, seed, repeats=REPEATS, collect=None):
    test, seg, x0, fits = prep
    vals = test[I.SENS].to_numpy(float)
    keep = np.isin(seg, list(fits))
    rows = []
    for fhz, sigma in conds:
        rng = np.random.default_rng(seed)
        reps = repeats if sigma > 0 else 1
        l1 = l2 = tot = 0
        first = dict(magnitude=0, waveform=0, dynamics=0)
        r2 = []
        for _ in range(reps):
            x = jittered(x0, fits, fhz, sigma, rng)
            for s, (idx, *_r) in fits.items():
                r2.append(I.best_sine(x[idx])[1])
                if collect is not None and fhz == 60.6 and sigma == 2.4:
                    collect.append(x[idx].copy())
            v = vals.copy(); v[:, 2] = x
            p = model.predict(v, test.TimeStamp, rec=I.records(test.TimeStamp, 0.02))
            p = p[keep].assign(rr=seg[keep])
            al = p.groupby("rr").alarm.sum()
            l1 += int((al >= 1).sum()); l2 += int((al >= 2).sum()); tot += len(al)
            for _, g in p[p.alarm.eq(1)].groupby("rr"):
                row = g.iloc[0]
                first[max(row.reason.split("+"), key=lambda c: row[f"g_{c}"])] += 1
        rows.append(dict(split=sid, f_hz=fhz, sigma_ms=sigma, seed=seed, records=len(fits), trials=tot, level1=l1, level2=l2,
                         level1_rate=l1 / tot, level2_rate=l2 / tot, r2_median=float(np.median(r2)), **{f"first_{k}": v for k, v in first.items()}))
    return pd.DataFrame(rows)


team = pd.read_csv(I.SNAP / "analysis" / "press_evidence" / "sampling_jitter_stress.csv")
models = {sid: I.Model(sid) for sid in ("A", "B")}
preps = {sid: prepare(sid) for sid in ("A", "B")}

# (2) 흔들림 0 복원
for sid in ("A", "B"):
    test, seg, x0, fits = preps[sid]
    x = jittered(x0, fits, None, 0.0, None)
    print(f"[복원] {sid}: 기록 {len(fits)}개, 최대 |재구성-원값| {np.max(np.abs(x - x0)):.3e}, 양자화 뒤 다른 값 {int((I.quantize(np.c_[x0, x0, x])[:, 2] != I.quantize(np.c_[x0, x0, x0])[:, 2]).sum())}행")

# (1) 같은 시드 재현
collect = []
mine = pd.concat([run(sid, models[sid], preps[sid], CONDS, SEED, collect=collect if sid == "A" else None) for sid in ("A", "B")], ignore_index=True)
cmp = mine.merge(team.rename(columns={"source_frequency_hz": "f_hz", "jitter_rms_ms": "sigma_ms"}), on=["split", "sigma_ms"], suffixes=("", "_team"), how="left")
cmp = cmp[(cmp.f_hz.fillna(-1) == cmp.f_hz_team.fillna(-1))]
cols = ["split", "f_hz", "sigma_ms", "level1", "level1_alerted", "level2", "level2_alerted", "r2_median", "sine_r2_median",
        "first_magnitude", "first_magnitude_team", "first_waveform", "first_waveform_team", "first_dynamics", "first_dynamics_team"]
print("\n[재현] 독립 구현(같은 시드·순서) 대 팀 CSV")
print(cmp[cols].to_string(index=False))
same = ((cmp.level1 == cmp.level1_alerted) & (cmp.level2 == cmp.level2_alerted) & (np.abs(cmp.r2_median - cmp.sine_r2_median) < 1e-9)
        & (cmp.first_magnitude == cmp.first_magnitude_team) & (cmp.first_waveform == cmp.first_waveform_team) & (cmp.first_dynamics == cmp.first_dynamics_team))
print("모든 행 일치:", bool(same.all()), f"({int(same.sum())}/{len(cmp)})")
mine.to_csv(Path(__file__).with_name("review4_jitter_same_seed.csv"), index=False)

# (3) 다른 시드
extra = []
for seed in (1, 2, 3, 4, 5):
    for sid in ("A", "B"):
        extra.append(run(sid, models[sid], preps[sid], ((60.6, .05), (60.6, .1), (60.6, .2), (60.0, .1)), seed))
extra = pd.concat(extra, ignore_index=True)
extra.to_csv(Path(__file__).with_name("review4_jitter_other_seeds.csv"), index=False)
print("\n[다른 시드 1~5] 1단계 경보 기록 비율(각 시드 5반복)")
print(extra.pivot_table(index=["split", "f_hz", "sigma_ms"], columns="seed", values="level1_rate").round(3).to_string())
print(extra.groupby(["split", "f_hz", "sigma_ms"]).level1_rate.agg(["min", "max", "mean"]).round(3).to_string())
print(f"경과 {time.time() - t0:.0f}초")
np.save(Path(__file__).with_name("review4_jitter24_A.npy"), np.array(collect, dtype=object), allow_pickle=True)
