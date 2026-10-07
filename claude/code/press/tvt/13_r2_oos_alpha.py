"""13단계(사후, test 채점 이후): R2 준-표본 밖 확인, conformal α 명목 대 실측, 블록 부트스트랩 대조(보고서 2.5·3.2절 †).

선택·잠금·2단계 규칙 추가에는 쓰지 않는다.
(A) R2 준-표본 밖: R2 착안 때 본 정상 기록(α 1% v2 오경보 303·423·461·570, 정상 기록 번호 0~599)과 앞뒤 1기록을 빼고,
    04의 V3 분할(분 단위 P2 + 시간순 5창)마다 다시 학습한 모델로 정상 오경보 기록 수를 센다(v2 대 v2+R2, v2+R1 대 v2+R1+R2, α 1·3·5%).
    시간순 5창의 평가 구간(300~599)은 서로 겹치지 않으므로 합계와 블록 부트스트랩은 5창으로 한다(창 안에서 연속 10기록 블록을
    복원 추출해 창을 합치는 쌍 부트스트랩, 2,000회, seed 0). 고부하는 domain/06의 기록 상태 busy_high(보고서 3.2절)다.
(B) α 명목 대 실측: v2·v2+R1·v2+R1+R2의 정상 오경보 기록 비율을 α 1·3·5·10%에서 test 정상(A 120·B 180기록)과 V3 6개 분할에서 재고
    Clopper–Pearson 양측 95% 구간을 붙인다. conformal 해상도 = 1/(보정 기록 수 + 1).
(C) 블록 부트스트랩: 10과 같은 v2 − v1 test 행 F1(R1 없음, α 1%)·AUROC 차이를, 정상은 연속 10기록·이상은 연속 3기록 이동 블록으로
    뽑아(2,000회, seed 0) 다시 구간을 내고 10의 기록 독립 구간(threshold_free_boot.csv)과 나란히 적는다.
출력: outputs/r2_oos_alpha.json
실행: python code/press/tvt/13_r2_oos_alpha.py --repo <팀 레포>
"""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import beta
from sklearn.metrics import roc_auc_score

from lib import CACHE, OUT, PRIMARY_ALPHA, SPLITS, prefix_r2, repo_arg, setup


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


V04 = _load("tvt_v04", "04_validation.py")
T10 = _load("tvt_t10", "10_threshold_free.py")

SEEN = (303, 423, 461, 570)                                   # R2 착안 때 본 α 1% v2 오경보 기록
EXCLUDE = {r + d for r in SEEN for d in (-1, 0, 1)}
ALPHAS_A = (0.01, 0.03, 0.05)
ALPHAS_B = (0.01, 0.03, 0.05, 0.10)
VARIANTS = ("v2", "v2+R2", "v2+R1", "v2+R1+R2")
N_BOOT = 2000
REGIME = Path(__file__).resolve().parents[1] / "domain/outputs/06_operating_regime_records.csv"


def rows_multi(fin, frame, alphas):
    """04 Final.rows와 같은 계산을 α 여러 개로 한 번에 한다(성분 점수·p값은 한 번만 계산)."""
    D, guard, cp = fin.M["D"], fin.M["guard"], fin.M["conformal_p"]
    frame = frame.reset_index(drop=True)
    _, seg = guard.layout(frame)
    q = D.quantize(D.inputs_only(frame), "matched")
    comp = fin.model.components(q, seg)
    p = {k: cp(fin.model.cal, comp[k]) for k in ("score", "g_magnitude", "g_waveform", "g_dynamics")}
    wave_ok = prefix_r2(q[D.SENSORS[2]].to_numpy(float), seg) >= fin.r2_ref
    base = dict(seg=seg, ts=pd.to_datetime(frame.TimeStamp).astype("datetime64[ns]").to_numpy(), wave_ok=wave_ok)
    out = {}
    for a in alphas:
        f = {k: np.isfinite(v) & (v <= a) for k, v in p.items()}
        mag_only = f["g_magnitude"] & ~f["g_waveform"] & ~f["g_dynamics"]
        out[a] = dict(base, v2=f["score"], own2=f["score"] & ~(mag_only & wave_ok))
    return out


