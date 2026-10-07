"""14단계(사후, test 채점 이후): 베이스라인 인공 주입 탐지율과 Ridge 예측 오차 베이스라인(보고서 2.4·2.7절 †). 선택·잠금·2단계 규칙 추가에는 쓰지 않는다.

① 베이스라인 주입: 09와 같은 주입(예준 v3 Generator, seed 11·29·47, 같은 test 정상 기록)을 베이스라인(max|z|·5NN·IsolationForest·
   MLP 오토인코더 5행·가이드북 방식 LSTM 오토인코더 20행)과 v1·v2에 넣고, 모델마다 01과 같은 α 1% 문턱(정상 valid 기록 최대 점수)으로
   기록 단위 탐지율(주입 뒤 한 행이라도 경보)을 잰다. 주입은 기록 안에서만 점수에 영향을 주므로 기록마다 따로 넣은 프레임을 한 번에 채점한다.
   확인: v2 탐지는 09의 ablation_injection.csv(v2 열)와 기록 단위로 같아야 한다
② Ridge 예측 오차(예측 계열 대표): 같은 기록 안 과거 5행 × 3채널로 세 센서의 현재 값을 예측(정상 train 학습, v2와 같은 표준화).
   과거 행이 1~4개인 행은 그만큼의 lag로 따로 학습한 Ridge로, 기록 첫 행은 점수 없음(가장 정상). 점수 = 세 센서 잔차 / 학습 잔차 SD의 최댓값.
   alpha는 train 기록 앞 80%로 학습·뒤 20%로 검증해 고른다. 01·03과 같은 계약(분할 A·B, α 1%, 행 단위 실시간)으로 채점한다
LSTM은 01과 같은 설정(seed 0)으로 분할마다 한 번 다시 학습한다(01의 캐시는 점수만 저장). 다시 학습한 점수와 01 캐시의 차이를 함께 적는다.
출력: outputs/baseline_injection.csv(조건×모델 탐지율), outputs/ridge_baseline.json
실행: python code/press/tvt/14_baseline_injection_ridge.py --repo <팀 레포>
"""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import average_precision_score, roc_auc_score

from evalcore import evaluate, predict_rows
from lib import CACHE, OUT, PRIMARY_ALPHA, SPLITS, f1_counts, repo_arg, setup, v3_records


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


S01, V04, S07 = _load("tvt_s01", "01_scores.py"), _load("tvt_v04", "04_validation.py"), _load("tvt_s07", "07_r1_on_baselines.py")
ALPHA = V04.ALPHA
LAGS = 5
RIDGE_ALPHAS = (0.01, 0.1, 1.0, 10.0, 100.0)
BASES = {"maxz3": "maxz_3", "iforest": "isolation_forest", "knn5": "5nn_distance", "mlp_ae5": "mlp_ae_w5"}
MODELS = ["maxz3", "knn5", "iforest", "mlp_ae5", "lstm20", "v1", "v2", "ridge"]
REGIME_CSV = Path(__file__).resolve().parents[1] / "domain/outputs/06_operating_regime_records.csv"


