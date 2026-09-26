"""E2 — v2 구조(크기 + 초반 6→8 사인 파형 + AR(2) 잔차, q95 지수 꼬리, fmax, 기록 최대 conformal)를 UCI 펌프 누설에 그대로 적용.

가중치 전이가 아니라 같은 구조를 UCI 정상 사이클로 새로 적합한다. 대회 F1과 합산·직접 비교하지 않는다.
"""
from pathlib import Path
import tempfile
from zipfile import ZipFile
import time

from sklearn.metrics import f1_score, roc_auc_score

from common import *  # noqa: F403
from model import sine_score as sine_pinned, window_index  # noqa: E402
from press.scores import ExpTail, sine_score as sine_blas  # noqa: E402

EXT = YEJUN / "analysis" / "press_external"
CACHE = Path(tempfile.gettempdir()) / "press_supplement_uci10hz.npz"   # 시스템 임시 폴더, Git 제외
SPEC = PROTOCOL["E2_uci_v2_structure"]
CHANNELS = {"v2_4ch": ["PS1", "FS1", "VS1", "EPS1"], "v2_3ch": ["VS1", "PS1", "EPS1"], "v2_4ch_phase": ["PS1", "FS1", "VS1", "EPS1"]}
CURRENT = "EPS1"


class GenericV2:
    """GuardModel.fit/components와 같은 산식을 임의 채널·기록 구조에 적용한다."""

    def __init__(self, values, seg, pos, channels, current, sine, phase=False, cached_sine=None):
        x = values[channels].to_numpy(float)
        if phase:
            frame = pd.DataFrame(x).assign(pos=pos)
            self.mean = frame.groupby("pos").mean().sort_index().to_numpy()
            std = frame.groupby("pos").std(ddof=0).sort_index().to_numpy()
            self.scale = np.maximum(std, .1 * x.std(axis=0))
        else:
            self.mean, self.scale = x.mean(axis=0), x.std(axis=0)
        self.channels, self.current, self.sine, self.phase = channels, current, sine, phase
        mag = self._magnitude(x, pos)
        cur = values[current].to_numpy(float)
        idx = window_index(seg, 3)
        design = np.column_stack([np.ones(len(idx)), cur[idx - 1], cur[idx - 2]])
        self.coef = np.linalg.lstsq(design, cur[idx], rcond=None)[0]
        s6, s8 = cached_sine if cached_sine is not None else (sine(cur, seg, 6), sine(cur, seg, 8))
        self.tails = dict(magnitude=ExpTail(mag), sine6=ExpTail(s6), sine8=ExpTail(s8),
                          dynamics=ExpTail(self._ar(cur, seg)))
        assert all(t.ok for t in self.tails.values())

    def _magnitude(self, x, pos):
        mean = self.mean[pos] if self.phase else self.mean
        scale = self.scale[pos] if self.phase else self.scale
        return np.abs((x - mean) / scale).max(axis=1)

    def _ar(self, cur, seg):
        idx = window_index(seg, 3)
        out = np.full(len(cur), np.nan)
        out[idx] = np.abs(cur[idx] - self.coef[0] - self.coef[1] * cur[idx - 1] - self.coef[2] * cur[idx - 2])
        return out

    def parts(self, values, seg, pos, cached_sine=None):
        cur = values[self.current].to_numpy(float)
        s6, s8 = cached_sine if cached_sine is not None else (self.sine(cur, seg, 6), self.sine(cur, seg, 8))
        gz = self.tails["magnitude"](self._magnitude(values[self.channels].to_numpy(float), pos))
        gs = np.where(pos < 7, self.tails["sine6"](s6), self.tails["sine8"](s8))
        ga = self.tails["dynamics"](self._ar(cur, seg))
        return dict(magnitude=gz, waveform=gs, dynamics=ga)

    def score(self, values, seg, pos, cached_sine=None):
        c = self.parts(values, seg, pos, cached_sine)
        return np.fmax(np.fmax(c["magnitude"], c["waveform"]), c["dynamics"])


