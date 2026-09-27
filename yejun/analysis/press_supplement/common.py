"""보완 실험 공용: 동결 v2 불러오기, 정상 분할 행 번호, 고장 주입, 기록구간 단위 탐지 집계."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[1]
sys.path.insert(0, str(YEJUN / "press_guard"))
from model import GuardModel, D, BASE, ALPHAS  # noqa: E402
from press.calibrate import conformal_p, segment_max  # noqa: E402
from train import baseline  # noqa: E402  v1 기준선(크기+사인8) 산식

PROTOCOL = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
E1 = PROTOCOL["E1_fault_injection"]
ARTIFACTS = YEJUN / "press_guard" / "artifacts"
POST_WINDOW = 20   # t0 이후 20행(2초) 안의 경보를 탐지로 본다


def load_data():
    normal, abnormal, report = D.load(BASE)
    return normal, abnormal, {k: v["sha256"] for k, v in report["files"].items()}


def split_rows(normal, sid):
    """분할의 학습/보정/평가 행 번호(원본 정상 CSV 기준)."""
    _, train_end, cal_end = D.SPLITS[sid]
    seg = D.segments(normal)
    return dict(train=np.flatnonzero(seg < train_end), cal=np.flatnonzero((seg >= train_end) & (seg < cal_end)),
                test=np.flatnonzero(seg >= cal_end))


def frozen(sid):
    return GuardModel.load(ARTIFACTS / f"guard_{sid}.json")


def standard_noise(n_rows, rep):
    """반복별 표준정규 난수(행×3). 모든 세기·분할이 같은 난수를 공유한다."""
    return np.random.default_rng(20260926 + rep).standard_normal((n_rows, 3))


def inject(frame, rows, model, family, level, mask, ramp, z):
    """frame(원본 행 번호 rows)에 주입. mask=주입 행, ramp=행별 세기 배율(0~1), z=원본 전체 길이의 표준정규."""
    out = frame.copy()
    vib, cur = D.SENSORS[:2], D.SENSORS[2]
    m = np.asarray(mask, bool)
    r = np.asarray(ramp, float)[m]
    zz = z[rows][m]
    if family == "none":
        return out
    if family == "vib_noise":
        for k, c in enumerate(vib):
            out.loc[m, c] = out.loc[m, c].to_numpy() + r * level * model.scale[k] * zz[:, k]
    elif family == "cur_noise":
        out.loc[m, cur] = out.loc[m, cur].to_numpy() + r * level * model.scale[2] * zz[:, 2]
    elif family == "cur_offset":
        out.loc[m, cur] = out.loc[m, cur].to_numpy() + r * level * np.sqrt(2) * model.scale[2]
    elif family == "cur_gain":
        x = out.loc[m, cur].to_numpy()
        k = 1 + r * (level - 1)
        out.loc[m, cur] = model.mean[2] + k * (x - model.mean[2])
    else:
        raise ValueError(family)
    return out


def v2_pvalues(model, frame):
    pred = model.predict(frame, .01)
    return pred.p_value.to_numpy(), pred


def v1_pvalues(model, cal_frame, frame):
    ref = segment_max(baseline(model, cal_frame), D.segments(cal_frame))
    return conformal_p(ref, baseline(model, frame))


def record_detection(p, seg, pos, eligible_records, t0, alpha):
    """주입 기록마다 t0 이후 첫 경보 위치·t0 이전 경보 유무·t0 이후 행 재현율."""
    alarm = np.isfinite(p) & (p <= alpha)
    rows = []
    for rec in eligible_records:
        m = seg == rec
        a, ps = alarm[m], pos[m]
        post = ps >= t0
        hits = ps[post & a]
        first = int(hits.min()) if len(hits) else None
        rows.append(dict(record=int(rec), pre_alarm=bool((a & ~post).any()), first_post=first,
                         delay_s=None if first is None else round((first - t0) * D.DT, 6),
                         detected_2s=first is not None and first - t0 < POST_WINDOW,
                         post_rows=int(post.sum()), post_alarm_rows=int((post & a).sum())))
    return pd.DataFrame(rows)
