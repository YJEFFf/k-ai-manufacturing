"""E3 재보정 절차 곡선 — 정상 자료를 몇 분 모으면 v2 문턱·성능이 안정되는가, 전류 배율로 모의한 '새 날'에서 재보정이 회복시키는가.

풀과 평가가 같은 날 77분이다. 다른 날 자료로 재보정 효과를 직접 잰 것이 아니다.
"""
from concurrent.futures import ProcessPoolExecutor
import time

from common import *  # noqa: F403
from model import layout  # noqa: E402

SPEC = PROTOCOL["E3_recalibration_curve"]
INJECT = [("vib_noise", 2), ("cur_noise", .2), ("cur_offset", .4)]
T0 = 10


def eval_sets(normal, abnormal, gain=1.0):
    """평가 정상(480~599)·이상·주입 자료. 주입 정의는 동결 guard_A의 척도로 고정(모델과 무관한 절대 크기)."""
    ref = frozen("A")
    def shift(frame):
        f = D.inputs_only(frame)
        if gain != 1.0:
            f[D.SENSORS[2]] = ref.mean[2] + gain * (f[D.SENSORS[2]] - ref.mean[2])
        return f
    rows = split_rows(normal, "A")["test"]
    test = shift(normal.iloc[rows])
    seg = D.segments(test)
    pos, length = D.segment_positions(seg)
    eligible = np.unique(seg[length >= 30])
    mask = np.isin(seg, eligible) & (pos >= T0)
    injected = []
    for rep in range(2):
        z = standard_noise(len(normal), rep)
        for fam, lv in INJECT:
            injected.append((fam, lv, rep, inject(test, rows, ref, fam, lv, mask, np.ones(len(pos)), z)))
    return dict(test=test, abnormal=shift(abnormal), injected=injected, seg=seg, pos=pos, eligible=eligible, shift=shift)


def evaluate(model, sets, alpha):
    pn = model.predict(sets["test"], .01)
    pa = model.predict(sets["abnormal"], .01)
    an = np.isfinite(pn.p_value) & (pn.p_value <= alpha)
    aa = np.isfinite(pa.p_value) & (pa.p_value <= alpha)
    tp, fp = int(aa.sum()), int(an.sum())
    fn = len(aa) - tp
    out = dict(normal_notified=int(pd.Series(an.to_numpy()).groupby(pn.record_id.to_numpy()).max().sum()), normal_segments=int(pn.record_id.nunique()),
               abnormal_detected=int(pd.Series(aa.to_numpy()).groupby(pa.record_id.to_numpy()).max().sum()), abnormal_segments=int(pa.record_id.nunique()),
               abnormal_missed_rows=fn, f1=2 * tp / (2 * tp + fp + fn), threshold_cal_max=float(np.max(model.cal)))
    rates = {}
    for fam, lv, rep, frame in sets["injected"]:
        p = model.predict(frame, .01).p_value.to_numpy()
        det = record_detection(p, sets["seg"], sets["pos"], sets["eligible"], T0, alpha)
        rates.setdefault(fam, []).append(det.detected_2s.mean())
    for fam, r in rates.items():
        out[f"inject_{fam}"] = float(np.mean(r))
    out["inject_min"] = min(out[f"inject_{f}"] for f, _ in INJECT)
    return out


def usage(frame):
    t = pd.to_datetime(frame[D.TIME])
    return dict(normal_rows=len(frame), normal_minutes=len(frame) * D.DT / 60, elapsed_minutes=(t.iloc[-1] - t.iloc[0]).total_seconds() / 60)


_STATE = {}


def _init():
    normal, abnormal, _ = load_data()
    _STATE.update(normal=normal, seg=D.segments(normal), sets=eval_sets(normal, abnormal))


def run_config(cfg):
    if not _STATE:
        _init()
    alpha, n_train, n_cal, s = cfg
    normal, seg = _STATE["normal"], _STATE["seg"]
    train = normal[(seg >= s) & (seg < s + n_train)]
    cal = normal[(seg >= s + n_train) & (seg < s + n_train + n_cal)]
    model = GuardModel.fit(train, cal, split=f"recal_{n_train}_{n_cal}_{s}")
    used = usage(pd.concat([train, cal]))
    return dict(alpha=alpha, n_train=n_train, n_cal=n_cal, start=s, **used, **evaluate(model, _STATE["sets"], alpha))


