"""15단계(사후, test 채점 이후): 기록 단위 AUROC와 특징 맞춤 베이스라인(보고서 2.4절 †). 선택·잠금·2단계 규칙 추가에는 쓰지 않는다.

(A) 기록 단위 AUROC: 기록이 5초 묶음으로 올라온다면(1.4절 추정) 운영 판정 단위는 기록이다. 01 캐시의 R1 없는 행 점수로 기록마다
    최대 점수(점수 없는 행 제외, 기록 전체가 점수 없으면 가장 정상)를 내고, test 기록(정상 A 120·B 180, 이상 11)에서 기록 단위
    AUROC·PR-AUC를 낸다. 모델: v2·v1·max|z|·5NN·IsolationForest·MLP 오토인코더·가이드북 LSTM 오토인코더, 그리고 14의 Ridge 예측 오차
    (LSTM 재학습 없이 Ridge만 다시 적합)와 아래 (B) 두 모델. 이상 기록이 11개라 AUROC 한 단계는 1/(11 × 정상 기록 수)이고 포화되기 쉽다.
(B) 특징 맞춤 베이스라인: "v2 우위가 모델이 아니라 이상 파일을 본 뒤 고른 특징에서 온 것 아니냐"를 본다. 5NN 거리와 IsolationForest의
    행 입력에 v2와 같은 원값 두 개를 더한다: 파형(전류 사인 적합 1−R², 기록 6·7행째는 최근 6행, 8행째부터 최근 8행 = v2 파형 성분 입력)과
    동역학(정상 전류 AR(2) 예측 오차의 절댓값 = v2 동역학 성분 입력). 값이 아직 없는 기록 앞 행(파형 5행 미만·동역학 2행 미만)은 학습 중앙값으로
    채우고, 두 원값은 학습 평균·SD로 표준화한다(세 센서는 베이스라인과 같은 학습 표준화). 5NN·IsolationForest 설정은 예준 Scorer와 같다
    (n_neighbors 5, IsolationForest random_state 0). 01·03과 같은 계약(분할 A·B, valid 정상 기록 최대 점수 conformal α 1%, 행 단위 실시간)으로
    valid·test 실시간 F1, 미탐·오경보 행, 행 AUROC·PR-AUC, 분할 B α 5% 고부하 정상 오경보 기록(valid+test, domain/06 busy_high)을 낸다.
확인: 세 센서만 넣은 5NN은 01 캐시의 knn5 점수와, 다시 적합한 v2 점수는 01 캐시의 v2 점수와 같아야 한다(행 순서 확인).
출력: outputs/record_auroc_featbase.json
실행: python code/press/tvt/15_record_auroc_featbase.py --repo <팀 레포>
"""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.neighbors import NearestNeighbors

from evalcore import evaluate, predict_rows
from lib import CACHE, OUT, PRIMARY_ALPHA, SPLITS, repo_arg, setup


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


S01, V04, S14 = _load("tvt_s01", "01_scores.py"), _load("tvt_v04", "04_validation.py"), _load("tvt_s14", "14_baseline_injection_ridge.py")
CACHED = ["v2", "v1", "maxz3", "knn5", "iforest", "mlp_ae5", "lstm20"]
NEW = ["ridge", "knn5_feat", "iforest_feat"]
FEAT = ["knn5_feat", "iforest_feat"]