def contest_sanity():
    """일반화 구현이 대회 자료에서 저장 v2 지표를 재현하는지 확인한다."""
    normal, abnormal, _ = load_data()
    got = []
    for sid in D.SPLITS:
        rows = split_rows(normal, sid)
        frames = {k: D.quantize(D.inputs_only(normal.iloc[v]), "matched") for k, v in rows.items()}
        frames["abnormal"] = D.quantize(D.inputs_only(abnormal), "matched")
        segpos = {k: (D.segments(f),) + D.segment_positions(D.segments(f)) for k, f in frames.items()}
        seg, pos, _ = segpos["train"]
        m = GenericV2(frames["train"], seg, pos, D.SENSORS, D.SENSORS[2], sine_pinned)
        cal = segment_max(m.score(frames["cal"], segpos["cal"][0], segpos["cal"][1]), segpos["cal"][0])
        ref = frozen(sid)
        assert np.allclose(np.sort(cal), np.sort(ref.cal), rtol=0, atol=1e-9), "보정 최대값 불일치"
        alarms = {}
        for k in ("test", "abnormal"):
            p = conformal_p(cal, m.score(frames[k], segpos[k][0], segpos[k][1]))
            alarms[k] = np.isfinite(p) & (p <= .01)
        tp, fp = int(alarms["abnormal"].sum()), int(alarms["test"].sum())
        fn = len(alarms["abnormal"]) - tp
        got.append(dict(split=sid, tp=tp, fp=fp, fn=fn, f1=2 * tp / (2 * tp + fp + fn)))
    saved = pd.read_csv(YEJUN / "press_guard" / "outputs" / "metrics.csv")
    for g in got:
        s = saved[saved.split.eq(g["split"]) & saved.model.eq("guard_v2") & saved.alpha.eq(.01)].iloc[0]
        assert (s.tp, s.fp, s.fn) == (g["tp"], g["fp"], g["fn"]), (g, s.to_dict())
    return got


