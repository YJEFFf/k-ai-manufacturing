"""프레스 진단 보강 표 2 — 루브릭 사이클2 1회차 평가관 01(D1~D6)·평가관 05(O1(a)·O4).

원본 CSV, 동결 v2 모델(press_guard/artifacts), 커밋된 분석 표만 읽는다. O1(a)만 `train.py --rolling`과 같은 5겹을
GuardModel.fit으로 다시 적합한다(모델은 저장하지 않는다). 모델·문턱·분할은 바꾸지 않고, build_tables.py의 17개 표도 건드리지 않는다.
관계·해석은 모두 기술 통계 또는 가설이며 인과·고장 근거가 아니다. 대회 보고서가 아니다.

    python yejun/analysis/press_evidence/build_diagnostics.py

표를 쓴 뒤 figures.py로 진단 그림 5장을 그린다(그림 속 수치는 표와 자동 대조). 입력·코드·인용 파일·산출물 해시는
diagnostics_manifest.json에 적는다. 결정표의 `파일:행`은 실행 시점에 찾아 넣으므로, 인용한 파일이 바뀌면 다시 실행한다.
가이드북 쪽 번호는 인쇄 쪽 번호다.
"""
from pathlib import Path
import math
import re
import sys
import time

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[1]
REPO = YEJUN.parent
sys.path.insert(0, str(YEJUN / "press_guard"))
sys.path.insert(0, str(HERE))
from model import GuardModel, D, BASE  # noqa: E402
from press.diagnosis import sine_fit, MIN_FIT_LEN  # noqa: E402
import figures  # noqa: E402

ART = YEJUN / "press_guard" / "artifacts"
GUARD = YEJUN / "press_guard"
GUARD_OUT = GUARD / "outputs"
SUPP = YEJUN / "analysis" / "press_supplement"
SUPV = YEJUN / "analysis" / "press_supervised"
V1 = YEJUN / "press_submission"
V1OUT = V1 / "outputs"
SENS = D.SENSORS
VIB = SENS[:2]
SHORT = {"AI0_Vibration": "AI0", "AI1_Vibration": "AI1", "AI2_Current": "AI2"}
PAIRS = [("AI0_Vibration", "AI1_Vibration"), ("AI0_Vibration", "AI2_Current"), ("AI1_Vibration", "AI2_Current")]
LONG = 17                     # 구간 수준 통계의 최소 길이(press_guard/analyze.py의 AMP_MIN_LEN과 같다)
ROLL_ENDS = (180, 240, 300, 360, 420)
SEED_SIM, SEED_PERM = 0, 2
CITED = {}                    # 결정표·교차 참조가 인용한 파일의 해시(manifest)
# 가이드북 표 2·3(인쇄 10~11쪽): 평균, 표준편차, 최솟값, 중앙값, 최댓값
GUIDE_STATS = {"normal": {"AI0_Vibration": (-0.000094, 0.070634, -0.314570, -0.000172, 0.351699),
                          "AI1_Vibration": (-0.000093, 0.118888, -0.366498, -0.009317, 0.399782),
                          "AI2_Current": (1.446209, 122.664494, -271.568330, 1.849830, 273.235000)},
               "abnormal": {"AI0_Vibration": (0.007578, 0.447928, -1.502735, 0.015771, 1.803204),
                            "AI1_Vibration": (-0.008137, 0.241226, -0.751253, 0.002161, 0.509321),
                            "AI2_Current": (57.329741, 153.172619, -399.351170, 53.644187, 538.826050)}}
# 가이드북 표 1(인쇄 63쪽)의 가중치와 가중치 지수(표시값)
GUIDE_WEIGHTS = {"completeness": .6, "uniqueness": .1, "validity": .1, "consistency": .1, "accuracy": np.nan, "integrity": .1}
GUIDE_WEIGHTED = {"normal": dict(completeness=60, uniqueness=9.99, validity=10, consistency=10, accuracy=np.nan, integrity=6.67, total=96.66),
                  "abnormal": dict(completeness=60, uniqueness=10, validity=10, consistency=10, accuracy=np.nan, integrity=10, total=100)}


def rel(path):
    return Path(path).resolve().relative_to(REPO).as_posix()


def cite(path, pattern, regex=False):
    """`저장소 루트 기준 경로:행`. pattern이 처음 나오는 행을 찾는다. 없으면 실패한다(인용이 낡았다는 뜻)."""
    path = Path(path)
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if (re.search(pattern, line) if regex else pattern in line):
            CITED[rel(path)] = D.sha256_file(path)
            return f"{rel(path)}:{i}"
    raise ValueError(f"인용할 행을 찾지 못함: {rel(path)} / {pattern!r}")


def segment_stats(frame, seg):
    """구간별 길이, 진동 SD(ddof=1), 전류 RMS(구간 평균 제거·원값). 원값 기준."""
    g = pd.DataFrame(dict(seg=seg, AI0=frame.AI0_Vibration.to_numpy(float), AI1=frame.AI1_Vibration.to_numpy(float),
                          cur=frame.AI2_Current.to_numpy(float)))
    grp = g.groupby("seg")
    out = grp.agg(n=("AI0", "size"), sd0=("AI0", "std"), sd1=("AI1", "std"))
    out["cur_rms_dm"] = grp.cur.apply(lambda x: float(np.sqrt(np.mean((x - x.mean()) ** 2))))
    out["cur_rms_raw"] = grp.cur.apply(lambda x: float(np.sqrt(np.mean(x ** 2))))
    return out


def train_scale(normal, seg_n):
    """A 학습 구간(0~359)의 진동 평균·SD(ddof=0). 기술 통계용 표준화 척도."""
    tr = normal[seg_n < D.SPLITS["A"][1]]
    return tr[VIB].mean().to_numpy(), tr[VIB].std(ddof=0).to_numpy()


def vib_maxz(frame, mu, sd):
    return np.abs((frame[VIB].to_numpy(float) - mu) / sd).max(axis=1)


def sine_coef(x, f, t=None):
    t = np.arange(len(x)) * D.DT if t is None else t
    A = np.column_stack([np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t), np.ones(len(x))])
    return np.linalg.lstsq(A, x, rcond=None)[0]


def harmonic_r2(x, f, harmonics):
    t = np.arange(len(x)) * D.DT
    cols = [np.ones_like(t)]
    for h in range(1, harmonics + 1):
        cols += [np.sin(2 * np.pi * h * f * t), np.cos(2 * np.pi * h * f * t)]
    A = np.column_stack(cols)
    resid = x - A @ np.linalg.lstsq(A, x, rcond=None)[0]
    return float(1 - (resid ** 2).sum() / ((x - x.mean()) ** 2).sum())


def rayleigh(phases):
    """평균 합성 길이 R̄와 Rayleigh 검정 p(Zar 근사)."""
    n = len(phases)
    r = float(np.abs(np.mean(np.exp(1j * phases))))
    p = math.exp(math.sqrt(1 + 4 * n + 4 * (n ** 2 - (n * r) ** 2)) - (1 + 2 * n))
    return r, min(1.0, p)


def resultant(d):
    return float(np.abs(np.mean(np.exp(1j * np.asarray(d)))))


def waveform_fits(frame, seg):
    """길이 ≥10 구간의 사인 격자 적합(press.diagnosis.sine_fit, 0~5 Hz 0.005 간격)."""
    cur = frame.AI2_Current.to_numpy(float)
    rows = []
    for s in np.unique(seg):
        idx = np.flatnonzero(seg == s)
        if len(idx) >= MIN_FIT_LEN:
            f, r2, _ = sine_fit(cur[idx])
            rows.append(dict(segment=int(s), start_row=int(idx[0]), length=len(idx), f=f, r2=r2))
    return pd.DataFrame(rows).set_index("segment")


def frozen_false_alarms(normal, seg_n, sid="B"):
    """동결 모델 α=1% 정상 평가의 오경보 기록구간(전역 번호)."""
    model = GuardModel.load(ART / f"guard_{sid}.json")
    pred = model.predict(D.split_normal(normal, seg_n, sid)["test"], .01)
    return sorted(int(r) + D.SPLITS[sid][2] for r in pred.loc[pred.alarm.eq(1), "record_id"].unique())