def record_alerts(r, rec_ids):
    """변형별로 경보가 한 번이라도 난 기록(전역 정상 기록 번호 → bool)."""
    out = {}
    assert len(pd.unique(r["seg"])) == len(rec_ids), "평가 프레임의 기록 수가 전역 기록 번호 수와 다름"
    for v in VARIANTS:
        a = r["own2"] if v == "v2+R2" else V04.Final.alarms(r, v)[0]
        per = pd.Series(a).groupby(r["seg"]).max()
        out[v] = dict(zip(rec_ids, per.reindex(pd.unique(r["seg"])).to_numpy(bool)))
    return out


def cp_ci(k, n):
    """Clopper–Pearson 양측 95% 구간."""
    lo = beta.ppf(0.025, k, n - k + 1) if k > 0 else 0.0
    hi = beta.ppf(0.975, k + 1, n - k) if k < n else 1.0
    return [round(float(lo), 4), round(float(hi), 4)]


def folds(normal, D):
    """04 v3_splits와 같은 V3 분할(학습·보정·평가 마스크)과 평가 구간의 정상 기록 번호."""
    seg_all = D.segments(normal)
    minutes = (pd.to_datetime(normal.TimeStamp) - pd.to_datetime(normal.TimeStamp).iloc[0]).dt.total_seconds() / 60
    rec_start = minutes.groupby(seg_all).transform("min").to_numpy()
    rec_end = minutes.groupby(seg_all).transform("max").to_numpy()
    out = {"P2(분 0~40/40~60/60~)": ((rec_end < 40), (rec_start >= 40) & (rec_end < 60), rec_start >= 60)}
    for end in (180, 240, 300, 360, 420):
        out[f"rolling 평가{end + 120}~{end + 179}"] = (seg_all < end, (seg_all >= end) & (seg_all < end + 120),
                                                    (seg_all >= end + 120) & (seg_all < end + 180))
    return seg_all, out


