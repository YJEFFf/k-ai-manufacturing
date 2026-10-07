"""7단계(사후, 예준 지적 2026-10-07): LSTM에도 R2(교차 확인)에 해당하는 규칙을 붙여 최종 모델 v2+R1+R2와 같은 규칙 수로 비교한다.

R2(보고서 2.3절, evalcore.own_alarm): 크기 성분만 문턱을 넘고(다른 성분은 안 넘음) 그 시점 전류 파형이 정상(기록 첫 행부터 그 행까지의
전류 사인 적합 R² ≥ 학습 정상 0.5% 분위, 8행 미만이면 정상 아님)이면 경보를 보류한다. 성분 p값은 결합 점수의 valid 보정 분포와 비교한다.
LSTM에는 성분이 없으므로 결과를 보기 전에 두 가지로 옮겨 정하고 둘 다 보고한다. 상수(R² 기준·8행)는 R2와 같고 LSTM 결과에 맞춰 고치지 않는다.
- R2-L1(보수적): 성분 = 채널. 'magnitude' = 진동 두 채널 꼬리 점수의 최댓값, 'current' = 전류 채널 꼬리 점수.
  진동 채널만 문턱을 넘고 전류 채널은 안 넘었는데 전류 파형이 정상이면 보류(R2 정의를 그대로 옮긴 것).
- R2-L2(적극적): 전류 파형이 정상이면 LSTM 경보를 모두 보류.
대상: 잠근 LSTM(W10-var-128x64-e1000p100 · ct-mean)의 새 시드 앙상블 e345. 앙상블 성분은 시드별 성분 점수의 평균.
규칙 순서는 v2+R1+R2와 같다(R2 다음 R1).
출력: outputs/07_eval.csv, 07_states.csv, 07_v1.csv, 07_v1_pod.csv, 07_v2_loss.csv, 07_v5.csv, 07_summary.md, 07_r2_analog.json
실행: PYTHONDONTWRITEBYTECODE=1 python 07_r2_analog.py --workers 7
"""
from __future__ import annotations

import argparse
import importlib.util
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
import lx_scoring as X  # noqa: E402

SEEDS = (3, 4, 5)
MEAN_COLS = X.AGG_COLS["mean"]          # ct-mean: 채널별 창 평균 오차
TRAIN_VALID_END = {"A": (360, 480), "B": (300, 420)}
STATES = ["quiet", "busy_low", "busy_mid", "busy_high", "busy_short"]
LX = ["L", "L+R1", "L+R2a", "L+R1+R2a", "L+R2b", "L+R1+R2b"]


def locked():
    sel = json.loads((H.OUT / "02_selection.json").read_text(encoding="utf-8"))
    assert H.sha256_file(H.OUT / "02_selection.json") == (H.OUT / "02_selection.sha256").read_text(encoding="utf-8").strip()
    s = sel["track_L"]
    assert s["scoring"] == "ct-mean", "R2-L은 ct-mean(채널별 꼬리 점수의 최댓값) 기준으로 정의했다"
    return s["cfg"]


def channel_g(F, run):
    """ct-mean의 채널별 꼬리 점수 g0·g1(진동)·g2(전류). 최댓값이 ct-mean 점수다."""
    ExpTail = H.setup()["ExpTail"]
    return [ExpTail(run["F_hold"][:, c])(F[:, c]) for c in MEAN_COLS]


def ensemble_parts(runs, Fs):
    """시드별 (결합, 진동, 전류) 점수의 평균. 결합 = 시드별 max(g) 평균(잠근 앙상블과 같은 정의)."""
    comb, vib, cur = [], [], []
    for F, run in zip(Fs, runs):
        g = channel_g(F, run)
        comb.append(np.max(np.column_stack(g), 1))
        vib.append(np.fmax(g[0], g[1]))
        cur.append(g[2])
    return np.mean(comb, 0), np.mean(vib, 0), np.mean(cur, 0)