# ---------- D1 센서 간 관계 ----------
def sensor_relations(raw, seg_stats):
    rows = []
    for subset, f in raw.items():
        for transform, x in (("원값", f[SENS]), ("절댓값(가이드북 코드 14)", f[SENS].abs())):
            c = x.corr()
            for a, b in PAIRS:
                rows.append(dict(section="행 상관", level="행", transform=transform, subset=subset, pair=f"{SHORT[a]}~{SHORT[b]}",
                                 method="pearson", value=float(c.loc[a, b]), p_value=np.nan, n=len(f), source="원본"))
    for subset, st in seg_stats.items():
        s = st[st.n >= LONG]
        for xa, xb, name in (("sd0", "cur_rms_dm", "AI0 SD~AI2 RMS"), ("sd1", "cur_rms_dm", "AI1 SD~AI2 RMS"), ("sd0", "sd1", "AI0 SD~AI1 SD")):
            r, p = stats.spearmanr(s[xa], s[xb])
            rows.append(dict(section="구간 수준 결합", level=f"기록구간(길이≥{LONG})", transform="SD·RMS(구간 평균 제거)", subset=subset, pair=name,
                             method="spearman", value=float(r), p_value=float(p), n=len(s), source="원본"))
    for r in pd.read_csv(GUARD_OUT / "coupling_fit_v2.csv").itertuples():
        rows.append(dict(section="교차 참조", level="기록구간(길이≥17·사인 유사, 정상 학습)", transform="log 진동 SD ~ log 전류 진폭",
                         subset=f"정상 학습({r.split})", pair="진동 SD~전류 진폭", method="pearson(log–log)", value=float(r.r), p_value=np.nan,
                         n=int(r.records), source=cite(GUARD_OUT / "coupling_fit_v2.csv", f"{r.split},"),
                         note=f"기울기 {r.slope:.2f}, AI0 {r.r_ai0:.2f}·AI1 {r.r_ai1:.2f}, 60구간 블록별 {r.block_r_min:.2f}~{r.block_r_max:.2f}"))
    for r in pd.read_csv(V1OUT / "load_normalization_meta.csv").itertuples():
        rows.append(dict(section="교차 참조", level="행(trailing-17 온라인 특징)", transform="전류 진폭 대리 ~ 진동", subset=f"A 학습({r.split})",
                         pair="진동~전류 진폭", method="pearson", value=float(r.amp_vib_corr_trainA), p_value=np.nan, n=int(r.fit_rows),
                         source=cite(V1OUT / "load_normalization_meta.csv", f"{r.split},"),
                         note="v1 진폭 정규화 후보의 메타값(모델 후보였고 채택하지 않음)"))
    t = pd.DataFrame(rows)
    get = lambda sec, sub, pair, tr=None: float(t[(t.section == sec) & (t.subset == sub) & (t.pair == pair) & ((t["transform"] == tr) if tr else True)].value.iloc[0])
    notes = []
    for r in t.itertuples():
        if r.section == "행 상관" and r.transform == "원값" and r.pair == "AI0~AI1":
            notes.append(f"상·하부 진동 원값 상관의 부호가 반전된다({get('행 상관', 'normal', 'AI0~AI1', '원값'):+.3f} → {get('행 상관', 'abnormal', 'AI0~AI1', '원값'):+.3f})")
        elif r.section == "행 상관" and r.transform.startswith("절댓값"):
            notes.append("가이드북 30쪽 '정상/이상 모두 양의 상관'은 절댓값 변환 뒤의 값이다. 원값의 부호 반전을 가린다")
        elif r.section == "행 상관":
            notes.append("진동–전류 순시값 상관은 0에 가깝다(위상이 다른 순시값 표본)")
        elif r.section == "구간 수준 결합" and r.subset == "normal":
            notes.append("정상에서 진동 크기와 전류 진폭이 함께 오르내린다. 부하 수준이라는 공통 요인과 일관(가설, 부하 측정 없음)")
        elif r.section == "구간 수준 결합":
            notes.append("이상 14구간에서는 결합이 깨진다. 고장 때문인지 날짜·운전 조건 때문인지 분리할 수 없다")
        else:
            notes.append(r.note)
    t["note"] = notes
    t.attrs["note"] = "기술 통계. 관계를 인과·고장 근거로 쓰지 않는다. 행 상관은 원본 전체 행, 구간 수준은 길이≥17 기록구간"
    return t


def operating_variation(seg_n, t_n, st_n):
    """정상 운전변화: 10분 블록별 전류 RMS(원값)·진동 SD 중앙값의 전체 중앙값 대비 비(길이≥17 구간)."""
    s = st_n[st_n.n >= LONG].copy()
    s["start"] = t_n.groupby(seg_n).min().loc[s.index]
    med = s[["cur_rms_raw", "sd0", "sd1"]].median()
    rows = []
    for b, g in s.groupby(s.start.dt.floor("10min")):
        rows.append(dict(block_start=f"{b:%H:%M}", segments=len(g), first_segment=int(g.index.min()), last_segment=int(g.index.max()),
                         current_rms_median=float(g.cur_rms_raw.median()), current_rms_rel=float(g.cur_rms_raw.median() / med.cur_rms_raw),
                         AI0_sd_rel=float(g.sd0.median() / med.sd0), AI1_sd_rel=float(g.sd1.median() / med.sd1)))
    t = pd.DataFrame(rows)
    t.attrs["note"] = (f"정상 운전변화 정의(기술): 진동 크기와 전류 진폭이 함께 오르내리는 부하 수준 변화. 10분 블록 전류 RMS 중앙값은 전체의 "
                       f"{t.current_rms_rel.min():.2f}~{t.current_rms_rel.max():.2f}배. 블록 간 Spearman(전류~AI0 SD) "
                       f"{stats.spearmanr(t.current_rms_rel, t.AI0_sd_rel)[0]:.2f}, (전류~AI1 SD) {stats.spearmanr(t.current_rms_rel, t.AI1_sd_rel)[0]:.2f}")
    return t


def false_alarm_levels(segs, seg_n, t_n, st_all):
    """B 오경보 구간의 운전 수준: 정상 600구간 중 값이 더 작은 구간의 비율(백분위)."""
    start = t_n.groupby(seg_n).min()
    rows = []
    for s in segs:
        r = st_all.loc[s]
        pct = {k: float((st_all[k] < r[k]).mean()) for k in ("sd0", "sd1", "cur_rms_dm")}
        rows.append(dict(segment=int(s), time=f"{start[s]:%H:%M:%S}", length=int(r.n), AI0_sd=float(r.sd0), AI0_sd_pct=pct["sd0"],
                         AI1_sd=float(r.sd1), AI1_sd_pct=pct["sd1"], current_rms_dm=float(r.cur_rms_dm), current_rms_pct=pct["cur_rms_dm"],
                         AI0_top_share=1 - pct["sd0"], current_top_share=1 - pct["cur_rms_dm"]))
    t = pd.DataFrame(rows)
    t.attrs["note"] = "동결 B, α=1% 정상 평가의 오경보 구간. 백분위 분모는 정상 600구간 전체(길이 1 구간의 SD는 결측으로 '작지 않음'). 운전 강도가 높은 쪽에 있다는 기술이며 원인 판정이 아니다"
    return t