def grid():
    cfgs = []
    for alpha, key in ((.01, "grid_alpha_1pct"), (.05, "grid_alpha_5pct")):
        g = SPEC[key]
        for nt in g["n_train"]:
            for nc in g["n_cal"]:
                for s in range(0, 480, 60):
                    if s + nt + nc <= 480:
                        cfgs.append((alpha, nt, nc, s))
    return cfgs


def stability(curve):
    rows = []
    for (alpha, nt, nc), g in curve.groupby(["alpha", "n_train", "n_cal"]):
        rows.append(dict(alpha=alpha, n_train=nt, n_cal=nc, starts=len(g),
                         normal_minutes=g.normal_minutes.median(), elapsed_minutes_median=g.elapsed_minutes.median(),
                         normal_notified_min=g.normal_notified.min(), normal_notified_median=g.normal_notified.median(), normal_notified_max=g.normal_notified.max(),
                         abnormal_detected_min=g.abnormal_detected.min(), missed_rows_median=g.abnormal_missed_rows.median(), missed_rows_max=g.abnormal_missed_rows.max(),
                         f1_min=g.f1.min(), f1_median=g.f1.median(), inject_min_worst=g.inject_min.min(),
                         threshold_cv=g.threshold_cal_max.std() / g.threshold_cal_max.mean(),
                         stable=bool((g.normal_notified <= 3).all() and (g.abnormal_detected == 21).all() and (g.inject_min >= .9).all())))
    return pd.DataFrame(rows).sort_values(["alpha", "normal_minutes"])


def domain_shift(normal, abnormal):
    rows = []
    seg = D.segments(normal)
    for gain in (1.0,) + (.85, 1.15, 1.3):
        sets = eval_sets(normal, abnormal, gain)
        shifted = sets["shift"](normal)
        base = frozen("A")
        rows.append(dict(gain=gain, condition="frozen", **evaluate(base, sets, .01)))
        # 학습 상태 유지, 보정만 이동 자료 360~479로 다시
        recal = GuardModel(dict(base.state))
        cf = D.quantize(D.inputs_only(shifted[(seg >= 360) & (seg < 480)]), "matched")
        sg = layout(cf)[1]
        recal.cal = segment_max(recal.components(cf, sg)["score"], sg)
        rows.append(dict(gain=gain, condition="recal_only", **evaluate(recal, sets, .01)))
        for nt in (60, 360):
            m = GuardModel.fit(shifted[(seg >= 360 - nt) & (seg < 360)], shifted[(seg >= 360) & (seg < 480)], split=f"shift_refit_{nt}")
            rows.append(dict(gain=gain, condition=f"refit_train{nt}", **evaluate(m, sets, .01)))
        print("shift", gain, flush=True)
    return pd.DataFrame(rows)


def main():
    start = time.monotonic()
    normal, abnormal, hashes = load_data()
    cfgs = grid()
    with ProcessPoolExecutor(4, initializer=_init) as ex:
        curve = pd.DataFrame(list(ex.map(run_config, cfgs, chunksize=2)))
    curve.to_csv(HERE / "e3_curve.csv", index=False)
    stab = stability(curve)
    stab.to_csv(HERE / "e3_stability.csv", index=False)
    shift = domain_shift(normal, abnormal)
    shift.to_csv(HERE / "e3_domain_shift.csv", index=False)
    D.dump_json(dict(experiment="E3", input_hashes=hashes, configs=len(cfgs), elapsed_s=time.monotonic() - start,
                     code_sha256={n: D.sha256_file(HERE / n) for n in ("common.py", "recalibration.py", "protocol.json")},
                     environment=D.environment()), HERE / "e3_manifest.json")
    print(stab.to_string(index=False))
    print(shift.to_string(index=False))


if __name__ == "__main__":
    main()
