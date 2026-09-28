"""A1-1b 파형 점수의 5.0 Hz(나이퀴스트) 격자점 수치 흔적.

팀 구현은 hat = A @ pinv(A)를 주파수 격자(0~5 Hz, 0.005 간격)마다 만든다. f=5.0 Hz에서 sin(2π·5·0.1k)=sin(πk)는 수학적으로 0이지만
부동소수로는 1e-16 크기의 잡음 열이다. pinv 기본 임계(1e-15·최대 특이값)에 걸리는지에 따라 이 잡음 열이 기저에 들어간다.
여기서는 팀 수식을 그대로 옮긴 계산(팀 모듈 import 없음)과 계수 부족을 버린 계산을 비교한다.
"""
import json

import numpy as np
import pandas as pd

import redA1_common as C

normal, abnormal = C.load_raw()
seg_n, seg_a = C.segment_ids(normal[C.TIME]), C.segment_ids(abnormal[C.TIME])
Xn, Xa = C.quantize(normal[C.SENS].to_numpy(float)), C.quantize(abnormal[C.SENS].to_numpy(float))
out = {}


def hat_team(win, f):
    t = np.arange(win) * C.DT
    A = np.column_stack([np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t), np.ones(win)])
    s = np.linalg.svd(A, compute_uv=False)
    return A @ np.linalg.pinv(A), A, s


for win in (6, 8):
    H, A, s = hat_team(win, C.FREQS[-1])
    out[f"win{win}"] = dict(f_last=float(C.FREQS[-1]), sin_column=A[:, 0].tolist(), singular_values=s.tolist(),
                           sv_ratio=float(s.min() / s.max()), pinv_default_rcond=1e-15,
                           hat_trace=float(np.trace(H)), hat_rank_expected_exact_math=2)
    print(f"창 {win}: f={C.FREQS[-1]!r} sin 열={A[:, 0]}")
    print(f"   특이값={s}, 최소/최대={s.min() / s.max():.3e}, hat 대각합={np.trace(H):.6f}(정확한 수학에서는 2)")


def score_both(cur, seg, win):
    """(팀 수식 1−R², 계수 부족 제거 1−R², 팀 최적 주파수, 내 최적 주파수)"""
    idx = C.windows_index(seg, win)
    W = np.stack([cur[i - win + 1:i + 1] for i in idx])
    sst = ((W - W.mean(axis=1, keepdims=True)) ** 2).sum(axis=1)
    t = np.arange(win) * C.DT
    best_t = np.full(len(idx), np.inf); arg_t = np.zeros(len(idx), int)
    best_m = np.full(len(idx), np.inf); arg_m = np.zeros(len(idx), int)
    for k, f in enumerate(C.FREQS):
        A = np.column_stack([np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t), np.ones(win)])
        H = A @ np.linalg.pinv(A)
        r = W - np.einsum("ij,kj->ik", W, H, optimize=False)
        e = (r * r).sum(axis=1)
        b = e < best_t; best_t[b] = e[b]; arg_t[b] = k
        u, s, _ = np.linalg.svd(A, full_matrices=False)
        Q = u[:, s > 1e-10 * s.max()]
        r = W - (W @ Q) @ Q.T
        e = (r * r).sum(axis=1)
        b = e < best_m; best_m[b] = e[b]; arg_m[b] = k
    full = lambda v: (lambda o: (o.__setitem__(idx, v), o)[1])(np.full(len(cur), np.nan))
    ok = sst > 0
    return (full(np.where(ok, best_t / np.where(ok, sst, 1), np.nan)), full(np.where(ok, best_m / np.where(ok, sst, 1), np.nan)),
            full(C.FREQS[arg_t]), full(C.FREQS[arg_m]))


rows = []
for name, X, seg in (("normal", Xn, seg_n), ("abnormal", Xa, seg_a)):
    for win in (6, 8):
        st, sm, ft, fm = score_both(X[:, 2], seg, win)
        ok = np.isfinite(st)
        at5 = ok & (ft == C.FREQS[-1])
        differ = ok & (np.abs(st - sm) > 1e-9)
        rows.append(dict(data=name, win=win, scored_rows=int(ok.sum()), team_best_at_5Hz=int(at5.sum()), differ_rows=int(differ.sum()),
                         share_differ=float(differ.sum() / ok.sum()), median_team_when_differ=float(np.median(st[differ])) if differ.any() else np.nan,
                         median_clean_when_differ=float(np.median(sm[differ])) if differ.any() else np.nan,
                         max_abs_diff=float(np.nanmax(np.abs(st - sm)))))
table = pd.DataFrame(rows)
pd.set_option("display.width", 250, "display.max_columns", 50)
print(table.to_string(index=False))
table.to_csv(C.OUT / "redA1_01b_nyquist_artifact.csv", index=False)

# 경보가 바뀌는가: 계수 부족을 버린 구현(redA1_common.Detector)은 A·B × α 1·3·5%에서 팀 경보와 모든 행이 같았다(redA1_01).
# 시간순 5창과 임계 근처 여유를 추가로 본다: 팀 수식 점수로 만든 검출기와 깨끗한 점수 검출기의 경보 차이.
import types


def detector_with_team_sine():
    det = C.Detector()
    return det


def run(det_sine, tr, ca, te, alpha):
    """det_sine(cur, seg, win) → 1−R². 나머지는 공용 구현."""
    orig = C.sine_1mr2
    C.sine_1mr2 = det_sine
    try:
        d = C.Detector().fit(Xn[tr], seg_n[tr]).calibrate(Xn[ca], seg_n[ca])
        pn, pa = d.predict(Xn[te], seg_n[te], alpha), d.predict(Xa, seg_a, alpha)
    finally:
        C.sine_1mr2 = orig
    return pn, pa


team_sine = lambda cur, seg, win: score_both(cur, seg, win)[0]
clean_sine = lambda cur, seg, win: score_both(cur, seg, win)[1]
folds = {"A": (360, 480, 600), "B": (300, 420, 600)}
for end in (180, 240, 300, 360, 420):
    folds[f"roll_{end + 120}_{end + 179}"] = (end, end + 120, end + 180)
flip = []
for name, (a, b, c) in folds.items():
    tr, ca, te = seg_n < a, (seg_n >= a) & (seg_n < b), (seg_n >= b) & (seg_n < c)
    for alpha in C.ALPHAS:
        tn, ta = run(team_sine, tr, ca, te, alpha)
        cn, ca_ = run(clean_sine, tr, ca, te, alpha)
        flip.append(dict(fold=name, alpha=alpha, team_fp=int(tn["alarm"].sum()), clean_fp=int(cn["alarm"].sum()),
                         team_fn=int((~ta["alarm"]).sum()), clean_fn=int((~ca_["alarm"]).sum()),
                         normal_rows_flip=int((tn["alarm"] != cn["alarm"]).sum()), abnormal_rows_flip=int((ta["alarm"] != ca_["alarm"]).sum())))
flip = pd.DataFrame(flip)
print(flip.to_string(index=False))
flip.to_csv(C.OUT / "redA1_01b_nyquist_flip.csv", index=False)
out["summary"] = table.to_dict("records")
out["alarm_flip_total"] = dict(normal=int(flip.normal_rows_flip.sum()), abnormal=int(flip.abnormal_rows_flip.sum()))
(C.OUT / "redA1_01b_nyquist_artifact.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(out["alarm_flip_total"])
