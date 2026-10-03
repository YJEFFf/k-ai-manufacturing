"""06 정상 운전 상태(운전 모드) 추정과 상태별 오경보·미탐 조건 분석 — test 채점 이후 사후 분석.

과제 ③ "정상적인 운전변화를 이상으로 판단하는 오경보를 줄이고, 미탐지·오경보 발생조건을 분석하시오"에 답하기 위한 분석이다.
tvt/ 의 잠금 선택(tvt_selection.json)과 test 채점이 끝난 뒤 추가했으며, 잠금 산출물을 읽기만 하고 바꾸지 않는다.
따라서 이 분석은 모델 선택·문턱·규칙 상수에 영향을 주지 않는다.

운전 상태를 나누는 방법과 근거
1) 부하 대리변수: 기록(약 8초, 최대 50행)마다 모터 전류를 고정 주파수 사인으로 적합한 진폭 cur_amp(공통 함수 case_table).
   전류 RMS(sqrt(mean(i²)))를 보조로 쓴다. 정상에서는 두 값의 상관이 1.00이고, 이상 기록은 사인 적합이 깨지므로 RMS만 쓴다.
   - 사인 진폭은 짧은 기록에서 불안정하다(주기 약 16.5표본). 8행 미만 기록(50개)은 부하 등급을 매기지 않고 '짧은 기록'으로 둔다.
     8행은 tvt 교차 확인(R2)이 전류 파형을 보기 시작하는 최소 길이(R2_MIN_LEN)와 같다.
2) 운전 구간(시간 연속 구간): 기록 순서대로 [log 상부 진동 SD, log 하부 진동 SD, log 전류 진폭]을 표준화하고,
   평균·분산이 함께 바뀌는 지점을 정확 최적 분할(optimal partitioning, 가우스 비용 n·Σlog σ²)로 찾는다.
   벌점은 BIC형 (2d+1)·ln N (d=3), 최소 구간 10기록. 벌점 ×0.5~×4, 최소 구간 5~20기록으로 바꿔도 경계가 같은지 확인한다.
   변동 부하 구간(기록마다 저·중·고 부하가 번갈아 나옴)과 정숙 구간(저부하가 연속, 진동 작음)이 나뉜다.
3) 부하 등급: 8행 이상 정상 기록 전체(77분)의 cur_amp에 1차원 가우스 혼합(3성분, random_state 0)을 맞추고,
   사후확률이 바뀌는 경계로 저(기저)·중(부분)·고부하를 나눈다. 단순 3분위(경계 약 121·192)는 기록의 약 45%가 몰린
   무부하 군집(110~130)의 한가운데를 잘라 같은 운전 상태를 저·중으로 쪼개므로 주 기준으로 쓰지 않고 민감도로만 보고한다.
   정숙 구간 기록은 구간 이름으로 묶는다.
   최종 상태 = 정숙 구간 / 변동 구간·저부하 / 변동 구간·중부하 / 변동 구간·고부하 / 변동 구간·짧은 기록.
   실제 운전 모드 정보(금형·스트로크·가동 기록)는 데이터에 없으므로 이 상태는 신호로 추정한 것이다.
4) 학습 분포와의 거리: 평가 기록의 상·하부 진동 SD와 전류 진폭이 학습 기록 분포의 몇 % 분위인지 보고
   상위 1% 밖·상위 1~5%·하위 1% 밖·몸통으로 나눈다. 보조로 k=5 최근접 거리(학습 99% 분위 초과 = 새로운 기록).
5) 이상 기록: 전류 RMS를 정상 상태별 RMS 범위와 비교하고, 정상의 부하-진동 관계(log 진동 SD ~ log 전류 RMS 회귀)에서
   얼마나 벗어나는지(표준화 잔차) 본다. 같은 표에 v2·최종 모델의 실시간 미탐 행 수를 붙인다.

오경보 계산은 tvt/evalcore.predict_rows를 그대로 쓴다(검증 정상 행 = 자기 기록을 뺀 LOO p, 시험 행 = 전체 보정 p,
사건 지속 H1은 정상 흐름 안에서 직전 기록 판정만 이어받는다). 실시간 행 경보를 센다.
R1 = H1(사건 지속), R2 = H2(교차 확인: 크기 성분만 넘고 전류 파형 정상이면 보류). 최종 모델 = v2+H1+H2.

실행: PYTHONIOENCODING=utf-8 python 06_operating_regime.py   (약 15초)
출력: outputs/06_operating_regime.json, outputs/06_operating_regime.csv(상태×모델 오경보 긴 표),
      outputs/06_operating_regime_records.csv(정상 기록별 상태·오경보), outputs/06_operating_regime_summary.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.mixture import GaussianMixture

HERE = Path(__file__).resolve().parent
PRESS = HERE.parent
sys.path.insert(0, str(PRESS / "tvt"))
sys.path.insert(0, str(PRESS / "cases"))
from common import case_table, load_both  # noqa: E402
from evalcore import _p, candidates, predict_rows  # noqa: E402

TVT_OUT = PRESS / "tvt" / "outputs"
TVT_CACHE = PRESS / "tvt" / "cache"
OUT = HERE / "outputs"

SPLIT_BOUNDS = {"A": (360, 480), "B": (300, 420)}       # 학습 끝·검증 끝(정상 기록 번호). tvt/lib.SPLITS와 같음
MODELS = ["maxz3", "knn5", "mlp_ae5", "lstm20", "iforest", "v1", "v2", "v2+H1", "v2+H2", "v2+H1+H2"]
ALPHAS = (0.01, 0.03, 0.05)
MIN_ROWS = 8                    # 부하 등급을 매기는 최소 기록 길이(= tvt R2_MIN_LEN)
CP_MIN_SIZE = 10
GUIDE_ROWS = (16000, 19000)     # 가이드북 p.27 정상 그래프에서 진동·전류 폭이 줄어 보이는 행 범위
TAIL_FEATS = ["vib_upper_sd", "vib_lower_sd", "cur_amp"]
STATE_ORDER = ["quiet", "busy_low", "busy_mid", "busy_high", "busy_short"]
STATE_KO = {"quiet": "정숙 구간(연속 저부하)", "busy_low": "변동 구간·저부하", "busy_mid": "변동 구간·중부하",
            "busy_high": "변동 구간·고부하", "busy_short": "변동 구간·짧은 기록(n<8)", "all": "전체"}
TAIL_ORDER = ["upper_out", "upper_tail", "body", "lower_out", "short"]
TAIL_KO = {"upper_out": "학습 상위 1% 밖", "upper_tail": "학습 상위 1~5%", "body": "학습 몸통",
           "lower_out": "학습 하위 1% 밖", "short": "짧은 기록(n<8)"}
MODEL_KO = {"v2+H1": "v2+R1", "v2+H2": "v2+R2", "v2+H1+H2": "최종(v2+R1+R2)"}


# ================================================================ 기록 표
def record_table(df: pd.DataFrame) -> pd.DataFrame:
    """기록별 특징(case_table) + 원 행 번호·시각·전류 RMS."""
    ct = case_table(df)
    row = df["Unnamed: 0"] if "Unnamed: 0" in df else pd.Series(df.index, index=df.index)
    ct["row0"] = row.groupby(df.rec).first().to_numpy()
    ct["row1"] = row.groupby(df.rec).last().to_numpy()
    ts = pd.to_datetime(df.TimeStamp).astype("datetime64[ns]")
    ct["ts0"] = ts.groupby(df.rec).first().to_numpy()
    ct["ts1"] = ts.groupby(df.rec).last().to_numpy()
    cur = df["AI2_Current"]
    ct["cur_rms"] = np.sqrt((cur ** 2).groupby(df.rec).mean()).to_numpy()
    ct["cur_mean"] = cur.groupby(df.rec).mean().to_numpy()
    return ct


# ================================================================ 변화점 검출
def optimal_partition(X: np.ndarray, beta: float, min_size: int) -> list[int]:
    """평균·분산 변화(대각 가우스 비용)의 정확 최적 분할. 반환: 구간 끝 인덱스(배타) 목록."""
    N, d = X.shape
    cs = np.vstack([np.zeros(d), np.cumsum(X, 0)])
    cs2 = np.vstack([np.zeros(d), np.cumsum(X ** 2, 0)])
    F = np.full(N + 1, np.inf)
    F[0] = -beta
    last = np.zeros(N + 1, int)
    for j in range(min_size, N + 1):
        cand = np.array([0] + list(range(min_size, j - min_size + 1)))
        cand = cand[np.isfinite(F[cand])]
        m = (j - cand)[:, None].astype(float)
        mu = (cs[j] - cs[cand]) / m
        var = np.maximum((cs2[j] - cs2[cand]) / m - mu ** 2, 1e-3)
        tot = F[cand] + m[:, 0] * np.log(var).sum(1) + beta
        k = int(np.argmin(tot))
        F[j], last[j] = tot[k], cand[k]
    ends, j = [], N
    while j > 0:
        ends.append(j)
        j = last[j]
    return sorted(ends)


def segment_regimes(rt: pd.DataFrame):
    ok = rt[rt.n >= MIN_ROWS].reset_index(drop=True)
    X = np.column_stack([np.log(ok.vib_upper_sd), np.log(ok.vib_lower_sd), np.log(ok.cur_amp)])
    X = (X - X.mean(0)) / X.std(0)
    N, d = X.shape
    base_beta = (2 * d + 1) * np.log(N)

    def bounds(mult, min_size):
        ends = optimal_partition(X, mult * base_beta, min_size)
        starts = [0] + ends[:-1]
        return [(int(ok.rec[s]), int(ok.rec[e - 1])) for s, e in zip(starts, ends)]

    main = bounds(1.0, CP_MIN_SIZE)
    sens = {f"벌점x{m}_최소{s}": bounds(m, s) for m in (0.5, 1.0, 2.0, 4.0) for s in (5, 10, 20)}
    starts = [b[0] for b in main]
    starts[0] = 0
    seg_id = np.searchsorted(np.array(starts), rt.rec.to_numpy(), side="right") - 1   # 짧은 기록도 시간순으로 배정
    return main, sens, seg_id, float(base_beta)


def gmm_load_bounds(x: np.ndarray):
    """전류 진폭 1차원 3성분 가우스 혼합. 기저·고부하 평균 사이에서 사후확률 최대 성분이 바뀌는 두 경계."""
    g = GaussianMixture(3, random_state=0, n_init=10).fit(x[:, None])
    means = np.sort(g.means_.ravel())
    grid = np.linspace(means[0], means[-1], 20001)
    lab = g.predict(grid[:, None])
    b = grid[1:][np.diff(lab) != 0]
    assert len(b) == 2, b
    return [float(v) for v in b], [float(v) for v in means], float(g.bic(x[:, None]))


def classify(rt, ok, b1, b2, prefix):
    load = np.select([~ok, rt.cur_amp < b1, rt.cur_amp < b2], ["short", "low", "mid"], "high")
    return load, np.where(rt.regime == "quiet", "quiet", "busy_" + load)


# ================================================================ 행 표 ↔ 원 기록 번호
def map_rows_to_records(table: pd.DataFrame, rt: pd.DataFrame, rt_ab: pd.DataFrame, split: str) -> dict:
    """tvt 행 표의 rec('valid:normal:k', 'test:abnormal:k')를 원 기록 번호로 바꾼다. 시작 시각과 행 수로 확인."""
    t0 = table.groupby("rec", sort=False).ts.first().astype("int64")
    nrow = table.groupby("rec", sort=False).size()
    by_ts = {"normal": dict(zip(rt.ts0.astype("int64"), rt.rec)), "abnormal": dict(zip(rt_ab.ts0.astype("int64"), rt_ab.rec))}
    n_by = {"normal": dict(zip(rt.rec, rt.n)), "abnormal": dict(zip(rt_ab.rec, rt_ab.n))}
    train_end, valid_end = SPLIT_BOUNDS[split]
    out = {}
    for r, ts in t0.items():
        part, subset, k = r.split(":")
        orig = int(by_ts[subset][int(ts)])
        expect = int(k) + ((train_end if part == "valid" else valid_end) if subset == "normal" else 0)
        assert orig == expect, (split, r, orig, expect)
        assert n_by[subset][orig] == nrow[r], (split, r)
        out[r] = orig
    return out


def partition_of(rec: int, split: str) -> str:
    tr, va = SPLIT_BOUNDS[split]
    return "train" if rec < tr else ("valid" if rec < va else "test")


# ================================================================ 오경보·미탐
def run_predictions(tables, rmaps, cands, meta):
    """모델·α·분할·평가 구간별 실시간 예측을 기록 단위로 합친다(정상: 경보 행, 이상: 미탐 행)."""
    fa_rows, miss_rows = [], []
    for s, t in tables.items():
        r2_ref = meta[s]["r2_ref"]
        for alpha in ALPHAS:
            for name in MODELS:
                for regime in ("valid", "test"):
                    p = predict_rows(t, cands[name], alpha, regime, r2_ref)
                    p = p.assign(alarm=p.alarm_realtime.astype(bool))
                    g = p.groupby(["subset", "rec"]).agg(n_rows=("alarm", "size"), alarms=("alarm", "sum"))
                    for (subset, r), x in g.iterrows():
                        d = dict(split=s, alpha=alpha, model=name, part=regime, rec=rmaps[s][r], n_rows=int(x.n_rows))
                        if subset == "normal":
                            fa_rows.append({**d, "fa_rows": int(x.alarms)})
                        else:
                            miss_rows.append({**d, "miss_rows": int(x.n_rows - x.alarms)})
    return pd.DataFrame(fa_rows), pd.DataFrame(miss_rows)


def summarize(per_rec: pd.DataFrame, key: str) -> pd.DataFrame:
    """key(상태·꼬리 구분) × 모델 × α × 구간 오경보 합계. 'valid+test'와 'all'(전체) 행을 같이 만든다."""
    keys = ["split", "alpha", "model", "part", key]

    def agg(frame):
        g = frame.groupby(keys)
        return pd.DataFrame(dict(n_records=g.rec.nunique(), n_rows=g.n_rows.sum(), fa_rows=g.fa_rows.sum(),
                                 fa_records=g.fa_rows.apply(lambda v: int((v > 0).sum())))).reset_index()
    parts = [agg(per_rec), agg(per_rec.assign(part="valid+test")),
             agg(per_rec.assign(**{key: "all"})), agg(per_rec.assign(part="valid+test", **{key: "all"}))]
    out = pd.concat(parts, ignore_index=True)
    out["fa_row_rate"] = out.fa_rows / out.n_rows
    out["fa_record_rate"] = out.fa_records / out.n_records
    return out


def r1_latch_extra(tables, rmaps, rt, cands, meta):
    """최종(v2+R1+R2)에만 있고 v2+R2에는 없는 정상 경보 = R1이 직전 기록에서 이어받은 경보. 어느 기록 뒤에 붙었는지."""
    state = dict(zip(rt.rec, rt.state))
    out = []
    for s, t in tables.items():
        for alpha in ALPHAS:
            for regime in ("valid", "test"):
                a = predict_rows(t, cands["v2+H1+H2"], alpha, regime, meta[s]["r2_ref"])
                b = predict_rows(t, cands["v2+H2"], alpha, regime, meta[s]["r2_ref"])
                extra = (a.subset == "normal").to_numpy() & a.alarm_realtime.astype(bool).to_numpy() & ~b.alarm_realtime.astype(bool).to_numpy()
                for r, g in a[extra].groupby("rec"):
                    orig = rmaps[s][r]
                    out.append(dict(split=s, alpha=alpha, part=regime, rec=orig, state=state[orig], rows=int(len(g)),
                                    pos=[int(g.pos.min()), int(g.pos.max())], prev_rec=orig - 1, prev_state=state.get(orig - 1)))
    return out


def v2_component_anatomy(tables, rmaps, rt, meta):
    """v2 자기 경보(규칙 전) 정상 행을 성분별로 쪼개고, R2가 보류하는 행(크기 단독 & 파형 정상)을 센다."""
    state = dict(zip(rt.rec, rt.state))
    rows = []
    for s, t in tables.items():
        r2_ref = meta[s]["r2_ref"]
        comps = [c.split("|")[2] for c in t.columns if c.startswith("v2|cp_full|")]
        for alpha in ALPHAS:
            for part in ("valid", "test"):
                mask = ((t.subset == "normal") & (t.part == part)).to_numpy()
                sub = t.loc[mask]
                p = _p(t, mask, part, "v2|p_full", "v2|p_loo")
                alarm = np.isfinite(p) & (p <= alpha)
                act = {}
                for c in comps:
                    cp = _p(t, mask, part, f"v2|cp_full|{c}", f"v2|cp_loo|{c}")
                    act[c] = np.isfinite(cp) & (cp <= alpha)
                mag_only = act["magnitude"] & ~np.any([act[c] for c in comps if c != "magnitude"], axis=0)
                r2 = sub.prefix_r2.to_numpy()
                wave_ok = r2 >= r2_ref
                st = np.array([state[rmaps[s][r]] for r in sub.rec])
                for k in STATE_ORDER:
                    m = alarm & (st == k)
                    rows.append(dict(split=s, alpha=alpha, part=part, state=k, normal_rows=int((st == k).sum()),
                                     v2_alarm_rows=int(m.sum()), magnitude_fired=int((m & act["magnitude"]).sum()),
                                     waveform_fired=int((m & act["waveform"]).sum()), dynamics_fired=int((m & act["dynamics"]).sum()),
                                     magnitude_only=int((m & mag_only).sum()),
                                     magnitude_only_before_8rows=int((m & mag_only & ~np.isfinite(r2)).sum()),
                                     held_by_R2=int((m & mag_only & wave_ok).sum())))
    return pd.DataFrame(rows)


# ================================================================ 학습 vs 평가
def train_percentile(rt: pd.DataFrame, ok: pd.Series, split: str) -> pd.DataFrame:
    """각 기록의 특징이 학습 기록(8행 이상) 분포에서 몇 % 분위인지(학습 값 중 더 작은 비율)."""
    tr = rt[ok & (rt[f"part_{split}"] == "train")]
    return pd.DataFrame({c: [(tr[c].to_numpy() < v).mean() * 100 for v in rt[c]] for c in TAIL_FEATS}, index=rt.index)


def tail_class(pct: pd.DataFrame, ok: pd.Series) -> np.ndarray:
    hi, lo = pct.max(axis=1), pct.min(axis=1)
    return np.select([~ok, hi > 99, hi > 95, lo < 1], ["short", "upper_out", "upper_tail", "lower_out"], "body")


def knn_novelty(rt: pd.DataFrame, ok: pd.Series, split: str, k: int = 5) -> pd.Series:
    """학습 기록 특징 공간(log 3특징, 학습 표준화)에서 k-최근접 평균 거리. 학습 기록은 자기 자신을 뺀다."""
    sub = rt[ok]
    F = np.log(sub[TAIL_FEATS].to_numpy())
    tr = sub[f"part_{split}"].to_numpy() == "train"
    Z = (F - F[tr].mean(0)) / F[tr].std(0)
    D = np.sqrt(((Z[:, None, :] - Z[None, tr, :]) ** 2).sum(-1))
    for j, i in enumerate(np.flatnonzero(tr)):
        D[i, j] = np.inf
    return pd.Series(np.sort(D, 1)[:, :k].mean(1), index=sub.rec.to_numpy())


def low_load_run(sub: pd.DataFrame):
    """저부하(정숙 구간 또는 변동 구간·저부하) 기록이 끊기지 않고 이어진 최장 길이(기록 수, 분)."""
    best_n = best_min = cur = 0
    start = None
    for r in sub.itertuples():
        if r.state in ("quiet", "busy_low"):
            cur += 1
            start = r.ts0 if start is None else start
            best_n = max(best_n, cur)
            best_min = max(best_min, (r.ts1 - start).total_seconds() / 60)
        else:
            cur, start = 0, None
    return int(best_n), round(float(best_min), 2)


# ================================================================ 보조
def med(x):
    return None if len(x) == 0 else round(float(np.median(x)), 4)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    normal, abnormal = load_both(matched=True)
    rt = record_table(normal)
    rt_ab = record_table(abnormal)
    ok = rt.n >= MIN_ROWS

    # ---- 1. 운전 구간·부하 등급
    regimes, sens, seg_id, beta = segment_regimes(rt)
    rt["regime_id"] = seg_id
    seg_stats = []
    for i, _ in enumerate(regimes):
        m = rt.regime_id == i
        mo = m & ok
        seg_stats.append(dict(regime_id=i, first_rec=int(rt.rec[m].min()), last_rec=int(rt.rec[m].max()),
                              row0=int(rt.row0[m].min()), row1=int(rt.row1[m].max()),
                              ts0=str(rt.ts0[m].min()), ts1=str(rt.ts1[m].max()),
                              minutes=round((rt.ts1[m].max() - rt.ts0[m].min()).total_seconds() / 60, 2),
                              n_records=int(m.sum()), n_records_n8=int(mo.sum()),
                              cur_amp_median=med(rt.cur_amp[mo]), cur_amp_iqr=round(float(stats.iqr(rt.cur_amp[mo])), 2),
                              cur_rms_median=med(rt.cur_rms[mo]),
                              vib_upper_sd_median=med(rt.vib_upper_sd[mo]), vib_lower_sd_median=med(rt.vib_lower_sd[mo])))
    quiet_id = int(np.argmin([s["vib_upper_sd_median"] for s in seg_stats]))
    rt["regime"] = np.where(rt.regime_id == quiet_id, "quiet", "busy")

    (b1, b2), gmm_means, gmm_bic = gmm_load_bounds(rt.cur_amp[ok].to_numpy())
    t1, t2 = (float(v) for v in np.quantile(rt.cur_amp[ok], [1 / 3, 2 / 3]))
    rt["load"], rt["state"] = classify(rt, ok, b1, b2, "")
    rt["load_tertile"], rt["state_tertile"] = classify(rt, ok, t1, t2, "")
    for s in SPLIT_BOUNDS:
        rt[f"part_{s}"] = [partition_of(r, s) for r in rt.rec]
    hist_counts, hist_edges = np.histogram(rt.cur_amp[ok], bins=np.arange(100, 300, 5))
    base_share = float(((rt.cur_amp[ok] >= 110) & (rt.cur_amp[ok] < 130)).mean())

    state_profile = []
    for k in STATE_ORDER:
        m = rt.state == k
        state_profile.append(dict(state=k, n_records=int(m.sum()), cur_amp_median=med(rt.cur_amp[m & ok]),
                                  cur_rms_median=med(rt.cur_rms[m & ok]), vib_upper_sd_median=med(rt.vib_upper_sd[m & ok]),
                                  vib_lower_sd_median=med(rt.vib_lower_sd[m & ok])))
    qm, bl = (rt.state == "quiet") & ok, rt.state == "busy_low"
    lowload_compare = dict(
        quiet=dict(n=int(qm.sum()), cur_amp=med(rt.cur_amp[qm]), vib_upper_sd=med(rt.vib_upper_sd[qm]), vib_lower_sd=med(rt.vib_lower_sd[qm])),
        busy_low=dict(n=int(bl.sum()), cur_amp=med(rt.cur_amp[bl]), vib_upper_sd=med(rt.vib_upper_sd[bl]), vib_lower_sd=med(rt.vib_lower_sd[bl])),
        mannwhitney_p_vib_upper=float(stats.mannwhitneyu(rt.vib_upper_sd[qm], rt.vib_upper_sd[bl]).pvalue),
        mannwhitney_p_cur_amp=float(stats.mannwhitneyu(rt.cur_amp[qm], rt.cur_amp[bl]).pvalue))

    # ---- 1b. 가이드북 16,000~19,000행
    gm = (rt.row1 >= GUIDE_ROWS[0]) & (rt.row0 <= GUIDE_ROWS[1])
    g_ok, o_ok = gm & ok, ~gm & ok
    rowidx = normal["Unnamed: 0"].to_numpy() if "Unnamed: 0" in normal else normal.index.to_numpy()
    in_g = (rowidx >= GUIDE_ROWS[0]) & (rowidx <= GUIDE_ROWS[1])

    def row_level(m):
        c, v0, v1 = (normal[k].to_numpy()[m] for k in ("AI2_Current", "AI0_Vibration", "AI1_Vibration"))
        w = lambda a: round(float(np.percentile(a, 99) - np.percentile(a, 1)), 4)  # noqa: E731
        return dict(rows=int(m.sum()), current_p1_p99_width=w(c), vib_upper_p1_p99_width=w(v0), vib_lower_p1_p99_width=w(v1))

    def rec_meds(m):
        return {k: med(rt[k][m]) for k in ("cur_amp", "cur_rms", "vib_upper_sd", "vib_lower_sd")}
    guide = dict(
        rows=list(GUIDE_ROWS), first_rec=int(rt.rec[gm].min()), last_rec=int(rt.rec[gm].max()), n_records=int(gm.sum()),
        ts0=str(rt.ts0[gm].min()), ts1=str(rt.ts1[gm].max()),
        minutes_from_start=[round((rt.ts0[gm].min() - rt.ts0.min()).total_seconds() / 60, 2),
                            round((rt.ts1[gm].max() - rt.ts0.min()).total_seconds() / 60, 2)],
        overlap_with_quiet_regime_records=int((gm & (rt.regime == "quiet")).sum()),
        record_medians=dict(guide=rec_meds(g_ok), rest=rec_meds(o_ok), rest_busy_low=rec_meds(o_ok & (rt.state == "busy_low"))),
        record_cur_amp_iqr=dict(guide=round(float(stats.iqr(rt.cur_amp[g_ok])), 2), rest=round(float(stats.iqr(rt.cur_amp[o_ok])), 2)),
        row_level=dict(guide=row_level(in_g), rest=row_level(~in_g)),
        partition={s: rt.loc[gm, f"part_{s}"].value_counts().to_dict() for s in SPLIT_BOUNDS},
        quiet_partition={s: rt.loc[rt.regime == "quiet", f"part_{s}"].value_counts().to_dict() for s in SPLIT_BOUNDS})

    # ---- 2. 상태별 오경보
    meta = json.loads((TVT_OUT / "tvt_scores_meta.json").read_text(encoding="utf-8"))
    cands = {c[0]: c for c in candidates(meta["A"]["complexity"])}
    tables = {s: pd.read_pickle(TVT_CACHE / f"rows_{s}.pkl") for s in SPLIT_BOUNDS}
    rmaps = {s: map_rows_to_records(t, rt, rt_ab, s) for s, t in tables.items()}
    per_rec, miss = run_predictions(tables, rmaps, cands, meta)
    per_rec = per_rec.merge(rt[["rec", "state", "state_tertile"]], on="rec")
    fa = summarize(per_rec, "state")
    fa_tert = summarize(per_rec.drop(columns="state").rename(columns={"state_tertile": "state"}), "state")
    anat = v2_component_anatomy(tables, rmaps, rt, meta)
    latch = r1_latch_extra(tables, rmaps, rt, cands, meta)

    chk =fa[(fa.alpha == 0.01) & (fa.state == "all") & (fa.part == "test")].set_index(["split", "model"]).fa_rows
    sanity = dict(B_test_v2_fa_rows=int(chk[("B", "v2")]), B_test_final_fa_rows=int(chk[("B", "v2+H1+H2")]),
                  A_test_final_fa_rows=int(chk[("A", "v2+H1+H2")]))
    assert sanity["B_test_v2_fa_rows"] == 3 and sanity["B_test_final_fa_rows"] == 0, sanity   # tvt README와 같아야 함

    fa_list = {}
    for s in SPLIT_BOUNDS:
        for name in MODELS:
            d = per_rec[(per_rec.split == s) & (per_rec.alpha == 0.01) & (per_rec.model == name) & (per_rec.fa_rows > 0)]
            fa_list[f"{s}|{name}"] = [dict(part=r.part, rec=int(r.rec), state=r.state, fa_rows=int(r.fa_rows),
                                           cur_amp=round(float(rt.cur_amp[r.rec]), 1), vib_upper_sd=round(float(rt.vib_upper_sd[r.rec]), 4),
                                           vib_lower_sd=round(float(rt.vib_lower_sd[r.rec]), 4)) for r in d.itertuples()]

    # ---- 3. 학습 vs 평가 분포
    shift, tail_frames = {}, []
    for s in SPLIT_BOUNDS:
        pct = train_percentile(rt, ok, s)
        for c in TAIL_FEATS:
            rt[f"trainpct_{s}_{c}"] = pct[c].round(1)
        rt[f"tail_{s}"] = tail_class(pct, ok)
        nov = knn_novelty(rt, ok, s)
        rt[f"novelty_{s}"] = rt.rec.map(nov)
        tr_nov = nov[rt.set_index("rec").loc[nov.index, f"part_{s}"].to_numpy() == "train"]
        thr99 = float(np.quantile(tr_nov, 0.99))
        rt[f"novel_{s}"] = rt[f"novelty_{s}"] > thr99
        counts = rt.groupby(f"part_{s}").state.value_counts().unstack(fill_value=0).reindex(columns=STATE_ORDER, fill_value=0)
        tails = rt.groupby(f"part_{s}")[f"tail_{s}"].value_counts().unstack(fill_value=0).reindex(columns=TAIL_ORDER, fill_value=0)
        runs = {part: dict(zip(("records", "minutes"), low_load_run(rt[rt[f"part_{s}"] == part]))) for part in ("train", "valid", "test")}
        ks = {}
        for col in TAIL_FEATS:
            a = rt.loc[ok & (rt[f"part_{s}"] == "train"), col]
            for part in ("valid", "test"):
                b = rt.loc[ok & (rt[f"part_{s}"] == part), col]
                res = stats.ks_2samp(a, b)
                ks[f"{col}|train_vs_{part}"] = dict(ks=round(float(res.statistic), 3), p=float(res.pvalue),
                                                     train_median=med(a), eval_median=med(b))
        ev = rt[ok & rt[f"part_{s}"].isin(["valid", "test"])]
        novel = dict(threshold_train_p99=round(thr99, 4), eval_records=int(len(ev)), novel=int(ev[f"novel_{s}"].sum()),
                     by_state={k: f"{int(v.sum())}/{len(v)}" for k, v in ev.groupby("state")[f"novel_{s}"]})
        tail_frames.append(per_rec[per_rec.split == s].merge(rt[["rec", f"tail_{s}"]].rename(columns={f"tail_{s}": "tail"}), on="rec"))
        quiet_tail = ev.loc[ev.state == "quiet", f"tail_{s}"].value_counts().to_dict()
        quiet_tail["short"] = int(((rt.state == "quiet") & ~ok & rt[f"part_{s}"].isin(["valid", "test"])).sum())
        shift[s] = dict(state_counts=counts.to_dict(orient="index"), tail_counts=tails.to_dict(orient="index"),
                        quiet_tail_counts=quiet_tail, low_load_runs=runs, ks=ks, knn_novelty=novel)
    fa_tail = summarize(pd.concat(tail_frames, ignore_index=True), "tail")

    # ---- 4. 이상 기록의 부하 대리변수(전류 RMS)와 부하-진동 관계
    ref = rt[ok]
    state_rms = {k: dict(min=round(float(v.min()), 1), p25=round(float(v.quantile(.25)), 1), median=round(float(v.median()), 1),
                         p75=round(float(v.quantile(.75)), 1), max=round(float(v.max()), 1))
                 for k, v in ref.groupby("state").cur_rms}
    rms_t1, rms_t2 = (float(v) for v in np.quantile(ref.cur_rms, [1 / 3, 2 / 3]))
    resid_fit = {}
    for c in ("vib_lower_sd", "vib_upper_sd"):
        x, y = np.log(ref.cur_rms.to_numpy()), np.log(ref[c].to_numpy())
        b, a = np.polyfit(x, y, 1)
        r = y - (a + b * x)
        resid_fit[c] = dict(intercept=float(a), slope=float(b), resid_sd=float(r.std()),
                            normal_z_p1_p99=[round(float(np.percentile(r / r.std(), 1)), 2), round(float(np.percentile(r / r.std(), 99)), 2)],
                            r2=float(1 - r.var() / y.var()))
    miss1 = miss[miss.alpha == 0.01].pivot_table(index="rec", columns=["split", "model"], values="miss_rows", aggfunc="sum")
    ab_rows = []
    for r in rt_ab.itertuples():
        near = min(state_rms, key=lambda k: abs(state_rms[k]["median"] - r.cur_rms))
        z = {c: (np.log(getattr(r, c)) - (f["intercept"] + f["slope"] * np.log(r.cur_rms))) / f["resid_sd"]
             if getattr(r, c) > 0 else np.nan for c, f in resid_fit.items()}
        ab_rows.append(dict(abn_rec=int(r.rec), part="valid" if r.rec < 10 else "test", n=int(r.n), ts0=str(r.ts0),
                            cur_rms=round(float(r.cur_rms), 1), cur_mean=round(float(r.cur_mean), 1),
                            cur_sine_r2=None if pd.isna(r.cur_sine_r2) else round(float(r.cur_sine_r2), 3),
                            vib_upper_sd=round(float(r.vib_upper_sd), 4), vib_lower_sd=round(float(r.vib_lower_sd), 4),
                            rms_percentile_in_normal=round(float((ref.cur_rms < r.cur_rms).mean() * 100), 1),
                            rms_load_tertile="low" if r.cur_rms < rms_t1 else ("mid" if r.cur_rms < rms_t2 else "high"),
                            nearest_state_by_median=near,
                            z_vib_lower_given_rms=round(float(z["vib_lower_sd"]), 2), z_vib_upper_given_rms=round(float(z["vib_upper_sd"]), 2),
                            **{f"miss1_{s}_{MODEL_KO.get(m, m)}": int(miss1.loc[r.rec, (s, m)]) for s in SPLIT_BOUNDS for m in ("v2", "v2+H1+H2")}))
    ab = pd.DataFrame(ab_rows)
    big = ab.n >= MIN_ROWS
    abn_summary = dict(
        normal_rms_range_n8=[round(float(ref.cur_rms.min()), 1), round(float(ref.cur_rms.max()), 1)],
        normal_rms_tertiles=[round(rms_t1, 1), round(rms_t2, 1)],
        abnormal_rms_median=round(float(ab.cur_rms.median()), 1),
        abnormal_rms_range=[float(ab.cur_rms.min()), float(ab.cur_rms.max())],
        below_normal_min=int((ab.cur_rms < ref.cur_rms.min()).sum()), above_normal_max=int((ab.cur_rms > ref.cur_rms.max()).sum()),
        inside_normal_range=int(((ab.cur_rms >= ref.cur_rms.min()) & (ab.cur_rms <= ref.cur_rms.max())).sum()),
        rms_tertile_counts=ab.rms_load_tertile.value_counts().to_dict(),
        n8_records=int(big.sum()), n8_rms_tertile_counts=ab[big].rms_load_tertile.value_counts().to_dict(),
        vib_upper_sd_median=dict(abnormal=med(ab.vib_upper_sd), normal_quiet=med(ref.vib_upper_sd[ref.state == "quiet"]),
                                 normal_busy=med(ref.vib_upper_sd[ref.state != "quiet"])),
        low_vibration_records=ab[ab.vib_upper_sd < ref.vib_upper_sd.quantile(0.05)].abn_rec.tolist(),
        resid_fit=resid_fit,
        lower_z_beyond_normal_p1_p99=int(((ab.z_vib_lower_given_rms < resid_fit["vib_lower_sd"]["normal_z_p1_p99"][0]) |
                                          (ab.z_vib_lower_given_rms > resid_fit["vib_lower_sd"]["normal_z_p1_p99"][1]))[big].sum()))

    # ---- 저장
    fa_out = pd.concat([fa.assign(scheme="gmm", grouping="state"), fa_tert.assign(scheme="tertile", grouping="state"),
                        fa_tail.rename(columns={"tail": "state"}).assign(scheme="train_tail", grouping="tail")], ignore_index=True)
    fa_out["group_ko"] = fa_out.state.map({**STATE_KO, **TAIL_KO})
    fa_out = fa_out[["scheme", "grouping", "split", "alpha", "part", "state", "group_ko", "model", "n_records", "n_rows",
                     "fa_rows", "fa_records", "fa_row_rate", "fa_record_rate"]].sort_values(["scheme", "split", "alpha", "part", "state", "model"])
    fa_out.to_csv(OUT / "06_operating_regime.csv", index=False, encoding="utf-8-sig")
    wide = per_rec[per_rec.alpha == 0.01].pivot_table(index="rec", columns=["split", "model"], values="fa_rows", aggfunc="sum")
    wide.columns = [f"fa1_{s}_{m}" for s, m in wide.columns]
    keep = ["rec", "row0", "row1", "ts0", "ts1", "n", "cur_amp", "cur_rms", "cur_sine_r2", "vib_upper_sd", "vib_lower_sd",
            "regime", "load", "state", "load_tertile", "part_A", "part_B", "tail_A", "tail_B", "novelty_A", "novelty_B", "novel_A", "novel_B"]
    keep += [c for c in rt.columns if c.startswith("trainpct_")]
    rt[keep].merge(wide, left_on="rec", right_index=True, how="left").to_csv(
        OUT / "06_operating_regime_records.csv", index=False, encoding="utf-8-sig")

    result = dict(
        note="test 채점·잠금 이후 추가한 사후 분석. tvt 잠금 산출물(tvt_selection.json)을 읽기만 하며 모델 선택·문턱·규칙에 영향 없음",
        method=dict(load_proxy="cur_amp(고정 주파수 사인 진폭), 보조 cur_rms", min_rows_for_load=MIN_ROWS,
                    changepoint=dict(algorithm="optimal partitioning, 대각 가우스 평균·분산 비용",
                                     features="표준화한 log 상부 진동 SD, log 하부 진동 SD, log 전류 진폭 (8행 이상 기록)",
                                     penalty=round(beta, 2), penalty_rule="(2d+1)·ln N", min_size=CP_MIN_SIZE),
                    load_bounds_gmm=[round(b1, 1), round(b2, 1)], gmm_means=[round(v, 1) for v in gmm_means], gmm_bic=round(gmm_bic, 1),
                    load_bounds_tertile=[round(t1, 1), round(t2, 1)], base_cluster_110_130_share=round(base_share, 3),
                    cur_amp_histogram=dict(edges=hist_edges.tolist(), counts=hist_counts.tolist())),
        sanity=sanity, regimes=seg_stats, quiet_regime_id=quiet_id, changepoint_sensitivity=sens,
        state_profile=state_profile, lowload_quiet_vs_busy=lowload_compare,
        guidebook_rows_16000_19000=guide,
        v2_alarm_anatomy=anat.to_dict(orient="records"),
        r1_latch_extra_alarms=latch,
        false_alarm_records_alpha1=fa_list,
        train_vs_eval=shift,
        abnormal_load=dict(summary=abn_summary, state_rms_ranges=state_rms, records=ab_rows))
    result["interpretation"] = interpret(result, fa, fa_tail, anat, miss, rt)
    (OUT / "06_operating_regime.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    write_summary(result, fa, fa_tert, fa_tail, anat)
    print(json.dumps(dict(sanity=sanity, regimes=[(s["first_rec"], s["last_rec"]) for s in seg_stats],
                          load_bounds=[round(b1, 1), round(b2, 1)], guide=(guide["first_rec"], guide["last_rec"])), ensure_ascii=False))


# ================================================================ 해석
def interpret(res, fa, fa_tail, anat, miss, rt):
    """해석 문단. 문장 틀은 결과를 보고 썼고, 수치는 실행 결과에서 다시 채운다."""
    vt = fa[fa.part == "valid+test"]
    singles = ["maxz3", "knn5", "mlp_ae5", "lstm20", "iforest", "v1", "v2"]

    def rec_rate(state, model, alpha=0.05):
        d = vt[(vt.state == state) & (vt.model == model) & (vt.alpha == alpha)]
        return int(d.fa_records.sum()), int(d.n_records.sum())

    def rows(model, alpha, split=None, state="all"):
        d = vt[(vt.state == state) & (vt.model == model) & (vt.alpha == alpha)]
        d = d if split is None else d[d.split == split]
        return int(d.fa_rows.sum())

    q = res["regimes"][res["quiet_regime_id"]]
    g = res["guidebook_rows_16000_19000"]
    gm, gr = g["record_medians"]["guide"], g["record_medians"]["rest"]
    quiet_fa = int(vt[vt.state == "quiet"].fa_rows.sum())
    quiet_fa_models = sorted(vt[(vt.state == "quiet") & (vt.fa_rows > 0)].model.unique().tolist())
    s5 = vt[(vt.alpha == 0.05) & vt.model.isin(singles) & (vt.state != "all")].groupby("state").fa_records.sum()
    s5_share = {k: s5.get(k, 0) / s5.sum() for k in STATE_ORDER}
    all5 = {m: rec_rate("all", m) for m in singles}
    hi = {m: rec_rate("busy_high", m) for m in singles + ["v2+H2", "v2+H1+H2"]}
    mid = {m: rec_rate("busy_mid", m) for m in ("mlp_ae5", "lstm20", "knn5", "v2")}
    hi_rate = np.mean([hi[m][0] / hi[m][1] for m in singles])
    all_rate = np.mean([all5[m][0] / all5[m][1] for m in singles])
    tv = res["train_vs_eval"]
    tail = fa_tail[(fa_tail.part == "valid+test") & (fa_tail.model == "v2")]

    def tail_fa(split, t, alpha):
        d = tail[(tail["split"] == split) & (tail["tail"] == t) & (tail["alpha"] == alpha)]
        return f"{int(d.fa_records.sum())}/{int(d.n_records.sum())}"

    an = anat.groupby("alpha")[["v2_alarm_rows", "magnitude_only", "held_by_R2", "magnitude_only_before_8rows",
                                "dynamics_fired", "waveform_fired"]].sum()
    m1 = miss[miss.alpha == 0.01]
    miss_tot = {m: int(m1[m1.model == m].miss_rows.sum()) for m in ("v2", "v2+H2", "v2+H1+H2")}
    ab = {r["abn_rec"]: r for r in res["abnormal_load"]["records"]}
    sm = res["abnormal_load"]["summary"]
    ka, kb = tv["A"]["ks"]["vib_upper_sd|train_vs_test"], tv["B"]["ks"]["vib_upper_sd|train_vs_test"]
    kva, kvb = tv["A"]["ks"]["vib_upper_sd|train_vs_valid"], tv["B"]["ks"]["vib_upper_sd|train_vs_valid"]
    sc = {s: tv[s]["state_counts"]["test"] for s in SPLIT_BOUNDS}
    ntest = {s: sum(sc[s].values()) for s in SPLIT_BOUNDS}
    qlow = {s: tv[s]["quiet_tail_counts"].get("lower_out", 0) for s in SPLIT_BOUNDS}
    lowvib_v2 = {s: sum(ab[k][f"miss1_{s}_v2"] for k in (3, 19, 20)) for s in SPLIT_BOUNDS}
    lowvib_fin = {s: sum(ab[k][f"miss1_{s}_{MODEL_KO['v2+H1+H2']}"] for k in (3, 19, 20)) for s in SPLIT_BOUNDS}
    # α 1% v2 오경보 기록과 그 상부 진동 SD의 학습 분위(분할별)
    v2fa = [(s, d["rec"]) for s in SPLIT_BOUNDS for d in res["false_alarm_records_alpha1"][f"{s}|v2"]]
    v2fa_recs = sorted({r for _, r in v2fa})
    v2fa_pct = [float(rt.loc[rt.rec == r, f"trainpct_{s}_vib_upper_sd"].iloc[0]) for s, r in v2fa]
    lat5 = [d for d in res["r1_latch_extra_alarms"] if d["alpha"] == 0.05]
    lat_txt = ", ".join(sorted({f"{STATE_KO[d['prev_state']].split('·')[-1]} 기록 {d['prev_rec']} → {STATE_KO[d['state']].split('·')[-1]} 기록 {d['rec']} 앞 {d['rows']}행"
                                for d in lat5})) or "없음"
    lat_parts = ", ".join(f"{d['split']} {d['part']}" for d in lat5)

    L = []
    w = L.append
    w("**(1) 가이드북의 설명 없는 구간 = 정숙 구간(연속 저부하 운전).** "
      f"기록 {q['first_rec']}~{q['last_rec']}({q['ts0'][11:16]}~{q['ts1'][11:16]}, 약 {q['minutes']:.0f}분) 동안 전류 진폭이 무부하 수준(약 121)에 고정되고 "
      f"고부하 기록이 사라진다. 기록 중앙값으로 전류 진폭 {gm['cur_amp'] / gr['cur_amp']:.2f}배, 상부 진동 {gm['vib_upper_sd'] / gr['vib_upper_sd']:.2f}배, "
      f"하부 진동 {gm['vib_lower_sd'] / gr['vib_lower_sd']:.2f}배다. 전류 파형은 정상 사인 그대로다. 설비 이상이 아니라 운전 조건 변화(가공 없이 모터만 도는 대기 운전으로 추정)로 본다.")
    w("")
    w("**(2) 이 정상 운전변화는 지금 모델들에 오경보를 일으키지 않았다.** "
      f"정숙 구간(A·B 각 90기록)에서 10개 모델 × α 1·3·5% 오경보는 모두 합쳐 {quiet_fa}행이다"
      + (f"({', '.join(quiet_fa_models)}, α 5%)" if quiet_fa_models else "") + ". "
      "모든 모델이 '학습보다 크거나 모양이 다른 것'을 이상으로 본다. 정숙 구간은 진동이 작고 전류 파형이 정상이어서 이상 점수가 오히려 낮다.")
    w("")
    w("**(3) 오경보는 고부하 정상에서 난다.** "
      f"α 5%에서 단일 모델 7개(maxz3·knn5·mlp_ae5·lstm20·iforest·v1·v2)의 오경보 기록 중 변동 구간 고부하가 {s5_share['busy_high'] * 100:.0f}%, "
      f"중부하가 {s5_share['busy_mid'] * 100:.0f}%, 저부하·정숙 구간이 {(s5_share['busy_low'] + s5_share['quiet']) * 100:.0f}%다. "
      f"고부하 기록 오경보율(α 5%, A·B 합산)은 maxz3 {hi['maxz3'][0]}/{hi['maxz3'][1]}, iforest {hi['iforest'][0]}/{hi['iforest'][1]}, v2 {hi['v2'][0]}/{hi['v2'][1]}이고, "
      f"7개 모델 평균 {hi_rate * 100:.1f}%로 전체 기록 평균 {all_rate * 100:.1f}%의 {hi_rate / all_rate:.1f}배다. "
      "고부하에서는 하부 진동이 부하를 따라 커지고(상관 0.97), 진동이 학습 분포 상위 꼬리에 닿는 기록에서 크기 성분 하나가 문턱을 넘는다. "
      f"α 1% v2 오경보 기록 {len(v2fa_recs)}개({'·'.join(str(r) for r in v2fa_recs)})는 모두 상부 진동 SD가 학습 기록의 "
      f"{min(v2fa_pct):.1f}~{max(v2fa_pct):.1f}% 분위였다. "
      f"딥러닝·거리 모델은 중부하에서도 오경보가 잦다(α 5% 중부하 기록: lstm20 {mid['lstm20'][0]}/{mid['lstm20'][1]}, mlp_ae5 {mid['mlp_ae5'][0]}/{mid['mlp_ae5'][1]}, "
      f"knn5 {mid['knn5'][0]}/{mid['knn5'][1]}; v2 {mid['v2'][0]}/{mid['v2'][1]}).")
    w("")
    w("**(4) R2(교차 확인)는 운전 상태 때문에 생기는 오경보를 대부분 막는다.** "
      f"v2 → v2+R2 오경보 행: α 1% A {rows('v2', .01, 'A')}→{rows('v2+H2', .01, 'A')}, B {rows('v2', .01, 'B')}→{rows('v2+H2', .01, 'B')} / "
      f"α 3% A {rows('v2', .03, 'A')}→{rows('v2+H2', .03, 'A')}, B {rows('v2', .03, 'B')}→{rows('v2+H2', .03, 'B')} / "
      f"α 5% A {rows('v2', .05, 'A')}→{rows('v2+H2', .05, 'A')}, B {rows('v2', .05, 'B')}→{rows('v2+H2', .05, 'B')}. "
      f"고부하 기록 오경보율(α 5%)은 v2 {hi['v2'][0]}/{hi['v2'][1]} → v2+R2 {hi['v2+H2'][0]}/{hi['v2+H2'][1]}이다. "
      f"정상 기록의 v2 경보는 대부분 크기 성분 단독이고(α 5% {an.loc[0.05, 'magnitude_only']}/{an.loc[0.05, 'v2_alarm_rows']}행), 파형 성분은 한 번도 켜지지 않았다. "
      f"R2는 크기 단독 경보 가운데 기록 앞 8행이 지나 파형을 확인할 수 있는 행을 모두 보류했다({an.loc[0.05, 'held_by_R2']}행). "
      f"남는 오경보는 두 종류다. ① 기록 앞 8행 미만의 크기 단독 경보(B valid 303, 모든 α에서 1행) ② 동역학 성분 경보(중부하, α 5%에서 {an.loc[0.05, 'dynamics_fired']}행). "
      f"탐지 손실은 없다(α 1%, 이상 기록 valid+test 미탐 행 A·B 합계: v2 {miss_tot['v2']}, v2+R2 {miss_tot['v2+H2']}).")
    w("")
    w("**(5) R1(사건 지속)은 정상에서 오경보를 다음 기록으로 끌고 갈 수 있다.** "
      "정상 기록에 경보가 2행 이상 나면 다음 기록 첫 행부터 파형이 확인될 때까지(8행) 경보가 이어진다. "
      f"최종과 v2+R2의 오경보 행은 α 1%에서 {rows('v2+H1+H2', .01)}·{rows('v2+H2', .01)}, α 3%에서 {rows('v2+H1+H2', .03)}·{rows('v2+H2', .03)}로 같다(A·B 합). "
      f"α 5%에서는 v2+R2 {rows('v2+H2', .05, 'A')}·{rows('v2+H2', .05, 'B')}행이 최종 {rows('v2+H1+H2', .05, 'A')}·{rows('v2+H1+H2', .05, 'B')}행(A·B)으로 늘었다. "
      f"늘어난 행은 {lat_txt}이다({lat_parts}). 중부하 기록에서 경보 2행이 나자 다음 저부하 기록이 파형 확인 전까지 경보를 이어받았다. "
      "부하가 기록마다 바뀌는 운전에서는 이렇게 '다른 운전 상태의 기록'으로 오경보가 번진다. 운영 문턱을 α 1%로 두는 근거 중 하나다.")
    w("")
    w("**(6) 학습 때 못 본 정상 운전 상태: 정숙 구간은 학습에 없었다.** "
      f"A·B 모두 학습 구간(기록 0~359 / 0~299)에 정숙 구간 기록이 0개다. 학습 구간의 연속 저부하 최장은 {tv['A']['low_load_runs']['train']['records']}기록"
      f"({tv['A']['low_load_runs']['train']['minutes']}분)인데 test에는 {tv['A']['low_load_runs']['test']['records']}·{tv['B']['low_load_runs']['test']['records']}기록"
      f"({tv['A']['low_load_runs']['test']['minutes']}·{tv['B']['low_load_runs']['test']['minutes']}분)이 이어진다(A·B). "
      f"상부 진동 SD의 학습 대비 분포 차이(KS)는 valid {kva['ks']}·{kvb['ks']}, test {ka['ks']}·{kb['ks']}다. "
      f"그 결과 test 정상 가운데 정숙 구간이 A {sc['A'].get('quiet', 0)}/{ntest['A']}, B {sc['B'].get('quiet', 0)}/{ntest['B']}기록이고 "
      f"A test의 고부하 기록은 {sc['A'].get('busy_high', 0)}개뿐이다. A test 오경보 0은 오경보가 잘 나지 않는 운전 상태에서 잰 값이라 낙관적이다. "
      f"고부하 오경보는 B test(고부하 {sc['B'].get('busy_high', 0)}기록)와 valid에서 읽어야 한다.")
    w("")
    w("**(7) '학습 분포 밖'이 위험한 방향은 위쪽이다.** "
      f"v2 오경보 기록(α 1%): 학습 상위 1% 밖 A {tail_fa('A', 'upper_out', .01)}, B {tail_fa('B', 'upper_out', .01)} / 학습 몸통 A {tail_fa('A', 'body', .01)}, B {tail_fa('B', 'body', .01)} / "
      f"학습 하위 1% 밖(대부분 정숙 구간) A {tail_fa('A', 'lower_out', .01)}, B {tail_fa('B', 'lower_out', .01)}. "
      f"α 5%에서는 상위 1% 밖 A {tail_fa('A', 'upper_out', .05)}, B {tail_fa('B', 'upper_out', .05)}, 상위 1~5% A {tail_fa('A', 'upper_tail', .05)}, B {tail_fa('B', 'upper_tail', .05)}, "
      f"몸통 A {tail_fa('A', 'body', .05)}, B {tail_fa('B', 'body', .05)}다. "
      "학습에 없던 정상 상태라도 진동이 작은 쪽이면 지금 모델에는 오경보 위험이 없다. 위험한 것은 학습 때 드물게만 본 '더 센 정상 부하'다. "
      "k-최근접 거리로 본 '새로운 기록'은 A·B 각 3개(모두 정숙 구간)뿐이고 오경보는 0이었다. 기록 하나만 보면 정숙 구간도 학습의 저부하 기록과 닮았기 때문이다.")
    w("")
    w("**(8) 이상 기록은 특정 부하 상태에 몰려 있지 않다.** "
      f"전류 RMS는 {sm['abnormal_rms_range'][0]:.0f}~{sm['abnormal_rms_range'][1]:.0f}로, 정상 범위({sm['normal_rms_range_n8'][0]:.0f}~{sm['normal_rms_range_n8'][1]:.0f}) 안이 {sm['inside_normal_range']}기록, "
      f"아래가 {sm['below_normal_min']}기록, 위가 {sm['above_normal_max']}기록이다. 부하(전류 크기)만으로는 이상을 가를 수 없다. "
      f"다른 것은 부하와 진동의 관계다. 정상에서는 log 하부 진동이 log 전류 RMS를 따라가는데(R² {sm['resid_fit']['vib_lower_sd']['r2']:.2f}), "
      f"8행 이상 이상 기록 {sm['n8_records']}개 중 {sm['lower_z_beyond_normal_p1_p99']}개가 이 관계의 정상 1~99% 범위 밖이다. "
      f"기록 19·20은 전류가 고부하 수준(RMS {ab[19]['cur_rms']}·{ab[20]['cur_rms']})인데 진동은 정숙 구간보다 작다(상부 SD {ab[19]['vib_upper_sd']}·{ab[20]['vib_upper_sd']}, 잔차 z {ab[19]['z_vib_lower_given_rms']}·{ab[20]['z_vib_lower_given_rms']}). "
      f"기록 3은 부하-진동 관계 위에 있지만(z {ab[3]['z_vib_lower_given_rms']}) 전류 사인 R²가 {ab[3]['cur_sine_r2']}로 파형이 깨졌다. "
      f"이 '진동이 작은 이상' 3기록에서 v2 미탐이 A {lowvib_v2['A']}행, B {lowvib_v2['B']}행이었고 최종 모델은 R1(사건 지속)과 파형 확인으로 A {lowvib_fin['A']}행, B {lowvib_fin['B']}행이다.")
    w("")
    w("**(9) 미탐 조건과 오경보 조건은 맞물려 있다.** 진동 크기만 보는 판정은 '진동이 커진 정상(고부하)'을 오경보로, '진동이 작아진 이상(기록 3·19·20)'을 미탐으로 만든다. "
      "미탐을 잡으려고 '진동이 너무 작음'까지 경보로 바꾸면 이번에는 학습에 없던 정숙 구간이 오경보가 된다"
      f"(정숙 구간 중 진동·부하가 학습 하위 1% 밖인 기록 A {qlow['A']}개, B {qlow['B']}개). "
      "둘 다 피하려면 진동을 절대 크기가 아니라 같은 순간의 부하(전류 크기)와 전류 파형에 비춰 판단해야 한다. "
      "R2가 그 방향의 최소 구현이다. 부하 조건부 진동 기준은 다음 단계 후보이며, 이번 잠금 선택에는 넣지 않았다.")
    return L


# ================================================================ 요약 md
def cell(d, m):
    return f"{int(d.fa_rows[m])} / {int(d.fa_records[m])}"


def write_summary(res, fa, fa_tert, fa_tail, anat):
    L = []
    w = L.append
    seg, qid = res["regimes"], res["quiet_regime_id"]
    g = res["guidebook_rows_16000_19000"]
    me = res["method"]
    b1, b2 = me["load_bounds_gmm"]
    sel = lambda f, **kw: f.loc[np.logical_and.reduce([f[k] == v for k, v in kw.items()])]  # noqa: E731

    w("---")
    w("title: 프레스 정상 운전 상태별 오경보 분석 (06_operating_regime)")
    w("created: 2026-10-04")
    w("updated: 2026-10-04")
    w("tags: [contest/k-ai-manufacturing]")
    w("source: code/press/domain/06_operating_regime.py 실행 결과")
    w("status: seed")
    w("---")
    w("")
    w("# 정상 운전 상태와 오경보 발생 조건 (과제 ③)")
    w("")
    w("> **사후 분석이다.** tvt의 valid 선택을 해시로 잠그고 test를 채점한 뒤에 추가했다. 잠금 산출물은 읽기만 했고")
    w("> 모델 선택·문턱·규칙 상수는 바꾸지 않았다. 아래 수치는 선택 근거가 아니라 오경보·미탐이 어떤 조건에서 나는지 설명하는 자료다.")
    w(f"> 재현 확인: B test 오경보 v2 {res['sanity']['B_test_v2_fa_rows']}행 → 최종 {res['sanity']['B_test_final_fa_rows']}행 (tvt 결과와 같음).")
    w("")
    w("## 1. 정상 77분의 운전 상태")
    w("")
    w("- 부하 대리변수: 기록(약 8초)마다 전류 사인 진폭 cur_amp, 보조로 전류 RMS. 진동 수준: 상·하부 진동 SD")
    w(f"- 운전 구간: [log 상부 SD, log 하부 SD, log 전류 진폭]의 평균·분산 변화점을 최적 분할로 찾음(벌점 (2d+1)·ln N = {me['changepoint']['penalty']}, 최소 10기록)")
    sens = res["changepoint_sensitivity"]
    main_b = [[s["first_rec"], s["last_rec"]] for s in seg]
    main_b[0][0] = 0
    same = [k for k, v in sens.items() if [list(x) for x in v] == main_b]
    qs, qe = seg[qid]["first_rec"], seg[qid]["last_rec"]
    keep_q = sum(any(b[0] == qs for b in v) and any(b[1] == qe for b in v) for v in sens.values())
    w(f"  - 벌점 ×0.5~×4, 최소 구간 5~20기록 12조합 중 {len(same)}조합이 같은 3구간을 낸다. 나머지(벌점 ×0.5)는 구간을 더 잘게 나눈다(정숙 구간 안 473~493 / 494~562 등). 그래도 "
      f"정숙 구간 경계({qs} 시작, {qe} 끝)는 {keep_q}/12조합에서 같다 (JSON `changepoint_sensitivity`)")
    w(f"- 부하 등급: 전류 진폭 3성분 가우스 혼합. 성분 평균 {' / '.join(str(v) for v in me['gmm_means'])}, 경계 **{b1} / {b2}**")
    w(f"  - 단순 3분위 경계({me['load_bounds_tertile'][0]} / {me['load_bounds_tertile'][1]})는 기록의 {me['base_cluster_110_130_share'] * 100:.0f}%가 몰린 무부하 군집(110~130)을 반으로 잘라서 민감도로만 썼다 (4.3절)")
    w("")
    w("| 구간 | 기록 | 원 행 | 시각 | 기록 수 | 전류 진폭 중앙값 (IQR) | 상부 진동 SD | 하부 진동 SD |")
    w("|---|---|---|---|---:|---:|---:|---:|")
    for s in seg:
        name = "**정숙 구간**" if s["regime_id"] == qid else "변동 구간"
        w(f"| {name} | {s['first_rec']}~{s['last_rec']} | {s['row0']:,}~{s['row1']:,} | {s['ts0'][11:19]}~{s['ts1'][11:19]} | {s['n_records']} | "
          f"{s['cur_amp_median']:.1f} ({s['cur_amp_iqr']:.1f}) | {s['vib_upper_sd_median']:.4f} | {s['vib_lower_sd_median']:.4f} |")
    w("")
    w("| 상태 | 기록 수 | 전류 진폭 | 전류 RMS | 상부 진동 SD | 하부 진동 SD |")
    w("|---|---:|---:|---:|---:|---:|")
    for p in res["state_profile"]:
        f = lambda v, d: "-" if v is None else f"{v:.{d}f}"  # noqa: E731
        w(f"| {STATE_KO[p['state']]} | {p['n_records']} | {f(p['cur_amp_median'], 1)} | {f(p['cur_rms_median'], 1)} | "
          f"{f(p['vib_upper_sd_median'], 4)} | {f(p['vib_lower_sd_median'], 4)} |")
    w("")
    lc = res["lowload_quiet_vs_busy"]
    w("- 변동 구간에서는 전류 진폭이 기록마다 기저(약 118)·부분(약 174)·고부하(약 244) 사이를 오간다. 하부 진동 SD가 부하를 거의 그대로 따른다(정상 기록 상관 0.97)")
    w(f"- 정숙 구간은 전류 진폭이 약 121에 고정되고(IQR {seg[qid]['cur_amp_iqr']}) 상·하부 진동이 모두 작다. "
      f"변동 구간의 저부하 기록과 비교하면 부하는 비슷하고({lc['quiet']['cur_amp']:.1f} vs {lc['busy_low']['cur_amp']:.1f}) "
      f"상부 진동은 더 작다({lc['quiet']['vib_upper_sd']:.4f} vs {lc['busy_low']['vib_upper_sd']:.4f}, Mann-Whitney p={lc['mannwhitney_p_vib_upper']:.1e})")
    run_tr = {s: res["train_vs_eval"][s]["low_load_runs"]["train"] for s in SPLIT_BOUNDS}
    w(f"- 정숙 구간이 다른 점은 기록 하나의 값보다 **저부하가 약 {seg[qid]['minutes']:.0f}분 끊기지 않고 이어진다**는 데 있다. "
      f"변동 구간에서 저부하 기록이 이어지는 길이는 학습 구간 최장 {run_tr['A']['records']}기록({run_tr['A']['minutes']}분)이다(4.1절)")
    w("")

    # ---- 2. 가이드북
    w("## 2. 가이드북 p.27의 16,000~19,000행")
    w("")
    gm, gr = g["record_medians"]["guide"], g["record_medians"]["rest"]
    w(f"- 원 행 16,000~19,000 = 정상 기록 **{g['first_rec']}~{g['last_rec']}** ({g['n_records']}기록), 시각 **{g['ts0'][11:19]}~{g['ts1'][11:19]}** "
      f"(수집 시작 후 {g['minutes_from_start'][0]:.0f}~{g['minutes_from_start'][1]:.0f}분)")
    w(f"- 이 중 {g['overlap_with_quiet_regime_records']}기록이 변화점으로 찾은 정숙 구간(473~562)과 겹친다. 가이드북이 설명 없이 보여 준 구간은 정숙 구간이다")
    w("")
    w("| 지표 | 16,000~19,000행 | 나머지 | 비 |")
    w("|---|---:|---:|---:|")
    for k, ko in (("cur_amp", "기록 중앙값: 전류 사인 진폭"), ("cur_rms", "기록 중앙값: 전류 RMS"),
                  ("vib_upper_sd", "기록 중앙값: 상부 진동 SD"), ("vib_lower_sd", "기록 중앙값: 하부 진동 SD")):
        w(f"| {ko} | {gm[k]:.4g} | {gr[k]:.4g} | {gm[k] / gr[k]:.2f} |")
    rg, rr = g["row_level"]["guide"], g["row_level"]["rest"]
    for k, ko in (("current_p1_p99_width", "행 값 폭(1~99% 분위): 전류"), ("vib_upper_p1_p99_width", "행 값 폭: 상부 진동"),
                  ("vib_lower_p1_p99_width", "행 값 폭: 하부 진동")):
        w(f"| {ko} | {rg[k]:.4g} | {rr[k]:.4g} | {rg[k] / rr[k]:.2f} |")
    w(f"| 기록 간 전류 진폭 IQR | {g['record_cur_amp_iqr']['guide']} | {g['record_cur_amp_iqr']['rest']} | |")
    w("")
    w("- 가이드북 그래프의 '진동 진폭 감소'는 진동 폭 약 절반, '전류 폭 축소'는 고부하 기록이 사라져 전류 폭이 약 0.6배가 된 것이다")
    w(f"- 분할 위치: 16,000~19,000행은 A·B 모두 **test**에만 있다. 정숙 구간 전체로 보면 A는 valid 끝 7기록(473~479)과 test 83기록, B는 test 90기록")
    w("- **두 분할 모두 학습 구간에 정숙 구간 기록이 하나도 없다**")
    w("")

    # ---- 3. 오경보
    w("## 3. 운전 상태별 오경보")
    w("")
    w("정상 valid+test 기록, 실시간 행 경보. valid 정상 행은 자기 기록을 뺀 LOO p, test 행은 전체 보정 p (evalcore와 같다).")
    w("칸 = **오경보 행 / 오경보 기록**. R1 = 사건 지속(H1), R2 = 교차 확인(H2).")
    w("")
    for alpha in ALPHAS:
        w(f"### 3.{ALPHAS.index(alpha) + 1} α {int(alpha * 100)}%")
        w("")
        w("| 분할 | 상태 | 기록 / 행 | " + " | ".join(MODEL_KO.get(m, m) for m in MODELS) + " |")
        w("|---|---|---|" + "---:|" * len(MODELS))
        for s in SPLIT_BOUNDS:
            for st in STATE_ORDER + ["all"]:
                d = sel(fa, split=s, alpha=alpha, part="valid+test", state=st).set_index("model")
                if d.empty:
                    continue
                lab = f"**{STATE_KO[st]}**" if st == "all" else STATE_KO[st]
                w(f"| {s} | {lab} | {int(d.n_records.iloc[0])} / {int(d.n_rows.iloc[0])} | " + " | ".join(cell(d, m) for m in MODELS) + " |")
        w("")
    # 기록 단위 오경보율 α5%
    w("### 3.4 기록 단위 오경보율 (α 5%, A·B 합산, 오경보 기록 / 기록)")
    w("")
    w("| 상태 | " + " | ".join(MODEL_KO.get(m, m) for m in MODELS) + " |")
    w("|---|" + "---:|" * len(MODELS))
    d5 = sel(fa, alpha=0.05, part="valid+test").groupby(["state", "model"])[["fa_records", "n_records"]].sum()
    for st in STATE_ORDER + ["all"]:
        cells = []
        for m in MODELS:
            x = d5.loc[(st, m)]
            cells.append(f"{100 * x.fa_records / x.n_records:.1f}% ({int(x.fa_records)}/{int(x.n_records)})")
        w(f"| {STATE_KO[st]} | " + " | ".join(cells) + " |")
    w("")
    # valid/test 분리
    w("### 3.5 valid·test 분리 (α 1%, 오경보 행)")
    w("")
    show = ("v2", "v2+H2", "v2+H1+H2", "mlp_ae5", "knn5", "lstm20", "maxz3")
    w("| 분할 | 구간 | 상태 | 기록 | " + " | ".join(MODEL_KO.get(m, m) for m in show) + " |")
    w("|---|---|---|---:|" + "---:|" * len(show))
    for s in SPLIT_BOUNDS:
        for part in ("valid", "test"):
            for st in STATE_ORDER:
                d = sel(fa, split=s, alpha=0.01, part=part, state=st).set_index("model")
                if d.empty:
                    continue
                w(f"| {s} | {part} | {STATE_KO[st]} | {int(d.n_records.iloc[0])} | " + " | ".join(str(int(d.fa_rows[m])) for m in show) + " |")
    w("")
    # v2 성분
    w("### 3.6 v2 자기 경보(규칙 적용 전)의 원인 성분과 R2 보류 (정상 valid+test)")
    w("")
    w("| 분할 | α | 상태 | v2 경보 행 | 크기 | 파형 | 동역학 | 크기 단독 | 그중 기록 앞 8행 미만 | R2 보류 |")
    w("|---|---:|---|---:|---:|---:|---:|---:|---:|---:|")
    a2 = anat.groupby(["split", "alpha", "state"], sort=False)[["v2_alarm_rows", "magnitude_fired", "waveform_fired", "dynamics_fired",
                                                                "magnitude_only", "magnitude_only_before_8rows", "held_by_R2"]].sum().reset_index()
    for r in a2.itertuples():
        if r.v2_alarm_rows:
            w(f"| {r.split} | {int(r.alpha * 100)}% | {STATE_KO[r.state]} | {r.v2_alarm_rows} | {r.magnitude_fired} | {r.waveform_fired} | "
              f"{r.dynamics_fired} | {r.magnitude_only} | {r.magnitude_only_before_8rows} | {r.held_by_R2} |")
    tot = anat.groupby("alpha")[["v2_alarm_rows", "magnitude_only", "held_by_R2", "waveform_fired"]].sum()
    w("")
    w("- 정숙 구간·변동 구간 저부하에서는 어느 α에서도 v2 경보가 없다. 파형 성분이 정상 기록에서 켜진 행은 0이다")
    w("")
    w("### 3.7 R2 효과 요약 (A·B 합, valid+test, 오경보 행: v2 → v2+R2 → 최종)")
    w("")
    w("| 상태 | " + " | ".join(f"α {int(a * 100)}%" for a in ALPHAS) + " |")
    w("|---|" + "---:|" * len(ALPHAS))
    vt = fa[fa.part == "valid+test"]
    for st in STATE_ORDER + ["all"]:
        cells = []
        for a in ALPHAS:
            v = [int(vt[(vt.state == st) & (vt.alpha == a) & (vt.model == m)].fa_rows.sum()) for m in ("v2", "v2+H2", "v2+H1+H2")]
            cells.append(" → ".join(map(str, v)))
        w(f"| {STATE_KO[st]} | " + " | ".join(cells) + " |")
    w("")
    w("### 3.8 α 1% 오경보 기록")
    w("")
    for key in ("A|v2", "B|v2", "A|v2+H1+H2", "B|v2+H1+H2", "A|mlp_ae5", "B|knn5"):
        lst = res["false_alarm_records_alpha1"][key]
        s, m = key.split("|")
        txt = ", ".join(f"{d['part']} {d['rec']}({STATE_KO[d['state']]}, {d['fa_rows']}행, 진폭 {d['cur_amp']}, 상부 SD {d['vib_upper_sd']})" for d in lst) or "없음"
        w(f"- {s} {MODEL_KO.get(m, m)}: {txt}")
    w("")

    # ---- 4. 학습 vs 평가
    w("## 4. 학습 구간과 평가 구간의 운전 상태 분포")
    w("")
    w("### 4.1 상태 구성과 연속 저부하 길이")
    w("")
    w("| 분할 | 구간 | " + " | ".join(STATE_KO[k] for k in STATE_ORDER) + " | 연속 저부하 최장 (기록 / 분) |")
    w("|---|---|" + "---:|" * (len(STATE_ORDER) + 1))
    for s, sh in res["train_vs_eval"].items():
        for part in ("train", "valid", "test"):
            c, run = sh["state_counts"].get(part, {}), sh["low_load_runs"][part]
            w(f"| {s} | {part} | " + " | ".join(str(c.get(k, 0)) for k in STATE_ORDER) + f" | {run['records']} / {run['minutes']} |")
    w("")
    w("| 분할 | 특징 | 학습 vs valid: KS (중앙값 학습→평가) | 학습 vs test: KS (중앙값) |")
    w("|---|---|---|---|")
    for s, sh in res["train_vs_eval"].items():
        for col, ko in (("cur_amp", "전류 진폭"), ("vib_upper_sd", "상부 진동 SD"), ("vib_lower_sd", "하부 진동 SD")):
            a, b = sh["ks"][f"{col}|train_vs_valid"], sh["ks"][f"{col}|train_vs_test"]
            w(f"| {s} | {ko} | {a['ks']} (p={a['p']:.1e}; {a['train_median']:.4g}→{a['eval_median']:.4g}) | "
              f"{b['ks']} (p={b['p']:.1e}; {b['train_median']:.4g}→{b['eval_median']:.4g}) |")
    w("")
    w("### 4.2 학습 분포의 어디에 있는 정상 기록이 오경보를 내는가")
    w("")
    w("평가 기록의 상·하부 진동 SD·전류 진폭 중 가장 극단인 값이 학습 기록 분포의 몇 % 분위인지로 나눴다. 칸 = 오경보 기록 / 기록 (valid+test).")
    w("")
    for alpha in (0.01, 0.05):
        w(f"**α {int(alpha * 100)}%**")
        w("")
        w("| 분할 | 학습 대비 위치 | 기록 | " + " | ".join(MODEL_KO.get(m, m) for m in MODELS) + " |")
        w("|---|---|---:|" + "---:|" * len(MODELS))
        for s in SPLIT_BOUNDS:
            for t in TAIL_ORDER:
                d = sel(fa_tail, split=s, alpha=alpha, part="valid+test", tail=t).set_index("model")
                if d.empty:
                    continue
                w(f"| {s} | {TAIL_KO[t]} | {int(d.n_records.iloc[0])} | " + " | ".join(f"{int(d.fa_records[m])}" for m in MODELS) + " |")
        w("")
    w("| 분할 | 학습 대비 위치 | valid | test | 그중 정숙 구간 |")
    w("|---|---|---:|---:|---:|")
    for s, sh in res["train_vs_eval"].items():
        for t in TAIL_ORDER:
            tc = sh["tail_counts"]
            w(f"| {s} | {TAIL_KO[t]} | {tc.get('valid', {}).get(t, 0)} | {tc.get('test', {}).get(t, 0)} | "
              f"{sh['quiet_tail_counts'].get(t, 0)} |")
    w("")
    for s, sh in res["train_vs_eval"].items():
        kn = sh["knn_novelty"]
        w(f"- {s}: k=5 최근접 거리로 '학습 때 못 본 기록'(학습 99% 분위 {kn['threshold_train_p99']} 초과)은 평가 {kn['eval_records']}기록 중 {kn['novel']}기록 "
          f"({', '.join(f'{STATE_KO[k]} {v}' for k, v in kn['by_state'].items())})")
    w("")
    w("### 4.3 부하 등급 기준 민감도 (단순 3분위, α 5%, A·B 합산 오경보 기록 / 기록)")
    w("")
    w("| 상태(3분위) | " + " | ".join(MODEL_KO.get(m, m) for m in MODELS) + " |")
    w("|---|" + "---:|" * len(MODELS))
    dt = sel(fa_tert, alpha=0.05, part="valid+test").groupby(["state", "model"])[["fa_records", "n_records"]].sum()
    for st in STATE_ORDER:
        if (st, MODELS[0]) in dt.index:
            w(f"| {STATE_KO[st]} | " + " | ".join(f"{int(dt.loc[(st, m)].fa_records)}/{int(dt.loc[(st, m)].n_records)}" for m in MODELS) + " |")
    w("")

    # ---- 5. 이상
    ab = res["abnormal_load"]
    sm = ab["summary"]
    rf = sm["resid_fit"]["vib_lower_sd"]
    w("## 5. 이상 기록의 부하 대리변수(전류 RMS)")
    w("")
    w("이상 기록은 전류 겉보기 주파수가 달라 사인 진폭이 의미가 없으므로 전류 RMS로 본다(정상에서 진폭과 상관 1.00).")
    w("")
    w(f"- 정상(8행 이상) RMS 범위 {sm['normal_rms_range_n8'][0]}~{sm['normal_rms_range_n8'][1]}, 3분위 경계 {sm['normal_rms_tertiles'][0]} / {sm['normal_rms_tertiles'][1]}")
    w(f"- 이상 21기록 RMS 중앙값 {sm['abnormal_rms_median']}, 범위 {sm['abnormal_rms_range'][0]:.1f}~{sm['abnormal_rms_range'][1]:.1f}. "
      f"정상 범위 안 {sm['inside_normal_range']}기록, 정상 최소 미만 {sm['below_normal_min']}, 정상 최대 초과 {sm['above_normal_max']}")
    w(f"- RMS 3분위 배정: 고 {sm['rms_tertile_counts'].get('high', 0)} · 중 {sm['rms_tertile_counts'].get('mid', 0)} · 저 {sm['rms_tertile_counts'].get('low', 0)}"
      f" (8행 이상 {sm['n8_records']}기록: 고 {sm['n8_rms_tertile_counts'].get('high', 0)} · 중 {sm['n8_rms_tertile_counts'].get('mid', 0)} · 저 {sm['n8_rms_tertile_counts'].get('low', 0)})")
    w(f"- 상부 진동 SD 중앙값: 이상 {sm['vib_upper_sd_median']['abnormal']} / 정상 변동 구간 {sm['vib_upper_sd_median']['normal_busy']} / 정상 정숙 구간 {sm['vib_upper_sd_median']['normal_quiet']}. "
      f"정상 상부 SD 5% 분위보다 작은 이상 기록: {sm['low_vibration_records']}")
    w(f"- 정상 부하-진동 관계: log 하부 SD = {rf['intercept']:.2f} + {rf['slope']:.2f}·log RMS (R² {rf['r2']:.2f}, 정상 표준화 잔차 1~99% 분위 {rf['normal_z_p1_p99']}). "
      f"8행 이상 이상 기록 {sm['n8_records']}개 중 {sm['lower_z_beyond_normal_p1_p99']}개가 이 범위 밖")
    w("")
    w("| 정상 상태 | RMS 최소 | 25% | 중앙값 | 75% | 최대 |")
    w("|---|---:|---:|---:|---:|---:|")
    for k in STATE_ORDER:
        v = ab["state_rms_ranges"].get(k)
        if v:
            w(f"| {STATE_KO[k]} | {v['min']} | {v['p25']} | {v['median']} | {v['p75']} | {v['max']} |")
    w("")
    w("| 이상 기록 | 구간 | 행 | 전류 RMS | 정상 내 백분위 | 가까운 정상 상태 | 사인 R² | 상부 SD | 하부 SD | 하부 SD 부하 잔차 z | 미탐 행 v2 A/B | 미탐 행 최종 A/B |")
    w("|---:|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|")
    fin = MODEL_KO["v2+H1+H2"]
    for r in ab["records"]:
        w(f"| {r['abn_rec']} | {r['part']} | {r['n']} | {r['cur_rms']} | {r['rms_percentile_in_normal']} | {STATE_KO[r['nearest_state_by_median']]} | "
          f"{r['cur_sine_r2']} | {r['vib_upper_sd']} | {r['vib_lower_sd']} | {r['z_vib_lower_given_rms']} | "
          f"{r['miss1_A_v2']}/{r['miss1_B_v2']} | {r[f'miss1_A_{fin}']}/{r[f'miss1_B_{fin}']} |")
    w("")

    # ---- 6. 해석
    w("## 6. 해석")
    w("")
    for line in res["interpretation"]:
        w(line)
    w("")
    w("## 7. 한계")
    w("")
    w("- 실제 운전 모드 정보(가동 일지·금형·스트로크 수·설비 상태 코드)가 데이터에 없다. 운전 상태는 전류·진동 신호로 추정했고, '정숙 구간 = 무부하 연속 운전'은 해석이지 확인된 사실이 아니다")
    w("- 정숙 구간은 77분 중 한 번(약 12분)뿐이다. 다른 정상 운전 모드(다른 금형·속도·재료)는 이 데이터에 없어서 그 상태의 오경보는 알 수 없다")
    w("- 오경보 수가 작다(α 1%에서 모델당 0~6행). 상태별 차이는 α 3·5%와 v2 규칙 전 경보, 기록 단위 집계를 함께 보고 판단했다. 상태별 오경보율의 신뢰구간은 넓다")
    w("- 부하 등급과 꼬리 구분은 정상 77분 전체 또는 학습 구간 기록으로 정한 서술용 구분이다. 운전 중 실시간으로 상태를 판정하는 규칙이 아니다")
    w("- 이상은 3분짜리 한 사건(21기록)이다. 이상의 부하 위치·미탐 조건은 이 사건 하나에 대한 것이다")
    w("- test 채점 이후의 사후 분석이며 잠금 선택에 영향이 없다")
    (OUT / "06_operating_regime_summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
