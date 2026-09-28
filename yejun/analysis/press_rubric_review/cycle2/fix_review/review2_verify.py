#!/usr/bin/env python
"""review2 독립 재계산 — 팀 모듈을 import하지 않는다(pandas·numpy·scipy·sklearn만).

입력: 원본 CSV 두 개, v2 행 단위 예측(test_predictions_A/B.csv), v1 행 단위 예측(predictions_A/B.csv),
      표(unit_results_v2.csv, probability_baselines_v2.csv)는 대조용으로만 읽는다.
실행: OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review2_verify.py --root <저장소 또는 스냅숏 루트>
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import roc_auc_score

ap = argparse.ArgumentParser()
ap.add_argument("--root", default=str(Path(__file__).resolve().parents[5]),
                help="저장소 루트(기본: 이 파일이 fix_review 폴더에 있을 때의 저장소) 또는 같은 구조의 스냅숏")
ap.add_argument("--json", default=None, help="결과 JSON 저장 경로")
args = ap.parse_args()
R = Path(args.root)
DATA = R / "yejun/press_submission/data/3_소성가공_예지보전"
PG = R / "yejun/press_guard/outputs"
PS = R / "yejun/press_submission/outputs"
OUT: dict = {}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def hdr(t):
    print("\n" + "=" * 100 + f"\n{t}\n" + "=" * 100)


hdr("0. 입력 해시")
for p in [DATA / "press_data_normal.csv", DATA / "outlier_data.csv", PG / "test_predictions_A.csv",
          PG / "test_predictions_B.csv", PS / "predictions_A.csv", PS / "predictions_B.csv",
          PG / "unit_results_v2.csv", PG / "probability_baselines_v2.csv"]:
    print(f"{sha(p)}  {p.relative_to(R)}")

# ------------------------------------------------------------------------------------------
hdr("1. 원본 로드·기록 분할(독립 구현)")
SENS = ["AI0_Vibration", "AI1_Vibration", "AI2_Current"]


def load_raw(name):
    df = pd.read_csv(DATA / name)
    t = pd.to_datetime(df["TimeStamp"])
    dt = t.diff().dt.total_seconds()
    new_strict = dt.sub(0.1).abs().gt(1e-6).fillna(False).to_numpy()
    new_20ms = dt.sub(0.1).abs().gt(0.02).fillna(False).to_numpy()
    assert (new_strict == new_20ms).all(), "허용오차에 따라 기록이 달라짐"
    rec = np.cumsum(new_strict)
    pos = pd.Series(rec).groupby(rec).cumcount().to_numpy()
    return df, t, rec, pos


nor, nt, nrec, npos = load_raw("press_data_normal.csv")
abn, at, arec, apos = load_raw("outlier_data.csv")
print(f"정상 {len(nor)}행 {nrec.max()+1}기록, 이상 {len(abn)}행 {arec.max()+1}기록 (1 µs·20 ms 허용오차 동일)")
print(f"정상 시각 {nt.iloc[0]} ~ {nt.iloc[-1]} ({(nt.iloc[-1]-nt.iloc[0]).total_seconds()/60:.2f}분, {nt.iloc[0].day_name()})")
print(f"이상 시각 {at.iloc[0]} ~ {at.iloc[-1]} ({(at.iloc[-1]-at.iloc[0]).total_seconds()/60:.2f}분, {at.iloc[0].day_name()})")
alen = pd.Series(arec).value_counts().sort_index().to_numpy()
print("이상 기록 길이:", alen.tolist())
gap_a = (at - at.shift()).dt.total_seconds()[pd.Series(arec).diff().fillna(0).to_numpy() > 0]
print(f"이상 기록 사이 공백: 최소 {gap_a.min():.2f}초, 최대 {gap_a.max():.2f}초, 행 합계 {len(abn)*0.1:.0f}초 분량")
OUT["abnormal_record_lengths"] = alen.tolist()
SPLITS = {"A": (360, 480), "B": (300, 420)}
for s, (tr, ca) in SPLITS.items():
    te = nrec >= ca
    r0, r1 = nt[te].iloc[0], nt[te].iloc[-1]
    print(f"{s}: 학습 0~{tr-1}, 보정 {tr}~{ca-1}, 평가 {ca}~599 | 평가 행 {te.sum()} | 평가 시각 {r0} ~ {r1}")
    OUT[f"{s}_test_rows"] = int(te.sum())
    OUT[f"{s}_test_time"] = [str(r0), str(r1)]

# ------------------------------------------------------------------------------------------
hdr("2. 예측 파일 정렬 확인(행 순서·시각·기록·위치를 원본과 대조)")


def load_v2(split):
    df = pd.read_csv(PG / f"test_predictions_{split}.csv")
    return df


def load_v1(split):
    return pd.read_csv(PS / f"predictions_{split}.csv")


def attach_truth(df, split, subset_col, normal_name, pos_col, rec_col):
    """예측 파일 행을 원본 행과 맞추고 절대 기록 번호·독립 위치를 붙인다."""
    _, ca = SPLITS[split]
    te = nrec >= ca
    ntest = te.sum()
    isn = (df[subset_col] == normal_name).to_numpy()
    assert isn.sum() == ntest and (~isn).sum() == len(abn), (isn.sum(), ntest)
    # 파일 안 순서: 정상 평가가 먼저, 이상이 뒤라고 가정하지 않고 각 부분집합 안 순서로 대조
    ts = df["timestamp"].astype(str).str.slice(0, 23).to_numpy()
    raw_n = nor.loc[te, "TimeStamp"].astype(str).str.slice(0, 23).to_numpy()
    raw_a = abn["TimeStamp"].astype(str).str.slice(0, 23).to_numpy()
    assert (ts[isn] == raw_n).all(), "정상 평가 시각 불일치"
    assert (ts[~isn] == raw_a).all(), "이상 시각 불일치"
    out = df.copy()
    out["abs_record"] = -1
    out.loc[isn, "abs_record"] = nrec[te]
    out.loc[~isn, "abs_record"] = arec
    out["my_pos"] = -1
    out.loc[isn, "my_pos"] = npos[te]
    out.loc[~isn, "my_pos"] = apos
    out["y"] = (~isn).astype(int)
    assert (out[pos_col].to_numpy() == out["my_pos"].to_numpy()).all(), "위치 불일치"
    # 팀 record_id가 부분집합 안 상대 번호인지 확인
    rel = out.loc[isn, rec_col].to_numpy()
    assert (rel + ca == out.loc[isn, "abs_record"].to_numpy()).all(), "정상 기록 번호 불일치"
    arel = out.loc[~isn, rec_col].to_numpy()
    assert (arel - arel.min() == arec).all(), "이상 기록 번호 불일치"  # v1은 정상 평가 뒤에 이어 번호를 매긴다
    return out


V2, V1 = {}, {}
for s in "AB":
    v2 = load_v2(s)
    v2 = attach_truth(v2, s, "subset", "normal_test", "position", "record_id")
    assert (v2["label"].to_numpy() == v2["y"].to_numpy()).all()
    v1 = load_v1(s)
    v1 = attach_truth(v1, s, "source", "normal_test", "position_in_record", "record_id")
    assert (v1["timestamp"].astype(str).to_numpy() == v2["timestamp"].astype(str).to_numpy()).all()
    V2[s], V1[s] = v2, v1
    print(f"{s}: v2 {len(v2)}행·v1 {len(v1)}행, 시각·기록·위치 원본과 일치. status 값 v2={v2.status.unique().tolist()} v1={v1.status.unique().tolist()}")
    # 경보 열과 p값 일관성
    print(f"   v2 alarm == (p<=0.01): {(v2.alarm.to_numpy() == (v2.p_value <= 0.01).astype(int).to_numpy()).all()}; "
          f"v1 alarm == (p<=0.01): {(v1.alarm.to_numpy() == (v1.p_value <= 0.01).astype(int).to_numpy()).all()}")
    print(f"   v1 threshold 열 고유값: {v1.threshold.unique().tolist()}")

# ------------------------------------------------------------------------------------------
hdr("3. 기록 단위·행 단위 결과(α 1·3·5%)")


def f1(y, a):
    tp = int(((y == 1) & (a == 1)).sum()); fp = int(((y == 0) & (a == 1)).sum()); fn = int(((y == 1) & (a == 0)).sum())
    return tp, fp, fn, 2 * tp / (2 * tp + fp + fn)


def record_view(df, score_col, alarm):
    g = pd.DataFrame({"y": df.y.to_numpy(), "rec": df.abs_record.to_numpy(), "s": df[score_col].to_numpy(), "a": alarm,
                      "pos": df.my_pos.to_numpy()})
    rmax = g.groupby(["y", "rec"]).agg(smax=("s", "max"), anya=("a", "max")).reset_index()
    auc = roc_auc_score(rmax.y, rmax.smax)
    first = g[(g.y == 1) & (g.a == 1)].groupby("rec").pos.min()
    return rmax, auc, first


rows = []
for s in "AB":
    v2, v1 = V2[s], V1[s]
    for alpha in (0.01, 0.03, 0.05):
        a2 = (v2.p_value.to_numpy() <= alpha + 1e-12).astype(int)
        col = "alarm" if alpha == 0.01 else f"alarm_conformal_{alpha:.2f}"
        a1 = v1[col].to_numpy().astype(int)
        # v1 p값으로도 확인
        a1p = (v1.p_value.to_numpy() <= alpha + 1e-12).astype(int)
        assert (a1 == a1p).all(), f"v1 {col}와 p값 불일치"
        for name, df, a, sc in [("v2", v2, a2, "score"), ("v1", v1, a1, "combined_score")]:
            tp, fp, fn, F = f1(df.y.to_numpy(), a)
            rmax, auc, first = record_view(df, sc, a)
            ab = rmax[rmax.y == 1]; no = rmax[rmax.y == 0]
            alerted = sorted(no.loc[no.anya == 1, "rec"].astype(int).tolist())
            rows.append(dict(split=s, alpha=alpha, model=name, tp=tp, fp=fp, fn=fn, f1=F,
                             abn_detected=int(ab.anya.sum()), abn_records=len(ab), normal_alerted=int(no.anya.sum()),
                             normal_records=len(no), record_auroc=auc, normal_max=no.smax.max(), abnormal_min=ab.smax.min(),
                             max_first_alarm_s=(first.max() * 0.1 if len(first) else np.nan), alerted_records=alerted))
res = pd.DataFrame(rows)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30); pd.set_option("display.max_colwidth", 60)
print(res.to_string(index=False))
OUT["unit_results_recomputed"] = res.to_dict(orient="records")

# 팀 표와 대조
ur = pd.read_csv(PG / "unit_results_v2.csv")
ur["model_key"] = ur.model.map(lambda m: "v2" if m.startswith("v2") else ("v1" if m.startswith("v1") else "simple"))
print("\n[팀 unit_results_v2.csv 와 대조: v1·v2]")
for _, r in res.iterrows():
    t = ur[(ur.split == r.split) & (np.isclose(ur.alpha, r.alpha)) & (ur.model_key == r.model)].iloc[0]
    diffs = {k: (t[k], r[k2]) for k, k2 in [("tp", "tp"), ("fp", "fp"), ("fn", "fn"), ("abnormal_records_detected", "abn_detected"),
                                            ("normal_records_alerted", "normal_alerted")] if t[k] != r[k2]}
    fd = abs(t.f1_rows - r.f1)
    ad = abs(t.record_auroc - r.record_auroc)
    nd = abs(t.record_normal_max - r.normal_max); md = abs(t.record_abnormal_min - r.abnormal_min)
    print(f"{r.split} α={r.alpha:.2f} {r.model}: 정수 불일치={diffs or '없음'} | F1차 {fd:.1e} | AUROC 팀 {t.record_auroc} 재계산 {r.record_auroc:.6f} | "
          f"정상최대 팀 {t.record_normal_max:.6f} 재계산 {r.normal_max:.6f} | 이상최소 팀 {t.record_abnormal_min:.6f} 재계산 {r.abnormal_min:.6f}")

# v1·v2 점수 관계와 경보 포함 관계
print("\n[v1 → v2 행 경보 전이(α 1%)와 점수 비교]")
for s in "AB":
    v2, v1 = V2[s], V1[s]
    d = v2.score.to_numpy() - v1.combined_score.to_numpy()
    only_v1 = int(((v1.alarm == 1) & (v2.alarm == 0)).sum()); only_v2 = int(((v1.alarm == 0) & (v2.alarm == 1)).sum())
    print(f"{s}: v2 점수 < v1 점수인 행 {int((d < -1e-12).sum())}/{len(d)} (최소 차 {d.min():.3e}), v1만 경보 {only_v1}행, v2만 경보 {only_v2}행")
    # 정상 알림 기록이 같은지
    for alpha in (0.01, 0.03, 0.05):
        r2 = res[(res.split == s) & (res.alpha == alpha) & (res.model == "v2")].iloc[0]
        r1 = res[(res.split == s) & (res.alpha == alpha) & (res.model == "v1")].iloc[0]
        print(f"   α={alpha:.2f} 정상 알림 기록 v2 {r2.alerted_records} | v1 {r1.alerted_records}")

# ------------------------------------------------------------------------------------------
hdr("4. 위치별 미탐(이상 600행, α 1%) — v1 대비 v2")
pos_out = {}
for s in "AB":
    v2, v1 = V2[s], V1[s]
    m = v2.y == 1
    pos = v2.loc[m, "my_pos"].to_numpy()
    miss2 = (v2.loc[m, "alarm"].to_numpy() == 0); miss1 = (v1.loc[m, "alarm"].to_numpy() == 0)
    buckets = {"0-1": pos <= 1, "2-6": (pos >= 2) & (pos <= 6), ">=7": pos >= 7}
    tot1, tot2 = miss1.sum(), miss2.sum()
    print(f"{s}: 미탐 v1 {tot1} → v2 {tot2} (감소 {tot1-tot2})")
    pos_out[s] = {}
    for b, mk in buckets.items():
        fixed = int((miss1 & ~miss2 & mk).sum()); broke = int((~miss1 & miss2 & mk).sum()); both = int((miss1 & miss2 & mk).sum())
        pos_out[s][b] = dict(rows=int(mk.sum()), v1_miss=int((miss1 & mk).sum()), v2_miss=int((miss2 & mk).sum()),
                             v1miss_v2hit=fixed, v1hit_v2miss=broke, both_miss=both)
        print(f"   위치 {b:>4}: 행 {mk.sum():3d} | v1 미탐 {int((miss1&mk).sum()):3d} | v2 미탐 {int((miss2&mk).sum()):3d} | "
              f"v1미탐→v2탐지 {fixed:3d} | v1탐지→v2미탐 {broke} | 둘다 미탐 {both}")
    # 위치 0~1 미탐이 같은 행인지
    b01 = buckets["0-1"]
    print(f"   위치 0~1 미탐 행 집합 동일: {bool(((miss1 & b01) == (miss2 & b01)).all())}")
    # 위치별 상세
    det = pd.DataFrame({"pos": pos, "v1": miss1, "v2": miss2}).groupby("pos").agg(rows=("v1", "size"), v1=("v1", "sum"), v2=("v2", "sum"))
    print("   위치별(0~10) 미탐 v1/v2:", "; ".join(f"{p}:{int(r.v1)}/{int(r.v2)}({int(r.rows)})" for p, r in det.head(11).iterrows()))
OUT["position_misses"] = pos_out

# ------------------------------------------------------------------------------------------
hdr("5. 단순 규칙(0.6 Hz 공진 잔차 + 진동 절댓값, 정상 학습 최댓값 척도, 보정 기록 최대 conformal)")
QV, QC = 1e-4, 1.1920929  # press_submission/press/data.py QUANTIZATION["matched"]


def quantize(df, matched=True):
    q = df[SENS].astype(float).copy()
    if matched:
        for c in SENS[:2]:
            q[c] = np.round(q[c] / QV) * QV
        q[SENS[2]] = np.round(q[SENS[2]] / QC) * QC
    return q


def components(df, pos, freq=0.6, matched=True, center=None):
    q = quantize(df, matched)
    x = q[SENS[2]].to_numpy(float)
    if center is not None:
        x = x - center
    w = 2 * np.cos(2 * np.pi * freq * 0.1)
    r = np.full(len(x), np.nan)
    idx = np.where(pos >= 2)[0]
    r[idx] = np.abs(x[idx] - w * x[idx - 1] + x[idx - 2])
    return r, np.abs(q[SENS[0]].to_numpy(float)), np.abs(q[SENS[1]].to_numpy(float))


def conformal_p(cal, s):
    cal = np.sort(cal)
    ge = len(cal) - np.searchsorted(cal, s, side="left")  # #{cal >= s}
    return (ge + 1) / (len(cal) + 1)


def simple_rule(split, freq=0.6, matched=True, alphas=(0.01, 0.03, 0.05), verbose=True, center_mode=None):
    tr_end, ca_end = SPLITS[split]
    trm = nrec < tr_end; cam = (nrec >= tr_end) & (nrec < ca_end); tem = nrec >= ca_end
    center = None
    if center_mode == "train_mean":
        center = quantize(nor[trm], matched)[SENS[2]].mean()
    rn, a0n, a1n = components(nor, npos, freq, matched, center)
    ra, a0a, a1a = components(abn, apos, freq, matched, center)
    Mr = np.nanmax(rn[trm]); M0 = a0n[trm].max(); M1 = a1n[trm].max()
    sn = np.fmax(np.fmax(a0n / M0, a1n / M1), rn / Mr)
    sa = np.fmax(np.fmax(a0a / M0, a1a / M1), ra / Mr)
    cal = pd.Series(sn[cam]).groupby(nrec[cam]).max().to_numpy()
    assert len(cal) == 120
    s_eval = np.r_[sn[tem], sa]; y = np.r_[np.zeros(tem.sum(), int), np.ones(len(abn), int)]
    rec = np.r_[nrec[tem], arec + 10_000]; pos = np.r_[npos[tem], apos]
    p = conformal_p(cal, s_eval)
    out = []
    for alpha in alphas:
        a = (p <= alpha + 1e-12).astype(int)
        tp, fp, fn, F = f1(y, a)
        g = pd.DataFrame({"y": y, "rec": rec, "s": s_eval, "a": a})
        rm = g.groupby(["y", "rec"]).agg(smax=("s", "max"), anya=("a", "max")).reset_index()
        ab, no = rm[rm.y == 1], rm[rm.y == 0]
        miss = (y == 1) & (a == 0)
        pb = {"0-1": pos <= 1, "2-6": (pos >= 2) & (pos <= 6), ">=7": pos >= 7}
        out.append(dict(split=split, alpha=alpha, freq=freq, matched=matched, center=center_mode, tp=tp, fp=fp, fn=fn, f1=F,
                        abn_detected=int(ab.anya.sum()), normal_alerted=int(no.anya.sum()), n_normal=len(no),
                        record_auroc=roc_auc_score(rm.y, rm.smax), normal_max=no.smax.max(), abnormal_min=ab.smax.min(),
                        **{f"miss_{k}": int((miss & (y == 1) & v).sum()) for k, v in pb.items()},
                        cal_max=cal.max(), scales=(Mr, M0, M1),
                        alerted=sorted((no.loc[no.anya == 1, "rec"]).astype(int).tolist())))
    return out


sr = []
for s in "AB":
    sr += simple_rule(s)
srd = pd.DataFrame(sr)
print(srd.drop(columns=["scales"]).to_string(index=False))
print("척도(Mr, M0, M1):", {s: tuple(float(v) for v in srd[srd.split == s].scales.iloc[0]) for s in "AB"})
OUT["simple_rule"] = [{k: (list(v) if isinstance(v, tuple) else v) for k, v in d.items()} for d in sr]
print("\n[팀 unit_results_v2.csv 단순 규칙 행과 대조]")
for d in sr:
    t = ur[(ur.split == d["split"]) & np.isclose(ur.alpha, d["alpha"]) & (ur.model_key == "simple")].iloc[0]
    keys = [("tp", "tp"), ("fp", "fp"), ("fn", "fn"), ("abnormal_records_detected", "abn_detected"), ("normal_records_alerted", "normal_alerted"),
            ("missed_pos_0-1", "miss_0-1"), ("missed_pos_2-6", "miss_2-6"), ("missed_pos_>=7", "miss_>=7")]
    diffs = {k: (int(t[k]), d[k2]) for k, k2 in keys if int(t[k]) != d[k2]}
    print(f"{d['split']} α={d['alpha']:.2f}: 정수 불일치={diffs or '없음'} | F1 팀 {t.f1_rows:.6f} 재계산 {d['f1']:.6f} | "
          f"정상최대 팀 {t.record_normal_max:.6f} 재계산 {d['normal_max']:.6f} | 이상최소 팀 {t.record_abnormal_min:.6f} 재계산 {d['abnormal_min']:.6f}")

print("\n[민감도: 전처리 raw, 주파수 0.5~0.7 Hz, 전류 학습 평균 제거] α 1%")
sens = []
for s in "AB":
    for kw in [dict(matched=False), dict(freq=0.5), dict(freq=0.55), dict(freq=0.65), dict(freq=0.7), dict(center_mode="train_mean")]:
        d = simple_rule(s, alphas=(0.01,), **kw)[0]
        sens.append({k: d[k] for k in ["split", "freq", "matched", "center", "tp", "fp", "fn", "f1", "abn_detected", "normal_alerted",
                                         "miss_0-1", "miss_2-6", "miss_>=7"]})
print(pd.DataFrame(sens).to_string(index=False))
OUT["simple_rule_sensitivity"] = sens

# 정상 학습 전류의 주 주파수(0.6 Hz가 자료에서 나온 값인지 참고)
print("\n[참고: 정상 학습 전류의 주 주파수 — 기록별 사인 최소제곱(0.30~1.00 Hz, 0.01 Hz 격자) 최빈값, 30행 이상 기록]")
freqs = np.round(np.arange(0.30, 1.0001, 0.01), 2)
best = []
qn = quantize(nor)
for r in range(300):
    m = nrec == r
    x = qn.loc[m, SENS[2]].to_numpy(float)
    if len(x) < 30:
        continue
    t = np.arange(len(x)) * 0.1
    sse = []
    for f in freqs:
        A = np.column_stack([np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t), np.ones(len(t))])
        c, *_ = np.linalg.lstsq(A, x, rcond=None)
        sse.append(((x - A @ c) ** 2).sum())
    best.append(freqs[int(np.argmin(sse))])
bs = pd.Series(best).value_counts().sort_index()
print(f"기록 {len(best)}개, 중앙 {np.median(best):.2f} Hz, 분포(상위): {bs.sort_values(ascending=False).head(6).to_dict()}")
OUT["normal_dominant_freq_median"] = float(np.median(best))

# ------------------------------------------------------------------------------------------
hdr("6. 확률 채점")
PI = 0.01


def post(lr, pi):
    lr = np.asarray(lr, float)
    return pi * lr / (pi * lr + 1 - pi)


def wmetrics(p, y, w, eps=1e-9):
    p = np.asarray(p, float); y = np.asarray(y, int); w = np.asarray(w, float)
    brier = float(np.sum(w * (p - y) ** 2) / np.sum(w))
    pc = np.clip(p, eps, 1 - eps)
    ll = float(-np.sum(w * (y * np.log(pc) + (1 - y) * np.log(1 - pc))) / np.sum(w))
    return brier, ll


def ece(p, y, w=None, bins=10, mode="width"):
    p = np.asarray(p, float); y = np.asarray(y, float)
    w = np.ones_like(p) if w is None else np.asarray(w, float)
    if mode == "width":
        edges = np.linspace(0, 1, bins + 1)
        b = np.clip(np.digitize(p, edges[1:-1], right=True), 0, bins - 1)
    else:  # 같은 개수
        order = np.argsort(p, kind="mergesort"); b = np.empty(len(p), int)
        b[order] = np.minimum((np.arange(len(p)) * bins) // len(p), bins - 1)
    tot = 0.0
    for k in range(bins):
        m = b == k
        if w[m].sum() > 0:
            tot += w[m].sum() / w.sum() * abs(np.average(p[m], weights=w[m]) - np.average(y[m], weights=w[m]))
    return float(tot)


prob = {}
pb = pd.read_csv(PG / "probability_baselines_v2.csv")
for s in "AB":
    v2 = V2[s]
    y = v2.y.to_numpy(); lr = v2.likelihood_ratio.to_numpy(float)
    nn, na = (y == 0).sum(), (y == 1).sum()
    p1 = post(lr, PI)
    print(f"{s}: probability_source 부분집합별 = {v2.groupby('subset').probability_source.unique().to_dict()}; "
          f"prior 열 {v2.probability_prior.unique().tolist()}")
    print(f"   π·LR/(π·LR+1−π) vs anomaly_probability 최대 |차| {np.nanmax(np.abs(p1 - v2.anomaly_probability.to_numpy())):.2e}; "
          f"anomaly_score vs 1−p_value 최대 |차| {np.nanmax(np.abs(v2.anomaly_score - (1 - v2.p_value))):.2e}; LR 결측 {int(np.isnan(lr).sum())}")
    # 파일 비율
    fp_ = na / len(y)
    pf = post(lr, fp_)
    print(f"   file_prior 열 {v2.file_prior.unique().tolist()} vs 재계산 {fp_:.10f}; file_prior 확률 최대 |차| "
          f"{np.nanmax(np.abs(pf - v2.anomaly_probability_file_prior.to_numpy())):.2e}")
    capped = lr >= 121 - 1e-9
    print(f"   LR=121(상한) 행: 이상 {int((capped & (y == 1)).sum())}/{na}, 정상 {int((capped & (y == 0)).sum())}/{nn}; "
          f"π1% 최대 확률 {p1.max():.4f}; 정상 경보행 LR {sorted(lr[(y == 0) & (v2.alarm == 1)].round(3).tolist())}")
    # (a) 파일 라벨 그대로(가중 없음)
    uw = np.ones(len(y))
    b_file, ll_file = wmetrics(p1, y, uw)
    b_fp, ll_fp = wmetrics(pf, y, uw)
    e_file = {m: ece(p1, y, bins=b, mode=m) for m in ["width"] for b in [10]}
    print(f"   [파일 라벨 그대로] π1% 확률: Brier {b_file:.4f}, log-loss {ll_file:.4f}, ECE(10등폭) {ece(p1,y):.4f}, ECE(15등폭) {ece(p1,y,bins=15):.4f}, ECE(10등빈도) {ece(p1,y,mode='mass'):.4f}")
    print(f"   [파일 라벨 그대로] 파일 비율 확률: Brier {b_fp:.4f}, log-loss {ll_fp:.4f}, ECE(10등폭) {ece(pf,y):.4f}, ECE(15등폭) {ece(pf,y,bins=15):.4f}, ECE(10등빈도) {ece(pf,y,mode='mass'):.4f}")
    # (b) 평가 비율 1% 재가중
    w = np.where(y == 1, PI / na, (1 - PI) / nn)
    pv = v2.p_value.to_numpy(float)
    al = v2.alarm.to_numpy(float)
    # 두 수준 교차 보정 재구성: 경보=1 → LR 상한 121(보정 행 경보 0), 경보=0 → 이상 미탐 비율 / 1 (이상 행은 자기 기록 제외)
    miss = (y == 1) & (al == 0)
    lr2 = np.where(al == 1, 121.0, miss.sum() / na)
    for r in np.unique(v2.abs_record[y == 1]):
        m = (y == 1) & (v2.abs_record.to_numpy() == r)
        other = (y == 1) & ~m
        lr2[m] = np.where(al[m] == 1, 121.0, miss[other].sum() / other.sum())
    p2 = post(lr2, PI)
    cand = {"현재 확률 층": p1, "두 수준 교차 보정(재구성)": p2, "경보 0/1": al, "1−p": 1 - pv, "상수 π": np.full(len(y), PI)}
    prob[s] = {}
    for name, p in cand.items():
        b, ll = wmetrics(p, y, w)
        ll_e6 = wmetrics(p, y, w, eps=1e-6)[1]; ll_e15 = wmetrics(p, y, w, eps=1e-15)[1]
        prob[s][name] = dict(brier=b, logloss_1e9=ll, logloss_1e6=ll_e6, logloss_1e15=ll_e15, ece_w=ece(p, y, w))
        print(f"   [1% 재가중] {name:<22} Brier {b:.5f} | log-loss ε=1e-9 {ll:.4f} · ε=1e-6 {ll_e6:.4f} · ε=1e-15 {ll_e15:.4f} | 가중 ECE {ece(p, y, w):.4f}")
    # 가중 Brier 분해: 정상 항·이상 항
    for name in ["현재 확률 층", "경보 0/1", "1−p"]:
        p = cand[name]
        nterm = 0.99 * np.mean((p[y == 0]) ** 2); aterm = 0.01 * np.mean((p[y == 1] - 1) ** 2)
        print(f"      {name}: 정상 항 0.99×{np.mean(p[y==0]**2):.5f}={nterm:.5f}, 이상 항 0.01×{np.mean((p[y==1]-1)**2):.4f}={aterm:.5f}")
    prob[s]["file_scoring"] = dict(brier_pi1=b_file, ece_pi1=ece(p1, y), brier_file_prior=b_fp, ece_file_prior=ece(pf, y),
                                   logloss_file_prior=ll_fp)
    # 팀 표와 대조
    team = pb[pb.split == s]
    print("   팀 표(probability_baselines_v2.csv):")
    for _, t in team.iterrows():
        print(f"      {t.evaluation_prior:<6} {t.method:<32} Brier {t.brier:.5f} log-loss {t.log_loss:.4f} ECE {t.ece:.4f}")
    # 로그손실 교차점: 경보 0/1이 현재 층보다 log-loss가 높아지는 ε
    ll_cur = prob[s]["현재 확률 층"]["logloss_1e9"]
    err_w = np.sum(w * np.abs(al - y))
    eps_star = float(np.exp(-ll_cur / err_w))  # (가중 오류율)×(−ln ε) = ll_cur 근사
    print(f"   경보 0/1 log-loss가 현재 층({ll_cur:.4f})보다 커지는 절단 ε 경계 ≈ {eps_star:.2e} (가중 오류율 {err_w:.5f})")
    prob[s]["eps_crossover"] = eps_star
OUT["probability"] = prob

# ------------------------------------------------------------------------------------------
hdr("7. A 평가 구간 '조용함' 대리지표(모델 무관, 원 신호) — 120기록 블록·이동 창")
qn_raw = nor[SENS].astype(float)
g = pd.DataFrame({"rec": nrec, "a0": qn_raw[SENS[0]], "a1": qn_raw[SENS[1]], "c": qn_raw[SENS[2]]})
per = g.groupby("rec").agg(n=("c", "size"), a0_rms=("a0", lambda v: np.sqrt(np.mean(v ** 2))),
                           a1_rms=("a1", lambda v: np.sqrt(np.mean(v ** 2))),
                           c_rms=("c", lambda v: np.sqrt(np.mean((v - v.mean()) ** 2))),
                           a0_absmax=("a0", lambda v: np.abs(v).max()))
per["low"] = (per.n >= 17) & (per.c_rms < 91.9)
per["load"] = (per.n >= 17) & (per.c_rms >= 91.9)
blocks = [(0, 120), (120, 240), (240, 360), (360, 480), (480, 600)]
for b0, b1 in blocks:
    p = per.loc[b0:b1 - 1]
    ge17 = p[p.n >= 17]
    print(f"기록 {b0:3d}~{b1-1:3d}: AI0 RMS 평균 {p.a0_rms.mean():.4f}, AI1 RMS 평균 {p.a1_rms.mean():.4f}, 전류 RMS 평균 {p.c_rms.mean():.1f}, "
          f"AI0 |max| 중앙 {p.a0_absmax.median():.4f}, 17행 이상 중 저수준 {ge17.low.mean()*100:.0f}% (부하 {int(p.load.sum())})")
# 이동 창(120기록)에서 전류 RMS 평균 최소·저수준 비율 최대 위치
roll_c = per.c_rms.rolling(120).mean(); roll_a0 = per.a0_rms.rolling(120).mean()
lowfrac = (per.low.astype(float).rolling(120).sum() / (per.n >= 17).astype(float).rolling(120).sum())
print(f"이동 창 전류 RMS 평균 최소: 끝 기록 {int(roll_c.idxmin())} (값 {roll_c.min():.1f}; 480~599 {roll_c.iloc[-1]:.1f})")
print(f"이동 창 AI0 RMS 평균 최소: 끝 기록 {int(roll_a0.idxmin())} (값 {roll_a0.min():.4f}; 480~599 {roll_a0.iloc[-1]:.4f})")
print(f"이동 창 저수준 비율 최대: 끝 기록 {int(lowfrac.idxmax())} (값 {lowfrac.max():.3f}; 480~599 {lowfrac.iloc[-1]:.3f})")
OUT["quiet"] = dict(roll_c_min_end=int(roll_c.idxmin()), roll_a0_min_end=int(roll_a0.idxmin()), lowfrac_max_end=int(lowfrac.idxmax()))
# 저장해 두고 모델 스크립트에서 쓴다
per.to_csv(Path(args.json).with_name("review2_record_signal_summary.csv") if args.json else "review2_record_signal_summary.csv")

# ------------------------------------------------------------------------------------------
hdr("8. 21/21 이항 하한")
print(f"단측 95% Clopper–Pearson 하한 = 0.05^(1/21) = {0.05 ** (1/21):.4f}; 양측 95% 하한 = 0.025^(1/21) = {0.025 ** (1/21):.4f}")

if args.json:
    Path(args.json).write_text(json.dumps(OUT, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                               encoding="utf-8")
