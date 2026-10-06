"""valid만으로 LSTM 변형을 채점하고 PROTOCOL.md 5절 규칙으로 고른다. test는 열지 않는다.

결과를 열기 전 단언(실패하면 멈춘다):
- 이 실험 경로의 기본 설정(W20·none·64-32·300/30·early80, raw-last, 시드 0) 점수 = 준용 행 표의 lstm20 점수(A·B, NaN 포함 비트 단위)
- 준용 행 표의 기록 번호(seg) = 학습 입력 npz의 기록 번호(valid 정상·test 정상·이상 순서)
- 채점에 들어가는 설정마다 분할 A·B × 시드 0·1·2가 모두 있다
선택 단위: 시드 0·1·2 앙상블(e012, 보정 전 점수 평균). 지표 = valid 실시간 행 F1(α 1%)의 A·B 평균.
동률 폭 = max(0.002, 단일 시드 지표 표준편차/√3). 동률이면 가이드북에서 바꾼 차원 수 → W → 이름순.
--stage 1    : 1단계 격자 → 트랙 L 승자, 상위 3개 (W, 앞부분, 용량) 조합 → outputs/02_stage1_selection.json(+.sha256)
--stage 2a   : 상위 3개 조합의 (W, 앞부분)에서 용량까지 비교 → outputs/02_stage2a_selection.json(+.sha256)
--stage final: 모든 설정(1·2a·2b) 중 트랙 L 최종, 트랙 L+R1 주 결과 = 같은 변형 + R1, 탐색 결과는 보조 → outputs/02_selection.json(+.sha256)
출력: outputs/02_valid.csv, outputs/02_valid_summary.csv, 단계별 선택 파일
실행: PYTHONDONTWRITEBYTECODE=1 python 02_valid_select.py --stage 1
"""
from __future__ import annotations

import argparse
import json
import sys
import time

sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import lx_harness as H  # noqa: E402
import lx_scoring as X  # noqa: E402

REFS = ["v2", "v2+H1", "v2+H1+H2", "lstm20", "lstm20+H1", "mlp_ae5", "maxz3"]
START = ("W20-none-64x32-e300p30", "raw-last")
DIMS = ["cfg", "scoring", "chan", "agg", "W", "warm", "h1", "h2", "epochs", "patience", "data"]


def lock(path):
    path.with_suffix(".sha256").write_text(H.sha256_file(path), encoding="utf-8")


def read_locked(name: str) -> dict:
    path = H.OUT / name
    lk = path.with_suffix(".sha256")
    if not lk.exists() or H.sha256_file(path) != lk.read_text(encoding="utf-8").strip():
        raise SystemExit(f"{name}의 잠금이 맞지 않는다")
    return json.loads(path.read_text(encoding="utf-8"))


def preflight(sid, table, info):
    """결과를 열기 전 단언."""
    inp = np.load(H.CACHE / f"inputs_{sid}.npz")
    seg_npz = np.concatenate([inp[f"seg_{k}"] for k in H.FRAMES])
    assert np.array_equal(table["seg"].to_numpy(), seg_npz), f"{sid}: 행 표와 학습 입력의 기록 번호가 다르다"
    mine = table[f"{X.vname(START[0], START[1], 0)}|score"].to_numpy()
    assert np.array_equal(mine, table["lstm20|score"].to_numpy(), equal_nan=True), f"{sid}: 기본 설정 점수가 lstm20과 다르다"
    single = info[~info.seed.str.startswith("e")]
    seeds = single.groupby("cfg").seed.apply(lambda s: sorted(set(s)))
    bad = seeds[seeds.apply(lambda s: s[:3] != ["0", "1", "2"])]
    assert bad.empty, f"{sid}: 시드 0·1·2가 다 있지 않은 설정 {bad.to_dict()}"


def eval_valid():
    _, ev, _ = H.tvt()
    rows, refs, infos, cfg_sets = [], [], [], []
    for sid in H.SPLITS:
        t, meta, info = X.build_variant_table(sid, ens_sets=("e012",))
        preflight(sid, t, info)
        r2 = meta["r2_ref"]
        for v in info.itertuples():
            ens = v.seed.startswith("e")
            for h1 in (False, True):
                for a in (H.ALPHAS if ens else (H.PRIMARY_ALPHA,)):
                    for mode, m in H.evaluate(t, v.variant, h1, a, "valid", r2).items():
                        rows.append(dict(split=sid, variant=v.variant, rule="R1" if h1 else "none", alpha=a, mode=mode, **m))
        infos.append(info)
        cfg_sets.append(set(info.cfg))
        known = {c[0]: c for c in ev.candidates(meta["complexity"])}
        for name in REFS:
            c = known.get(name) or (name, name.split("+")[0], "+H1" in name, "+H2" in name, False, 1)
            for a in H.ALPHAS:
                for mode, m in ev.evaluate(t, c, a, "valid", r2).items():
                    refs.append(dict(split=sid, model=name, alpha=a, mode=mode, **m))
    assert cfg_sets[0] == cfg_sets[1], f"분할 A·B의 설정이 다르다: {cfg_sets[0] ^ cfg_sets[1]}"
    info = pd.concat(infos, ignore_index=True).drop_duplicates("variant").reset_index(drop=True)
    return pd.DataFrame(rows), info, pd.DataFrame(refs)