class RidgeForecast:
    """기록 안 과거 L행(L = min(위치, 5))으로 현재 값을 예측하는 Ridge 묶음. 점수 = 표준화 잔차의 센서 최댓값."""

    def __init__(self, mean, scale):
        self.mean, self.scale = np.asarray(mean, float), np.asarray(scale, float)

    def _z(self, q, D):
        return (q[D.SENSORS].to_numpy(float) - self.mean) / self.scale

    @staticmethod
    def _design(z, pos, L, only=None):
        idx = np.flatnonzero(pos >= L if only is None else pos == only)
        return idx, np.hstack([z[idx - l] for l in range(1, L + 1)]), z[idx]

    def fit(self, q, seg, D):
        z, pos = self._z(q, D), D.segment_positions(seg)[0]
        ids = pd.unique(seg)
        early = np.isin(seg, ids[: int(len(ids) * 0.8)])   # 기록 시간순 앞 80% 학습, 뒤 20% 검증
        mse = {}
        for a in RIDGE_ALPHAS:
            i_a, Xa, ya = self._design(z, np.where(early, pos, -1), LAGS)
            i_b, Xb, yb = self._design(z, np.where(~early, pos, -1), LAGS)
            mse[a] = float(((Ridge(alpha=a).fit(Xa, ya).predict(Xb) - yb) ** 2).mean())
        self.alpha, self.val_mse = min(mse, key=mse.get), mse
        self.models, self.sd = {}, {}
        for L in range(1, LAGS + 1):
            _, X, y = self._design(z, pos, L)
            m = Ridge(alpha=self.alpha).fit(X, y)
            self.models[L], self.sd[L] = m, (m.predict(X) - y).std(0)
        return self

    def score(self, q, seg, D):
        z, pos = self._z(q, D), D.segment_positions(seg)[0]
        out = np.full(len(z), np.nan)   # 기록 첫 행은 점수 없음
        for L in range(1, LAGS + 1):
            idx, X, y = self._design(z, pos, L, only=None if L == LAGS else L)
            if len(idx):
                out[idx] = (np.abs(self.models[L].predict(X) - y) / self.sd[L]).max(1)
        return out


class Suite:
    """분할 하나의 모델 묶음(01과 같은 학습). frame → 모델별 행 점수."""

    def __init__(self, M, sp):
        self.M = M
        D = M["D"]
        self.fin = V04.fit_split(M, sp["train"], sp["cal"])
        g = self.fin.model
        self.q_tr, self.seg_tr, _ = S01.frame_rows(M, sp["train"], "train", "normal")
        self.scorer = M["Scorer"](self.q_tr, self.seg_tr, D.load_vendor(), wins=(8,), baselines=True)
        self.ridge = RidgeForecast(g.mean, g.scale).fit(self.q_tr, self.seg_tr, D)
        # LSTM: 01(lstm_ae.protocol_common)과 같은 창·조기 종료·seed로 다시 학습
        L = M["lstm_ae"]
        ztr = self._zl(self.q_tr)
        ids = np.unique(self.seg_tr)
        cut = ids[int(len(ids) * 0.8)]
        Wa = self._windows(ztr[self.seg_tr < cut], self.seg_tr[self.seg_tr < cut])[1]
        Wb = self._windows(ztr[self.seg_tr >= cut], self.seg_tr[self.seg_tr >= cut])[1]
        self.lstm, hist = L.train_ae(Wa, Wb, 300, 30, 0, log=lambda *_: None)
        self.lstm_epochs = int(len(hist))

    def _zl(self, q):
        return (q[self.M["D"].SENSORS].to_numpy(float) - self.fin.model.mean) / self.fin.model.scale

    def _windows(self, z, seg):
        L = self.M["lstm_ae"]
        idx = L.window_index(seg, L.SEQ)
        return idx, (np.stack([z[i - L.SEQ + 1:i + 1] for i in idx]) if len(idx) else np.empty((0, L.SEQ, 3)))

    def scores(self, q, seg):
        M, D = self.M, self.M["D"]
        base = self.scorer.score(q, seg)[0]
        out = {ours: base[theirs] for ours, theirs in BASES.items()}
        comp = self.fin.model.components(q, seg)
        out["v2"] = comp["score"]
        sine8 = self.fin.model.tails["sine8"](M["sine_score"](q[D.SENSORS[2]].to_numpy(float), seg, 8))
        out["v1"] = np.fmax(comp["g_magnitude"], sine8)
        idx, W = self._windows(self._zl(q), seg)
        s = np.full(len(q), np.nan)
        if len(idx):
            s[idx] = M["lstm_ae"].last_step_error(self.lstm, W)
        out["lstm20"] = s
        out["ridge"] = self.ridge.score(q, seg, D)
        return out


def frame_scores(suite, frame):
    D, guard = suite.M["D"], suite.M["guard"]
    frame = frame.reset_index(drop=True)
    _, seg = guard.layout(frame)
    q = D.quantize(D.inputs_only(frame), "matched")
    return suite.scores(q, seg), seg, D.segment_positions(seg)[0]


