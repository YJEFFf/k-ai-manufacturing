"""보조 확인: 콘솔이 쓰는 v2 동결 모델 사본(yejun/press_guard/outputs/expected/guard_{A,B}.json, 다른 기기·numpy 1.26에서 학습)으로
두 단계 스트림을 돌려도 제출 예측 파일의 1·2단계·v2 열이 시험 행마다 같은지, 새로 학습한 모델과 원소 차이가 얼마인지 잰다.

흐름은 replay.py와 같다(정상: 검증 → 시험 한 흐름, 이상: 21기록 전체). r2_ref는 정상 학습 구간으로 정한다.
출력: outputs/frozen_copy_check.json
실행: PYTHONDONTWRITEBYTECODE=1 python yejun/analysis/press_stage_replay_2026-10-08/frozen_copy_check.py [--data <원본 폴더>]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import common as C

C.setup()

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import stages  # noqa: E402
from model import D, GuardModel  # noqa: E402

PRED = {"stage1": "locked_v2_R1_realtime", "stage2": "final_v2_R1_R2_realtime", "v2_alarm": "v2_realtime"}


def max_diff(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    return float(np.max(np.abs(np.sort(a) - np.sort(b)))) if a.shape == b.shape else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=C.DATA_DEFAULT)
    args = ap.parse_args()
    normal, abnormal = C.load_data(args.data)
    out = {}
    for sid in C.SPLITS:
        sp = D.split_normal(normal, D.segments(normal), sid)
        frozen = GuardModel.load(C.GUARD / "outputs" / "expected" / f"guard_{sid}.json")
        fresh = GuardModel.fit(sp["train"], sp["cal"], split=sid)
        diffs = {k: max_diff(frozen.state[k], fresh.state[k]) for k in ("mean", "scale", "ar2")}
        diffs["calibration"] = max_diff(frozen.cal, fresh.cal)
        diffs.update({f"tail_{k}_ref": max_diff(frozen.tails[k].ref, fresh.tails[k].ref) for k in frozen.tails})
        state = stages.StageState(frozen, stages.fit_r2_ref(sp["train"]))
        pred = C.official_predictions(sid)
        flows = {"normal": (pd.concat([sp["cal"], sp["test"]], ignore_index=True), len(sp["cal"])),
                 "abnormal": (abnormal, int((D.segments(abnormal) < C.ABN_VALID_RECORDS).sum()))}
        eq = {}
        for subset, (frame, n_valid) in flows.items():
            res = stages.replay(state, frame).iloc[n_valid:].reset_index(drop=True)
            p = pred[pred.subset.eq(subset)].reset_index(drop=True)
            eq[subset] = {k: dict(equal=int((res[k].to_numpy(bool) == C.as_bool(p[v])).sum()), rows=int(len(p))) for k, v in PRED.items()}
        out[sid] = dict(frozen_model_sha256=stages.model_sha256(frozen), fresh_model_sha256=stages.model_sha256(fresh),
                        max_abs_param_diff=diffs, test_rows_equal_prediction_file=eq,
                        all_equal=all(v["equal"] == v["rows"] for e in eq.values() for v in e.values()))
        print(sid, out[sid]["all_equal"], diffs, flush=True)
    C.dump(out, C.OUT / "frozen_copy_check.json")
    if not all(v["all_equal"] for v in out.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