class FeatBase:
    """세 센서 표준화 값 + v2 파형·동역학 원값을 입력으로 쓰는 5NN·IsolationForest."""

    def __init__(self, M, model, q_tr, seg_tr):
        self.M, self.g = M, model
        X, raw = self._x(q_tr, seg_tr, fill=None)
        self.med = np.nanmedian(raw, 0)
        raw = np.where(np.isnan(raw), self.med, raw)
        self.mu, self.sd = raw.mean(0), raw.std(0)
        Xtr = np.hstack([X, (raw - self.mu) / self.sd])
        self.nn = NearestNeighbors(n_neighbors=5).fit(Xtr)
        self.nn3 = NearestNeighbors(n_neighbors=5).fit(X)     # 확인용: 01의 knn5와 같아야 한다
        self.iforest = IsolationForest(random_state=0).fit(Xtr)

    def _x(self, q, seg, fill):
        D, guard = self.M["D"], self.M["guard"]
        z = (q[D.SENSORS].to_numpy(float) - self.g.mean) / self.g.scale
        pos = D.segment_positions(seg)[0]
        cur = q[D.SENSORS[2]].to_numpy(float)
        wave = np.where(pos < 7, guard.sine_score(cur, seg, 6), guard.sine_score(cur, seg, 8))
        dyn = guard.ar_residual(q, seg, self.g.coef)
        raw = np.column_stack([wave, dyn])
        if fill is not None:
            raw = np.where(np.isnan(raw), fill, raw)
        return z, raw

    def scores(self, q, seg):
        z, raw = self._x(q, seg, fill=self.med)
        X = np.hstack([z, (raw - self.mu) / self.sd])
        return {"knn5_feat": self.nn.kneighbors(X)[0].mean(1), "iforest_feat": -self.iforest.score_samples(X),
                "knn5_check": self.nn3.kneighbors(z)[0].mean(1)}


def run_split(M, normal, abnormal, sid):
    D, guard = M["D"], M["guard"]
    sp = D.split_normal(normal, D.segments(normal), sid)
    fin = V04.fit_split(M, sp["train"], sp["cal"])
    q_tr, seg_tr, _ = S01.frame_rows(M, sp["train"], "train", "normal")
    ridge = S14.RidgeForecast(fin.model.mean, fin.model.scale).fit(q_tr, seg_tr, D)
    fb = FeatBase(M, fin.model, q_tr, seg_tr)

    parts = {}
    for k, frame in (("valid_normal", sp["cal"]), ("test_normal", sp["test"]), ("abnormal", abnormal)):
        frame = frame.reset_index(drop=True)
        _, seg = guard.layout(frame)
        q = D.quantize(D.inputs_only(frame), "matched")
        sc = fb.scores(q, seg)
        sc["ridge"] = ridge.score(q, seg, D)
        sc["v2"] = fin.model.components(q, seg)["score"]
        parts[k] = (sc, seg)

    t = pd.read_pickle(CACHE / f"rows_{sid}.pkl")
    full = {m: np.concatenate([parts[k][0][m] for k in parts]) for m in NEW + ["v2", "knn5_check"]}
    assert len(full["v2"]) == len(t)
    check = {"v2": float(np.nanmax(np.abs(full["v2"] - t["v2|score"].to_numpy(float)))),
             "knn5_3sensors": float(np.nanmax(np.abs(full["knn5_check"] - t["knn5|score"].to_numpy(float))))}
    assert check["v2"] < 1e-9 and check["knn5_3sensors"] < 1e-9, check
    sc_va, seg_va = parts["valid_normal"]
    for m in NEW:
        _, pf, loo = S01.calibrate(M, sc_va[m], seg_va, {k: v[0][m] for k, v in parts.items()})
        t[f"{m}|score"] = full[m]
        t[f"{m}|p_full"] = np.concatenate([pf[k] for k in parts])
        t[f"{m}|p_loo"] = np.concatenate([loo, np.full(len(t) - len(loo), np.nan)])
    return t, check


