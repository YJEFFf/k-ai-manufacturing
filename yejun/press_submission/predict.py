"""저장된 artifact로 새 입력에 추론한다 (PLAN.md §7). 재학습·재선택은 하지 않는다.

    python predict.py --model artifacts/main_A.json --input new.csv --out predictions.csv

입력 CSV는 TimeStamp, AI0_Vibration, AI1_Vibration, AI2_Current 열이 있어야 한다. 그 밖의 열은 무시한다.
artifact의 전처리(round 간격)·스케일러·창·꼬리 변환·보정 문턱을 그대로 적용한다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from press import data as D  # noqa: E402
from press.artifact import Artifact  # noqa: E402
from press.calibrate import conformal_p  # noqa: E402
from press.scores import MainModel  # noqa: E402

MAIN_ALPHA = 0.01


def apply_preprocess(frame: pd.DataFrame, spec) -> pd.DataFrame:
    out = frame.copy()
    if spec is None:
        return out
    for c in D.SENSORS[:2]:
        out[c] = np.round(out[c].astype(float) / spec["vib"]) * spec["vib"]
    out[D.SENSORS[2]] = np.round(out[D.SENSORS[2]].astype(float) / spec["cur"]) * spec["cur"]
    return out


def predict_frame(art: Artifact, frame: pd.DataFrame) -> pd.DataFrame:
    status = D.validate_rows(frame)
    seg = D.segments(frame, status)
    pos, length = D.segment_positions(seg)
    base = pd.DataFrame(dict(row_id=np.arange(len(frame)), record_id=seg, timestamp=frame[D.TIME].astype(str), status=status,
                             position_in_record=pos, record_length=length))
    if not art.trained:
        for c in ("score_maxz3", "score_sine", "combined_score", "p_value", "anomaly_score", "budget"):
            base[c] = np.nan
        base["is_scored"], base["criterion"], base["alarm"], base["alarm_reason"] = 0, "", 0, "no_model_state"
        base["model_id"], base["protocol_version"] = art.model_id, art.protocol_version
        return base
    st = art.state
    x = frame.copy()
    bad = status != "ok"
    for c in D.SENSORS:   # 잘못된 행은 점수 계산에서 NaN으로 두고 상태로 남긴다 (삭제하지 않음)
        x[c] = pd.to_numeric(x[c], errors="coerce").where(~bad)
    x = apply_preprocess(x, st.get("preprocess_spec"))
    mm = MainModel(st)
    r = mm.score(x, seg)
    cal = np.asarray(st["calibration"]["segment_max"], float)
    p = conformal_p(cal, r["combined"])
    base["is_scored"] = np.isfinite(r["combined"]).astype(int)
    base["score_maxz3"], base["maxz_sensor"], base["score_sine"] = r["maxz3"], r["maxz_sensor"], r["sine"]
    base["g_maxz3"], base["g_sine"], base["combined_score"] = r["g_maxz3"], r["g_sine"], r["combined"]
    base["p_value"], base["anomaly_score"] = p, 1 - p
    thresholds = st["calibration"]["thresholds"]
    main = next(t for t in thresholds if t["criterion"] == "conformal" and t["alpha"] == MAIN_ALPHA)
    for t in thresholds:
        col = "alarm" if t is main else f"alarm_{t['criterion']}_{t['alpha']:g}"
        base[col] = (np.isfinite(r["combined"]) & (r["combined"] > t["threshold"])).astype(int)
    thr = main["threshold"]
    zf, sf = r["g_maxz3"] > thr, np.nan_to_num(r["g_sine"], nan=-np.inf) > thr
    reason = np.where(zf & sf, "both", np.where(zf, "maxz", np.where(sf, "sine", "")))
    base["criterion"], base["budget"], base["threshold"] = "conformal", MAIN_ALPHA, thr
    base["alarm_reason"] = np.where(base.alarm.to_numpy() == 1, reason, "")
    base["model_id"], base["protocol_version"] = art.model_id, art.protocol_version
    return base


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    art = Artifact.load(args.model)
    frame = pd.read_csv(args.input)
    out = predict_frame(art, frame)
    if not art.trained:
        print(f"경고: {args.model} 에는 학습 상태가 없다. 점수·경보는 비워 둔다.", file=sys.stderr)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    n_alarm = int(out.groupby("record_id").alarm.max().sum()) if "alarm" in out else 0
    print(f"{len(out)}행 → {args.out} (기록구간 {out.record_id.nunique()}개, 잘못된 행 {(out.status != 'ok').sum()}개, 알림 구간 {n_alarm}개)")


if __name__ == "__main__":
    main()
