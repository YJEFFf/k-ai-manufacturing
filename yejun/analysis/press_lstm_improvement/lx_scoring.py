"""LSTM 변형의 채점 방식(PROTOCOL.md 4절)과, 변형 점수를 준용 행 표에 보정 열로 붙이는 부분.

채점 방식 이름 = '<채널 처리>-<시간 요약>'.
- 시간 요약: last(창 마지막 시점, 가이드북) · mean(창 전체 평균) · max(창 안 시점별 최댓값)
- 채널 처리
  · raw : 세 채널 평균(가이드북)
  · cn  : 채널마다 참조 평균으로 나눈 뒤 최댓값
  · cq  : 채널마다 참조 99% 분위로 나눈 뒤 최댓값
  · ct  : 채널마다 참조 분포의 꼬리 변환(예준 ExpTail, −log10 꼬리 확률 척도) 뒤 최댓값 — v2가 성분을 합치는 방식과 같은 척도
  · md  : 채널별 오차(제곱근) 벡터의 마할라노비스 거리(EncDec-AD 방식의 근사, 부호 없는 오차)
  · cpn : (edge·var) 기록 안 위치 구간별·채널별 참조 평균으로 나눈 뒤 최댓값
  · cpt : (edge·var) cpn처럼 위치 구간별 평균으로 나눈 값에 채널별 꼬리 변환 뒤 최댓값
참조는 조기 종료용 학습 구간 창의 오차다(가중치 적합에 쓰지 않은 정상 학습 자료, valid·test를 보지 않음).
앙상블: 시드 묶음(e012 = 시드 0·1·2, e345 = 새 시드 3·4·5)의 행 점수를 보정 전에 평균한다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import lx_harness as H  # noqa: E402

AGG_COLS = {"last": [1, 2, 3], "mean": [4, 5, 6], "max": [7, 8, 9]}
AGGS = ("last", "mean", "max")
CHANNELS = {"none": ["raw", "cn", "cq", "ct", "md"], "edge": ["raw", "cn", "cq", "ct", "md", "cpn", "cpt"]}
CHANNELS["var"] = CHANNELS["edge"]
ENSEMBLES = {"e012": (0, 1, 2), "e345": (3, 4, 5)}
FRAMES = H.FRAMES


def scorings(warm: str) -> list[str]:
    return [f"{k}-{a}" for k in CHANNELS[warm] for a in AGGS]


def load_run(path: Path) -> dict:
    z = np.load(path, allow_pickle=False)
    run = {k: z[k] for k in z.files if k != "meta"}
    run.update(json.loads(str(z["meta"])))
    return run


def _bucket_means(run, cols):
    """cpn·cpt 참조: 위치 구간 b = min(위치, W−1)마다 채널별 참조 평균."""
    W = int(run["W"])
    bh = np.minimum(run["pos_hold"], W - 1)
    ref = np.vstack([np.nanmean(run["F_hold"][bh == b][:, cols], 0) for b in range(W)])
    assert np.isfinite(ref).all() and (ref > 0).all(), "위치 구간 참조가 비었다"
    return ref, bh


def apply_scoring(F: np.ndarray, pos: np.ndarray, run: dict, scoring: str) -> np.ndarray:
    """오차 요약 F(행 × FEATS)를 채점 방식 하나로 행 점수로 바꾼다. 창이 없는 행은 NaN으로 남는다."""
    kind, agg = scoring.split("-")
    Fh = run["F_hold"]
    if kind == "raw":
        return np.asarray(F[:, 0] if agg == "last" else (F[:, 4:7].mean(1) if agg == "mean" else F[:, 10]), float)
    cols = AGG_COLS[agg]
    if kind == "cn":
        return (F[:, cols] / np.nanmean(Fh[:, cols], 0)).max(1)
    if kind == "cq":
        return (F[:, cols] / np.nanquantile(Fh[:, cols], 0.99, axis=0)).max(1)
    if kind == "ct":
        ExpTail = H.setup()["ExpTail"]
        return np.column_stack([ExpTail(Fh[:, c])(F[:, c]) for c in cols]).max(1)
    if kind == "md":
        R, Rh = np.sqrt(F[:, cols]), np.sqrt(Fh[:, cols])
        mu, cov = Rh.mean(0), np.cov(Rh.T) + 1e-12 * np.eye(len(cols))
        D = R - mu
        return np.einsum("ij,jk,ik->i", D, np.linalg.inv(cov), D)
    if kind in ("cpn", "cpt"):
        W = int(run["W"])
        ref, bh = _bucket_means(run, cols)
        N = F[:, cols] / ref[np.minimum(pos, W - 1)]
        if kind == "cpn":
            return N.max(1)
        ExpTail = H.setup()["ExpTail"]
        Nh = Fh[:, cols] / ref[bh]
        return np.column_stack([ExpTail(Nh[:, j])(N[:, j]) for j in range(len(cols))]).max(1)
    raise ValueError(scoring)


def score_rows(run: dict, scoring: str) -> dict:
    """프레임별 행 점수."""
    return {k: apply_scoring(run[f"F_{k}"], run[f"pos_{k}"], run, scoring) for k in FRAMES}


def run_paths(sid: str, cfgs=None) -> list[tuple[str, int, Path]]:
    out = []
    for p in sorted((H.CACHE / "runs").glob(f"{sid}_*.npz")):
        if p.name.endswith(".tmp.npz"):
            continue
        cfg, seed = p.stem[len(sid) + 1:].rsplit("_s", 1)
        if cfgs is None or cfg in cfgs:
            out.append((cfg, int(seed), p))
    return out


def vname(cfg: str, scoring: str, seed) -> str:
    return f"lx:{cfg}:{scoring}:{seed if isinstance(seed, str) else f's{seed}'}"


def parse_cfg(cfg: str) -> dict:
    """'W20-var-64x32-e300p30[-late80]' → 차원 값."""
    parts = cfg.split("-")
    h1, h2 = parts[2].split("x")
    e, p = parts[3][1:].split("p")
    return dict(W=int(parts[0][1:]), warm=parts[1], h1=int(h1), h2=int(h2), epochs=int(e), patience=int(p),
                data=parts[4] if len(parts) > 4 else "early80")


def build_variant_table(sid: str, cfgs=None, singles: bool = True, ens_sets=("e012",)):
    """준용 행 표(base) + LSTM 변형의 보정 열(단일 시드, 시드 묶음 앙상블). 반환 (table, meta, 변형 목록)."""
    base, meta = H.base_table(sid)
    inp = np.load(H.CACHE / f"inputs_{sid}.npz")
    seg_vn = inp["seg_valid_normal"]
    by_cfg: dict = {}
    for cfg, seed, path in run_paths(sid, cfgs):
        by_cfg.setdefault(cfg, {})[seed] = path
    cols, info = {}, []
    for cfg, seeds in sorted(by_cfg.items()):
        d = parse_cfg(cfg)
        runs = {k: load_run(p) for k, p in seeds.items()}
        for sc in scorings(d["warm"]):
            chan, agg = sc.split("-")
            per_seed = {k: score_rows(r, sc) for k, r in runs.items()}
            if singles:
                for k, s in per_seed.items():
                    name = vname(cfg, sc, k)
                    cols.update(H.calibrated_columns(name, s, seg_vn, len(base)))
                    info.append(dict(variant=name, cfg=cfg, scoring=sc, chan=chan, agg=agg, seed=str(k), **d))
            for ename in ens_sets:
                members = ENSEMBLES[ename]
                if all(k in per_seed for k in members):
                    s = {f: np.mean([per_seed[k][f] for k in members], axis=0) for f in FRAMES}
                    name = vname(cfg, sc, ename)
                    cols.update(H.calibrated_columns(name, s, seg_vn, len(base)))
                    info.append(dict(variant=name, cfg=cfg, scoring=sc, chan=chan, agg=agg, seed=ename, **d))
    table = pd.concat([base, pd.DataFrame(cols, index=base.index)], axis=1)
    return table, meta, pd.DataFrame(info)


def guidebook_distance(row) -> int:
    """가이드북 lstm20(W20·none·raw-last·64-32·300/30·early80·단일 모델)에서 바꾼 차원 수. 동률일 때 가까운 쪽을 고른다."""
    return int(row["W"] != 20) + int(row["warm"] != "none") + int(row["agg"] != "last") + int(row["chan"] != "raw") + \
        int((row["h1"], row["h2"]) != (64, 32)) + int((row["epochs"], row["patience"]) != (300, 30)) + \
        int(row["data"] != "early80") + int(str(row["seed"]).startswith("e"))
