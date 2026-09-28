"""A1-2 누설 점검: 구간 겹침·경계, matched 양자화 뒤 형식 흔적.

팀 모듈을 import하지 않는다.
"""
import json
import re

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression

import redA1_common as C

pd.set_option("display.width", 250, "display.max_columns", 60, "display.max_rows", 200)
normal, abnormal = C.load_raw()
seg_n, seg_a = C.segment_ids(normal[C.TIME]), C.segment_ids(abnormal[C.TIME])
sec_n = C.seconds(normal[C.TIME])
out = {}

# ---------- (1) 분할 겹침·경계 ----------
print("== (1) 분할 겹침·시간 순서")
rows = []
for sid in ("A", "B"):
    m = C.split_frames(normal, seg_n, sid)
    parts = {}
    for k, mask in m.items():
        idx = np.flatnonzero(mask)
        parts[k] = dict(rows=int(mask.sum()), records=int(len(np.unique(seg_n[mask]))), first_row=int(idx[0]), last_row=int(idx[-1]),
                        t_first=str(normal[C.TIME].iloc[idx[0]]), t_last=str(normal[C.TIME].iloc[idx[-1]]),
                        rec_first=int(seg_n[idx[0]]), rec_last=int(seg_n[idx[-1]]), contiguous=bool((np.diff(idx) == 1).all()))
    overlap = int((m["train"] & m["cal"]).sum() + (m["train"] & m["test"]).sum() + (m["cal"] & m["test"]).sum())
    gap_tc = sec_n[parts["cal"]["first_row"]] - sec_n[parts["train"]["last_row"]]
    gap_ct = sec_n[parts["test"]["first_row"]] - sec_n[parts["cal"]["last_row"]]
    shared = set(np.unique(seg_n[m["train"]])) & set(np.unique(seg_n[m["cal"]])) | set(np.unique(seg_n[m["cal"]])) & set(np.unique(seg_n[m["test"]]))
    rows.append(dict(split=sid, overlap_rows=overlap, records_shared=len(shared), gap_train_cal_s=float(gap_tc), gap_cal_test_s=float(gap_ct),
                     all_rows_covered=bool((m["train"] | m["cal"] | m["test"]).all()), **{f"{k}_{a}": v for k, p in parts.items() for a, v in p.items()}))
split_table = pd.DataFrame(rows)
print(split_table.T.to_string())
out["splits"] = rows

# 완전 중복 행
dup = normal[normal.duplicated(subset=[C.TIME] + C.SENS, keep=False)]
print("완전 중복 행", len(dup), dup.index.tolist(), "기록 번호", seg_n[dup.index].tolist())
out["duplicate_rows"] = dict(rows=dup.index.tolist(), records=seg_n[dup.index].tolist())

# ---------- (2) 저장 형식: 원값 ----------
print("\n== (2) 원값 저장 형식")


def decimals(series):
    """CSV 원문에서 소수 자릿수(지수 표기는 −1)."""
    out_ = []
    for s in series:
        if "e" in s or "E" in s:
            out_.append(-1)
        elif "." in s:
            out_.append(len(s.split(".")[1]))
        else:
            out_.append(0)
    return np.array(out_)


raw_n = pd.read_csv(C.DATA / "press_data_normal.csv", dtype=str)
raw_a = pd.read_csv(C.DATA / "outlier_data.csv", dtype=str)
fmt = []
for c in C.SENS:
    dn, da = decimals(raw_n[c]), decimals(raw_a[c])
    fmt.append(dict(sensor=c, normal_decimals=pd.Series(dn).value_counts().sort_index().to_dict(), abnormal_decimals=pd.Series(da).value_counts().sort_index().to_dict()))
    print(c, "정상 자릿수", fmt[-1]["normal_decimals"], "| 이상 자릿수", fmt[-1]["abnormal_decimals"])
out["raw_decimals"] = fmt
for name, df in (("normal", normal), ("abnormal", abnormal)):
    x = df[C.SENS[2]].to_numpy(float)
    r = x / C.CUR_STEP
    off = np.abs(r - np.round(r))
    print(name, "전류 격자(1.1920929) 나머지: 중앙", np.median(off), "<1e-3 비율", float((off * C.CUR_STEP < 1e-3).mean()))
    out[f"current_grid_{name}"] = dict(median_offset_steps=float(np.median(off)), share_on_grid_1e3=float((off * C.CUR_STEP < 1e-3).mean()))
    for c in C.SENS[:2]:
        v = df[c].to_numpy(float)
        u = np.unique(np.round(v, 8))
        d = np.diff(u)
        print(name, c, "고유값", len(u), "/", len(v), "최소 간격", d.min(), "간격 분위(1,5,50%)", np.quantile(d, [.01, .05, .5]))