def run_split(M, normal, abnormal, sid):
    D, v3 = M["D"], M["v3"]
    sp = D.split_normal(normal, D.segments(normal), sid)
    suite = Suite(M, sp)
    # ---- 보정(01과 같음): 정상 valid 기록 최대 점수 ----
    sc_va, seg_va, _ = frame_scores(suite, sp["cal"])
    cal = {m: S01.calibrate(M, sc_va[m], seg_va, {"valid_normal": sc_va[m]})[0] for m in MODELS}
    assert np.allclose(np.sort(cal["v2"]), np.sort(suite.fin.model.cal)), "v2 보정값 불일치"

    # ---- 01 캐시와 같은 행 순서로 점수를 붙인다(Ridge 채점·재학습 차이 확인) ----
    t = pd.read_pickle(CACHE / f"rows_{sid}.pkl")
    abn = abnormal.reset_index(drop=True)
    parts = {"valid_normal": (sc_va, seg_va), "test_normal": frame_scores(suite, sp["test"])[:2], "abnormal": frame_scores(suite, abn)[:2]}
    full = {m: np.concatenate([parts[k][0][m] for k in parts]) for m in MODELS}
    assert len(full["v2"]) == len(t)
    refit_diff = {m: float(np.nanmax(np.abs(full[m] - t[f"{m}|score"].to_numpy(float)))) for m in MODELS if m != "ridge"}
    assert refit_diff["v2"] < 1e-9 and np.array_equal(np.isnan(full["v2"]), t["v2|score"].isna().to_numpy()), "v2 행 순서 불일치"
    _, pf, loo = S01.calibrate(M, sc_va["ridge"], seg_va, {k: v[0]["ridge"] for k, v in parts.items()})
    t["ridge|score"] = full["ridge"]
    t["ridge|p_full"] = np.concatenate([pf[k] for k in parts])
    t["ridge|p_loo"] = np.concatenate([loo, np.full(len(t) - len(loo), np.nan)])

    # ---- 주입(09와 같은 조건·순서) ----
    test = sp["test"].reset_index(drop=True)
    recs = V04.records_of(test, M)
    S = D.SENSORS
    X = test[S].to_numpy(float)
    q_tr = D.quantize(D.inputs_only(sp["train"]), "matched")
    gen = v3.Generator(v3.features(v3_records(M, q_tr, "train")), sid)
    f_test = v3.features([V04.v3_record(M, X[idx], k) for k, idx in enumerate(recs)])
    rows = []
    for fam, strengths in V04.SELECTION.items():
        for target in V04.TARGETS[fam]:
            axis = f"v{target}_rms" if target < 2 else "i_residual"
            scale = gen.scales(f_test, axis)
            for strength in (0.0,) + strengths:
                for seed in (V04.SEEDS if strength > 0 else V04.SEEDS[:1]):
                    Xn, onset, ok = X.copy(), np.zeros(len(recs), int), np.ones(len(recs), bool)
                    for k, idx in enumerate(recs):
                        rec, info = gen.inject(V04.v3_record(M, X[idx], k), fam, target, strength, seed, scale[k])
                        if strength > 0 and not info["valid"]:   # 09와 같이 미지원 주입은 미탐으로 센다
                            ok[k] = False
                            continue
                        Xn[idx], onset[k] = rec.x, max(info["onset"], 0)
                    frame = test.copy()
                    frame[S] = Xn
                    sc, _, pos = frame_scores(suite, frame)
                    for m in MODELS:
                        p = M["conformal_p"](cal[m], sc[m])
                        a = np.isfinite(p) & (p <= ALPHA)
                        det = [bool(ok[k] and (a[idx] & (pos[idx] >= onset[k])).any()) for k, idx in enumerate(recs)]
                        rows += [dict(split=sid, family=fam, target=target, strength=strength, seed=seed, record=k, model=m, detected=d)
                                 for k, d in enumerate(det)]
    meta = dict(ridge_alpha=suite.ridge.alpha, ridge_val_mse=suite.ridge.val_mse, lstm_epochs=suite.lstm_epochs,
                refit_max_abs_diff_vs_01_cache=refit_diff)
    return t, pd.DataFrame(rows), meta


