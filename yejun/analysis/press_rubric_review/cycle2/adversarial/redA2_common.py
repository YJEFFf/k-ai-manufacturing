"""적대적 검수 A2 공용 모듈 — 분할·설계·초모수를 바꿔 v2 점수 규칙을 다시 적합한다.

- 팀 모듈은 임시 사본(REDA2_REPO)에서 import한다. 저장소 작업 사본의 생성 스크립트는 실행하지 않는다.
- 기본 설정(Config())은 press_guard/model.py의 GuardModel.fit/predict와 같은 점수·보정·경보를 낸다.
  일치 여부는 redA2_00_validate.py가 팀 API와 행 단위로 대조한다.
- 사인 1−R² 점수는 분할과 무관한 행 특징이다(창이 기록구간을 넘지 않는다). 한 번 계산해 임시 폴더에 저장한다.

실행: OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 REDA2_REPO=<임시 사본> /opt/anaconda3/bin/python redA2_XX.py
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = Path(os.environ.get("REDA2_REPO", "")).resolve() if os.environ.get("REDA2_REPO") else None
if REPO is None or not (REPO / "yejun" / "press_guard" / "model.py").is_file():
    raise SystemExit("REDA2_REPO가 임시 사본(…/repo, 그 아래 yejun/)을 가리켜야 한다")
if "k-제조데이터" in str(REPO) and "/tmp/" not in str(REPO):
    raise SystemExit("저장소 작업 사본이 아니라 임시 사본에서 실행한다")
CACHE = Path(os.environ.get("REDA2_CACHE", REPO.parent / "cache"))
CACHE.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(REPO / "yejun" / "press_guard"))

import model as M  # noqa: E402  (임시 사본의 press_guard/model.py)
from press.calibrate import conformal_p, segment_max  # noqa: E402
from press.scores import ExpTail, window_index  # noqa: E402
from scipy import stats  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

D = M.D
ALPHAS = (.01, .03, .05)
SPLITS = {"A": (360, 480, 600), "B": (300, 420, 600)}   # 학습 끝, 보정 끝, 평가 끝(미포함)


@dataclass(frozen=True)
class Config:
    w_late: int = 8            # 주 파형 창
    w_early: int | None = 6    # 초반 창(None이면 초반 창 없음 = v1식)
    switch: int | None = None  # 이 위치부터 주 창. None이면 w_late−1(주 창이 처음 차는 위치)
    ar_order: int | None = 2   # None이면 동역학 성분 없음
    q: float = .95             # 꼬리 접합 분위
    rule: str = "fmax"         # fmax | fisher | sum
    unit_rows: int = 50        # 보정·알림 단위 최대 길이
    magnitude: bool = True

    def label(self):
        return (f"wl{self.w_late}_we{self.w_early}_sw{self.switch_pos}_ar{self.ar_order}_q{self.q:g}_{self.rule}_u{self.unit_rows}"
                + ("" if self.magnitude else "_nomag"))

    @property
    def switch_pos(self):
        return self.w_late - 1 if self.switch is None else self.switch


V2 = Config()
V1 = Config(w_early=None, ar_order=None)


class Data:
    """정상 20,000행·이상 600행의 matched 입력, 기록구간, 위치, 행 특징(사인 점수)."""

    def __init__(self):
        normal, abnormal, report = D.load()
        self.report = report
        self.raw = dict(n=normal, a=abnormal)
        self.q = {k: D.quantize(D.inputs_only(f), "matched") for k, f in self.raw.items()}
        self.seg = {k: M.layout(f)[1] for k, f in self.q.items()}
        self.pos = {k: D.segment_positions(s)[0] for k, s in self.seg.items()}
        self.len = {k: D.segment_positions(s)[1] for k, s in self.seg.items()}
        self.X = {k: f[D.SENSORS].to_numpy(float) for k, f in self.q.items()}
        self.cur = {k: f[D.SENSORS[2]].to_numpy(float) for k, f in self.q.items()}
        self.time = {k: pd.to_datetime(f[D.TIME], format="mixed", utc=True) for k, f in self.q.items()}
        self._sine = {}

    def sine(self, key, w):
        if (key, w) not in self._sine:
            path = CACHE / f"sine_{key}_w{w}.npy"
            if path.is_file():
                self._sine[(key, w)] = np.load(path)
            else:
                self._sine[(key, w)] = M.sine_score(self.cur[key], self.seg[key], w)
                np.save(path, self._sine[(key, w)])
        return self._sine[(key, w)]

    def frame(self, key, mask):
        """팀 API에 넣을 원본 프레임(시간 순서 유지)."""
        return self.raw[key][mask].reset_index(drop=True)


def ar_fit(cur, seg, order, rows):
    """정상 학습 행(rows: bool)에서 상수항 + 직전 order개 전류의 최소제곱. 팀 GuardModel.fit과 같은 설계행렬 순서."""
    idx = window_index(seg, order + 1)
    idx = idx[rows[idx]]
    design = np.column_stack([np.ones(len(idx))] + [cur[idx - k] for k in range(1, order + 1)])
    return np.linalg.lstsq(design, cur[idx], rcond=None)[0]


def ar_residual(cur, seg, coef):
    order = len(coef) - 1
    idx = window_index(seg, order + 1)
    out = np.full(len(cur), np.nan)
    pred = coef[0]
    for k in range(1, order + 1):
        pred = pred + coef[k] * cur[idx - k]
    out[idx] = np.abs(cur[idx] - pred)
    return out


def ar2_residual_team(cur, seg, coef):
    """팀 model.ar_residual과 같은 연산 순서(x − c0 − c1·x1 − c2·x2)."""
    idx = window_index(seg, 3)
    out = np.full(len(cur), np.nan)
    out[idx] = np.abs(cur[idx] - coef[0] - coef[1] * cur[idx - 1] - coef[2] * cur[idx - 2])
    return out


def fuse(g, rule):
    """g: (행, 성분) −log10(정상 꼬리 확률). press_selection/run.py의 fusions와 같은 정의."""
    finite = np.isfinite(g)
    k = finite.sum(1)
    none = k == 0
    kk = np.maximum(k, 1)
    if rule == "fmax":
        with np.errstate(all="ignore"):
            out = np.nanmax(np.where(finite, g, -np.inf), 1)
        return np.where(none, np.nan, out)
    total = np.where(none, np.nan, np.nansum(np.where(finite, g, 0.0), 1))
    if rule == "sum":
        return total
    if rule == "fisher":
        with np.errstate(all="ignore"):
            return np.where(none, np.nan, -stats.chi2.logsf(2 * np.log(10) * total, 2 * kk) / np.log(10))
    raise ValueError(rule)


class Fitted:
    """분할 하나·설정 하나의 적합 결과. 정상 전체 행과 이상 행의 점수·p값을 갖는다."""

    def __init__(self, data: Data, train_rec, cal_rec, cfg: Config = V2):
        self.data, self.cfg = data, cfg
        seg_n = data.seg["n"]
        self.train_rows = np.isin(seg_n, train_rec)
        self.cal_rows = np.isin(seg_n, cal_rec)
        tr = self.train_rows
        scaler = StandardScaler().fit(data.q["n"].loc[tr, D.SENSORS])
        self.mean, self.scale = scaler.mean_, scaler.scale_
        self.tails = {}
        comp_train = {}
        mag_n = np.abs((data.X["n"] - self.mean) / self.scale).max(1)
        self.tails["magnitude"] = ExpTail(mag_n[tr], cfg.q)
        for w in {cfg.w_late, cfg.w_early} - {None}:
            self.tails[f"sine{w}"] = ExpTail(data.sine("n", w)[tr], cfg.q)
        if cfg.ar_order:
            self.coef = ar_fit(data.cur["n"], seg_n, cfg.ar_order, tr)
            res = self._residual("n")
            self.tails["dynamics"] = ExpTail(res[tr], cfg.q)
        self.ok = all(t.ok for t in self.tails.values())
        self.comp = {k: self.components(k) for k in ("n", "a")}
        self.score = {k: self.comp[k]["score"] for k in ("n", "a")}
        units = self.units("n")
        self.cal = segment_max(self.score["n"][self.cal_rows], units[self.cal_rows])
        self.p = {k: conformal_p(self.cal, self.score[k]) for k in ("n", "a")}

    def _residual(self, key):
        d = self.data
        if self.cfg.ar_order == 2:
            return ar2_residual_team(d.cur[key], d.seg[key], self.coef)
        return ar_residual(d.cur[key], d.seg[key], self.coef)

    def units(self, key):
        d = self.data
        seg, block = d.seg[key], d.pos[key] // self.cfg.unit_rows
        return np.cumsum(np.r_[False, (seg[1:] != seg[:-1]) | (block[1:] != block[:-1])])

    def components(self, key):
        d, cfg = self.data, self.cfg
        z = (d.X[key] - self.mean) / self.scale
        mag = np.abs(z).max(1)
        pos = d.pos[key]
        gz = self.tails["magnitude"](mag) if cfg.magnitude else np.full(len(mag), np.nan)
        late = self.tails[f"sine{cfg.w_late}"](d.sine(key, cfg.w_late))
        if cfg.w_early is None:
            gs = late
        else:
            early = self.tails[f"sine{cfg.w_early}"](d.sine(key, cfg.w_early))
            gs = np.where(pos < cfg.switch_pos, early, late)
        ga = self.tails["dynamics"](self._residual(key)) if cfg.ar_order else np.full(len(mag), np.nan)
        g = np.column_stack([gz, gs, ga])
        if cfg.rule == "fmax":
            score = np.fmax(np.fmax(gz, gs), ga)
        else:
            score = fuse(g, cfg.rule)
        return dict(g=g, score=score, magnitude=mag, sensor=np.abs(z).argmax(1))

    def alarm(self, key, alpha):
        p = self.p[key]
        return np.isfinite(p) & (p <= alpha)

    def threshold(self, alpha):
        n = len(self.cal)
        a = int(np.floor(alpha * (n + 1))) - 1
        return float(np.sort(self.cal)[::-1][a]) if a >= 0 else np.inf


def abnormal_metrics(fit: Fitted, alpha):
    d = fit.data
    al = fit.alarm("a", alpha)
    seg, pos = d.seg["a"], d.pos["a"]
    tp = int(al.sum())
    fn = int(len(al) - tp)
    g = pd.DataFrame(dict(r=seg, a=al, pos=pos))
    detected = g.groupby("r").a.any()
    first = g[g.a].groupby("r").pos.min() * D.DT
    rows_per = g.groupby("r").a.sum()
    return dict(tp=tp, fn=fn, abnormal_detected=int(detected.sum()), abnormal_records=int(len(detected)),
                delay_median_s=float(first.median()) if len(first) else np.nan, delay_max_s=float(first.max()) if len(first) else np.nan,
                fn_pos0_1=int((~al & (pos <= 1)).sum()), fn_pos2_6=int((~al & (pos >= 2) & (pos <= 6)).sum()), fn_pos7plus=int((~al & (pos >= 7)).sum()),
                abnormal_level2_records=int((rows_per >= 2).sum()), fn_by_record=(g.groupby("r").size() - rows_per).to_numpy(int),
                detected_by_record=detected.to_numpy(bool))


def normal_metrics(fit: Fitted, alpha, test_rec):
    """정상 평가: 알림 단위(기록구간 안 unit_rows 블록)·기록구간·행 단위 오경보와 오경보 기록의 경보 행 수."""
    d = fit.data
    rows = np.isin(d.seg["n"], test_rec)
    al = fit.alarm("n", alpha) & rows
    seg = d.seg["n"]
    units = fit.units("n")
    n_units = int(pd.Series(units[rows]).nunique())
    rec_rows = pd.Series(al[rows]).groupby(seg[rows]).sum()
    unit_any = pd.Series(al[rows]).groupby(units[rows]).any()
    alerted = rec_rows[rec_rows > 0]
    return dict(fp=int(al.sum()), normal_rows=int(rows.sum()), normal_records=int(len(rec_rows)), normal_alerted=int(len(alerted)),
                normal_units=n_units, normal_units_alerted=int(unit_any.sum()),
                alerted_records=alerted.index.to_numpy(int), alerted_rows=alerted.to_numpy(int),
                normal_level2_records=int((alerted >= 2).sum()))


def f1(tp, fp, fn):
    d = 2 * tp + fp + fn
    return 2 * tp / d if d else 0.0


def summarize(fit: Fitted, alpha, test_rec):
    a = abnormal_metrics(fit, alpha)
    n = normal_metrics(fit, alpha, test_rec)
    out = {k: v for k, v in {**a, **n}.items() if not isinstance(v, np.ndarray)}
    out["f1"] = f1(a["tp"], n["fp"], a["fn"])
    out["normal_alert_rate"] = n["normal_units_alerted"] / n["normal_units"] if n["normal_units"] else np.nan
    out["threshold"] = fit.threshold(alpha)
    out["n_cal"] = len(fit.cal)
    out["alpha_grid"] = np.floor(alpha * (len(fit.cal) + 1)) / (len(fit.cal) + 1)
    return out, a, n


def incident_counts(times, seg, units, alarm, gap_s=60.0, escalate_rows=2):
    """팀 IncidentTracker와 같은 규칙: 경보 단위가 이어지고 단위 사이 공백이 gap_s 이하면 한 사건. 사건별 경보 행 수를 돌려준다."""
    f = pd.DataFrame(dict(u=units, t=times, a=alarm, s=seg))
    g = f.groupby("u", sort=True).agg(start=("t", "min"), end=("t", "max"), alarmed=("a", "any"), rows=("a", "sum"), rec=("s", "first"))
    incidents = []
    prev_alarmed, prev_end, open_rows = False, None, None
    for u in g.itertuples():
        if u.alarmed:
            gap = (u.start - prev_end).total_seconds() if prev_end is not None else np.inf
            if prev_alarmed and open_rows is not None and 0 <= gap <= gap_s:
                open_rows["rows"] += int(u.rows); open_rows["units"] += 1; open_rows["records"].append(int(u.rec))
            else:
                open_rows = dict(rows=int(u.rows), units=1, records=[int(u.rec)])
                incidents.append(open_rows)
        prev_alarmed, prev_end = bool(u.alarmed), u.end
    return [dict(rows=i["rows"], units=i["units"], records=i["records"], level=2 if i["rows"] >= escalate_rows else 1) for i in incidents]