def summarize(valid, info) -> pd.DataFrame:
    """(설정, 채점 방식, 규칙)마다 앙상블 지표와 단일 시드 지표(평균·표준편차·SE)."""
    p = valid[(valid.alpha == H.PRIMARY_ALPHA) & (valid["mode"] == "realtime")]
    ab = p.pivot_table(index=["variant", "rule"], columns="split", values="f1").reset_index()
    assert ab[list(H.SPLITS)].notna().all().all(), "분할 하나가 빠진 변형이 있다"
    ab["ab_mean"] = ab[list(H.SPLITS)].mean(1)
    ab = ab.merge(info, on="variant")
    ens = ab[ab.seed == "e012"].rename(columns={"ab_mean": "metric", "A": "metric_A", "B": "metric_B"})
    single = ab[~ab.seed.str.startswith("e")].groupby(DIMS + ["rule"]).ab_mean.agg(
        single_mean="mean", single_sd="std", single_min="min", single_max="max", n_seeds="size").reset_index()
    out = ens[DIMS + ["rule", "seed", "metric", "metric_A", "metric_B"]].merge(single, on=DIMS + ["rule"], how="left")
    out["se"] = out.single_sd / np.sqrt(out.n_seeds)
    out["dist"] = out.apply(X.guidebook_distance, axis=1)
    return out


def pick(df: pd.DataFrame):
    """최고 지표에서 max(0.002, 그 변형의 SE) 안이면 동률 → 바꾼 차원 수 → W → 이름순."""
    top = df.sort_values("metric", ascending=False).iloc[0]
    band = max(H.TIE, float(top.se) if np.isfinite(top.se) else H.TIE)
    tied = df[df.metric >= top.metric - band].sort_values(["dist", "W", "cfg", "scoring"])
    return tied.iloc[0].to_dict(), tied, band


def spec(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if k in ("W", "h1", "h2", "epochs", "patience", "dist", "n_seeds"):
            out[k] = int(v)
        elif isinstance(v, (np.floating, float)):
            out[k] = None if not np.isfinite(v) else round(float(v), 6)
        else:
            out[k] = v
    return out


def ref_metrics(refs: pd.DataFrame) -> dict:
    p = refs[(refs.alpha == H.PRIMARY_ALPHA) & (refs["mode"] == "realtime")]
    return {m: dict(A=round(float(g[g.split == "A"].f1.iloc[0]), 6), B=round(float(g[g.split == "B"].f1.iloc[0]), 6),
                    mean=round(float(g.f1.mean()), 6)) for m, g in p.groupby("model")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["1", "2a", "final"], required=True)
    a = ap.parse_args()
    t0 = time.time()
    valid, info, refs = eval_valid()
    valid.to_csv(H.OUT / "02_valid.csv", index=False)
    agg = summarize(valid, info)
    agg.sort_values(["rule", "metric"], ascending=[True, False]).to_csv(H.OUT / "02_valid_summary.csv", index=False)
    base = (agg.epochs == 300) & (agg.patience == 30) & (agg.data == "early80")
    L = agg[agg.rule == "none"]
    out = dict(stage=a.stage, rule="PROTOCOL.md 5절", references_valid_realtime_alpha1=ref_metrics(refs),
               start_point=spec(L[(L.cfg == START[0]) & (L.scoring == START[1])].iloc[0].to_dict()))

    if a.stage == "1":
        s1 = L[base & L.cfg.isin(set(info.cfg))]
        w, tied, band = pick(s1)
        out.update(track_L=spec(w), band=band, track_L_tied=[spec(r) for r in tied.to_dict("records")],
                   track_L_top10=[spec(r) for r in s1.nlargest(10, "metric").to_dict("records")])
        combos = s1.sort_values("metric", ascending=False).drop_duplicates(["W", "warm", "h1", "h2"]).head(3)
        out["top3_combos"] = [spec(r) for r in combos.to_dict("records")]
        r1 = agg[(agg.rule == "R1") & base]
        out["exploratory_LR1_top5"] = [spec(r) for r in r1.nlargest(5, "metric").to_dict("records")]
        path = H.OUT / "02_stage1_selection.json"
    elif a.stage == "2a":
        s1 = read_locked("02_stage1_selection.json")
        pairs = {(c["W"], c["warm"]) for c in s1["top3_combos"]}
        c2 = L[base & L.apply(lambda r: (r.W, r.warm) in pairs, axis=1)]
        w, tied, band = pick(c2)
        out.update(chosen=spec(w), band=band, tied=[spec(r) for r in tied.to_dict("records")],
                   candidates_top10=[spec(r) for r in c2.nlargest(10, "metric").to_dict("records")])
        path = H.OUT / "02_stage2a_selection.json"
    else:
        read_locked("02_stage2a_selection.json")
        w, tied, band = pick(L)
        out.update(track_L=spec(w), band=band, track_L_tied=[spec(r) for r in tied.to_dict("records")],
                   track_L_top10=[spec(r) for r in L.nlargest(10, "metric").to_dict("records")])
        r1 = agg[agg.rule == "R1"]
        prim = r1[(r1.cfg == w["cfg"]) & (r1.scoring == w["scoring"])].iloc[0].to_dict()
        out["track_LR1"] = spec(prim)     # 주 결과: 트랙 L 승자 + R1 (v2 → v2+R1과 같은 짝)
        ew, etied, eband = pick(r1)
        out.update(exploratory_LR1=spec(ew), exploratory_LR1_band=eband,
                   exploratory_LR1_top10=[spec(r) for r in r1.nlargest(10, "metric").to_dict("records")])
        path = H.OUT / "02_selection.json"
    H.dump(out, path)
    lock(path)
    show = {k: v for k, v in out.items() if not k.endswith(("_top10", "_tied", "tied", "_top5", "candidates_top10"))}
    print(json.dumps(show, ensure_ascii=False, indent=1, default=str))
    cols = ["cfg", "scoring", "metric", "metric_A", "metric_B", "single_mean", "single_sd", "dist"]
    print(L.nlargest(15, "metric")[cols].round(4).to_string(index=False))
    print(f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