# ---------------------------------------------------------------- valid·test 채점과 운전 상태별 오경보
def build_table(sid, cfg):
    _, _, s01 = H.tvt()
    M = H.setup()
    base, meta = H.base_table(sid)
    inp = np.load(H.CACHE / f"inputs_{sid}.npz")
    seg_vn = inp["seg_valid_normal"]
    runs = [X.load_run(H.CACHE / "runs" / f"{sid}_{cfg}_s{k}.npz") for k in SEEDS]
    comb, vib, cur = {}, {}, {}
    for k in H.FRAMES:
        comb[k], vib[k], cur[k] = ensemble_parts(runs, [r[f"F_{k}"] for r in runs])
        ref = np.mean([X.score_rows(r, "ct-mean")[k] for r in runs], 0)   # 03의 e345 점수와 같아야 한다
        assert np.array_equal(comb[k], ref, equal_nan=True), f"{sid} {k}: 결합 점수가 03 경로와 다르다"
    cols = {}
    n = len(base)
    n_vn = len(comb["valid_normal"])
    for name, comps in (("LR2a", {"magnitude": vib, "current": cur}),
                        ("LR2b", {"magnitude": comb, "never": {k: np.full(len(v), -np.inf) for k, v in comb.items()}})):
        cols.update(H.calibrated_columns(name, comb, seg_vn, n))
        for cname, g in comps.items():
            _, cfull, cloo = s01.calibrate(M, comb["valid_normal"], seg_vn, g)   # 성분을 결합 점수의 보정 분포와 비교(01_scores와 같음)
            cols[f"{name}|cp_full|{cname}"] = np.concatenate([cfull[k] for k in H.FRAMES])
            cols[f"{name}|cp_loo|{cname}"] = np.concatenate([cloo, np.full(n - n_vn, np.nan)])
    return pd.concat([base, pd.DataFrame(cols, index=base.index)], axis=1), meta


def candidates(meta):
    _, ev, _ = H.tvt()
    known = {c[0]: c for c in ev.candidates(meta["complexity"])}
    out = {"L": ("L", "LR2a", False, False, False, 1), "L+R1": ("L+R1", "LR2a", True, False, False, 2),
           "L+R2a": ("L+R2a", "LR2a", False, True, False, 2), "L+R1+R2a": ("L+R1+R2a", "LR2a", True, True, False, 3),
           "L+R2b": ("L+R2b", "LR2b", False, True, False, 2), "L+R1+R2b": ("L+R1+R2b", "LR2b", True, True, False, 3)}
    for ours, theirs in (("v2", "v2"), ("v2+R2", "v2+H2"), ("v2+R1", "v2+H1"), ("v2+R1+R2", "v2+H1+H2")):
        out[ours] = (ours,) + tuple(known[theirs][1:])
    return out


def eval_split(sid):
    cfg = locked()
    _, ev, _ = H.tvt()
    spec = importlib.util.spec_from_file_location("tvt_s07", H.TVT / "07_r1_on_baselines.py")
    m07 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m07)
    t, meta = build_table(sid, cfg)
    r2 = meta["r2_ref"]
    states = pd.read_csv(H.DOMAIN_OUT / "06_operating_regime_records.csv", encoding="utf-8-sig").set_index("rec")["state"]
    tr_end, va_end = TRAIN_VALID_END[sid]
    rows, st = [], []
    for name, c in candidates(meta).items():
        for a in H.ALPHAS:
            for regime in ("valid", "test"):
                for mode, m in ev.evaluate(t, c, a, regime, r2).items():
                    rows.append(dict(split=sid, model=name, alpha=a, regime=regime, mode=mode, **m))
            preds = pd.concat([ev.predict_rows(t, c, a, rg, r2).assign(part=rg) for rg in ("valid", "test")], ignore_index=True)
            nm = preds[preds.subset == "normal"].copy()
            k = nm.rec.str.split(":").str[2].astype(int)
            nm["orig"] = np.where(nm.part == "valid", k + tr_end, k + va_end)
            nm["alarm"] = nm.alarm_realtime.astype(bool)
            per = nm.groupby(["part", "orig"]).alarm.agg(["max", "sum"]).reset_index()
            per["state"] = per.orig.map(states)
            for part in ("valid", "test", "valid+test"):
                q = per if part == "valid+test" else per[per.part == part]
                for s in STATES + ["all"]:
                    qq = q if s == "all" else q[q.state == s]
                    st.append(dict(split=sid, model=name, alpha=a, part=part, state=s, records=int(len(qq)),
                                   fa_records=int(qq["max"].sum()), fa_rows=int(qq["sum"].sum())))
        if c[2]:
            to = m07.test_only(t, c[1], True, c[3], r2)
            rows.append(dict(split=sid, model=name, alpha=H.PRIMARY_ALPHA, regime="test", mode="test_only", **to))
    return rows, st


