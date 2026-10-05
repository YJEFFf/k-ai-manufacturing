"""1단계: 분할(A·B)마다 학습 구간에서 모든 후보를 학습하고 검증·시험 행의 점수와 p값을 만든다(보고서 2.3·2.4절).

후보: 행 단위(실시간) maxz3·iforest·knn5·mlp_ae5(예준 press_submission Scorer), lstm20(예준 lstm_ae 공통 프로토콜),
  v1·v2(예준 press_guard GuardModel), v2+C1·v2+C2(예준 v3 조건부 Detector를 기록 앞부분에 적용한 4번째 성분),
  기록 단위 전용 v3 B1·C1d1·C1d2·C2d1·C2d2·B3k5·B3k10. 규칙 H1(R1)·H2(R2)는 2·3단계에서 이 점수 위에 얹는다.
출력: cache/rows_{A,B}.pkl(행 표, git 제외), outputs/tvt_scores_meta.json(재현 확인·누수 점검·기준값)
실행: python code/press/tvt/01_scores.py --repo <팀 레포>
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from lib import (ABN_VALID_RECORDS, CACHE, OUT, R2_Q, SPLITS, V3_COMPONENT_MIN_LEN,
                 f1_counts, ns_time, prefix_r2, repo_arg, setup, v3_records)

V3_RECORD_MODELS = ["B1", "C1d1", "C1d2", "C2d1", "C2d2", "B3k5", "B3k10"]
V3_COMPONENTS = ["C1d1", "C2d1"]
# 동률(검증 F1 차 0.002 이내)일 때 단순한 쪽을 고르는 데 쓴다. 규칙을 얹으면 규칙 수만큼 더한다(evalcore.candidates)
COMPLEXITY = {"maxz3": 1, "iforest": 1, "knn5": 1, "mlp_ae5": 1, "lstm20": 1, "v1": 2, "v2": 3,
              "v2+C1d1": 4, "v2+C2d1": 4, **{f"v3_{m}": 2 for m in V3_RECORD_MODELS}}


def frame_rows(M, F, part, subset):
    """원 프레임 → (정밀도 맞춘 프레임, 기록 번호, 행 표)."""
    D, guard = M["D"], M["guard"]
    status, seg = guard.layout(F)
    assert (status == "ok").all(), f"{part}/{subset}: 수집 상태 오류 행"
    q = D.quantize(D.inputs_only(F), "matched")
    pos, _ = D.segment_positions(seg)
    rows = pd.DataFrame(dict(part=part, subset=subset, rec=[f"{part}:{subset}:{s}" for s in seg], seg=seg, pos=pos,
                             ts=pd.to_datetime(F[D.TIME]).astype("datetime64[ns]").to_numpy(), label=int(subset == "abnormal"),
                             current=q[D.SENSORS[2]].to_numpy(float)))
    return q, seg, rows


def calibrate(M, score_valid, rec_valid, scores: dict):
    """검증 정상 기록별 최대 점수로 conformal p를 낸다. 반환 (보정 분포, 전체 보정 p, 검증 정상 행 LOO p).

    LOO: 검증 정상 행은 자기 기록의 최대 점수를 보정 분포에서 빼고 p를 낸다. 빼지 않으면 그 기록의 p가 작게 나올 수 없어 오경보를 적게 센다.
    """
    cp = M["conformal_p"]
    cal = pd.Series(np.where(np.isfinite(score_valid), score_valid, -np.inf)).groupby(rec_valid).max()
    full = {k: cp(cal.to_numpy(), v) for k, v in scores.items()}
    loo = np.full(len(score_valid), np.nan)
    for r in cal.index:
        m = rec_valid == r
        loo[m] = cp(cal.drop(r).to_numpy(), scores["valid_normal"][m])
    return cal.to_numpy(), full, loo


def v3_prefix_scores(M, det, q, seg, ns):
    """v3 Detector를 '그 행까지의 기록 앞부분'(20행 이상)에 적용한 행별 점수. 실시간으로 계산할 수 있는 값이다."""
    v3 = M["v3"]
    X = q[M["D"].SENSORS].to_numpy(float)
    recs, where = [], []
    for s in pd.unique(seg):
        idx = np.flatnonzero(seg == s)
        for j in range(V3_COMPONENT_MIN_LEN - 1, len(idx)):
            recs.append(v3.Record(len(recs), X[idx[: j + 1]], 0.0, 0.0, 0.0, (), ns))
            where.append(idx[j])
    out = np.full(len(q), np.nan)
    if recs:
        out[np.array(where)] = det.score(v3.features(recs))
    return out


def build_split(M, normal, abnormal, sid):
    """분할 하나의 행 표(검증 정상·시험 정상·이상)와 메타 정보를 만든다."""
    D, guard, ExpTail = M["D"], M["guard"], M["ExpTail"]
    sp = D.split_normal(normal, D.segments(normal), sid)
    train, valid_n, test_n = sp["train"], sp["cal"], sp["test"]

    q_tr, seg_tr, rows_tr = frame_rows(M, train, "train", "normal")
    q_vn, seg_vn, rows_vn = frame_rows(M, valid_n, "valid", "normal")
    q_tn, seg_tn, rows_tn = frame_rows(M, test_n, "test", "normal")
    q_ab, seg_ab, rows_ab = frame_rows(M, abnormal, "abn", "abnormal")
    rows_ab["part"] = np.where(rows_ab.seg < ABN_VALID_RECORDS, "valid", "test")  # 이상 앞 10기록 = 검증
    rows_ab["rec"] = [f"{p}:abnormal:{s}" for p, s in zip(rows_ab.part, rows_ab.seg)]
    frames = {"valid_normal": (q_vn, seg_vn), "test_normal": (q_tn, seg_tn), "abnormal": (q_ab, seg_ab)}

    # 누수 점검: 구간끼리 시각이 하나도 겹치지 않아야 한다
    sets = {k: set(r.ts.astype("int64")) for k, r in (("train", rows_tr), ("valid_n", rows_vn), ("test_n", rows_tn))}
    leak = dict(train_valid=len(sets["train"] & sets["valid_n"]), train_test=len(sets["train"] & sets["test_n"]),
                valid_test=len(sets["valid_n"] & sets["test_n"]),
                abn_valid_test=len(set(rows_ab[rows_ab.part == "valid"].ts.astype("int64")) &
                                   set(rows_ab[rows_ab.part == "test"].ts.astype("int64"))))
    assert not any(leak.values()), leak

    # ---- 예준 v2 (학습 = 정상 학습, 보정 = 정상 검증) ----
    model = guard.GuardModel.fit(train, valid_n, split=sid)
    comp = {k: model.components(q, s) for k, (q, s) in frames.items()}
    sine8 = {k: model.tails["sine8"](M["sine_score"](q[D.SENSORS[2]].to_numpy(float), s, 8)) for k, (q, s) in frames.items()}

    models = {}   # 이름 → (프레임별 점수, 성분별 점수 또는 None)
    models["v2"] = ({k: c["score"] for k, c in comp.items()},
                    {n: {k: c[g] for k, c in comp.items()} for n, g in
                     (("magnitude", "g_magnitude"), ("waveform", "g_waveform"), ("dynamics", "g_dynamics"))})
    # v1 = 크기 성분과 8행 사인 파형 점수 중 큰 값
    models["v1"] = ({k: np.fmax(comp[k]["g_magnitude"], sine8[k]) for k in frames},
                    {"magnitude": {k: comp[k]["g_magnitude"] for k in frames}, "waveform": sine8})

    # ---- v2 + 예준 v3 조건부 성분 ----
    v3 = M["v3"]
    fit_feat = v3.features(v3_records(M, q_tr, "train"))
    for name in V3_COMPONENTS:
        det = v3.Detector(name).fit(fit_feat)
        ref = v3_prefix_scores(M, det, q_tr, seg_tr, "train_prefix")
        tail = ExpTail(ref)  # 학습 구간 점수 분포로 꼬리 확률 척도를 맞춘다
        g = {k: tail(v3_prefix_scores(M, det, q, s, f"{k}_prefix")) for k, (q, s) in frames.items()}
        sc = {k: np.fmax(models["v2"][0][k], g[k]) for k in frames}
        cm = {**models["v2"][1], "conditional": g}
        models[f"v2+{name}"] = (sc, cm)

    # ---- 베이스라인 (예준 press_submission) ----
    scorer = M["Scorer"](q_tr, seg_tr, D.load_vendor(), wins=(8,), baselines=True)
    base = {k: scorer.score(q, s)[0] for k, (q, s) in frames.items()}
    for ours, theirs in (("maxz3", "maxz_3"), ("iforest", "isolation_forest"), ("knn5", "5nn_distance"), ("mlp_ae5", "mlp_ae_w5")):
        models[ours] = ({k: base[k][theirs] for k in frames}, None)
    lstm, _, meta_lstm, _ = M["lstm_ae"].protocol_common(
        q_tr, seg_tr, {"cal": q_vn, "test": q_tn, "abn": q_ab}, {"cal": seg_vn, "test": seg_tn, "abn": seg_ab},
        model.mean, model.scale, CACHE / "lstm", 300, 30, 0, dict(split=sid, variant="tvt_v1"), log=lambda *_: None)
    models["lstm20"] = ({"valid_normal": lstm["cal"], "test_normal": lstm["test"], "abnormal": lstm["abn"]}, None)

    # ---- 보정 → 행 표 ----
    table = pd.concat([rows_vn, rows_tn, rows_ab], ignore_index=True)
    sl = {"valid_normal": slice(0, len(rows_vn)), "test_normal": slice(len(rows_vn), len(rows_vn) + len(rows_tn)),
          "abnormal": slice(len(rows_vn) + len(rows_tn), len(table))}
    no_loo = np.full(len(table) - len(rows_vn), np.nan)  # LOO p는 검증 정상 행에만 있다
    cols = {}
    for name, (sc, cm) in models.items():
        cal, full, loo = calibrate(M, sc["valid_normal"], seg_vn, sc)
        cols[f"{name}|score"] = np.concatenate([sc[k] for k in sl])
        cols[f"{name}|p_full"] = np.concatenate([full[k] for k in sl])
        cols[f"{name}|p_loo"] = np.concatenate([loo, no_loo])
        if cm is not None:
            for cname, g in cm.items():
                # 성분 점수를 결합 점수의 보정 분포와 비교한다(v2 predict와 같음). R2가 '크기 단독' 경보를 가리는 데 쓴다
                _, cfull, cloo = calibrate(M, sc["valid_normal"], seg_vn, g)
                cols[f"{name}|cp_full|{cname}"] = np.concatenate([cfull[k] for k in sl])
                cols[f"{name}|cp_loo|{cname}"] = np.concatenate([cloo, no_loo])
        if name == "v2":
            assert np.allclose(np.sort(cal), np.sort(model.cal)), "v2 보정값이 예준 GuardModel과 다르다"

    # ---- 예준 v3 기록 단위 모델 ----
    rec_list = {"valid_normal": v3_records(M, q_vn, "valid"), "test_normal": v3_records(M, q_tn, "test"),
                "abnormal": v3_records(M, q_ab, "abnormal")}
    rec_feat = {k: v3.features(r) for k, r in rec_list.items()}
    for name in V3_RECORD_MODELS:
        det = v3.Detector(name).fit(fit_feat)
        s = {k: det.score(f) for k, f in rec_feat.items()}
        calib = v3.RankCalibration().fit(s["valid_normal"])
        p = {k: calib.p(v) for k, v in s.items()}
        # 기록 단위 LOO: i번째 검증 정상 기록을 빼고 보정한 순위로 그 기록의 p를 낸다
        loo = np.array([v3.RankCalibration().fit(np.delete(s["valid_normal"], i)).p(s["valid_normal"][i:i + 1])[0]
                        for i in range(len(s["valid_normal"]))])
        # v3 기록 → 행: Record의 원래 행 번호(source_rows)로 펼친다. v3는 중복 행을 지우고 앞뒤를 한 기록으로 합친다
        col_full, col_loo = [], []
        for k, (q, _) in frames.items():
            full_rows, loo_rows = np.full(len(q), np.nan), np.full(len(q), np.nan)
            for i, r in enumerate(rec_list[k]):
                full_rows[list(r.source_rows)] = p[k][i]
                if k == "valid_normal":
                    loo_rows[list(r.source_rows)] = loo[i]
            assert np.isfinite(full_rows).all() or name.startswith("B3"), f"{k}: v3 점수가 빠진 행"
            col_full.append(full_rows)
            col_loo.append(loo_rows)
        cols[f"v3_{name}|score"] = np.full(len(table), np.nan)
        cols[f"v3_{name}|p_full"] = np.concatenate(col_full)
        cols[f"v3_{name}|p_loo"] = np.concatenate(col_loo)

    table = pd.concat([table, pd.DataFrame(cols)], axis=1)
    table["prefix_r2"] = np.concatenate([prefix_r2(q[D.SENSORS[2]].to_numpy(float), s) for q, s in frames.values()])
    # R2 파형 정상 기준은 정상 학습 구간 prefix R²로만 정한다
    r2_train = prefix_r2(q_tr[D.SENSORS[2]].to_numpy(float), seg_tr)
    r2_ref = float(np.nanquantile(r2_train, R2_Q))

    # ---- 재현 확인: 예준 원래 평가(정상 시험 + 이상 21기록 전부)에서 v2 F1 ----
    m = (table.subset == "abnormal") | (table.part == "test")
    v2_alarm = table.loc[m, "v2|p_full"].to_numpy() <= 0.01
    repro = f1_counts(table.loc[m, "label"].to_numpy() == 1, v2_alarm)
    meta = dict(split=sid, rows=dict(valid_normal=len(rows_vn), test_normal=len(rows_tn),
                                     abnormal_valid=int((rows_ab.part == "valid").sum()), abnormal_test=int((rows_ab.part == "test").sum())),
                records=dict(train=int(len(pd.unique(seg_tr))), valid_normal=int(len(pd.unique(seg_vn))),
                             test_normal=int(len(pd.unique(seg_tn))), abnormal_valid=ABN_VALID_RECORDS,
                             abnormal_test=int(len(pd.unique(seg_ab)) - ABN_VALID_RECORDS)),
                leak_check=leak, r2_ref=r2_ref, v2_original_protocol=repro,
                lstm=dict(epochs_run=meta_lstm["epochs_run"], cached=meta_lstm["cached"]),
                models=list(models) + [f"v3_{n}" for n in V3_RECORD_MODELS], complexity=COMPLEXITY)
    return table, meta


def v3_reproduction(M, repo):
    """예준 v3 P2 틀(분 단위 분할, 원자료)에서 B1이 이상 18/21·정상 요청 33을 내는지 확인한다."""
    v3 = M["v3"]
    d = repo / "yejun/press_submission/data/3_소성가공_예지보전"
    normal, _ = v3.records_from_frame(ns_time(pd.read_csv(d / "press_data_normal.csv")))
    abn = v3_records(M, pd.read_csv(d / "outlier_data.csv"), "abnormal")
    roles = v3.split_records(normal, "P2")
    models, cals = v3.fit_suite(v3.features(roles["fit"]), v3.features(roles["cal"]), names=["B1"])
    ev = cals["B1"].p(models["B1"].score(v3.features(roles["evaluation"])))
    ab = cals["B1"].p(models["B1"].score(v3.features(abn)))
    return dict(normal_requests=int((ev <= 0.05).sum()), normal_records=len(ev),
                abnormal_detected=int((ab <= 0.05).sum()), abnormal_records=len(ab),
                expected=dict(normal_requests=33, abnormal_detected=18))


def main():
    repo = repo_arg()
    M = setup(repo)
    OUT.mkdir(exist_ok=True)
    CACHE.mkdir(exist_ok=True)
    normal, abnormal, report = M["D"].load(repo / "yejun/press_submission")
    metas = {"input_sha256": {k: v["sha256"] for k, v in report["files"].items()}}
    for sid in SPLITS:
        table, meta = build_split(M, normal, abnormal, sid)
        table.to_pickle(CACHE / f"rows_{sid}.pkl")
        metas[sid] = meta
        print(sid, "v2 원래 평가 재현:", meta["v2_original_protocol"], "| 누수 점검:", meta["leak_check"], "| R² 기준", round(meta["r2_ref"], 4))
    metas["v3_reproduction"] = v3_reproduction(M, repo)
    print("v3 B1 재현(P2):", metas["v3_reproduction"])
    (OUT / "tvt_scores_meta.json").write_text(json.dumps(metas, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