def main():
    repo = repo_arg()
    M = setup(repo)
    D = M["D"]
    normal, _, _ = D.load(repo / "yejun/press_submission")
    regime = pd.read_csv(REGIME).set_index("rec")
    high = set(regime.index[regime.state == "busy_high"])
    seg_all, fold_masks = folds(normal, D)
    assert len(regime) == len(np.unique(seg_all)) == 600

    # ---- (A)·(B) V3 분할
    fold_rows, rec_tables = [], {}
    for name, (tr, ca, te) in fold_masks.items():
        fin = V04.fit_split(M, normal[tr].reset_index(drop=True), normal[ca].reset_index(drop=True))
        ev = normal[te].reset_index(drop=True)
        rec_ids = list(pd.unique(seg_all[te]))
        rm = rows_multi(fin, ev, sorted(set(ALPHAS_A) | set(ALPHAS_B)))
        n_cal = len(np.unique(seg_all[ca]))
        for a, r in rm.items():
            al = record_alerts(r, rec_ids)
            rec_tables[(name, a)] = al
            keep = [k for k in rec_ids if k not in EXCLUDE]
            hk = [k for k in keep if k in high]
            fold_rows.append(dict(fold=name, alpha=a, n_cal=n_cal, resolution=round(1 / (n_cal + 1), 4), n_all=len(rec_ids),
                                  n_keep=len(keep), n_keep_high=len(hk),
                                  **{f"all|{v}": int(sum(al[v][k] for k in rec_ids)) for v in VARIANTS},
                                  **{f"keep|{v}": int(sum(al[v][k] for k in keep)) for v in VARIANTS},
                                  **{f"high|{v}": int(sum(al[v][k] for k in hk)) for v in VARIANTS}))
    fr = pd.DataFrame(fold_rows)
    rolling = fr[fr.fold.str.startswith("rolling")]

    # (A) 5창 합계와 쌍 블록 부트스트랩(창 안 연속 10기록 블록)
    rng = np.random.default_rng(0)
    A = {}
    for a in ALPHAS_A:
        sub = rolling[rolling.alpha == a]
        tot = {c: int(sub[c].sum()) for c in sub.columns if "|" in c or c.startswith("n_")}
        blocks = []                                   # 창별 블록 목록: 블록 = 남긴 기록들의 [v2, v2+R2, v2+R1, v2+R1+R2, high] 배열
        for name in sub.fold:
            al = rec_tables[(name, a)]
            recs = sorted(al["v2"])
            fb = []
            for b0 in range(recs[0], recs[-1] + 1, 10):
                ks = [k for k in recs if b0 <= k < b0 + 10 and k not in EXCLUDE]
                fb.append(np.array([[al[v][k] for v in VARIANTS] + [k in high] for k in ks], dtype=float).reshape(-1, 5))
            blocks.append(fb)
        diffs = {"v2-v2+R2": [], "v2+R1-v2+R1+R2": [], "high:v2-v2+R2": [], "high:v2+R1-v2+R1+R2": []}
        for _ in range(N_BOOT):
            x = np.vstack([fb[i] for fb in blocks for i in rng.integers(0, len(fb), len(fb))])
            h = x[:, 4] == 1
            diffs["v2-v2+R2"].append(x[:, 0].mean() - x[:, 1].mean())
            diffs["v2+R1-v2+R1+R2"].append(x[:, 2].mean() - x[:, 3].mean())
            diffs["high:v2-v2+R2"].append(x[h, 0].mean() - x[h, 1].mean() if h.any() else np.nan)
            diffs["high:v2+R1-v2+R1+R2"].append(x[h, 2].mean() - x[h, 3].mean() if h.any() else np.nan)
        A[f"{a}"] = dict(rolling_total=tot,
                         rate_keep={v: round(tot[f"keep|{v}"] / tot["n_keep"], 4) for v in VARIANTS},
                         rate_high={v: round(tot[f"high|{v}"] / tot["n_keep_high"], 4) for v in VARIANTS},
                         boot_ci95={k: [round(float(np.nanquantile(d, .025)), 4), round(float(np.nanquantile(d, .975)), 4)] for k, d in diffs.items()})

    # (B) test 정상 A·B와 V3 6개 분할의 α 명목 대 실측(전체 기록, 제외 없음)
    B = {"test": {}, "v3": {}}
    for sid in SPLITS:
        sp = D.split_normal(normal, seg_all, sid)
        fin = V04.fit_split(M, sp["train"], sp["cal"])
        rec_ids = list(pd.unique(seg_all[seg_all >= D.SPLITS[sid][2]]))
        n_cal = D.SPLITS[sid][2] - D.SPLITS[sid][1]
        rm = rows_multi(fin, sp["test"], ALPHAS_B)
        # 확인: α 1%의 행 경보가 04 Final.rows와 같아야 한다
        r_ref = fin.rows(sp["test"])
        assert (r_ref["v2"] == rm[0.01]["v2"]).all() and (r_ref["own2"] == rm[0.01]["own2"]).all()
        B["test"][sid] = {"n": len(rec_ids), "n_cal": n_cal, "resolution": round(1 / (n_cal + 1), 4)}
        for a, r in rm.items():
            al = record_alerts(r, rec_ids)
            B["test"][sid][f"{a}"] = {v: dict(k=int(sum(al[v].values())), rate=round(sum(al[v].values()) / len(rec_ids), 4),
                                              ci95=cp_ci(int(sum(al[v].values())), len(rec_ids))) for v in ("v2", "v2+R1", "v2+R1+R2")}
    for name in fold_masks:
        g = fr[fr.fold == name]
        B["v3"][name] = {"n": int(g.n_all.iloc[0]), "n_cal": int(g.n_cal.iloc[0]), "resolution": float(g.resolution.iloc[0])}
        for _, r in g.iterrows():
            B["v3"][name][f"{r.alpha}"] = {v: dict(k=int(r[f"all|{v}"]), rate=round(int(r[f"all|{v}"]) / int(r.n_all), 4),
                                                  ci95=cp_ci(int(r[f"all|{v}"]), int(r.n_all)))
                                           for v in ("v2", "v2+R1", "v2+R1+R2")}

    # 시간순 5창 합(평가 300~599가 서로 겹치지 않음)
    B["v3_rolling_pooled"] = {"n": int(rolling[rolling.alpha == ALPHAS_B[0]].n_all.sum())}
    for a in ALPHAS_B:
        g = rolling[rolling.alpha == a]
        n = int(g.n_all.sum())
        B["v3_rolling_pooled"][f"{a}"] = {v: dict(k=int(g[f"all|{v}"].sum()), rate=round(int(g[f"all|{v}"].sum()) / n, 4),
                                                 ci95=cp_ci(int(g[f"all|{v}"].sum()), n)) for v in ("v2", "v2+R1", "v2+R1+R2")}

    # (C) v2 − v1 이동 블록 부트스트랩(정상 10기록, 이상 3기록)
    rng = np.random.default_rng(0)
    old = pd.read_csv(OUT / "threshold_free_boot.csv").query("other == 'v1'").set_index("split")
    C = {}
    for s in SPLITS:
        t = pd.read_pickle(CACHE / f"rows_{s}.pkl").query("part == 'test'").reset_index(drop=True)
        y = (t.label == 1).to_numpy()
        sc, al = {}, {}
        for m in ("v1", "v2"):
            x = np.nan_to_num(t[f"{m}|score"].to_numpy(float), nan=-np.inf, neginf=-np.inf)
            sc[m] = np.where(np.isfinite(x), x, np.nanmin(x[np.isfinite(x)]) - 1)
            p = t[f"{m}|p_full"].to_numpy(float)
            al[m] = np.isfinite(p) & (p <= PRIMARY_ALPHA)
        order = {sub: sorted(t.loc[t.subset == sub, "rec"].unique(), key=lambda r: int(r.split(":")[-1])) for sub in ("normal", "abnormal")}
        rows_of = {r: np.flatnonzero(t.rec.to_numpy() == r) for sub in order for r in order[sub]}

        def mbb(recs, L):
            n = len(recs)
            starts = rng.integers(0, n - L + 1, int(np.ceil(n / L)))
            return [recs[i + j] for i in starts for j in range(L)][:n]

        dd = []
        for _ in range(N_BOOT):
            pick = np.concatenate([rows_of[r] for r in mbb(order["normal"], 10) + mbb(order["abnormal"], 3)])
            yb = y[pick]
            dd.append((T10.f1(yb, al["v2"][pick]) - T10.f1(yb, al["v1"][pick]),
                       roc_auc_score(yb, sc["v2"][pick]) - roc_auc_score(yb, sc["v1"][pick])))
        dd = np.array(dd)
        C[s] = dict(n_normal=len(order["normal"]), n_abnormal=len(order["abnormal"]),
                    block=dict(d_f1=[round(float(np.quantile(dd[:, 0], q)), 4) for q in (.025, .975)],
                               d_auroc=[round(float(np.quantile(dd[:, 1], q)), 4) for q in (.025, .975)]),
                    record_independent=dict(d_f1=[round(float(old.loc[s, "d_f1_lo"]), 4), round(float(old.loc[s, "d_f1_hi"]), 4)],
                                            d_auroc=[round(float(old.loc[s, "d_auroc_lo"]), 4), round(float(old.loc[s, "d_auroc_hi"]), 4)]))

    res = dict(excluded_records=sorted(EXCLUDE), high_load_definition="domain/06 state == busy_high",
               A_r2_out_of_sample=A, A_per_fold=fr.to_dict("records"), B_alpha_nominal_vs_actual=B, C_block_bootstrap=C)
    (OUT / "r2_oos_alpha.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    pd.set_option("display.width", 250)
    print(fr.to_string(index=False))
    print(json.dumps(dict(A=A, C=C), ensure_ascii=False, indent=1))
    print(json.dumps(B, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