def record_auc(t, models):
    """test 기록 단위 AUROC·PR-AUC(기록 최대 점수, 점수 없는 기록은 가장 정상)."""
    tt = t.query("part == 'test'")
    key = tt.subset + ":" + tt.rec.astype(str)
    y = tt.groupby(key).label.max().to_numpy() == 1
    out = {}
    for m in models:
        s = tt[f"{m}|score"].to_numpy(float)
        rmax = pd.Series(np.where(np.isfinite(s), s, np.nan)).groupby(key.to_numpy()).max().reindex(pd.unique(key.to_numpy()))
        rmax = rmax.sort_index()
        v = rmax.to_numpy()
        v = np.where(np.isfinite(v), v, np.nanmin(v) - 1)
        out[m] = dict(auroc=roc_auc_score(y, v), prauc=average_precision_score(y, v))
    n_norm, n_abn = int((~y).sum()), int(y.sum())
    return out, dict(normal_records=n_norm, abnormal_records=n_abn, auroc_step=1 / (n_norm * n_abn), prauc_baseline=n_abn / (n_norm + n_abn))


def row_metrics(t, r2):
    """01·03·10과 같은 계약의 행 단위 지표(R1 없음)."""
    out = {}
    tt = t.query("part == 'test'")
    y = (tt.label == 1).to_numpy()
    for m in FEAT:
        cand = (m, m, False, False, False, 1)
        va = evaluate(t, cand, PRIMARY_ALPHA, "valid", r2)["realtime"]
        te = evaluate(t, cand, PRIMARY_ALPHA, "test", r2)["realtime"]
        sc = tt[f"{m}|score"].to_numpy(float)
        sc = np.where(np.isfinite(sc), sc, np.nanmin(sc) - 1)
        out[m] = dict(valid_f1=va["f1"], test_f1=te["f1"], test_miss_rows=te["fn"], test_fa_rows=te["fp"],
                      auroc=roc_auc_score(y, sc), prauc=average_precision_score(y, sc))
    return out


def high_load_fa(t, r2):
    """분할 B, α 5%, valid+test 정상 기록 중 고부하(domain/06 busy_high) 기록의 오경보 기록 수(14와 같은 계산). v2는 9/53이어야 한다."""
    st = pd.read_csv(S14.REGIME_CSV, encoding="utf-8-sig").set_index("rec").state
    tr_end, va_end = SPLITS["B"]
    res = {}
    for base in ["v2"] + FEAT:
        cand = (base, base, False, False, False, 1)
        hit = []
        for regime in ("valid", "test"):
            g = predict_rows(t, cand, 0.05, regime, r2).query("subset == 'normal'").groupby("rec").alarm_realtime.max()
            for r, a in g.items():
                part, _, k = r.split(":")
                hit.append((int(k) + (tr_end if part == "valid" else va_end), bool(a)))
        h = pd.DataFrame(hit, columns=["rec", "alarm"]).assign(state=lambda d: d.rec.map(st))
        hi = h[h.state == "busy_high"]
        res[base] = dict(fa_records=int(hi.alarm.sum()), records=int(len(hi)), all_fa_records=int(h.alarm.sum()), all_records=int(len(h)))
    assert (res["v2"]["fa_records"], res["v2"]["records"]) == (9, 53), res["v2"]
    return res


def main():
    repo = repo_arg()
    M = setup(repo)
    normal, abnormal, _ = M["D"].load(repo / "yejun/press_submission")
    smeta = json.loads((OUT / "tvt_scores_meta.json").read_text(encoding="utf-8"))
    r2 = {s: smeta[s]["r2_ref"] for s in SPLITS}
    res = {"record_auroc": {}, "record_meta": {}, "featbase_rows": {}, "check_vs_01_cache": {}}
    for sid in SPLITS:
        t, check = run_split(M, normal, abnormal.reset_index(drop=True), sid)
        res["check_vs_01_cache"][sid] = check
        res["record_auroc"][sid], res["record_meta"][sid] = record_auc(t, CACHED + NEW)
        res["featbase_rows"][sid] = row_metrics(t, r2[sid])
        if sid == "B":
            res["high_load_fa_B_a5_valid_test"] = high_load_fa(t, r2[sid])
        print(sid, "완료", check, flush=True)
    res["featbase_valid_f1_mean"] = {m: float(np.mean([res["featbase_rows"][s][m]["valid_f1"] for s in SPLITS])) for m in FEAT}
    (OUT / "record_auroc_featbase.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
