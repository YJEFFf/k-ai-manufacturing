"""A1-5 보조 확인: 기록 단위 한 줄 규칙, 전류 첨도, 5.0 Hz 흔적 행 목록. 팀 모듈 import 없음."""
import json
import numpy as np, pandas as pd
from scipy.stats import kurtosis
import redA1_common as C

rn = pd.read_csv(C.OUT / "redA1_03_records_normal.csv"); ra = pd.read_csv(C.OUT / "redA1_03_records_abnormal.csv")
out = {}
# (1) 기록 단위 한 줄 규칙: 기록 안 |전류 2차 차분| 최대 > 정상 보정 기록 최대(학습 없음)
rows = []
for sid, (a, b) in C.SPLITS.items():
    for f in ("d2_max", "d1_max", "v0_max_abs", "v1_max_abs"):
        thr = rn[(rn.record >= a) & (rn.record < b)][f].max()
        te = rn[rn.record >= b]
        rows.append(dict(split=sid, feature=f, threshold=float(thr), abnormal_flagged=int((ra[f] > thr).sum()), abnormal_records=len(ra),
                         normal_test_flagged=int((te[f] > thr).sum()), normal_test_records=len(te), normal_all_600_flagged=int((rn[f] > thr).sum())))
one = pd.DataFrame(rows); print(one.to_string(index=False)); out["record_one_liners"] = rows
print("d2_max 전체 정상 600기록 최대", rn.d2_max.max(), "| 이상 기록 중 이를 넘는 수", int((ra.d2_max > rn.d2_max.max()).sum()), "/ 21")
# (2) 기록 평균을 뺀 전류의 첨도(Fisher+3 = 보통 첨도). 순수 사인 1.5, 가우스 3.
normal, abnormal = C.load_raw()
k = []
for lab, df in (("normal", normal), ("abnormal", abnormal)):
    seg = C.segment_ids(df[C.TIME]); X = C.quantize(df[C.SENS].to_numpy(float))
    for r in np.unique(seg):
        x = X[seg == r, 2]
        if len(x) >= 17:
            k.append(dict(data=lab, record=int(r), n=len(x), kurtosis=float(kurtosis(x - x.mean(), fisher=False)),
                          max_over_sd=float(np.abs(x - x.mean()).max() / x.std())))
k = pd.DataFrame(k)
ks = k.groupby("data")[["kurtosis", "max_over_sd"]].describe(percentiles=[.05, .5, .95]).T
print(ks.round(3).to_string()); out["kurtosis"] = k.groupby("data").kurtosis.describe().to_dict()
# (3) 팀 수식(pinv hat)으로 8행 창 최적 주파수가 5.0 Hz인 이상 행
seg = C.segment_ids(abnormal[C.TIME]); X = C.quantize(abnormal[C.SENS].to_numpy(float)); cur = X[:, 2]
idx = C.windows_index(seg, 8); W = np.stack([cur[i - 7:i + 1] for i in idx]); t = np.arange(8) * C.DT
best = np.full(len(idx), np.inf); arg = np.zeros(len(idx), int)
for j, f in enumerate(C.FREQS):
    A = np.column_stack([np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t), np.ones(8)])
    r = W - np.einsum("ij,kj->ik", W, A @ np.linalg.pinv(A), optimize=False); e = (r * r).sum(1)
    b = e < best; best[b] = e[b]; arg[b] = j
hit = idx[C.FREQS[arg] == 5.0]
pd.DataFrame(dict(abnormal_row=hit, record=seg[hit], position=C.positions(seg)[hit])).to_csv(C.OUT / "redA1_05_rows_best_at_5Hz.csv", index=False)
print("5.0 Hz가 최적인 이상 행", len(hit), "개, 기록", sorted(set(seg[hit].tolist())), "위치 범위", C.positions(seg)[hit].min(), C.positions(seg)[hit].max())
out["rows_best_at_5Hz"] = hit.tolist()
(C.OUT / "redA1_05_extra.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