# ---------------------------------------------------------------- 강건성 (05의 주입 흐름을 그대로 쓰고 경보 계산만 바꾼다)
def m05():
    spec = importlib.util.spec_from_file_location("lx_m05", H.HERE / "05_robustness.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class LSTMDetR2:
    """잠근 LSTM e345의 결합·진동·전류 점수와 p값(결합 점수의 valid 보정 분포 기준)."""

    def __init__(self, sid, cfg):
        self.runs = [X.load_run(H.CACHE / "runs" / f"{sid}_{cfg}_s{k}.npz") for k in SEEDS]
        r0 = self.runs[0]
        self.W, self.warm = int(r0["W"]), str(r0["warm"])
        self.models = [L.load_model(H.CACHE / "models" / f"{sid}_{cfg}_s{k}.pt", int(r0["h1"]), int(r0["h2"])) for k in SEEDS]
        inp = np.load(H.CACHE / f"inputs_{sid}.npz")
        self.mean, self.scale = inp["mean"], inp["scale"]
        comb, _, _ = ensemble_parts(self.runs, [r["F_valid_normal"] for r in self.runs])
        self.cal = pd.Series(np.where(np.isfinite(comb), comb, -np.inf)).groupby(inp["seg_valid_normal"]).max().to_numpy()

    def parts(self, q, seg, cp, alpha):
        z = (q[H.setup()["D"].SENSORS].to_numpy(float) - self.mean) / self.scale
        Fs = [L.frame_features(m, z, np.asarray(seg), self.W, self.warm) for m in self.models]
        comb, vib, cur = ensemble_parts(self.runs, Fs)
        act = lambda s: (lambda p: np.isfinite(p) & (p <= alpha))(cp(self.cal, s))  # noqa: E731
        return act(comb), act(vib), act(cur)


def all_alarms_r2(M, V, fin, dets, frame):
    """v2 계열(v2, v2+R2, v2+R1, v2+R1+R2)과 LSTM 계열(L, +R1, +R2-L1/L2, +R1+R2-L1/L2)의 행 경보."""
    lib, _, _ = H.tvt()
    r = fin.rows(frame)
    out = {v: V.Final.alarms(r, v)[0] for v in V.VARIANTS}
    out["v2+R2"] = r["own2"].copy()
    q = M["D"].quantize(M["D"].inputs_only(frame.reset_index(drop=True)), "matched")
    alarm, vib, cur = dets[0].parts(q, r["seg"], M["conformal_p"], V.ALPHA)
    wave = r["wave_ok"]
    own = {"L": alarm, "L+R2a": alarm & ~(vib & ~cur & wave), "L+R2b": alarm & ~wave}
    for k, a in own.items():
        out[k] = a
        name = "L+R1" if k == "L" else k.replace("L+", "L+R1+")
        out[name] = lib.stream_rules(r["ts"], r["seg"], a, wave, latch=True)[0]
    return r, out


def robust_job(args):
    kind, sid, fam = args
    m = m05()
    cfg = locked()
    orig_build = m.build

    def build2(s):
        M, V, sp, fin, _, gen, test, recs, Xs, f_test = orig_build(s)
        return M, V, sp, fin, [LSTMDetR2(s, cfg)], gen, test, recs, Xs, f_test

    m.build, m.all_alarms = build2, all_alarms_r2
    if kind == "v1":
        return m.job_v1(sid, fam)
    if kind == "v2":
        return m.job_v2(sid)
    return m.job_v5(sid)


# ---------------------------------------------------------------- 요약
def summarize(ev_df, st_df, seconds):
    L_ = []
    w = L_.append
    order = ["v2+R1+R2", "L+R1+R2a", "L+R1+R2b", "v2+R1", "L+R1", "v2+R2", "L+R2a", "L+R2b", "v2", "L"]
    p = ev_df[ev_df["mode"] == "realtime"]
    w("## R2 대응 규칙을 붙인 비교 (실시간 행 F1, LSTM = 잠근 설정의 새 시드 앙상블 e345)")
    w("")
    w("| α | 모델 | valid A / B (평균) | test A / B | test 미탐 행 A / B | test 오경보 행 A / B |")
    w("|---|---|---|---|---|---|")
    table = []
    for a in H.ALPHAS:
        for m in order:
            g = p[(p.model == m) & (p.alpha == a)]
            d = dict(alpha=a, model=m)
            for reg in ("valid", "test"):
                for s in H.SPLITS:
                    x = g[(g.regime == reg) & (g.split == s)].iloc[0]
                    d[f"{reg}_{s}"] = float(x.f1)
                    if reg == "test":
                        d[f"fn_{s}"], d[f"fp_{s}"] = int(x.fn), int(x.fp)
            d["valid_mean"] = (d["valid_A"] + d["valid_B"]) / 2
            table.append(d)
            w(f"| {int(a * 100)}% | {m} | {d['valid_A']:.3f} / {d['valid_B']:.3f} ({d['valid_mean']:.3f}) | {d['test_A']:.3f} / {d['test_B']:.3f} | "
              f"{d['fn_A']} / {d['fn_B']} | {d['fp_A']} / {d['fp_B']} |")
    to = ev_df[ev_df["mode"] == "test_only"].pivot(index="model", columns="split", values="f1")
    w("")
    w("이상 흐름을 test 기록부터 따로 돌린 값(α 1%): " + "; ".join(f"{m} {to.loc[m, 'A']:.3f}/{to.loc[m, 'B']:.3f}" for m in order if m in to.index))
    w("")
    w("## 운전 상태별 오경보 (분할 B, valid+test 정상 300기록, 경보 기록 수 / 경보 행 수)")
    for a in H.ALPHAS:
        q = st_df[(st_df.split == "B") & (st_df.alpha == a) & (st_df.part == "valid+test")]
        q = q.assign(v=q.fa_records.astype(str) + " / " + q.fa_rows.astype(str))
        pv = q.pivot(index="state", columns="model", values="v").reindex(STATES + ["all"])[order]
        pv.insert(0, "기록 수", q[q.model == "v2"].set_index("state").records)
        w(f"\nα {int(a * 100)}%\n")
        w(pv.to_markdown())
    return L_, table


def summarize_robust():
    v1, loss, v5 = (pd.read_csv(H.OUT / n) for n in ("07_v1.csv", "07_v2_loss.csv", "07_v5.csv"))
    det = [c for c in v1.columns if c.endswith("|detected")]
    v1[det] = v1[det].astype(object).fillna(False).astype(float)
    pod = v1[v1.strength > 0].groupby(["split", "family", "target", "strength"])[det].mean().reset_index()
    pod.to_csv(H.OUT / "07_v1_pod.csv", index=False)
    ctrl = v1[v1.strength == 0].groupby(["split", "family", "target"])[det].mean().reset_index()
    lcols = [c for c in loss.columns if c.endswith("|detected")]
    lpod = loss.groupby(["split", "target", "multiplier"])[lcols].mean().reset_index()
    # v2 계열이 준용 04 산출물과 같은지(같은 주입인지)
    ref = pd.read_csv(H.TVT / "outputs/validation_v1_pod.csv")
    chk = pod.merge(ref, on=["split", "family", "target", "strength"], suffixes=("", "_ref"))
    same = {v: bool(np.allclose(chk[f"{v}|detected"].astype(float), chk[f"{v}|detected_ref"].astype(float))) for v in ("v2", "v2+R1", "v2+R1+R2")}
    models = ["v2+R1+R2", "L+R1+R2a", "L+R1+R2b", "v2+R1", "L+R1", "v2+R2", "L+R2a", "L+R2b", "v2", "L"]
    L_ = ["", "## 강건성 (준용 04와 같은 주입, α 1%)", ""]
    show = pod.copy()
    show.columns = [c.replace("|detected", "") for c in show.columns]
    L_.append("인공 주입 탐지율 (test 정상 기록, 주입할 수 없던 기록은 못 잡음으로 셈)\n")
    L_.append(show[["split", "family", "target", "strength"] + models].round(3).to_markdown(index=False))
    c2 = ctrl.copy()
    c2.columns = [c.replace("|detected", "") for c in c2.columns]
    L_.append("\n주입 없는 대조의 경보율\n")
    L_.append(c2[["split", "family", "target"] + models].round(4).to_markdown(index=False))
    lp = lpod.copy()
    lp.columns = [c.replace("|detected", "") for c in lp.columns]
    L_.append("\n진폭 감소(V2) 탐지율\n")
    L_.append(lp[["split", "target", "multiplier"] + models].round(3).to_markdown(index=False))
    L_.append("\nV5 교락 시험 (경보 기록 수 / 기록 수)\n")
    v5 = v5.assign(v=v5.alerted.astype(str) + "/" + v5.records.astype(str), level=v5.level.astype(str))
    L_.append(v5.pivot_table(index=["test", "level", "split"], columns="model", values="v", aggfunc="first")[models].to_markdown())
    return L_, dict(v2_matches_tvt_validation=same, cells=int(len(chk)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--summary-only", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    cfg = locked()
    if not a.summary_only:
        with ProcessPoolExecutor(max_workers=a.workers, mp_context=mp.get_context("spawn")) as ex:
            ev_f = {ex.submit(eval_split, s): s for s in H.SPLITS}
            work = [("v1", s, f) for s in H.SPLITS for f in ("band_noise", "damped_impulse", "current_residual")] + \
                   [("v2", s, None) for s in H.SPLITS] + [("v5", s, None) for s in H.SPLITS]
            rb_f = {ex.submit(robust_job, w): w for w in work}
            rows, st = [], []
            for f in as_completed(ev_f):
                r, s = f.result()
                rows += r
                st += s
                print("채점 완료", ev_f[f], f"{time.time() - t0:.0f}s", flush=True)
            res = {"v1": [], "loss": [], "v5": []}
            for f in as_completed(rb_f):
                kind, df = f.result()
                res[kind].append(df)
                print("강건성 완료", rb_f[f], f"{time.time() - t0:.0f}s", flush=True)
        pd.DataFrame(rows).to_csv(H.OUT / "07_eval.csv", index=False)
        pd.DataFrame(st).to_csv(H.OUT / "07_states.csv", index=False)
        pd.concat(res["v1"], ignore_index=True).to_csv(H.OUT / "07_v1.csv", index=False)
        pd.concat(res["loss"], ignore_index=True).to_csv(H.OUT / "07_v2_loss.csv", index=False)
        pd.concat(res["v5"], ignore_index=True).to_csv(H.OUT / "07_v5.csv", index=False)
    ev_df, st_df = pd.read_csv(H.OUT / "07_eval.csv"), pd.read_csv(H.OUT / "07_states.csv")
    lines, table = summarize(ev_df, st_df, time.time() - t0)
    rl, chk = summarize_robust()
    lines += rl
    (H.OUT / "07_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    H.dump(dict(locked_cfg=cfg, seeds=SEEDS, table=table, robustness_check=chk, seconds=round(time.time() - t0, 1)),
           H.OUT / "07_r2_analog.json")
    print("\n".join(lines))
    print(chk, f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
