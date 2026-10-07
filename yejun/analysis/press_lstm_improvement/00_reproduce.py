"""0단계: 준용 tvt 결과를 이 PC에서 다시 만들어, 이후 비교가 보고서와 같은 조건인지 확인한다.

01_scores.build_split으로 분할 A·B의 행 표(v2·v1·베이스라인·lstm20·v3)를 다시 만들고,
잠금 후보 전부를 valid·test, α 1·3·5%로 채점해 claude/code/press/tvt/outputs/tvt_valid.csv·tvt_test.csv와 견준다.
R1을 붙인 기준선(07_r1_on_baselines의 valid·test F1)도 tvt_r1_baselines.csv와 견준다.
출력: outputs/00_reproduction.csv(행별 차이), outputs/00_reproduction.json(요약)
실행: PYTHONDONTWRITEBYTECODE=1 python 00_reproduce.py
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

import lx_harness as H


def main():
    t0 = time.time()
    _, ev, _ = H.tvt()
    rows, metas = [], {}
    for sid in H.SPLITS:
        t1 = time.time()
        table, meta = H.base_table(sid)
        metas[sid] = dict(r2_ref=meta["r2_ref"], lstm=meta["lstm"], v2_original_protocol=meta["v2_original_protocol"],
                          build_seconds=round(time.time() - t1, 1))
        print(sid, "행 표", table.shape, "LSTM", meta["lstm"], f"{time.time() - t1:.0f}s", flush=True)
        for c in ev.candidates(meta["complexity"]):
            for a in H.ALPHAS:
                for regime in ("valid", "test"):
                    for mode, m in ev.evaluate(table, c, a, regime, meta["r2_ref"]).items():
                        rows.append(dict(split=sid, alpha=a, model=c[0], mode=mode, regime=regime, **m))
    mine = pd.DataFrame(rows)
    ref = pd.concat([pd.read_csv(H.TVT / "outputs/tvt_valid.csv").assign(regime="valid"),
                     pd.read_csv(H.TVT / "outputs/tvt_test.csv").assign(regime="test")], ignore_index=True)
    key = ["split", "alpha", "model", "mode", "regime"]
    j = mine.merge(ref[key + ["tp", "fp", "fn", "f1"]], on=key, how="outer", suffixes=("", "_ref"), indicator=True)
    for k in ("tp", "fp", "fn", "f1"):
        j[f"d_{k}"] = j[k] - j[f"{k}_ref"]
    j["same"] = (j[["d_tp", "d_fp", "d_fn"]].abs().sum(axis=1) == 0) & (j["_merge"] == "both")
    j.to_csv(H.OUT / "00_reproduction.csv", index=False)

    # R1을 붙인 기준선(07)
    r1 = pd.read_csv(H.TVT / "outputs/tvt_r1_baselines.csv")
    r1_rows = []
    for sid in H.SPLITS:
        table, meta = H.base_table(sid)
        for base in ("iforest", "lstm20", "mlp_ae5", "maxz3", "knn5", "v1", "v2"):
            va = H.evaluate(table, base, True, H.PRIMARY_ALPHA, "valid", meta["r2_ref"])["realtime"]
            te = H.evaluate(table, base, True, H.PRIMARY_ALPHA, "test", meta["r2_ref"])["realtime"]
            ref_r = r1[(r1.split == sid) & (r1.model == base + "+H1")].iloc[0]
            r1_rows.append(dict(split=sid, model=base + "+H1", valid_f1=va["f1"], valid_f1_ref=ref_r.valid_f1,
                                test_f1=te["f1"], test_f1_ref=ref_r.test_f1))
    r1m = pd.DataFrame(r1_rows)
    r1m["same"] = np.isclose(r1m.valid_f1, r1m.valid_f1_ref, atol=1e-9) & np.isclose(r1m.test_f1, r1m.test_f1_ref, atol=1e-9)

    bad = j[~j.same]
    summary = dict(
        cells=int(len(j)), identical=int(j.same.sum()), differing=int((~j.same).sum()),
        differing_models=sorted(bad.model.unique().tolist()),
        differing_detail=bad[key + ["tp", "tp_ref", "fp", "fp_ref", "fn", "fn_ref", "f1", "f1_ref"]].round(6).to_dict("records")[:60],
        r1_baselines=r1m.round(6).to_dict("records"), r1_all_same=bool(r1m.same.all()),
        meta=metas, seconds=round(time.time() - t0, 1),
        tvt_lstm_meta={s: __import__("json").loads((H.TVT / "outputs/tvt_scores_meta.json").read_text(encoding="utf-8"))[s]["lstm"]
                       for s in H.SPLITS},
    )
    H.dump(summary, H.OUT / "00_reproduction.json")
    print(f"셀 {summary['cells']} 중 같음 {summary['identical']}, 다름 {summary['differing']} → 다른 모델 {summary['differing_models']}")
    print("R1 기준선 모두 같음:", summary["r1_all_same"])
    if len(bad):
        print(bad[key + ["tp", "tp_ref", "fp", "fp_ref", "fn", "fn_ref"]].head(40).to_string(index=False))
    print(f"{summary['seconds']}s")


if __name__ == "__main__":
    main()