# float32로 다시 읽으면 같은가(이상 파일이 float32 저장인지)
for name, df in (("normal", normal), ("abnormal", abnormal)):
    for c in C.SENS:
        v = df[c].to_numpy(float)
        same = np.isclose(v, v.astype(np.float32).astype(float), rtol=0, atol=0)
        # float32 최단 표기와 CSV 문자열 일치율
        raw = (raw_n if name == "normal" else raw_a)[c].to_numpy()
        rep32 = np.array([np.format_float_positional(np.float32(t), unique=True, trim="-") for t in v])
        match = np.mean([float(a) == float(b) for a, b in zip(raw, rep32)])
        print(name, c, "float64→float32→float64 동일 비율", float(same.mean()), "| float32 최단 표기 값 일치율", float(match))
        out[f"float32_{name}_{c}"] = dict(roundtrip_same=float(same.mean()), shortest_repr_match=float(match))

# ---------- (3) matched 양자화 뒤 남는 흔적 ----------
print("\n== (3) matched 양자화 뒤 형식 흔적")
Xn, Xa = C.quantize(normal[C.SENS].to_numpy(float)), C.quantize(abnormal[C.SENS].to_numpy(float))
steps = np.array([C.VIB_STEP, C.VIB_STEP, C.CUR_STEP])
Kn, Ka = np.round(Xn / steps).astype(np.int64), np.round(Xa / steps).astype(np.int64)
print("격자 복원 오차(정상, 이상)", np.abs(Xn - Kn * steps).max(), np.abs(Xa - Ka * steps).max())
trace = []
for j, c in enumerate(C.SENS):
    for mod in (2, 3, 4, 5, 8, 10, 16, 100):
        tn = np.bincount(np.mod(Kn[:, j], mod), minlength=mod)
        ta = np.bincount(np.mod(Ka[:, j], mod), minlength=mod)
        keep = (tn + ta) > 0
        chi2, p, dof, _ = chi2_contingency(np.vstack([tn[keep], ta[keep]]))
        # 효과 크기: 총변동 거리
        tv = 0.5 * np.abs(tn / tn.sum() - ta / ta.sum()).sum()
        trace.append(dict(sensor=c, modulus=mod, chi2=float(chi2), dof=int(dof), p=float(p), total_variation=float(tv),
                          abnormal_empty_residues=int((ta == 0).sum()), normal_empty_residues=int((tn == 0).sum())))
trace = pd.DataFrame(trace)
print(trace.to_string(index=False))
trace.to_csv(C.OUT / "redA1_02_format_residue.csv", index=False)

# 고유값·동률: 기록 안에서 같은 양자화 값이 반복되는 비율
uniq = []
for name, K, seg in (("normal", Kn, seg_n), ("abnormal", Ka, seg_a)):
    for j, c in enumerate(C.SENS):
        g = pd.Series(K[:, j]).groupby(seg)
        share = (g.nunique() / g.size())
        long = g.size() >= 17
        uniq.append(dict(data=name, sensor=c, unique_share_median=float(share[long].median()), unique_share_q05=float(share[long].quantile(.05)),
                         global_unique=int(len(np.unique(K[:, j]))), rows=int(len(K))))
uniq = pd.DataFrame(uniq)
print(uniq.to_string(index=False))

# 분류 시험: 양자화 값의 끝자리(격자 나머지)만으로 두 파일을 가를 수 있는가. 기록 묶음 교차검증.
print("\n== (3b) 끝자리 특징만 쓴 분류(기록 묶음 5겹)")


def residue_features(K, mods=(2, 3, 4, 5, 8, 10, 16)):
    cols = []
    for j in range(3):
        for mod in mods:
            r = np.mod(K[:, j], mod)
            for v in range(mod):
                cols.append((r == v).astype(float))
    return np.column_stack(cols)


def grouped_auc(Fn, Fa, seg_n_, seg_a_, make, seeds=(0, 1, 2)):
    res = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        rn, ra = np.unique(seg_n_), np.unique(seg_a_)
        fold_n = dict(zip(rn, rng.integers(0, 5, len(rn))))
        fold_a = dict(zip(ra, rng.permutation(len(ra)) % 5))
        fn_, fa_ = np.array([fold_n[s] for s in seg_n_]), np.array([fold_a[s] for s in seg_a_])
        score_n, score_a = np.zeros(len(Fn)), np.zeros(len(Fa))
        for k in range(5):
            Xtr = np.vstack([Fn[fn_ != k], Fa[fa_ != k]])
            ytr = np.r_[np.zeros((fn_ != k).sum()), np.ones((fa_ != k).sum())]
            clf = make().fit(Xtr, ytr)
            score_n[fn_ == k] = clf.predict_proba(Fn[fn_ == k])[:, 1]
            score_a[fa_ == k] = clf.predict_proba(Fa[fa_ == k])[:, 1]
        res.append(C.auroc(score_n, score_a))
    return float(np.mean(res)), float(np.min(res)), float(np.max(res))