def load_uci():
    archive = EXT / "data" / "hydraulic.zip"
    sha = D.sha256_file(archive)
    if CACHE.exists():
        c = np.load(CACHE, allow_pickle=False)
        if str(c["sha"]) == sha:
            return {k: c[k] for k in ("PS1", "EPS1", "FS1", "VS1")}, pd.read_csv(EXT / "partitions.csv"), sha
    arrays = {}
    with ZipFile(archive) as z:
        for s in ("PS1", "EPS1", "FS1", "VS1"):
            raw = np.loadtxt(z.open(s + ".txt"))
            assert raw.shape[0] == 2205 and np.isfinite(raw).all()
            per = raw.shape[1] // 60
            arrays[s] = raw.reshape(2205, 600, -1).mean(axis=2) if per >= 10 else np.repeat(raw, 10 // per, axis=1)
            assert arrays[s].shape == (2205, 600)
            print(s, raw.shape, "→", arrays[s].shape, flush=True)
    np.savez(CACHE, sha=sha, **arrays)
    return arrays, pd.read_csv(EXT / "partitions.csv"), sha


def profile_table():
    with ZipFile(EXT / "data" / "hydraulic.zip") as z:
        return pd.read_csv(z.open("profile.txt"), sep="\t", header=None, names=["cooler", "valve", "pump", "accumulator", "unstable"])


def partitions(profile):
    """press_external/evaluate.py와 같은 규칙."""
    stable, normal = profile.unstable.eq(0).to_numpy(), profile.pump.eq(0).to_numpy()
    parts = np.full(len(profile), "excluded", dtype=object)
    for _, g in profile[stable & normal].groupby(["cooler", "valve", "accumulator"]):
        ids = g.index.to_numpy(); n = len(ids)
        parts[ids[:int(.6 * n)]] = "train"; parts[ids[int(.6 * n):int(.8 * n)]] = "cal"; parts[ids[int(.8 * n):]] = "test_normal"
    parts[stable & ~normal] = "test_leak"
    return parts, stable, normal


def frame_of(arrays, cycles):
    n = len(cycles)
    values = pd.DataFrame({k: v[cycles].ravel() for k, v in arrays.items()})
    seg = np.repeat(np.arange(n), 600)
    pos = np.tile(np.arange(600), n)
    return values, seg, pos


def main():
    start = time.monotonic()
    sanity = contest_sanity()
    print("대회 자료 재현:", sanity, flush=True)
    arrays, saved_parts, sha = load_uci()
    profile = profile_table()
    parts, stable, normal = partitions(profile)
    # 기존 외부 검증과 같은 분할인지 확인
    for (mode, cooler, part), g in saved_parts.groupby(["mode", "cooler", "partition"]):
        here = profile.cooler.eq(cooler).to_numpy()
        source = here if mode == "local_normal_reference" else ~here
        want = {"train": (parts == "train") & source, "cal": (parts == "cal") & source,
                "test": here & ((parts == "test_normal") | (parts == "test_leak")) if mode == "local_normal_reference" else here & stable}[part]
        assert set(np.flatnonzero(want)) == set(g.cycle_id), (mode, cooler, part)
    cycles = np.flatnonzero(stable)
    values, seg, pos = frame_of(arrays, cycles)
    cur = values[CURRENT].to_numpy(float)
    t = time.monotonic()
    sine_all = (sine_blas(cur, seg, 6), sine_blas(cur, seg, 8))   # 적합 없는 성분: 한 번만 계산
    print(f"사인 점수 {time.monotonic()-t:.1f}s", flush=True)
    where = {c: i for i, c in enumerate(cycles)}

    def rows_of(ids):
        return np.concatenate([np.arange(where[i] * 600, where[i] * 600 + 600) for i in ids])

    metrics, strata, diag = [], [], []
    for mode in [e.split("(")[0] for e in SPEC["evaluations"]]:
        for cooler in (3, 20, 100):
            here = profile.cooler.eq(cooler).to_numpy()
            source = here if mode == "local_normal_reference" else ~here
            ids = dict(train=np.flatnonzero((parts == "train") & source), cal=np.flatnonzero((parts == "cal") & source),
                       test=np.flatnonzero(here & ((parts == "test_normal") | (parts == "test_leak"))) if mode == "local_normal_reference" else np.flatnonzero(here & stable))
            y = (~normal[ids["test"]]).astype(int)
            for variant, channels in CHANNELS.items():
                r = rows_of(ids["train"])
                sub = lambda rr: (values.iloc[rr].reset_index(drop=True), seg[rr], pos[rr])
                v, s, p = sub(r)
                s = np.searchsorted(np.unique(s), s)
                m = GenericV2(v, s, p, channels, CURRENT, sine_blas, phase=variant.endswith("phase"), cached_sine=(sine_all[0][r], sine_all[1][r]))
                seg_scores = {}
                for part in ("cal", "test"):
                    rr = rows_of(ids[part]); v, s, p = sub(rr)
                    s = np.searchsorted(np.unique(s), s)
                    comp = m.parts(v, s, p, cached_sine=(sine_all[0][rr], sine_all[1][rr]))
                    sc = np.fmax(np.fmax(comp["magnitude"], comp["waveform"]), comp["dynamics"])
                    seg_scores[part] = segment_max(sc, s)
                    if part == "test":
                        # 사후 진단(프로토콜 밖): 성분별 사이클 최대 점수의 AUROC와 최대 점수가 나온 사이클 내 위치
                        for name, c in comp.items():
                            cm = segment_max(c, s)
                            where_max = pd.Series(np.where(np.isfinite(c), c, -np.inf)).groupby(s).idxmax().to_numpy() % 600
                            diag.append(dict(mode=mode, cooler=cooler, model=variant, component=name, auroc=roc_auc_score(y, cm),
                                             normal_argmax_pos_median=float(np.median(where_max[y == 0])),
                                             leak_argmax_pos_median=float(np.median(where_max[y == 1]))))
                        diag.append(dict(mode=mode, cooler=cooler, model=variant, component="cycle_mean_magnitude",
                                         auroc=roc_auc_score(y, pd.Series(comp["magnitude"]).groupby(s).mean().to_numpy())))
                pv = conformal_p(seg_scores["cal"], seg_scores["test"])
                alarm = pv <= SPEC["alpha"]
                tp = int((alarm & (y == 1)).sum()); fp = int((alarm & (y == 0)).sum())
                fn = int((~alarm & (y == 1)).sum()); tn = int((~alarm & (y == 0)).sum())
                metrics.append(dict(mode=mode, cooler=cooler, model=variant, n_train=len(ids["train"]), n_cal=len(ids["cal"]),
                                    n_test=len(ids["test"]), alpha=SPEC["alpha"], tp=tp, fp=fp, fn=fn, tn=tn,
                                    precision=tp / (tp + fp) if tp + fp else 0, recall=tp / (tp + fn), f1=f1_score(y, alarm),
                                    normal_alarm_rate=fp / (tn + fp), auroc=roc_auc_score(y, seg_scores["test"]),
                                    ar2=";".join(f"{c:.4f}" for c in m.coef)))
                for level in (0, 1, 2):
                    mm = profile.pump.to_numpy()[ids["test"]] == level
                    strata.append(dict(mode=mode, cooler=cooler, model=variant, pump_leakage=level, n=int(mm.sum()),
                                       alarms=int(alarm[mm].sum()), alarm_rate=float(alarm[mm].mean())))
            print(mode, cooler, flush=True)
    new = pd.DataFrame(metrics)
    old = pd.read_csv(EXT / "metrics.csv")
    both = pd.concat([old.assign(source="press_external(기존)"), new.assign(source="press_supplement E2")], ignore_index=True)
    new.to_csv(HERE / "e2_uci_metrics.csv", index=False)
    pd.DataFrame(strata).to_csv(HERE / "e2_uci_strata.csv", index=False)
    pd.DataFrame(diag).to_csv(HERE / "e2_uci_component_diagnostic_posthoc.csv", index=False)
    both[["source", "mode", "cooler", "model", "f1", "normal_alarm_rate", "recall", "auroc", "tp", "fp", "fn", "tn"]].to_csv(HERE / "e2_uci_comparison.csv", index=False)
    D.dump_json(dict(experiment="E2", contest_sanity=sanity, uci_sha256=sha, cycles_stable=int(len(cycles)),
                     elapsed_s=time.monotonic() - start, environment=D.environment(),
                     code_sha256={n: D.sha256_file(HERE / n) for n in ("common.py", "uci_v2.py", "protocol.json")}), HERE / "e2_manifest.json")
    print(both.sort_values(["mode", "cooler", "model"])[["source", "mode", "cooler", "model", "f1", "normal_alarm_rate", "recall", "auroc"]].to_string(index=False))


if __name__ == "__main__":
    main()
