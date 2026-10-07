"""LSTM 오토인코더 변형 학습(PROTOCOL.md 4·5절). 결과는 cache/runs/*.npz(행별 오차 요약), 가중치는 cache/models/*.pt.

--stage 1      : 1단계 격자 — none W5·10·20, edge W5·10·20·30, var W5·10·20·30 (64-32) + 짧은 창 병목 맞춤
                 (W5 16-4, W10 32-8 × none·edge·var), 300/30, early80, 시드 0·1·2, 분할 A·B
--stage 2a     : 1단계 상위 3개 (W, 앞부분, 용량) 조합마다 용량 32-16·128-64
--stage 2b     : 2a 선택 조합에서 학습 예산 1000/100, 학습 자료 late80, 둘 다
--stage confirm: 잠긴 최종 설정을 새 시드 3·4·5로 다시 학습(선택 낙관 없이 비교에 쓸 값)
단계별 선택 파일은 sha256 잠금이 맞을 때만 읽는다. 학습 입력(cache/inputs_{A,B}.npz)은 준용 build_split과 같은 전처리.
실행: PYTHONDONTWRITEBYTECODE=1 python 01_train.py --stage 1 --workers 7
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import lx_harness as H  # noqa: E402
import lx_lstm as L  # noqa: E402

SEEDS = (0, 1, 2)
CONFIRM_SEEDS = (3, 4, 5)
BASE_CAP, BASE_BUDGET = (64, 32), (300, 30)
STAGE1 = ([(W, "none", BASE_CAP) for W in (5, 10, 20)] + [(W, "edge", BASE_CAP) for W in (5, 10, 20, 30)] +
          [(W, "var", BASE_CAP) for W in (5, 10, 20, 30)] +
          [(5, w, (16, 4)) for w in ("none", "edge", "var")] + [(10, w, (32, 8)) for w in ("none", "edge", "var")])
CAPS_2A = [(32, 16), (128, 64)]
BUDGET_2B = (1000, 100)


def cfg_name(W, warm, cap=BASE_CAP, budget=BASE_BUDGET, data="early80"):
    return f"W{W}-{warm}-{cap[0]}x{cap[1]}-e{budget[0]}p{budget[1]}" + ("" if data == "early80" else f"-{data}")


def read_locked(name: str) -> dict:
    path = H.OUT / name
    lock = path.with_suffix(".sha256")
    if not lock.exists() or H.sha256_file(path) != lock.read_text(encoding="utf-8").strip():
        raise SystemExit(f"{name}의 잠금이 맞지 않는다")
    return json.loads(path.read_text(encoding="utf-8"))


def prepare_inputs():
    """분할마다 표준화한 입력을 저장한다. 표준화는 v2 GuardModel의 평균·척도(예준 LSTM 공통 프로토콜과 같음)."""
    for sid in H.SPLITS:
        p = H.CACHE / f"inputs_{sid}.npz"
        if p.exists():
            continue
        d = H.split_inputs(sid)
        S = H.setup()["D"].SENSORS
        Z = lambda q: (q[S].to_numpy(float) - d["mean"]) / d["scale"]  # noqa: E731
        arr = dict(z_train=Z(d["train"][0]), seg_train=np.asarray(d["train"][1]), mean=d["mean"], scale=d["scale"])
        for k, (q, seg) in d["frames"].items():
            arr[f"z_{k}"], arr[f"seg_{k}"] = Z(q), np.asarray(seg)
        H.CACHE.mkdir(parents=True, exist_ok=True)
        np.savez(p, **arr)
        print(sid, "입력 저장", {k: v.shape for k, v in arr.items()}, flush=True)


def configs_for(stage: str) -> tuple[list[dict], tuple]:
    if stage == "1":
        return [dict(W=W, warm=w, cap=c, budget=BASE_BUDGET, data="early80") for W, w, c in STAGE1], SEEDS
    if stage == "2a":
        s1 = read_locked("02_stage1_selection.json")
        out = []
        for combo in s1["top3_combos"]:
            for c in CAPS_2A:
                if tuple(c) != (combo["h1"], combo["h2"]):
                    out.append(dict(W=combo["W"], warm=combo["warm"], cap=c, budget=BASE_BUDGET, data="early80"))
        return out, SEEDS
    if stage == "2b":
        s2 = read_locked("02_stage2a_selection.json")["chosen"]
        cap = (s2["h1"], s2["h2"])
        return [dict(W=s2["W"], warm=s2["warm"], cap=cap, budget=b, data=d)
                for b, d in ((BUDGET_2B, "early80"), (BASE_BUDGET, "late80"), (BUDGET_2B, "late80"))], SEEDS
    if stage == "confirm":
        s = read_locked("02_selection.json")["track_L"]
        return [dict(W=s["W"], warm=s["warm"], cap=(s["h1"], s["h2"]), budget=(s["epochs"], s["patience"]), data=s["data"])], CONFIRM_SEEDS
    raise ValueError(stage)


def jobs_for(stage: str) -> list[dict]:
    cfgs, seeds = configs_for(stage)
    jobs = []
    for c in cfgs:
        name = cfg_name(c["W"], c["warm"], c["cap"], c["budget"], c["data"])
        for sid in H.SPLITS:
            for seed in seeds:
                jobs.append(dict(sid=sid, cfg=name, W=c["W"], warm=c["warm"], h1=c["cap"][0], h2=c["cap"][1],
                                 epochs=c["budget"][0], patience=c["budget"][1], data=c["data"], seed=seed,
                                 inputs=str(H.CACHE / f"inputs_{sid}.npz"),
                                 path=str(H.CACHE / "runs" / f"{sid}_{name}_s{seed}.npz"),
                                 model_path=str(H.CACHE / "models" / f"{sid}_{name}_s{seed}.pt")))
    return jobs


def collect_runs() -> pd.DataFrame:
    rows = []
    for p in sorted((H.CACHE / "runs").glob("*.npz")):
        if p.name.endswith(".tmp.npz"):
            continue
        m = json.loads(str(np.load(p)["meta"]))
        rows.append({k: v for k, v in m.items() if k not in ("inputs", "path", "model_path")})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["1", "2a", "2b", "confirm"], required=True)
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--exclude", default="", help="쉼표로 구분한 설정 이름. 다른 프로세스가 학습 중인 설정을 빼서 중복 학습을 막는다")
    ap.add_argument("--reverse", action="store_true")
    a = ap.parse_args()
    prepare_inputs()
    skip = {c for c in a.exclude.split(",") if c}
    jobs = [j for j in jobs_for(a.stage) if j["cfg"] not in skip]
    # 오래 걸리는 작업(긴 창·edge/var·큰 용량·큰 예산)을 먼저 보낸다. --reverse는 짧은 것부터(빈 코어를 채우는 보조 실행용)
    jobs.sort(key=lambda j: -(j["W"] * (2 if j["warm"] != "none" else 1) * j["h1"] * j["epochs"]), reverse=a.reverse)
    t0 = time.time()
    print(f"stage {a.stage}: 작업 {len(jobs)}개, 작업자 {a.workers}", flush=True)
    with ProcessPoolExecutor(max_workers=a.workers, mp_context=mp.get_context("spawn")) as ex:
        futs = {ex.submit(L.run, j): j for j in jobs}
        for i, f in enumerate(as_completed(futs), 1):
            j = futs[f]
            m = f.result()
            tag = "건너뜀" if m.get("skipped") else f"에폭 {m['epochs_run']}, {m['train_seconds']}s, best {m['best_val']:.5f}"
            print(f"[{i}/{len(jobs)}] {j['sid']} {j['cfg']} s{j['seed']}: {tag} (경과 {time.time() - t0:.0f}s)", flush=True)
    runs = collect_runs()
    runs.to_csv(H.OUT / "01_train_runs.csv", index=False)
    print(f"완료 {time.time() - t0:.0f}s, 저장된 실행 {len(runs)}개")


if __name__ == "__main__":
    main()