# ---------- D4 생산단위·전류 의미 ----------
def production_unit(raw, seg, t, fits_n, mu, sd):
    n = raw["normal"]
    cur = n.AI2_Current.to_numpy(float)
    rows = []
    at06 = fits_n[np.isclose(fits_n.f, .6)]
    phases = np.array([np.arctan2(*sine_coef(cur[r.start_row:r.start_row + r.length], .6)[[1, 0]]) for r in at06.itertuples()])
    rbar, p = rayleigh(phases)
    rows.append(dict(item="기록 시작 위상(최적 주파수 0.600 Hz 구간)", measure="평균 합성 길이 R̄ / Rayleigh p", value=rbar, value2=p, n=len(at06),
                     reference="균일하면 R̄≈0", interpretation="행정 신호에 맞춰 시작하는 사건 트리거 수집이 아니다(시간 기반 수집과 일관, 가설)", basis="관측"))
    pos = D.segment_positions(seg["normal"])[0]
    z = vib_maxz(n, mu, sd)
    groups = [z[(pos // 5) == b] for b in range(10)]
    prof = [float(g.mean()) for g in groups]
    rows.append(dict(item="기록 안 위치별 진동 크기(5행씩 10구간)", measure="진동 max|z| 평균 최소~최대 / Kruskal–Wallis p",
                     value=min(prof), value2=max(prof), n=len(n), reference=f"p={stats.kruskal(*groups).pvalue:.2f}",
                     interpretation="특정 위치(타격 순간)에 진동이 몰리지 않는다. 기록구간은 행정 단위가 아니다(가설)", basis="관측"))
    full = fits_n[(fits_n.length == 50) & np.isclose(fits_n.f, .6)]
    segs50 = [cur[r.start_row:r.start_row + 50] for r in full.itertuples()]
    gain = np.array([harmonic_r2(x, .6, 3) - harmonic_r2(x, .6, 1) for x in segs50])
    rows.append(dict(item="2·3차 고조파가 더 설명하는 분산(50행·0.600 Hz 구간)", measure="R² 증가 중앙값 / 95백분위", value=float(np.median(gain)),
                     value2=float(np.quantile(gain, .95)), n=len(full), reference="행정 파형이면 고조파가 크다",
                     interpretation="전류는 거의 순수 사인이다. 행정(가압·복귀)을 가르는 파형 구조가 보이지 않는다", basis="관측"))
    ratio = np.array([np.hypot(*sine_coef(x[25:], .6)[:2]) / np.hypot(*sine_coef(x[:25], .6)[:2]) for x in segs50])
    rows.append(dict(item="앞 25행 대비 뒤 25행 진폭 비(같은 구간)", measure="중앙값 / 5~95백분위", value=float(np.median(ratio)),
                     value2=f"{np.quantile(ratio, .05):.3f}~{np.quantile(ratio, .95):.3f}", n=len(full), reference="변조가 없으면 1",
                     interpretation="5초 안 진폭 변조가 없다. 제품·스트로크 단위는 열이 없을 뿐 아니라 신호로도 복원할 수 없다", basis="관측"))
    exact, total, spans = 0, 0, []
    for k, f in raw.items():
        dt = t[k].diff().dt.total_seconds().to_numpy()[1:]
        within = seg[k][1:] == seg[k][:-1]
        exact += int((np.abs(dt[within] - D.DT) <= D.GAP_TOL).sum()); total += int(within.sum())
        lens = pd.Series(seg[k]).value_counts()
        for s in lens[lens == 50].index:
            tt = t[k][seg[k] == s]
            spans.append((tt.iloc[-1] - tt.iloc[0]).total_seconds())
    spans = np.asarray(spans)
    rows.append(dict(item="기록 안 표본 간격", measure="정확히 0.100초인 간격 / 기록 안 간격 전체", value=exact, value2=total, n=total,
                     reference="앨리어싱이 60 Hz에서 나오려면 실제 간격 0.101초 또는 0.099초", interpretation="기록 안 간격은 모두 명목값과 같다", basis="관측"))
    rows.append(dict(item="50행 기록의 시간 폭", measure="최소 / 최대(초)", value=float(spans.min()), value2=float(spans.max()), n=len(spans),
                     reference="실제 간격이 0.101·0.099초면 49간격에 ±49 ms가 쌓인다", interpretation="±49 ms 누적이 없다", basis="관측"))
    rows.append(dict(item="0.6 Hz 해석 조건(앨리어싱)", measure="필요 간격(초)", value=6.06 / 60, value2=5.94 / 60, n=np.nan,
                     reference="또는 간격 0.100초에서 원 신호 59.4·60.6 Hz",
                     interpretation="60 Hz 순시값의 앨리어싱이라면 시각이 명목값(실측이 아님)이거나 원 신호가 59.4·60.6 Hz다(가설, 검증 불가)", basis="가설"))
    rows.append(dict(item="0.6 Hz 해석 조건(물리 주기)", measure="분당 주기 수", value=.6 * 60, value2=np.nan, n=np.nan,
                     reference="phase_continuity.csv: 기록 사이 위상이 이어지지 않는다",
                     interpretation="0.6 Hz가 정확한 시각의 연속 기계 주기(분당 36회)라면 공백을 건너 위상이 이어져야 한다. 관측과 맞지 않는다(가설 약화, 확정 아님)",
                     basis="가설"))
    tab = pd.DataFrame(rows)
    tab["n"] = tab["n"].astype("Int64")
    tab.attrs["note"] = "기록구간은 사건 트리거·스트로크 단위가 아니고, 전류는 거의 순수 0.6 Hz 사인이다. 모든 해석은 가설이며 물리 단위·원인을 단정하지 않는다"
    return tab


def variable_expected_signals(raw, obs):
    """변수별 관측 성질과 가이드북 7쪽(기어 마모 → 진동·소음 증가, 출력 유압 약화 → 불량) 기반 기대 신호(가설)."""
    o = obs.set_index(["file", "sensor"])
    rows = []
    for c in SENS:
        on = o.loc[("normal", c)]
        if c == "AI2_Current":
            observed = f"정상 음수 {on.share_negative:.1%}, 기록 안 lag-1 {on.lag1_within:.3f}(순수 0.6 Hz 사인 {math.cos(2 * math.pi * .06):.3f}), 거의 순수 0.6 Hz 사인"
            expected = "출력 유압이 약해지면 같은 가압에 드는 전류의 진폭·수준·파형이 바뀔 수 있다(가설. 가이드북 7쪽은 전류를 직접 언급하지 않는다)"
            comp, fm = "파형(사인 1−R²)·예측 오차(AR(2))·크기(AI2 |z|)", "FM4, FM5, FM6"
        else:
            observed = f"정상 음수 {on.share_negative:.1%}, 평균 {on['mean']:.1e}, 기록 안 lag-1 {on.lag1_within:.3f}: 10 Hz 순시값 표본(RMS 아님)"
            expected = "기어 마모 시 진동·소음이 심해진다(가이드북 7쪽) → 진동 SD·첨두 증가. 결함 주파수(수십 Hz~kHz)는 5 Hz 위라 접혀 들어와 광대역 에너지로만 보인다(가설)"
            comp, fm = "크기(max|z|)", "FM1, FM2, FM3, FM4"
        rows.append(dict(column=c, guidebook_meaning={"AI0_Vibration": "유압펌프 상부진동", "AI1_Vibration": "유압펌프 하부진동", "AI2_Current": "유압펌프 전류"}[c],
                         observed_property=observed, expected_signal_hypothesis=expected, v2_component=comp, failure_modes=fm,
                         dictionary=cite(HERE / "variable_dictionary.csv", f"{c},")))
    t = pd.DataFrame(rows)
    t.attrs["note"] = "variable_dictionary.csv(R2)를 바꾸지 않고 연결한다. 기대 신호는 가설이며 이 자료로 고장 기전을 확인하지 않았다"
    return t


# ---------- D5 라벨 일관성 ----------
def abnormal_segments(raw, seg, t, fits, mu, sd, st_a):
    n, a = raw["normal"], raw["abnormal"]
    vmax_n = pd.Series(vib_maxz(n, mu, sd)).groupby(seg["normal"]).max()
    thr = float(vmax_n[vmax_n.index >= D.SPLITS["A"][1]].quantile(.99))
    r2_min = float(fits["normal"].r2.min())
    vmax_a = pd.Series(vib_maxz(a, mu, sd)).groupby(seg["abnormal"]).max()
    start = t["abnormal"].groupby(seg["abnormal"]).min()
    rows = []
    for s in range(len(vmax_a)):
        r2 = float(fits["abnormal"].r2.get(s, np.nan))
        vo, ro = bool(vmax_a[s] > thr), bool(np.isfinite(r2) and r2 < r2_min)
        kind = "진동·파형 모두" if vo and ro else ("진동만" if vo else ("파형만" if ro else "없음"))
        rows.append(dict(segment=s, start=f"{start[s]:%H:%M:%S.%f}"[:-3], length=int(st_a.loc[s, "n"]), vib_segmax_z=float(vmax_a[s]),
                         vib_threshold_q99=thr, vib_out=vo, r2=r2, r2_normal_min=r2_min, r2_out=ro,
                         fittable=bool(np.isfinite(r2)), outside_normal=kind, AI0_sd=float(st_a.loc[s, "sd0"]), current_rms_dm=float(st_a.loc[s, "cur_rms_dm"])))
    tab = pd.DataFrame(rows)
    long = st_a[st_a.n >= LONG]
    trend = {k: stats.spearmanr(long.index, long[k]) for k in ("sd0", "cur_rms_dm")}
    summary = pd.DataFrame([
        dict(item="정상 범위 밖 특징이 1개 이상인 이상 구간", value=int((tab.vib_out | tab.r2_out).sum()), n=len(tab), note="정상처럼 보이는 구간 0"),
        dict(item=f"진동 구간 최대 |z| > 정상 비학습(A 평가 쪽 360~599) q99 {thr:.2f}", value=int(tab.vib_out.sum()), n=len(tab), note="A 학습 평균·SD(ddof=0) 표준화"),
        dict(item=f"전류 사인 R² < 정상 최소 {r2_min:.4f}", value=int(tab.r2_out.sum()), n=int(tab.fittable.sum()), note="길이 ≥10 구간만 적합"),
        dict(item="진동 정상 범위(파형으로만 벗어남)", value=int((~tab.vib_out & tab.r2_out).sum()), n=len(tab),
             note=f"구간 {', '.join(map(str, tab[~tab.vib_out].segment))}, 진동 max|z| {tab[~tab.vib_out].vib_segmax_z.min():.2f}~{tab[~tab.vib_out].vib_segmax_z.max():.2f}"),
        dict(item="파형 판정 불가(길이 <10, 진동으로만 벗어남)", value=int((~tab.fittable).sum()), n=len(tab),
             note=f"구간 {', '.join(map(str, tab[~tab.fittable].segment))}, 길이 {tab[~tab.fittable].length.min()}~{tab[~tab.fittable].length.max()}행"),
        dict(item="구간 순서 ~ AI0 SD(Spearman)", value=float(trend["sd0"][0]), n=len(long), note=f"p={trend['sd0'][1]:.2f}, 길이≥17 구간"),
        dict(item="구간 순서 ~ 전류 RMS(Spearman)", value=float(trend["cur_rms_dm"][0]), n=len(long), note=f"p={trend['cur_rms_dm'][1]:.2f}. 3분 안 진행·발생 시점 정보가 없다"),
    ])
    tab.attrs["note"] = "라벨 일관성 점검(성능 주장 아님). 진동으로만 벗어나는 짧은 구간과 파형으로만 벗어나는 저진동 구간이 서로 다르다(R18 성분 상보성을 자료 쪽에서 뒷받침)"
    return tab, summary


# ---------- D6 관행 기준·가중 품질 지수·가이드북 표 ----------
def outlier_rules(raw, seg_n):
    n, a = raw["normal"], raw["abnormal"]
    tr = seg_n < D.SPLITS["A"][1]
    rows, union = [], {"iqr": (np.zeros((~tr).sum(), bool), np.zeros(len(a), bool)), "sigma3": (np.zeros((~tr).sum(), bool), np.zeros(len(a), bool))}
    for c in SENS:
        x, y = n[c].to_numpy(float), a[c].to_numpy(float)
        q1, q3 = np.percentile(x[tr], [25, 75])
        mu, sdv = x[tr].mean(), x[tr].std(ddof=1)
        for rule, lo, hi in (("1.5×IQR", q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)), ("3σ", mu - 3 * sdv, mu + 3 * sdv)):
            fn, fa = ((x < lo) | (x > hi))[~tr], (y < lo) | (y > hi)
            if c != "AI2_Current":
                key = "iqr" if rule == "1.5×IQR" else "sigma3"
                union[key][0][:] |= fn; union[key][1][:] |= fa
            rows.append(dict(rule=rule, sensor=c, lower=lo, upper=hi, normal_nontrain_rows=int(fn.sum()), normal_nontrain_total=int((~tr).sum()),
                             normal_nontrain_share=float(fn.mean()), abnormal_rows=int(fa.sum()), abnormal_total=len(a), abnormal_share=float(fa.mean())))
    for key, name in (("iqr", "1.5×IQR"), ("sigma3", "3σ")):
        fn, fa = union[key]
        rows.append(dict(rule=name, sensor="진동 두 센서 중 하나라도", lower=np.nan, upper=np.nan, normal_nontrain_rows=int(fn.sum()),
                         normal_nontrain_total=len(fn), normal_nontrain_share=float(fn.mean()), abnormal_rows=int(fa.sum()), abnormal_total=len(a),
                         abnormal_share=float(fa.mean())))
    t = pd.DataFrame(rows)
    u = t[(t.rule == "1.5×IQR") & (t.sensor.str.startswith("진동"))].iloc[0]
    t.attrs["note"] = (f"기준은 A 학습 구간(0~359). 관행 1.5×IQR로 진동 이상치를 지우면 이상 행 {u.abnormal_rows}/{u.abnormal_total}"
                       f"({u.abnormal_share:.0%})와 정상 비학습 {u.normal_nontrain_rows}행({u.normal_nontrain_share:.1%})이 사라진다. 결정: 이상치를 제거하지 않는다(outliers.csv, R3)")
    return t


def quality_weighted(raw):
    """가이드북 품질 지수(인쇄 61~62쪽 산식, build_tables.quality_index와 같은 계산)와 63쪽 가중 합계."""
    days = {"normal": ("2022-07-12", "2022-07-13"), "abnormal": ("2022-07-17", "2022-07-18")}
    rows = []
    for k, f in raw.items():
        body = f.drop(columns=[f.columns[0]])
        vc = body.value_counts()
        tt = pd.to_datetime(f.TimeStamp, errors="coerce")
        q = dict(completeness=(1 - body.isna().sum().sum() / body.size) * 100,
                 uniqueness=round((len(vc) - int((vc > 1).sum())) / len(vc) * 100, 2),        # 가이드북 코드 7: 소수 2자리
                 validity=((tt >= days[k][0]) & (tt < days[k][1])).mean() * 100,
                 consistency=(f[SENS].apply(pd.to_numeric, errors="coerce").notna().all(axis=1) & tt.notna()).mean() * 100, accuracy=np.nan)
        q["integrity"] = (1 - sum(v < 100 for v in (q["uniqueness"], q["validity"], q["consistency"])) / 3) * 100
        total = 0.0
        for name, value in q.items():
            w = GUIDE_WEIGHTS[name]
            wi = value * w if np.isfinite(w) else np.nan
            total += 0 if np.isnan(wi) else wi
            rows.append(dict(file=k, index=name, quality_index=value, weight=w, weighted_index=wi, guidebook_weighted_index=GUIDE_WEIGHTED[k][name]))
        rows.append(dict(file=k, index="total", quality_index=np.nan, weight=1.0, weighted_index=total, guidebook_weighted_index=GUIDE_WEIGHTED[k]["total"]))
    t = pd.DataFrame(rows)
    tot = t[t["index"].eq("total")].set_index("file").weighted_index
    t.attrs["note"] = (f"가이드북 63쪽 표 1·2. 가중치 완전성 60%, 유일성·유효성·일관성·무결성 각 10%, 정확성 제외. 정상 합계 재계산 {tot['normal']:.3f}은 "
                       f"가이드북 표시값 96.66과 같다(가중치 지수를 소수 2자리로 적은 표시 차이: 유일성 9.999→9.99, 무결성 6.667→6.67). 이상 {tot['abnormal']:.2f}")
    return t


def guidebook_stats(raw):
    rows = []
    for k, f in raw.items():
        for c in SENS:
            x = f[c].to_numpy(float)
            mine = (x.mean(), x.std(ddof=1), x.min(), np.median(x), x.max())
            for name, m, g in zip(("mean", "std", "min", "median", "max"), mine, GUIDE_STATS[k][c]):
                rows.append(dict(file=k, sensor=c, stat=name, recomputed=float(m), guidebook=g, abs_diff=abs(round(float(m), 6) - g),
                                 match=bool(abs(round(float(m), 6) - g) <= 1.5e-6)))
    t = pd.DataFrame(rows)
    t.attrs["note"] = f"가이드북 표 2·3(인쇄 10~11쪽) {len(t)}개 값을 원본으로 재계산했다. 소수 6자리 반올림 비교, 일치 {int(t.match.sum())}/{len(t)}"
    return t


# ---------- O1(a) 시간순 5겹 보정 곡선 ----------
def rolling_calibration_curve(normal, seg_n):
    frozen = {sid: GuardModel.load(ART / f"guard_{sid}.json") for sid in D.SPLITS}
    folds = []
    for end in ROLL_ENDS:
        tr = normal[seg_n < end].reset_index(drop=True)
        ca = normal[(seg_n >= end) & (seg_n < end + 120)].reset_index(drop=True)
        te = normal[(seg_n >= end + 120) & (seg_n < end + 180)].reset_index(drop=True)
        m = GuardModel.fit(tr, ca, split=f"train_to_{end}")
        minp = m.predict(te, .01).groupby("record_id").p_value.min().fillna(1.0).to_numpy()
        same = [sid for sid, fm in frozen.items() if np.array_equal(fm.cal, m.cal) and np.array_equal(fm.mean, m.mean)
                and np.array_equal(fm.scale, m.scale) and np.array_equal(fm.coef, m.coef)]
        folds.append(dict(fold=f"normal_{end + 120}_{end + 179}", train_end=end, n_cal=len(m.cal), minp=minp, same=same[0] if same else ""))
    ref = pd.read_csv(GUARD_OUT / "rolling.csv")
    for f in folds:     # train.py --rolling 결과와 같은 적합인지 확인(α 1·3·5%)
        for alpha in (.01, .03, .05):
            r = ref[ref.split.eq(f["fold"]) & ref.model.eq("guard_v2") & np.isclose(ref.alpha, alpha)].iloc[0]
            assert int((f["minp"] <= alpha).sum()) == int(r.normal_notified_segments), (f["fold"], alpha)
    rng = np.random.default_rng(SEED_SIM)
    rows = []
    for k in range(1, 13):
        per = []
        for f in folds:
            n_cal, m_eval = f["n_cal"], len(f["minp"])
            x = int((f["minp"] <= k / (n_cal + 1) + 1e-12).sum())
            lo, hi = stats.betabinom(m_eval, k, n_cal + 1 - k).ppf([.05, .95])
            per.append(x)
            rows.append(dict(fold=f["fold"], train_end=f["train_end"], same_as_frozen=f["same"], n_cal=n_cal, eval_records=m_eval, k=k,
                             nominal=k / (n_cal + 1), alerted=x, realized=x / m_eval, pi90_low=int(lo), pi90_high=int(hi), within_pi90=bool(lo <= x <= hi),
                             above_pi90=bool(x > hi), below_pi90=bool(x < lo), interval="Beta-Binomial(60, k, 121−k) 5~95%"))
        far = rng.beta(k, 121 - k, size=(200_000, len(folds)))
        sims = rng.binomial(60, far).sum(axis=1)
        lo, hi = np.percentile(sims, [5, 95])
        x = sum(per)
        rows.append(dict(fold="합산(5겹)", train_end=np.nan, same_as_frozen="", n_cal=120, eval_records=60 * len(folds), k=k, nominal=k / 121,
                         alerted=x, realized=x / (60 * len(folds)), pi90_low=int(lo), pi90_high=int(hi), within_pi90=bool(lo <= x <= hi),
                         above_pi90=bool(x > hi), below_pi90=bool(x < lo), interval="겹마다 Beta(k, 121−k)·Binomial(60) 독립 모의 20만 회 5~95%(보정 구간이 60구간씩 겹쳐 실제보다 약간 좁다)"))
    t = pd.DataFrame(rows)
    same = {f["fold"]: f["same"] for f in folds if f["same"]}
    t.attrs["note"] = (f"train.py --rolling과 같은 5겹(학습 0~end−1, 보정 직전 120구간, 평가 다음 60구간)을 다시 적합했다. 기록 최소 p ≤ k/121. "
                       f"같은 날·교환가능성 가정 아래의 점검이며 새 날짜의 보장이 아니다. "
                       + ", ".join(f"{k} 폴드는 동결 {v}와 학습·보정이 같아 보정값이 비트 단위로 같다" for k, v in same.items())
                       + f". 동결 모델과 독립인 폴드는 {len(folds) - len(same)}개다. 겹별 90% 구간 위로 벗어난 경우 "
                       f"{int(t[t.fold.ne('합산(5겹)')].above_pi90.sum())}건, 아래로 벗어난 경우 {int(t[t.fold.ne('합산(5겹)')].below_pi90.sum())}건"
                       f"({', '.join(sorted(set(t[t.below_pi90 & t.fold.ne('합산(5겹)')].fold)))}: 가장 조용한 블록에서 경보가 적은 쪽)")
    return t, folds


# ---------- O4 제조지식 ----------
def observability(raw, seg):
    rows = []
    for k, f in raw.items():
        same = np.r_[False, seg[k][1:] == seg[k][:-1]]
        for c in SENS:
            x = f[c].to_numpy(float)
            rows.append(dict(file=k, sensor=c, mean=float(x.mean()), sd=float(x.std()), share_negative=float((x < 0).mean()),
                             lag1_within=float(np.corrcoef(x[1:][same[1:]], x[:-1][same[1:]])[0, 1]),
                             interpretation=("10 Hz 순시값 표본(부호 대칭·평균 0, 이웃 표본 상관 낮음). RMS·포락선이 아니다. 5 Hz 위 성분은 접혀 들어온다"
                                             if c != "AI2_Current" else "0.6 Hz 사인형 순시값(lag-1이 순수 0.6 Hz 사인과 비슷)")))
    rows.append(dict(file="기준", sensor="순수 0.6 Hz 사인(10 Hz 표본)", mean=0.0, sd=np.nan, share_negative=.5, lag1_within=math.cos(2 * math.pi * .06),
                     interpretation="비교 기준"))
    t = pd.DataFrame(rows)
    t.attrs["note"] = ("10 Hz 순시값 표본이라 나이퀴스트 5 Hz 위(베어링 결함·펌프 맥동·캐비테이션의 수십 Hz~kHz)는 식별할 수 없다. "
                       "크기 성분은 광대역 에너지 변화만 본다. 정상 원본 기준(lag-1은 같은 기록구간 안 이웃 행)")
    return t


def phase_continuity(normal, seg_n, t_n):
    tsec = (t_n - t_n.iloc[0]).dt.total_seconds().to_numpy()
    cur = normal.AI2_Current.to_numpy(float)
    ids = np.unique(seg_n)
    rows_of = {s: np.flatnonzero(seg_n == s) for s in ids}

    def phase(idx, f):
        out = np.empty(len(idx))
        for i, ix in enumerate(idx):
            tt = tsec[ix]
            A = np.column_stack([np.cos(2 * np.pi * f * tt), np.sin(2 * np.pi * f * tt), np.ones(len(ix))])
            c = np.linalg.lstsq(A, cur[ix], rcond=None)[0]
            out[i] = np.arctan2(c[1], c[0])
        return out

    ends = np.array([rows_of[s][-20:] for s in ids[:-1] if len(rows_of[s]) >= 20 and len(rows_of[s + 1]) >= 20])
    begins = np.array([rows_of[s + 1][:20] for s in ids[:-1] if len(rows_of[s]) >= 20 and len(rows_of[s + 1]) >= 20])
    gaps = tsec[begins[:, 0]] - tsec[ends[:, -1]]
    ph_b, ph_e = phase(begins, .6), phase(ends, .6)
    d = ph_b - ph_e
    rng = np.random.default_rng(SEED_PERM)
    null = np.array([resultant(rng.permutation(ph_b) - ph_e) for _ in range(200)])
    short = gaps < np.median(gaps)
    sub_null = {}
    for name, m in (("짧은 공백 절반", short), ("긴 공백 절반", ~short)):
        sub_null[name] = np.array([resultant(rng.permutation(ph_b[m]) - ph_e[m]) for _ in range(200)])
    scan = [(float(f), resultant(phase(begins, f) - phase(ends, f))) for f in np.arange(.55, .65 + 1e-12, .0025)]
    f_best, r_best = max(scan, key=lambda z: z[1])
    long_recs = [rows_of[s] for s in ids if len(rows_of[s]) >= 50]
    ctrl = phase(np.array([ix[-20:] for ix in long_recs]), .6) - phase(np.array([ix[:20] for ix in long_recs]), .6)
    starts = []
    for s in ids:
        ix = rows_of[s]
        if len(ix) >= 20:
            c = sine_coef(cur[ix[:20]], .6, t=tsec[ix[:20]] - tsec[ix[0]])
            starts.append(np.arctan2(c[1], c[0]))
    r_start, p_start = rayleigh(np.asarray(starts))
    rows = [
        dict(test="양성 대조: 같은 기록 안 처음 20관측 대 마지막 20관측(50행 기록)", pairs=len(long_recs), gap_s="1.1(기록 안)", R=resultant(ctrl),
             null_mean=np.nan, null_q95=np.nan, frequency_hz=.6, interpretation="기록 안에서는 0.6 Hz 위상이 이어진다(방법 점검)"),
        dict(test="이웃 기록 사이: 앞 기록 마지막 20관측 대 다음 기록 처음 20관측", pairs=len(d), gap_s=f"{gaps.min():.2f}~{gaps.max():.2f}(중앙 {np.median(gaps):.2f})",
             R=resultant(d), null_mean=float(null.mean()), null_q95=float(np.quantile(null, .95)), frequency_hz=.6,
             interpretation="공백을 건너면 위상이 이어지지 않는다(섞은 귀무 95% 안)"),
    ]
    for name, m in (("짧은 공백 절반", short), ("긴 공백 절반", ~short)):
        rows.append(dict(test=f"이웃 기록 사이({name})", pairs=int(m.sum()), gap_s=f"{gaps[m].min():.2f}~{gaps[m].max():.2f}", R=resultant(d[m]),
                         null_mean=float(sub_null[name].mean()), null_q95=float(np.quantile(sub_null[name], .95)), frequency_hz=.6,
                         interpretation="공백 길이와 무관하게 귀무 범위"))
    rows.append(dict(test="이웃 기록 사이 주파수 탐색(0.55~0.65 Hz, 0.0025 간격) 최대", pairs=len(d), gap_s="", R=r_best, null_mean=np.nan,
                     null_q95=float(np.quantile(null, .95)), frequency_hz=f_best, interpretation="어느 주파수로도 위상 연속이 복원되지 않는다"))
    rows.append(dict(test="기록 시작 위상(기록 안 상대 시각, 처음 20관측)", pairs=len(starts), gap_s="", R=r_start, null_mean=np.nan,
                     null_q95=np.nan, frequency_hz=.6, interpretation=f"시작 위상이 고르게 흩어진다(Rayleigh p={p_start:.2f})"))
    t = pd.DataFrame(rows)
    t.attrs["note"] = ("정확한 시각의 연속 기계 주기(0.6 Hz ≈ 분당 36회)라면 3초 안팎 공백을 넘어서도 위상이 이어져야 한다. 관측은 이 가설과 맞지 않고, "
                       "교류 전류 순시값의 앨리어싱(또는 기록 사이 시각 부정확)과 맞는다(확정 아님). 설계 연결: 창·AR을 기록구간 안에서만 쓰고, "
                       "위치 0·1을 직전 기록의 위상으로 채울 수 없다. 섞은 귀무는 다음 기록 위상의 순서를 섞은 200회(시드 2)")
    return t


def e1_rate(e1, family, level, t0=10):
    """E1 v2(α=1%, 계단형) 2초 안 탐지율 A·B와 그 행의 인용."""
    x = e1[(e1.model == "guard_v2") & np.isclose(e1.alpha, .01) & (e1["shape"] == "step") & (e1.t0 == t0)
           & (e1.family == family) & np.isclose(e1.level, level)].set_index("split").detect_rate_2s
    where = [cite(SUPP / "e1_summary.csv", f"{sid},{family},{float(level)},step,{t0},guard_v2,0.01,").rsplit(":", 1)[-1] for sid in ("A", "B")]
    return f"A {x['A']:.1%}·B {x['B']:.1%}(e1_summary.csv:{'·'.join(where)})"


def failure_mode_map():
    e1 = pd.read_csv(SUPP / "e1_summary.csv")
    e2 = pd.read_csv(SUPP / "e2_uci_metrics.csv")
    e2_local = e2[e2["mode"] == "local_normal_reference"].auroc
    floor = pd.read_csv(SUPP / "e1_detection_floor.csv").set_index(["family", "model"]).floor
    src_e2 = cite(SUPP / "e2_uci_metrics.csv", "local_normal_reference,3,v2_4ch")
    rows = [
        dict(fm_id="FM1", failure_mode="베어링 손상",
             expected_change_10hz="결함 주파수(수십 Hz~kHz)가 5 Hz 위라 순시값 표본에 접혀 들어와 진동 SD·첨두가 커지는 광대역 변화로만 보인다",
             reacting_component="크기(진동 max|z|)", e1_proxy="진동 잡음(vib_noise)",
             evidence=f"E1 v2 2초 탐지 s=2 {e1_rate(e1, 'vib_noise', 2)}, s=4 {e1_rate(e1, 'vib_noise', 4)}, s=1 {e1_rate(e1, 'vib_noise', 1)}(하한 {floor[('vib_noise', 'guard_v2')]:g}σ)",
             hypothesis_general_engineering="베어링 결함은 결함 주파수와 그 고조파의 진동을 키운다",
             confirmed_in_this_data="이상 21구간 중 18구간이 진동 max|z| > 정상 q99(abnormal_segments.csv). 원인이 베어링인지는 알 수 없다",
             not_identifiable="결함 주파수·포락선 스펙트럼(10 Hz 표본으로 불가)"),
        dict(fm_id="FM2", failure_mode="캐비테이션·흡입 공기 혼입",
             expected_change_10hz="고주파 소음·진동(접힘으로 진동 분산 증가)과 토출 압력 맥동에 따른 전류 불규칙",
             reacting_component="크기, 예측 오차(AR(2) 잔차)·파형", e1_proxy="진동 잡음 + 전류 잡음(cur_noise)",
             evidence=f"E1 전류 잡음 0.1σ {e1_rate(e1, 'cur_noise', .1)}, 0.05σ {e1_rate(e1, 'cur_noise', .05)}(하한 {floor[('cur_noise', 'guard_v2')]:g}σ)",
             hypothesis_general_engineering="흡입측 압력 저하로 기포가 생기고 붕괴하며 광대역 소음과 압력 맥동을 만든다",
             confirmed_in_this_data="이상 구간의 전류 사인 R² 중앙 0.451(정상 0.996, class_differences.csv). 캐비테이션 때문인지는 알 수 없다",
             not_identifiable="캐비테이션 특유의 kHz 대역, 흡입 압력"),
        dict(fm_id="FM3", failure_mode="체결·정렬(커플링) 불량",
             expected_change_10hz="회전 1×·2× 성분(수십 Hz)이 접혀 진동 크기가 커지고, 상·하부 진동의 관계가 바뀔 수 있다",
             reacting_component="크기(상·하부 관계는 v2가 쓰지 않는다)", e1_proxy="진동 잡음",
             evidence=f"E1 진동 잡음 s=4 {e1_rate(e1, 'vib_noise', 4)}, s=2 {e1_rate(e1, 'vib_noise', 2)}",
             hypothesis_general_engineering="축 정렬 불량·풀림은 회전 주파수 배수의 진동과 방향별 진동 차이를 만든다",
             confirmed_in_this_data="이상에서 상·하부 원값 상관이 +0.37 → −0.38로 반전(sensor_relations.csv). 날짜 교락으로 원인 분리 불가",
             not_identifiable="회전수·위상 차 스펙트럼, 축 방향 진동"),
        dict(fm_id="FM4", failure_mode="내부 누설·기어 마모(출력 유압 저하, 가이드북 7쪽)",
             expected_change_10hz="진동·소음 증가(가이드북 7쪽)와 같은 가압에 드는 전류의 진폭·수준 변화. 누설은 느린 수준 변화일 수 있다",
             reacting_component="크기(진동), 예측 오차는 전류 수준이 바뀌는 순간만", e1_proxy="전류 오프셋(cur_offset)·전류 배율(cur_gain)",
             evidence=(f"E1 오프셋 0.4×진폭 {e1_rate(e1, 'cur_offset', .4)}(하한 {floor[('cur_offset', 'guard_v2')]:g}×진폭), "
                       f"기록 시작부터 있는 오프셋 0.8 {e1_rate(e1, 'cur_offset', .8, t0=0)}, 배율 1.15 {e1_rate(e1, 'cur_gain', 1.15)}, 1.5 {e1_rate(e1, 'cur_gain', 1.5)}. "
                       f"E2 UCI 펌프 내부 누설에 v2 구조 AUROC {e2_local.min():.2f}~{e2_local.max():.2f}(실패, {src_e2})"),
             hypothesis_general_engineering="기어 마모·내부 누설은 체적 효율을 낮춰 출력 유압을 떨어뜨린다(가이드북 7쪽: 진동·소음 증가, 출력 유압 약화 → 불량)",
             confirmed_in_this_data="v2는 느린 누설(E2)과 기록 시작부터 있는 수준 변화·진폭만 커지는 변화(E1)에 약하다",
             not_identifiable="출력 유압·유량(측정 열 없음)"),
        dict(fm_id="FM5", failure_mode="전기·전원(전압 강하·상 불평형·모터)",
             expected_change_10hz="전류 파형 왜곡(고조파), 진폭·수준 변화. 0.6 Hz가 60 Hz 앨리어싱이라면(가설) 파형 성분이 왜곡에 반응",
             reacting_component="파형(사인 1−R²)·예측 오차", e1_proxy="전류 잡음·전류 배율",
             evidence=f"E1 전류 잡음 0.1σ {e1_rate(e1, 'cur_noise', .1)}, 배율 0.7 {e1_rate(e1, 'cur_gain', .7)}, 1.5 {e1_rate(e1, 'cur_gain', 1.5)}",
             hypothesis_general_engineering="공급 전압·상 불평형·권선 이상은 전류 진폭·고조파를 바꾼다",
             confirmed_in_this_data="정상 전류는 거의 순수 사인(고조파 추가 설명 중앙 0.16%, production_unit_evidence.csv)이라 파형 왜곡에 민감한 기준이 된다",
             not_identifiable="전압·상별 전류·역률(측정 열 없음)"),
        dict(fm_id="FM6", failure_mode="계측·배선(센서 단선·접촉 불량·수집 이상)",
             expected_change_10hz="값 고정·스파이크·비유한 값·시각 오류, 저장 형식 변화",
             reacting_component="입력 검증(status → '수집 상태 확인'), 크기(스파이크)", e1_proxy="없음(직접 주입하지 않음)",
             evidence="진단: 결측·비유한 값·시각 오류 0행. 저장 형식(진동 자릿수 6/8, 전류 격자 0.18%/100%)이 파일마다 다르다(class_differences.csv)",
             hypothesis_general_engineering="배선·접지 불량은 잡음·단속 신호를, 수집 설정 변화는 형식 변화를 만든다",
             confirmed_in_this_data="정상·이상 파일의 저장 형식 차이를 matched 양자화로 제거했다. 계측 경로가 달랐을 가능성은 배제할 수 없다",
             not_identifiable="센서 교정 이력·수집 장비 설정"),
    ]
    t = pd.DataFrame(rows)
    t["basis_note"] = "hypothesis_general_engineering은 일반 공학 지식에 기반한 가설, confirmed_in_this_data는 이 자료로 확인한 것. 펌프 물리 모델로 검증하지 않았다"
    t.attrs["note"] = "E1은 같은 날 정상 기록에 더한 인공 신호(α=1%, 계단형, t0=10행, 2초 안 탐지율)이며 실제 고장 모양의 보장이 아니다. E2는 다른 설비(UCI) 누설"
    return t


# ---------- D3 v2 기준 진단 → 전처리 → 검증 결정표 ----------
def guidebook_protocol(normal, seg_n, t_n, rel_ab):
    pos = D.segment_positions(seg_n)[0]
    idx = np.arange(len(normal) - 121)
    tt = t_n.to_numpy()
    lead = (tt[idx + 120] - tt[idx + 19]) / np.timedelta64(1, "s")
    raw_n = rel_ab[(rel_ab.section == "행 상관") & (rel_ab.pair == "AI0~AI1")].set_index(["subset", "transform"]).value
    rows = [
        dict(item="행 15000 분할(가이드북 코드 19, 30쪽)", value=f"구간 {seg_n[15000]}의 {pos[15000] + 1}번째 행({t_n[15000]:%H:%M:%S.%f}"[:-3] + ")",
             guidebook="X_normal[:15000] 학습, 나머지 평가", ours="기록구간 경계에서 분할(A 0~359/360~479/480~599, B 0~299/300~419/420~599)"),
        dict(item="20행 입력창이 기록 공백을 건너는 비율(코드 21, 32쪽)", value=f"{((seg_n[idx + 19] - seg_n[idx]) > 0).mean():.1%}",
             guidebook="파일 전체를 1행씩 미는 20행 창", ours="창·AR은 기록구간 안에서만 만든다"),
        dict(item="라벨 행(창 끝 +101행)이 다른 기록구간에 있는 비율", value=f"{((seg_n[idx + 120] - seg_n[idx + 19]) > 0).mean():.1%}",
             guidebook="'과거 20개(2초)로 100시점(10초) 이후 탐지'", ours="라벨 행을 쓰지 않는다(정상만 학습·보정)"),
        dict(item="실제 선행시간(마지막 입력 행 → 라벨 행)", value=f"중앙 {np.median(lead):.1f}초(5~95% {np.quantile(lead, .05):.1f}~{np.quantile(lead, .95):.1f}초)",
             guidebook="명목 10초(101행)", ours="선행시간을 주장하지 않는다(시작 시각을 아는 주입 E1으로 지연만 잰다)"),
        dict(item="절댓값 변환(코드 14, 27쪽)", value=f"상·하부 원값 상관 {raw_n[('normal', '원값')]:+.3f} → {raw_n[('abnormal', '원값')]:+.3f}, 절댓값 {raw_n[('normal', '절댓값(가이드북 코드 14)')]:+.3f} → {raw_n[('abnormal', '절댓값(가이드북 코드 14)')]:+.3f}",
             guidebook="모든 센서에 절댓값('진폭'으로 변환) 후 상관 확인(30쪽 '양의 상관')", ours="원값을 쓰고 크기 성분에서만 |z|를 쓴다. 부호 반전을 기술 통계로 남긴다"),
        dict(item="정규화(코드 20, 31쪽)", value="학습 구간만 적합", guidebook="MinMaxScaler를 학습에만 fit", ours="같은 원칙(표준화 평균·SD를 학습 구간에서만)"),
    ]
    t = pd.DataFrame(rows)
    t.attrs["note"] = "가이드북 프로토콜과 기록 구조의 충돌을 정량한 것. 가이드북 LSTM-AE 재현은 press_submission/outputs/lstm_guidebook_reproduction.json"
    return t


def decision_table(raw, seg, t, st, fb, ctx):
    n, a = raw["normal"], raw["abnormal"]
    E = HERE
    gaps = pd.read_csv(E / "gaps.csv").set_index("file")
    cov = {k: len(f) * D.DT / (t[k].max() - t[k].min()).total_seconds() for k, f in raw.items()}
    missing = {k: int(f[SENS].isna().sum().sum() + (~np.isfinite(f[SENS].to_numpy(float))).sum()) for k, f in raw.items()}
    abl = pd.read_csv(GUARD_OUT / "ablation_v2.csv")
    def fn(model, sid):
        return int(abl[abl.model.eq(model) & abl.criterion.eq("conformal") & np.isclose(abl.alpha, .01) & abl.split_id.eq(sid)].fn.iloc[0])
    sup = pd.read_csv(SUPV / "random_rows.csv")
    fmt = sup[sup.features.eq("decimal_digits(AI0)")].iloc[0]
    grp = pd.read_csv(SUPV / "grouped_records.csv")
    g21 = grp[grp.cv.eq("21fold") & grp.threshold.eq("conformal") & grp.features.eq("window_plus_v2") & grp.model.eq("logistic")].set_index("split").f1
    floor = pd.read_csv(SUPP / "e1_detection_floor.csv").set_index(["family", "model"]).floor
    e2 = pd.read_csv(SUPP / "e2_uci_metrics.csv"); e2l = e2[e2["mode"] == "local_normal_reference"].auroc
    e3 = pd.read_csv(SUPP / "e3_stability.csv")
    imb = pd.read_csv(E / "imbalance.csv").set_index("scope")
    out_rules = ctx["outlier_rules"]
    iqr = out_rules[(out_rules.rule == "1.5×IQR") & out_rules.sensor.str.startswith("진동")].iloc[0]
    roll, gp = ctx["rolling_curve"], ctx["guidebook_protocol"].set_index("item").value
    pooled = roll[roll.fold.eq("합산(5겹)")].set_index("k")
    same = roll[roll.same_as_frozen.ne("") & roll.k.eq(1)][["fold", "same_as_frozen"]].values.tolist()
    indep = sorted(set(roll[roll.same_as_frozen.eq("") & roll.fold.ne("합산(5겹)")].fold))
    B_fa = ", ".join(map(str, fb))
    rows = [
        ("진단", "단위 계층",
         f"행 0.1초 → 기록구간(정상 {int(gaps.loc['normal', 'segments'])}·이상 {int(gaps.loc['abnormal', 'segments'])}, 50행 구간 {int(gaps.loc['normal', 'segments_len50'])}·{int(gaps.loc['abnormal', 'segments_len50'])}개, 50행 초과 0) → 알림 단위(기록 안 50행 블록) → 평가 단위(행 F1·기록구간 탐지·정상 알림 구간). {cite(E / 'gaps.csv', 'normal,')}; {cite(GUARD / 'model.py', 'def alert_units')}",
         "창·AR·보정·알림을 기록구간 안에서만 계산한다. 주 지표는 행 F1과 구간 단위 탐지·정상 알림을 함께 쓴다",
         f"가이드북처럼 파일 전체를 연속으로 보면 20행 창의 {gp['20행 입력창이 기록 공백을 건너는 비율(코드 21, 32쪽)']}가 공백을 건넌다",
         "기록구간은 수집 묶음이다. 스트로크·제품·독립 고장 단위가 아니다(production_unit_evidence.csv)"),
        ("진단", "입력 열",
         f"TimeStamp·센서 3열만 입력. 행 번호·Equipment_state·파일명은 제외. {cite(E / 'variable_dictionary.csv', 'Equipment_state,')}; {cite(V1OUT / 'label_bypass.csv', 'timestamps_shifted_5_days')}",
         "라벨·날짜·시각은 입력이 아니다(시각은 기록구간 경계에만 쓴다)",
         "시각·날짜 특징을 넣으면 정상 화요일 00:00~01:17 대 이상 일요일 10:51~10:54의 교락을 그대로 배운다",
         "교락 자체는 제거할 수 없다(dayshift §6)"),
        ("진단", "기록구간 규칙",
         f"|Δt−0.1초|>1e-6이면 새 구간. 허용오차 1e-9~0.099초에서 600/21구간 불변. {cite(E / 'segment_rule_tolerance.csv', 'normal,0.099,')}",
         "현행 규칙 유지", "허용오차를 0.1초 이상으로 넓히면 중복 시각 경계 1개만 사라진다", "0.1초 초과 1.5초 미만 간격이 없어서 규칙이 안정적이다"),
        ("전처리", "무효 행 처리",
         f"시각 파싱 불가·비유한 값 행은 삭제하지 않고 status로 표시하고 앞뒤를 구간 경계로 둔다. 대회 자료에는 0행. {cite(V1 / 'README.md', '잘못된 행')}",
         "현장 입력 대비 규칙으로 유지. 해당 행은 '수집 상태 확인'", "삭제하면 구간이 이어 붙어 가짜 창이 생긴다", f"대회 자료에는 없는 경로라 단위 테스트로만 확인({cite(GUARD / 'test_guard.py', 'def test_invalid_reset_and_no_false_normal')})"),
        ("전처리", "중복 유지",
         f"00:43:33.196 완전 중복 1쌍. B 보정 최대 점수 순위 119·120/120. {cite(E / 'duplicate_rows.csv', '00:43:33.196')}",
         "삭제하지 않는다", "삭제해도 α=1·3·5% 문턱(보정 최대 1·3·6위)은 같다", "없음"),
        ("진단", "결측·시간 적용률",
         f"값 결측·비유한 값 정상 {missing['normal']}·이상 {missing['abnormal']}. 시간 적용률(기록 시간/경과 시간) 정상 {cov['normal']:.1%}·이상 {cov['abnormal']:.1%}. {cite(E / 'gaps.csv', 'abnormal,')}",
         "보간·채움을 하지 않는다. 공백은 구간 경계로만 쓴다", "공백을 보간하면 관측하지 않은 신호를 만든다", "공백 동안의 설비 상태는 관측되지 않는다"),
        ("전처리", "이상치 비제거",
         f"이상 205/600행이 A 학습 범위 밖. 관행 1.5×IQR 적용 시 이상 {iqr.abnormal_rows}/{iqr.abnormal_total}행({iqr.abnormal_share:.0%})·정상 비학습 {iqr.normal_nontrain_rows}행({iqr.normal_nontrain_share:.1%}) 삭제. {cite(E / 'outliers.csv', '어느 센서든')}; {cite(E / 'outlier_rules.csv', '진동 두 센서 중 하나라도')}",
         "이상치를 제거하지 않는다(이상 신호 자체)", f"IQR 제거는 이상 신호의 {iqr.abnormal_share:.0%}를 지운다", "정상 극값도 그대로 학습 꼬리에 들어간다"),
        ("전처리", "matched 양자화",
         f"형식 규칙 판별력 raw AUROC 0.999 → matched 0.500. 소수 자릿수 하나로 무작위 행 분할 F1 {fmt.f1:.3f}. {cite(V1OUT / 'diagnosis.md', '| either | matched |')}; {cite(SUPV / 'random_rows.csv', 'decimal_digits(AI0)')}",
         "진동 1e-4, 전류 격자 1.1920929로 두 클래스에 같은 반올림", "raw를 쓰면 저장 형식 지름길(F1 0.99)이 생긴다", "형식 밖 클래스 차이(R4)는 남는다"),
        ("전처리", "표준화(학습만)",
         f"평균·척도·AR 계수·꼬리는 정상 학습 구간에서만 적합. {cite(GUARD / 'model.py', 'def fit')}",
         "학습 구간 적합 값을 보정·평가·현장에 그대로 쓴다", "전체 자료 표준화는 평가 누설", "가이드북 코드 20(31쪽)도 학습만 fit(차이 없음)"),
        ("전처리", "사인 창 6→8",
         f"위치 0~6은 6관측, 7부터 8관측 창. 파형 성분 제거 시 미탐 A {fn('v2', 'A')}→{fn('no_waveform', 'A')}·B {fn('v2', 'B')}→{fn('no_waveform', 'B')}, 조기 전환 제거 시 A {fn('no_early_switch', 'A')}·B {fn('no_early_switch', 'B')}. {cite(GUARD / 'model.py', 'np.where(pos < 7')}; {cite(GUARD_OUT / 'ablation_v2.csv', 'no_early_switch,recording_segments,conformal,0.01')}",
         "기록구간 안 창만 쓴다", f"가이드북 20행 창은 {gp['20행 입력창이 기록 공백을 건너는 비율(코드 21, 32쪽)']}가 공백을 건넌다", "창 길이는 이상 자료를 본 뒤 고른 탐색적 설계다"),
        ("전처리", "AR(2) 3관측",
         f"예측 오차 성분 제거 시 미탐 A {fn('v2', 'A')}→{fn('no_dynamics', 'A')}·B {fn('v2', 'B')}→{fn('no_dynamics', 'B')}. AR(2) 특성근 0.6064 Hz(사인과 같은 진동자). {cite(E / 'ar2_oscillator.csv', 'A,')}; {cite(GUARD_OUT / 'ablation_v2.csv', 'no_dynamics,recording_segments,conformal,0.01')}",
         "기록 안 3관측(현재+직전 2개)으로 예측 오차를 만든다", "기록 공백을 건너는 AR은 위상이 이어지지 않아 쓸 수 없다(phase_continuity.csv)", "위치 0·1에는 예측 오차가 없다(구조적 미탐)"),
        ("진단", "불균형 대응",
         f"이상 행 2.9%, 평가셋 이상 비율 A {imb.loc['A 평가', 'abnormal_row_share']:.1%}·B {imb.loc['B 평가', 'abnormal_row_share']:.1%}, 전부 양성 F1 {imb.loc['A 평가', 'all_positive_row_f1']:.3f}·{imb.loc['B 평가', 'all_positive_row_f1']:.3f}. {cite(E / 'imbalance.csv', 'A 평가')}",
         "정상 자료만으로 학습·보정. 구간 단위 지표를 함께 쓰고 A·B F1을 같은 잣대로 비교하지 않는다",
         f"라벨 지도학습은 같은 입력·문턱이면 대회 F1이 같고(21겹 창+v2 로지스틱 A {g21['A']:.3f}·B {g21['B']:.3f}) 진동형 주입 전이에 약하다. {cite(SUPV / 'grouped_records.csv', 'A,window_plus_v2,logistic,21fold,conformal')}",
         "이상 21구간은 한 에피소드라 불균형 처방의 일반화를 검증할 수 없다"),
        ("검증", "A/B·시간순 분할",
         f"A 360/480, B 300/420 구간 경계. 롤링 5겹 중 {', '.join(f'{f} = 동결 {s}' for f, s in same)}(보정값 비트 단위 동일). 독립 폴드 {len(indep)}개({', '.join(indep)}). {cite(V1OUT / 'splits.csv', 'A,normal_60_20_20,train')}; {cite(E / 'rolling_calibration_curve.csv', 'normal_420_479')}",
         f"오경보 판단의 주 근거는 B α=1% 3/180(구간 {B_fa})이다. 롤링 420~479의 2/60은 같은 모델의 같은 오경보(423·461)라 합산하지 않는다",
         "결과를 본 뒤 분할을 다시 고르지 않는다", "모두 같은 날 77분 안이다. 새 날짜 검증이 아니다"),
        ("검증", "conformal 보정",
         f"기록(알림 단위) 최대 점수로 보정, α 격자 k/121. 시간순 5겹 합산 {int(pooled.loc[1, 'alerted'])}/300·{int(pooled.loc[3, 'alerted'])}/300·{int(pooled.loc[6, 'alerted'])}/300·{int(pooled.loc[12, 'alerted'])}/300(k=1·3·6·12), k 1~12 중 {int(pooled.within_pi90.sum())}개가 90% 예측 구간 안. {cite(E / 'calibration_curve.csv', 'B,1,')}; {cite(E / 'rolling_calibration_curve.csv', '합산(5겹)')}",
         "α=1%(보정 120단위의 최대값)를 기본 운영점으로 둔다", "행 단위 보정은 기록 안 자기상관으로 오경보가 부푼다", "같은 날·교환가능성 가정. 새 날짜의 보장이 아니다"),
        ("검증", "블록 부트스트랩",
         f"정상 알림 수의 이동 블록 부트스트랩(블록 5·10·20). {cite(GUARD_OUT / 'uncertainty_v2.csv', 'A,normal_60_20_20,v1,0.01,normal,notified_segments,5')}",
         "관측 건수를 주 결과로, 부트스트랩은 민감도로 둔다", "0건은 퇴화로 표시한다", "같은 날 자료 안의 변동만 반영한다"),
        ("검증", "누설 검사",
         f"날짜 이동·열 추가·6자리 재직렬화·미래 행 추가에 추론 불변. {cite(V1OUT / 'label_bypass.csv', 'timestamps_shifted_5_days')}",
         "라벨·날짜·파일명을 입력에서 제외한 효과를 불변성으로 확인", "형식 누설은 matched로 따로 막는다", "형식 밖 교락은 검사 대상이 아니다"),
        ("검증", "무작위 분할 지름길",
         f"무작위 행 분할에서 저장 소수 자릿수(AI0 하나)만으로 F1 {fmt.f1:.3f}. {cite(SUPV / 'random_rows.csv', 'decimal_digits(AI0)')}",
         "무작위 행 분할을 평가에 쓰지 않는다", "쓰면 같은 기록의 이웃 행과 저장 형식이 학습·평가에 함께 들어간다", "없음"),
        ("검증", "기록 묶음 교차검증",
         f"이상 21구간을 1구간씩 떼는 21겹. 창+v2 성분 지도학습 로지스틱 F1 A {g21['A']:.3f}·B {g21['B']:.3f} 대 v2 0.962·0.971. {cite(SUPV / 'grouped_records.csv', 'A,window_plus_v2,logistic,21fold,conformal')}",
         "선정 이유는 F1 우위가 아니라 라벨 불필요·전이·재보정이다", "행 단위 교차검증은 기록 내 이웃 행을 공유한다", "21구간은 독립 고장이 아니다"),
        ("검증", "E1 고장 주입",
         f"같은 날 정상 기록에 시작 시각을 아는 주입. v2 탐지 하한 전류 잡음 {floor[('cur_noise', 'guard_v2')]:g}σ·오프셋 {floor[('cur_offset', 'guard_v2')]:g}×진폭·진동 잡음 {floor[('vib_noise', 'guard_v2')]:g}σ. {cite(SUPP / 'e1_detection_floor.csv', 'cur_noise,guard_v2')}",
         "탐지 하한과 약점(기록 시작부터 있는 변화, 전류 배율)을 공개", "없음", "인공 신호. 실제 고장 모양의 보장이 아니다"),
        ("검증", "E2 외부 자료",
         f"UCI 펌프 누설에 v2 구조 AUROC {e2l.min():.2f}~{e2l.max():.2f}(실패). {cite(SUPP / 'e2_uci_metrics.csv', 'local_normal_reference,3,v2_4ch')}",
         "적용 범위를 짧은 과도 변화로 좁힌다", "없음", "다른 설비·센서. 대회 성능과 합산하지 않는다"),
        ("검증", "E3 재보정",
         f"사전 안정성 기준 충족 {int(e3.stable.sum())}/{len(e3)}. {cite(SUPP / 'e3_stability.csv', '0.01,15,99,')}",
         "재보정은 고장 주입 수락 검사(recalibrate.py)와 함께 쓴다", "없음", "사전 기준 미충족을 그대로 공개한다"),
    ]
    for item, value in gp.items():
        rows.append(("가이드북 대비", item, f"{value}. {cite(E / 'guidebook_protocol_vs_records.csv', item.split('(')[0])}",
                     ctx["guidebook_protocol"].set_index("item").ours[item], ctx["guidebook_protocol"].set_index("item").guidebook[item], "가이드북 방식 비판이 아니라 이 자료 구조와의 차이"))
    tab = pd.DataFrame(rows, columns=["stage", "item", "evidence", "decision", "alternative_and_result", "limitation"])
    tab.attrs["note"] = ("v2 기준 진단 → 전처리 → 검증 결정표. 근거의 `파일:행`은 실행 시점에 찾아 넣는다(인용 파일 해시는 manifest). "
                         "오경보 근거를 폴드끼리 합산하지 않는다(420~479 폴드 = 동결 B, 480~539 폴드 = 동결 A)")
    return tab


def main():
    for stream in (sys.stdout, sys.stderr):     # 한국어 Windows(CP949) 콘솔에서 못 쓰는 기호는 바꿔 쓴다
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    start = time.monotonic()
    normal, abnormal, report = D.load(BASE)
    raw = {"normal": normal, "abnormal": abnormal}
    seg = {k: D.segments(f) for k, f in raw.items()}
    t = {k: pd.to_datetime(f.TimeStamp) for k, f in raw.items()}
    st = {k: segment_stats(raw[k], seg[k]) for k in raw}
    mu, sd = train_scale(normal, seg["normal"])
    fits = {k: waveform_fits(raw[k], seg[k]) for k in raw}
    fb = frozen_false_alarms(normal, seg["normal"], "B")
    tables = {}
    tables["sensor_relations.csv"] = sensor_relations(raw, st)
    tables["operating_variation.csv"] = operating_variation(seg["normal"], t["normal"], st["normal"])
    tables["false_alarm_operating_level.csv"] = false_alarm_levels(fb, seg["normal"], t["normal"], st["normal"])
    tables["observability.csv"] = observability(raw, seg)
    tables["production_unit_evidence.csv"] = production_unit(raw, seg, t, fits["normal"], mu, sd)
    tables["abnormal_segments.csv"], tables["abnormal_summary.csv"] = abnormal_segments(raw, seg, t, fits, mu, sd, st["abnormal"])
    tables["outlier_rules.csv"] = outlier_rules(raw, seg["normal"])
    tables["quality_index_weighted.csv"] = quality_weighted(raw)
    tables["guidebook_stats_match.csv"] = guidebook_stats(raw)
    tables["rolling_calibration_curve.csv"], folds = rolling_calibration_curve(normal, seg["normal"])
    tables["phase_continuity.csv"] = phase_continuity(normal, seg["normal"], t["normal"])
    tables["guidebook_protocol_vs_records.csv"] = guidebook_protocol(normal, seg["normal"], t["normal"], tables["sensor_relations.csv"])
    for name, tab in tables.items():          # 결정표·대응표가 이 표들을 인용하므로 먼저 쓴다
        tab.to_csv(HERE / name, index=False)
    tables["variable_expected_signals.csv"] = variable_expected_signals(raw, tables["observability.csv"])
    tables["failure_mode_map.csv"] = failure_mode_map()
    ctx = dict(outlier_rules=tables["outlier_rules.csv"], rolling_curve=tables["rolling_calibration_curve.csv"],
               guidebook_protocol=tables["guidebook_protocol_vs_records.csv"])
    tables["decision_table_diagnosis_v2.csv"] = decision_table(raw, seg, t, st, fb, ctx)
    notes = {}
    for name, tab in tables.items():
        tab.to_csv(HERE / name, index=False)
        if tab.attrs.get("note"):
            notes[name] = tab.attrs["note"]
    fig_files = figures.draw_all(raw=raw, seg=seg, t=t, st=st, mu=mu, sd=sd, fb=fb, tables=tables)
    try:
        from threadpoolctl import threadpool_info
        blas = [{k: v for k, v in i.items() if k in ("internal_api", "version", "num_threads")} for i in threadpool_info()]
    except ImportError:
        blas = None
    sources = [GUARD_OUT / n for n in ("coupling_fit_v2.csv", "rolling.csv", "ablation_v2.csv", "uncertainty_v2.csv")] + \
              [V1OUT / "load_normalization_meta.csv", SUPP / "e1_summary.csv", SUPP / "e1_detection_floor.csv", SUPP / "e2_uci_metrics.csv",
               SUPP / "e3_stability.csv", SUPV / "random_rows.csv", SUPV / "grouped_records.csv"] + \
              [HERE / n for n in ("gaps.csv", "imbalance.csv", "outliers.csv", "quality_index.csv", "block_context.csv", "current_grid.csv", "class_differences.csv")]
    D.dump_json(dict(purpose="루브릭 사이클2 1회차 평가관 01 D1~D6·평가관 05 O1(a)·O4 진단 보강 표와 그림",
                     input_hashes={k: v["sha256"] for k, v in report["files"].items()},
                     artifacts={p.name: D.sha256_file(p) for p in sorted(ART.glob("guard_*.json"))},
                     code_sha256={rel(p): D.sha256_file(p) for p in (Path(__file__), HERE / "figures.py", HERE / "build_tables.py", GUARD / "model.py",
                                                                    V1 / "press" / "diagnosis.py", V1 / "press" / "data.py")},
                     sources={rel(p): D.sha256_file(p) for p in sources}, cited=dict(sorted(CITED.items())),
                     rolling_folds=[dict(fold=f["fold"], train_end=f["train_end"], n_cal=f["n_cal"], same_as_frozen=f["same"]) for f in folds],
                     outputs={name: D.sha256_file(HERE / name) for name in tables} | {rel(p): D.sha256_file(p) for p in fig_files},
                     table_notes=notes, seeds=dict(simulation=SEED_SIM, permutation=SEED_PERM),
                     environment=dict(D.environment(), blas_runtime=blas), elapsed_s=round(time.monotonic() - start, 1)),
                HERE / "diagnostics_manifest.json")
    print(f"완료 {time.monotonic() - start:.1f}초, 표 {len(tables)}개, 그림 {len(fig_files)}장")


if __name__ == "__main__":
    main()