def ridge_metrics(t, sid, r2):
    """01·03·07·10과 같은 계약의 Ridge 지표."""
    out = {}
    for name, h1 in (("ridge", False), ("ridge+R1", True)):
        cand = (name, "ridge", h1, False, False, 1 + h1)
        va = evaluate(t, cand, PRIMARY_ALPHA, "valid", r2)["realtime"]
        te = evaluate(t, cand, PRIMARY_ALPHA, "test", r2)["realtime"]
        to = S07.test_only(t, "ridge", h1, False, r2)
        out[name] = dict(valid_f1=va["f1"], test_f1=te["f1"], test_miss_rows=te["fn"], test_fa_rows=te["fp"], test_only_f1=to["f1"])
    tt = t.query("part == 'test'")
    y = (tt.label == 1).to_numpy()
    sc = tt["ridge|score"].to_numpy(float)
    sc = np.where(np.isfinite(sc), sc, np.nanmin(sc) - 1)   # 점수 없는 행(기록 첫 행)은 가장 정상
    out["ridge"].update(auroc=roc_auc_score(y, sc), prauc=average_precision_score(y, sc))
    return out


def high_load_fa(tables, meta_r2):
    """분할 B, α 5%, valid+test 정상 기록 중 고부하(06의 busy_high) 기록의 오경보 기록 수. v2로 3.2절 표(9/53)와 맞는지 확인한다."""
    st = pd.read_csv(REGIME_CSV, encoding="utf-8-sig").set_index("rec").state
    t = tables["B"]
    tr_end, va_end = SPLITS["B"]
    res = {}
    for base in ("v2", "ridge"):
        cand = (base, base, False, False, False, 1)
        hit = []
        for regime in ("valid", "test"):
            p = predict_rows(t, cand, 0.05, regime, meta_r2["B"]).query("subset == 'normal'")
            g = p.groupby("rec").alarm_realtime.max()
            for r, a in g.items():
                part, _, k = r.split(":")
                orig = int(k) + (tr_end if part == "valid" else va_end)
                hit.append((orig, bool(a)))
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
    tables, inj, metas = {}, [], {}
    for sid in SPLITS:
        t, rows, meta = run_split(M, normal, abnormal, sid)
        tables[sid], metas[sid] = t, meta
        inj.append(rows)
        print(sid, "완료", meta["ridge_alpha"], meta["refit_max_abs_diff_vs_01_cache"], flush=True)
    inj = pd.concat(inj, ignore_index=True)
    # 확인: v2 = 09의 기록 단위 결과
    ref = pd.read_csv(OUT / "ablation_injection.csv")
    key = ["split", "family", "target", "strength", "seed", "record"]
    m = inj[inj.model == "v2"].merge(ref[key + ["v2"]], on=key, how="inner")
    mismatch = int((m.detected != m.v2).sum())
    if len(m) != len(ref) or mismatch:
        raise SystemExit(f"v2 주입 결과가 09와 다름: {len(m)} / {len(ref)}, 불일치 {mismatch}")
    pod = inj.groupby(["split", "family", "target", "strength", "model"]).detected.mean().round(4).unstack("model")[MODELS].reset_index()
    pod.to_csv(OUT / "baseline_injection.csv", index=False)
    res = {"meta": metas, "v2_check_vs_09": dict(records=len(m), mismatch=mismatch),
           "ridge": {s: ridge_metrics(tables[s], s, r2[s]) for s in SPLITS},
           "high_load_fa_B_a5_valid_test": high_load_fa(tables, r2)}
    (OUT / "ridge_baseline.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    pd.set_option("display.width", 220)
    print(pod.to_string(index=False))
    print(json.dumps(res, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