Fn, Fa = residue_features(Kn), residue_features(Ka)
clf_rows = []
for label, make in (("logistic", lambda: LogisticRegression(max_iter=500, class_weight="balanced")),
                    ("boosting", lambda: HistGradientBoostingClassifier(max_iter=100, random_state=0, class_weight="balanced"))):
    mean, lo, hi = grouped_auc(Fn, Fa, seg_n, seg_a, make)
    clf_rows.append(dict(features="matched 격자 나머지(mod 2~16), 세 센서", model=label, row_auroc_mean=mean, row_auroc_min=lo, row_auroc_max=hi))
    print(clf_rows[-1])
# 대조: 원값 소수 자릿수(양자화 전) — 팀이 공개한 지름길
dec_n = np.column_stack([decimals(raw_n[c]) for c in C.SENS]).astype(float)
dec_a = np.column_stack([decimals(raw_a[c]) for c in C.SENS]).astype(float)
mean, lo, hi = grouped_auc(dec_n, dec_a, seg_n, seg_a, lambda: HistGradientBoostingClassifier(max_iter=100, random_state=0, class_weight="balanced"))
clf_rows.append(dict(features="원값 저장 소수 자릿수(양자화 전), 세 센서", model="boosting", row_auroc_mean=mean, row_auroc_min=lo, row_auroc_max=hi))
print(clf_rows[-1])
# 대조: 원값의 전류 격자 나머지(양자화 전)
offn = np.abs(normal[C.SENS[2]].to_numpy(float) / C.CUR_STEP - np.round(normal[C.SENS[2]].to_numpy(float) / C.CUR_STEP))[:, None]
offa = np.abs(abnormal[C.SENS[2]].to_numpy(float) / C.CUR_STEP - np.round(abnormal[C.SENS[2]].to_numpy(float) / C.CUR_STEP))[:, None]
mean, lo, hi = grouped_auc(offn, offa, seg_n, seg_a, lambda: HistGradientBoostingClassifier(max_iter=100, random_state=0, class_weight="balanced"))
clf_rows.append(dict(features="원값 전류 격자 나머지(양자화 전)", model="boosting", row_auroc_mean=mean, row_auroc_min=lo, row_auroc_max=hi))
print(clf_rows[-1])
pd.DataFrame(clf_rows).to_csv(C.OUT / "redA1_02_format_classifier.csv", index=False)
out["format_classifier"] = clf_rows
out["residue_tests_significant_p_lt_0.001"] = trace[trace.p < 1e-3][["sensor", "modulus", "p", "total_variation"]].to_dict("records")

# ---------- (4) 양자화가 검출 결과에 주는 영향: raw·matched 입력으로 같은 검출기 ----------
print("\n== (4) 전처리별 재적합(raw, matched) 결과")
prep_rows = []
for prep, (Yn, Ya) in dict(raw=(normal[C.SENS].to_numpy(float), abnormal[C.SENS].to_numpy(float)), matched=(Xn, Xa)).items():
    for sid in ("A", "B"):
        m = C.split_frames(normal, seg_n, sid)
        det = C.Detector().fit(Yn[m["train"]], seg_n[m["train"]]).calibrate(Yn[m["cal"]], seg_n[m["cal"]])
        pn, pa = det.predict(Yn[m["test"]], seg_n[m["test"]]), det.predict(Ya, seg_a)
        prep_rows.append(dict(preprocess=prep, split=sid, **C.f1_rows(pn["alarm"], pa["alarm"]),
                              normal_records=int(pd.Series(pn["alarm"]).groupby(seg_n[m["test"]]).max().sum()),
                              abnormal_records=int(pd.Series(pa["alarm"]).groupby(seg_a).max().sum()), threshold=float(det.cal.max())))
prep = pd.DataFrame(prep_rows)
print(prep.to_string(index=False))
prep.to_csv(C.OUT / "redA1_02_preprocess.csv", index=False)
out["preprocess"] = prep_rows
(C.OUT / "redA1_02_leakage_format.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
