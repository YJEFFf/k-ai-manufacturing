"""평가관 05(창의성·차별성) 검수용 독립 확인. 기존 산출물만 읽고 이 폴더의 judge05_checks.json 하나만 쓴다.

1) 저장 v2 AR(2) 계수의 특성근 → 암시 주파수·감쇠, 정상 전류 사인 주파수(진단 0.600Hz)와의 대응
2) 정상 평가 구간의 기록 단위 경보율 vs 명목 α 격자(k/121) — conformal p값의 실현 보정
3) 결합 성분의 상보성: 이상 행 경보를 성분 조합별로 분해, 성분 점수 간 순위상관
실행: OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python yejun/analysis/press_rubric_review/judge05_checks.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import beta as beta_dist, spearmanr

HERE = Path(__file__).resolve().parent
Y = HERE.parents[1]
G = Y / "press_guard"
DT = 0.1


def upper95(k, n):
    return 1.0 if k >= n else float(beta_dist.ppf(0.95, k + 1, n - k))


def cp(cal, s):
    ref = np.sort(cal)
    out = np.full(len(s), np.nan)
    ok = np.isfinite(s)
    out[ok] = (len(ref) - np.searchsorted(ref, s[ok], side="left") + 1) / (len(ref) + 1)
    return out


result = {}
for split in "AB":
    st = json.loads((G / "artifacts" / f"guard_{split}.json").read_text())["state"]
    c = np.asarray(st["ar2"], float)
    roots = np.roots([1, -c[1], -c[2]])
    f_hat = float(np.abs(np.angle(roots[0])) / (2 * np.pi * DT))
    pure = dict(phi1=float(2 * np.cos(2 * np.pi * 0.6 * DT)), phi2=-1.0)
    cal = np.asarray(st["calibration"], float)

    nrm = pd.read_csv(G / "outputs" / f"predictions_normal_{split}.csv")
    abn = pd.read_csv(G / "outputs" / f"predictions_abnormal_{split}.csv")
    # 2) 기록 단위 최소 p → α 격자별 실현 경보율
    minp = nrm.groupby("record_id").p_value.min().fillna(1.0).to_numpy()
    n_rec, n_cal = len(minp), len(cal)
    curve = []
    for k in range(1, 13):
        a = k / (n_cal + 1)
        hits = int((minp <= a + 1e-12).sum())
        curve.append(dict(alpha_grid=round(a, 6), alarmed_records=hits, n_records=n_rec,
                          realized=round(hits / n_rec, 6), binom_upper95=round(upper95(hits, n_rec), 6)))
    # 3) 이상 행 경보의 성분 분해(α=1%)
    alpha = 0.01
    comp = {k: cp(cal, abn[f"g_{k}"].to_numpy(float)) <= alpha for k in ("magnitude", "waveform", "dynamics")}
    alarm = abn.alarm.eq(1).to_numpy()
    combo = pd.Series(["+".join(k for k in comp if comp[k][i]) for i in range(len(abn))])[alarm]
    only = {k: int(((combo == k)).sum()) for k in comp}
    first = abn[abn.alarm.eq(1)].groupby("record_id").head(1)
    first_reason = first.reason.value_counts().to_dict()
    rho = {}
    for name, df in (("normal_eval", nrm), ("abnormal", abn)):
        m = df[["g_waveform", "g_dynamics", "g_magnitude"]].dropna()
        rho[name] = dict(n=int(len(m)),
                         waveform_vs_dynamics=round(float(spearmanr(m.g_waveform, m.g_dynamics)[0]), 4),
                         magnitude_vs_dynamics=round(float(spearmanr(m.g_magnitude, m.g_dynamics)[0]), 4),
                         magnitude_vs_waveform=round(float(spearmanr(m.g_magnitude, m.g_waveform)[0]), 4))
    result[split] = dict(
        ar2=dict(coef=[float(x) for x in c], root_modulus=float(abs(roots[0])), implied_freq_hz=round(f_hat, 5),
                 pure_sinusoid_0p6hz=pure),
        p_value=dict(n_calibration=n_cal, distinct_p_values_normal_eval=int(nrm.p_value.nunique()),
                     min_possible_p=round(1 / (n_cal + 1), 6), record_alarm_curve=curve),
        components_abnormal_alpha1=dict(alarm_rows=int(alarm.sum()), combo_counts=combo.value_counts().to_dict(),
                                        single_component_only_rows=only,
                                        first_alarm_reason_by_record=first_reason),
        rank_correlation=rho)

(HERE / "judge05_checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps(result, ensure_ascii=False, indent=1))
