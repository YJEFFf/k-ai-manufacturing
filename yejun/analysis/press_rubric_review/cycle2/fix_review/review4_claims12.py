"""review4 주장 1·2 독립 재계산(팀 함수 미사용). 결과는 표준 출력."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import review4_indep as I  # noqa: E402

pd.set_option("display.width", 220)
n, a = I.load_raw()
rec = {"normal": I.records(n.TimeStamp), "abnormal": I.records(a.TimeStamp)}
frames = {"normal": n, "abnormal": a}
print("기록 수", {k: len(np.unique(v)) for k, v in rec.items()})
assert np.array_equal(I.records(n.TimeStamp, 0.02), rec["normal"]) and np.array_equal(I.records(a.TimeStamp, 0.02), rec["abnormal"])

# ---------- 주장 1 ----------
def offset(k, cur, min_len=10, ddof=1):
    f = frames[k]
    t = pd.to_datetime(f.TimeStamp)
    g = pd.DataFrame(dict(r=rec[k], c=cur, t=t)).groupby("r")
    s = pd.DataFrame(dict(n=g.c.size(), m=g.c.mean(), sd=g.c.std(ddof=ddof), lo=g.c.min(), t0=g.t.min()))
    s = s[s.n >= min_len].sort_values("t0")
    m = s.m.to_numpy()
    return dict(over=f"{int((s.m.abs() > s.sd).sum())}/{len(s)}", allpos=f"{int((s.lo > 0).sum())}/{len(s)}",
                maxabs=round(float(s.m.abs().max()), 2), lag1=round(float(np.corrcoef(m[:-1], m[1:])[0, 1]), 4)), s

print("\n[주장 1] 전류 기록 평균 치우침")
for k in ("normal", "abnormal"):
    raw = frames[k].AI2_Current.to_numpy(float)
    qv = I.quantize(frames[k][I.SENS].to_numpy(float))[:, 2]
    for label, cur in (("matched", qv), ("raw", raw)):
        for ml in (10, 17):
            for dd in (1, 0):
                r, _ = offset(k, cur, ml, dd)
                print(f"  {k:8s} {label:7s} len>={ml} ddof={dd}: {r}")

# 이상 기록별 상세(길이≥10): 평균·SD·적합 주파수·R²
_, s = offset("abnormal", I.quantize(a[I.SENS].to_numpy(float))[:, 2], 10, 1)
det = []
for r_id, row in s.iterrows():
    idx = np.flatnonzero(rec["abnormal"] == r_id)
    f, r2, _ = I.best_sine(a.AI2_Current.to_numpy(float)[idx])
    det.append(dict(record=int(r_id), n=int(row.n), mean=round(row.m, 1), sd=round(row.sd, 1), over=bool(abs(row.m) > row.sd),
                    allpos=bool(row.lo > 0), f_fit=f, r2=round(r2, 3)))
det = pd.DataFrame(det)
print(det.to_string(index=False))
print("  |평균|>SD 기록의 적합 주파수 중앙", det[det.over].f_fit.median(), "· 나머지", det[~det.over].f_fit.median())

# 정상: 이웃 평균 상관 부트스트랩 대비 이상 16쌍 상관의 불확실성(피셔 z 근사 95% CI)
r_ab = float(offset("abnormal", I.quantize(a[I.SENS].to_numpy(float))[:, 2])[0]["lag1"])
npair = int(offset("abnormal", I.quantize(a[I.SENS].to_numpy(float))[:, 2])[0]["over"].split("/")[1]) - 1
zf = np.arctanh(r_ab); se = 1 / np.sqrt(npair - 3)
print(f"  이상 이웃 평균 상관 {r_ab:.3f}, 쌍 {npair}, 피셔 95% CI {np.tanh(zf - 1.96 * se):.3f}~{np.tanh(zf + 1.96 * se):.3f}")

# ---------- 주장 2 ----------
print("\n[주장 2] 기록 평균 제거와 동결 v2(독립 구현)")
OUT = I.SNAP / "press_guard" / "outputs"
SPL = {"A": 480, "B": 420}


def demean(values, r, cols):
    v = np.array(values, float, copy=True)
    for c in cols:
        m = pd.Series(v[:, c]).groupby(r).transform("mean").to_numpy()
        v[:, c] = v[:, c] - m
    return v


def summary(pa, pn):
    al = pa.alarm.to_numpy(bool)
    has = lambda part: al & pa.reason.str.contains(part).to_numpy()
    return dict(ab_rows=int(al.sum()), ab_rec=f"{int(pa.groupby('record').alarm.max().sum())}/{pa.record.nunique()}",
                mag=int(has("magnitude").sum()), mag_cur=int((has("magnitude") & (pa.magnitude_sensor == "AI2_Current").to_numpy()).sum()),
                wave=int(has("waveform").sum()), dyn=int(has("dynamics").sum()),
                n_rows=int(pn.alarm.sum()), n_rec=f"{int(pn.groupby('record').alarm.max().sum())}/{pn.record.nunique()}")


flips = []
for sid in ("A", "B"):
    m = I.Model(sid)
    test_mask = rec["normal"] >= SPL[sid]
    nt = n[test_mask].reset_index(drop=True)
    rn = I.records(nt.TimeStamp)
    ra = rec["abnormal"]
    va, vn = a[I.SENS].to_numpy(float), nt[I.SENS].to_numpy(float)
    base_a, base_n = m.predict(va, a.TimeStamp), m.predict(vn, nt.TimeStamp)
    # 동결 출력과 대조
    fa = pd.read_csv(OUT / f"predictions_abnormal_{sid}.csv")
    fn_ = pd.read_csv(OUT / f"predictions_normal_{sid}.csv")
    same_a = (np.array_equal(fa.alarm.to_numpy(), base_a.alarm.to_numpy()) and
              (fa.reason.fillna("").to_numpy() == base_a.reason.to_numpy()).all() and
              (fa.magnitude_sensor.to_numpy() == base_a.magnitude_sensor.to_numpy()).all())
    same_n = np.array_equal(fn_.alarm.to_numpy(), base_n.alarm.to_numpy()) and len(fn_) == len(base_n)
    gmax = max(np.nanmax(np.abs(fa[c].to_numpy() - base_a[c].to_numpy())) for c in ("g_magnitude", "g_waveform", "g_dynamics"))
    print(f" {sid}: 독립 구현 = 동결 예측(이상 alarm·reason·센서 {same_a}, 정상평가 alarm {same_n}), g 최대 차 {gmax:.2e}")
    for name, cols in (("원자료", []), ("전류 기록 평균 제거", [2]), ("세 센서 기록 평균 제거", [0, 1, 2])):
        pa = m.predict(demean(va, ra, cols), a.TimeStamp) if cols else base_a
        pn = m.predict(demean(vn, rn, cols), nt.TimeStamp) if cols else base_n
        sm = summary(pa, pn)
        if cols:
            lost = int((base_a.alarm.eq(1) & pa.alarm.eq(0)).sum()); gained = int((base_a.alarm.eq(0) & pa.alarm.eq(1)).sum())
            dlost = int((base_a.reason.str.contains("dynamics") & ~pa.reason.str.contains("dynamics")).sum())
            dgain = int((~base_a.reason.str.contains("dynamics") & pa.reason.str.contains("dynamics")).sum())
            first_b = base_a[base_a.alarm.eq(1)].groupby("record").pos.min(); first_v = pa[pa.alarm.eq(1)].groupby("record").pos.min()
            sm.update(lost=lost, gained=gained, dyn_lost=dlost, dyn_gained=dgain,
                      first_pos_changed=int((first_b != first_v.reindex(first_b.index)).sum()))
        print(f"   {name}: {sm}")
    # 기록 평균 치우침이 큰 기록에서 동역학 성분의 변화
    cur_mean = pd.Series(va[:, 2]).groupby(ra).mean()
    big = cur_mean[cur_mean.abs() > 100].index
    pa = m.predict(demean(va, ra, [2]), a.TimeStamp)
    sel = np.isin(ra, big)
    print(f"   |기록 평균|>100 기록 {list(big)}: 원자료 경보 {int(base_a.alarm[sel].sum())}/{int(sel.sum())}행·dynamics {int(base_a.reason[sel].str.contains('dynamics').sum())}, "
          f"제거 후 경보 {int(pa.alarm[sel].sum())}·dynamics {int(pa.reason[sel].str.contains('dynamics').sum())}; "
          f"AR 잔차 중앙 {np.nanmedian(base_a.residual[sel]):.1f} → {np.nanmedian(pa.residual[sel]):.1f}(꼬리 u {m.tails['dynamics'].u:.1f})")
    # 동역학 단독 경보가 평균에 의존하는 정도: 평균 제거 대신 '기록 평균을 정상 학습 평균으로 옮김'
