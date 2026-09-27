"""프레스 진단·근거 보강 표 — 루브릭 검수(d9655af)의 R1~R4·R10·R14·R18~R22.

원본 CSV와 동결 v2 모델(press_guard/artifacts)만 읽는다. v1·v2 동결 기대값 밖의 분석용 표이며 보고서 서술이 아니다.
모델·문턱·분할은 바꾸지 않는다. 이미 본 이상 21구간을 쓰는 기술 통계다.

    python yejun/analysis/press_evidence/build_tables.py
"""
from pathlib import Path
import json
import sys
import time

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[1]
sys.path.insert(0, str(YEJUN / "press_guard"))
from model import GuardModel, D, BASE, layout  # noqa: E402
from analyze import segment_feature_table, condition_bounds, _wave, AMP_MIN_LEN  # noqa: E402
from press.calibrate import conformal_p, segment_max  # noqa: E402
from press.diagnosis import sine_fit, MIN_FIT_LEN  # noqa: E402

ART = YEJUN / "press_guard" / "artifacts"
GUARD_OUT = YEJUN / "press_guard" / "outputs"
GRID = 1.1920929          # 전류 저장 격자(float32 기계 엡실론×1e7)
GUIDE = "가이드북"         # 「소성가공 예지보전 AI 데이터셋」 분석실습 가이드북
COMP = ("magnitude", "waveform", "dynamics")


def decimals(series):
    s = series.astype(str).str.strip().str.lstrip("-")
    return s.str.split(".").str[1].fillna("").str.len()


def lag1(x, seg):
    same = seg[1:] == seg[:-1]
    return float(np.corrcoef(x[:-1][same], x[1:][same])[0, 1])


def demean(x, seg):
    return x - pd.Series(x).groupby(seg).transform("mean").to_numpy()


def part_masks(seg, sid):
    _, tr, ca = D.SPLITS[sid]
    return {"train": seg < tr, "cal": (seg >= tr) & (seg < ca), "test": seg >= ca}


def v2_segment_max(model, frame):
    """GuardModel.predict와 같은 전처리·구간 규칙으로 구간 최대 결합 점수."""
    q = D.quantize(D.inputs_only(frame), "matched")
    seg = layout(q)[1]
    return segment_max(model.components(q, seg)["score"], seg)


# ---------- R2 변수 사전 ----------
def variable_dictionary(raw, text):
    n, a = raw["normal"], raw["abnormal"]
    dn = {c: decimals(text["normal"][c]) for c in D.SENSORS}
    da = {c: decimals(text["abnormal"][c]) for c in D.SENSORS}
    cur = n.AI2_Current.to_numpy(float)
    rows = [
        dict(column="Unnamed: 0", guidebook_meaning="(표 1에 없음)", guidebook_type="-", unit_in_guidebook="-",
             stored_precision="정수", observed=f"0~{len(n) - 1}, 0~{len(a) - 1}의 행 번호(파일마다 0부터)",
             model_use="입력 제외", team_rule="행 번호. 순서 확인에만 쓰고 특징으로 쓰지 않는다"),
        dict(column="TimeStamp", guidebook_meaning="수집시간", guidebook_type="object", unit_in_guidebook="-",
             stored_precision="밀리초 3자리",
             observed=f"정상 {pd.to_datetime(n.TimeStamp).min():%Y-%m-%d(%a) %H:%M:%S}~{pd.to_datetime(n.TimeStamp).max():%H:%M:%S}, "
                      f"이상 {pd.to_datetime(a.TimeStamp).min():%Y-%m-%d(%a) %H:%M:%S}~{pd.to_datetime(a.TimeStamp).max():%H:%M:%S}. 기록 안 간격 0.1초",
             model_use="기록구간 경계(간격≠0.1초)에만 사용. 절대 시각·날짜는 입력 아님",
             team_rule="라벨과 날짜·요일·시간대가 완전히 겹친다. 시각 차이를 고장 근거로 쓰지 않는다"),
    ]
    meaning = {"AI0_Vibration": "유압펌프 상부진동", "AI1_Vibration": "유압펌프 하부진동", "AI2_Current": "유압펌프 전류"}
    for c in D.SENSORS:
        x, y = n[c].to_numpy(float), a[c].to_numpy(float)
        obs = f"정상 평균 {x.mean():.4g}·SD {x.std(ddof=1):.4g}, 이상 평균 {y.mean():.4g}·SD {y.std(ddof=1):.4g}"
        if c == "AI2_Current":
            obs += f". 정상 음수 비율 {(cur < 0).mean():.1%}, 정상 기록은 0.6 Hz 사인형"
            rule = "단위 미기재. 음수가 절반이라 RMS가 아닌 순시값 표본으로 추정(검증 불가). 정상 학습 표준화 척도로만 해석하고 A 등 물리 단위로 쓰지 않는다"
        else:
            rule = "단위 미기재(g·mm/s 등 미확인). 정상 학습 표준화 척도로만 해석한다"
        rows.append(dict(column=c, guidebook_meaning=meaning[c], guidebook_type="float64", unit_in_guidebook="미기재",
                         stored_precision=f"소수 자릿수 최빈 정상 {int(dn[c].mode()[0])}·이상 {int(da[c].mode()[0])}",
                         observed=obs, model_use="입력(matched 양자화 후)", team_rule=rule))
    rows.append(dict(column="Equipment_state", guidebook_meaning="장비 고장 여부(정상 0, 고장 1)", guidebook_type="int64",
                     unit_in_guidebook="-", stored_precision="정수",
                     observed=f"정상 파일 전체 {sorted(n.Equipment_state.unique())}, 이상 파일 전체 {sorted(a.Equipment_state.unique())}",
                     model_use="입력 제외. 평가 분리에만 사용",
                     team_rule="파일 단위 상수라 시점별 고장 라벨이 아니다. 고장 시작 시각·원인을 주장하지 않는다"))
    return pd.DataFrame(rows)


# ---------- R3 불균형·이상치·품질 지수 ----------
def imbalance(seg_n):
    rows = [dict(scope="전체", normal_rows=20000, abnormal_rows=600, abnormal_row_share=600 / 20600,
                 normal_segments=600, abnormal_segments=21, abnormal_segment_share=21 / 621,
                 recorded_seconds_normal=2000.0, recorded_seconds_abnormal=60.0, all_positive_row_f1=np.nan)]
    for sid in D.SPLITS:
        test = part_masks(seg_n, sid)["test"]
        nr, ns = int(test.sum()), int(len(np.unique(seg_n[test])))
        prev = 600 / (600 + nr)
        rows.append(dict(scope=f"{sid} 평가", normal_rows=nr, abnormal_rows=600, abnormal_row_share=prev, normal_segments=ns,
                         abnormal_segments=21, abnormal_segment_share=21 / (21 + ns),
                         recorded_seconds_normal=nr * D.DT, recorded_seconds_abnormal=60.0, all_positive_row_f1=2 * prev / (1 + prev)))
    t = pd.DataFrame(rows)
    t["note"] = ["", "전부 양성으로 예측해도 F1 0.227", "전부 양성으로 예측해도 F1 0.164. A와 기준선이 달라 F1을 같은 잣대로 직접 비교하지 않는다"]
    return t


def outliers(raw, seg_n, seg_a):
    n, a = raw["normal"], raw["abnormal"]
    tr = part_masks(seg_n, "A")["train"]
    rows, out_any, out_vib = [], np.zeros(len(a), bool), np.zeros(len(a), bool)
    for c in D.SENSORS:
        x, y = n[c].to_numpy(float), a[c].to_numpy(float)
        med = np.median(x[tr]); mad = 1.4826 * np.median(np.abs(x[tr] - med))
        lo, hi = x[tr].min(), x[tr].max()
        outside = (y < lo) | (y > hi)
        out_any |= outside
        if c != "AI2_Current":
            out_vib |= outside
        rows.append(dict(sensor=c, normal_robust_z_max=float(np.abs((x - med) / mad).max()),
                         normal_rows_at_min_or_max=int(((x == x.min()) | (x == x.max())).sum()),
                         normal_nontrain_rows_outside_trainA_range=int(((x < lo) | (x > hi))[~tr].sum()),
                         abnormal_rows_outside_trainA_range=int(outside.sum()),
                         abnormal_rows_robust_z_gt5=int((np.abs((y - med) / mad) > 5).sum()),
                         note="전류는 사인형이라 행 단위 robust z는 참고치" if c == "AI2_Current" else ""))
    rows.append(dict(sensor="어느 센서든", normal_robust_z_max=np.nan, normal_rows_at_min_or_max=np.nan,
                     normal_nontrain_rows_outside_trainA_range=np.nan, abnormal_rows_outside_trainA_range=int(out_any.sum()),
                     abnormal_rows_robust_z_gt5=np.nan,
                     note=f"학습 범위 밖 행이 있는 이상 구간 {len(np.unique(seg_a[out_any]))}/21(진동 기준 {len(np.unique(seg_a[out_vib]))}/21). "
                          "결정: 이상치를 제거하지 않는다(이상 신호 자체). 정상 최솟값·최댓값이 각 1행뿐이라 포화·클리핑 흔적 없음"))
    return pd.DataFrame(rows)


def quality_index(raw):
    """가이드북 62쪽의 6개 품질 지수를 같은 산식으로 다시 계산한다(유일성은 가이드북 코드 7과 같은 value_counts 방식)."""
    days = {"normal": ("2022-07-12", "2022-07-13"), "abnormal": ("2022-07-17", "2022-07-18")}
    reported = {"normal": dict(completeness=100, uniqueness=99.99, validity=100, consistency=100, integrity=66.67),
                "abnormal": dict(completeness=100, uniqueness=100, validity=100, consistency=100, integrity=100)}
    rows = []
    for k, f in raw.items():
        body = f.drop(columns=[f.columns[0]])            # 행 번호 열 제외(가이드북도 제외해야 99.99%가 나온다)
        comp = (1 - body.isna().sum().sum() / body.size) * 100
        vc = body.value_counts()
        uniq = (len(vc) - int((vc > 1).sum())) / len(vc) * 100
        t = pd.to_datetime(f.TimeStamp, errors="coerce")
        valid = ((t >= days[k][0]) & (t < days[k][1])).mean() * 100
        cons = (f[D.SENSORS].apply(pd.to_numeric, errors="coerce").notna().all(axis=1) & t.notna()).mean() * 100
        integ = (1 - sum(v < 100 for v in (round(uniq, 2), valid, cons)) / 3) * 100
        for name, value in (("completeness", comp), ("uniqueness", uniq), ("validity", valid), ("consistency", cons),
                            ("accuracy", np.nan), ("integrity", integ)):
            rows.append(dict(file=k, index=name, recomputed=round(value, 4) if np.isfinite(value) else np.nan,
                             guidebook_reported=reported[k].get(name, np.nan),
                             note={"uniqueness": "완전 중복 1행(R20) 때문에 정상만 100% 미만" if k == "normal" else "",
                                   "accuracy": "가이드북도 산출하지 않음(기준값 없음)",
                                   "integrity": "유일성·유효성·일관성 중 100%가 아닌 지수 비율"}.get(name, "")))
    return pd.DataFrame(rows)


# ---------- R4 형식 밖 클래스 차이 ----------
def class_differences(raw, text, seg_n, seg_a):
    n, a = raw["normal"], raw["abnormal"]
    q = {k: D.quantize(D.inputs_only(f), "matched") for k, f in raw.items()}
    segs = {"normal": seg_n, "abnormal": seg_a}
    feat = {}
    for k, f in raw.items():
        sg = segs[k]
        lens = pd.Series(sg).value_counts()
        long17 = np.isin(sg, lens[lens >= 17].index)
        cur = q[k].AI2_Current.to_numpy(float)
        dm = demean(cur, sg)[long17]
        r2, fr = [], []
        for s in np.unique(sg):
            idx = np.flatnonzero(sg == s)
            if len(idx) >= MIN_FIT_LEN:
                f_, r_ = sine_fit(f.AI2_Current.to_numpy(float)[idx])[:2]
                fr.append(f_); r2.append(r_)
        cors = [np.corrcoef(g.AI0_Vibration, g.AI1_Vibration)[0, 1] for _, g in q[k].groupby(sg) if len(g) >= 17]
        feat[k] = dict(
            dec_vib=int(decimals(text[k].AI0_Vibration).mode()[0]),
            grid=float((np.abs(f.AI2_Current / GRID - np.round(f.AI2_Current / GRID)) < 1e-3).mean()),
            sd0=float(f.AI0_Vibration.std(ddof=1)), sd1=float(f.AI1_Vibration.std(ddof=1)),
            lag0=lag1(q[k].AI0_Vibration.to_numpy(float), sg), lag1_=lag1(q[k].AI1_Vibration.to_numpy(float), sg),
            lag0_dm=lag1(demean(q[k].AI0_Vibration.to_numpy(float), sg), sg), lag1_dm=lag1(demean(q[k].AI1_Vibration.to_numpy(float), sg), sg),
            corr=float(np.corrcoef(q[k].AI0_Vibration, q[k].AI1_Vibration)[0, 1]),
            corr_seg_median=float(np.median(cors)), corr_seg_neg=f"{int((np.asarray(cors) < 0).sum())}/{len(cors)}",
            cur_mean=float(pd.Series(cur).groupby(sg).mean()[lens[lens >= 17].index].median()),
            r2=float(np.median(r2)), freq=float(np.median(fr)), kurt=float(np.mean(dm ** 4) / np.mean(dm ** 2) ** 2))
    fN, fA = feat["normal"], feat["abnormal"]
    sigma = lambda r2: float(np.sqrt(-np.log(r2)) / (2 * np.pi * 60) * 1e3)   # 60 Hz 앨리어싱 가정의 등가 시각 흔들림(ms)
    alias = f"앨리어싱 가설(60 Hz 순시값, 독립 가우스 시각 흔들림)이면 R² {fA['r2']:.3f}은 RMS 약 {sigma(fA['r2']):.1f} ms, 정상 {fN['r2']:.3f}은 약 {sigma(fN['r2']):.2f} ms 흔들림과 같은 크기(검증 불가)"
    rows = [
        ("수집 날짜·요일·시간대", "2022-07-12(화) 00:00~01:17", "2022-07-17(일) 10:51~10:54", "아니오", "모든 성분·모델", "모든 성분·모델", "분리 불가(교락 자체)", "라벨=파일=날짜"),
        ("진동 저장 소수 자릿수(최빈)", fN["dec_vib"], fA["dec_vib"], "예", "-", "-", "수집 차이(저장 형식)", "matched 1e-4 반올림으로 제거"),
        (f"전류 격자 {GRID} 일치율(허용 1e-3)", round(fN["grid"], 5), round(fA["grid"], 5), "예", "-", "-", "수집 차이(저장 형식)", "matched 격자 반올림으로 제거"),
        ("AI0 진동 SD", round(fN["sd0"], 4), round(fA["sd0"], 4), "아니오", "크기", "5NN·IF·AE·LSTM", "분리 불가", f"×{fA['sd0'] / fN['sd0']:.1f}"),
        ("AI1 진동 SD", round(fN["sd1"], 4), round(fA["sd1"], 4), "아니오", "크기", "5NN·IF·AE·LSTM", "분리 불가", f"×{fA['sd1'] / fN['sd1']:.1f}"),
        ("AI0 lag-1(구간 안, matched)", round(fN["lag0"], 3), round(fA["lag0"], 3), "아니오", "직접 사용 안 함(크기는 행별 |z|)", "AE(창 5)·LSTM(창 20)", "분리 불가",
         f"구간 평균 제거 시 정상 {fN['lag0_dm']:.3f}·이상 {fA['lag0_dm']:.3f}"),
        ("AI1 lag-1(구간 안, matched)", round(fN["lag1_"], 3), round(fA["lag1_"], 3), "아니오", "직접 사용 안 함", "AE·LSTM", "분리 불가",
         f"구간 평균 제거 시 정상 {fN['lag1_dm']:.3f}·이상 {fA['lag1_dm']:.3f}"),
        ("상·하부 진동 상관(합동)", round(fN["corr"], 3), round(fA["corr"], 3), "아니오", "직접 사용 안 함", "AE·LSTM", "분리 불가",
         f"부호 반전. 구간별(길이≥17) 중앙값 정상 {fN['corr_seg_median']:.2f}(음수 {fN['corr_seg_neg']})·이상 {fA['corr_seg_median']:.2f}(음수 {fA['corr_seg_neg']})"),
        ("전류 구간 평균 중앙값(길이≥17)", round(fN["cur_mean"], 2), round(fA["cur_mean"], 2), "아니오", "크기·예측 오차(상수항)", "5NN·IF·AE·LSTM", "분리 불가(영점·계측 가능성 포함)", "짧은 구간 표본평균이라 DC 오프셋과 같지 않다"),
        ("전류 사인 적합 R² 중앙값(길이≥10)", round(fN["r2"], 4), round(fA["r2"], 4), "아니오", "파형·예측 오차", "LSTM·AE", "분리 불가(고장 또는 표본화 시각 흔들림)", alias),
        ("전류 사인 적합 주파수 중앙값(Hz)", round(fN["freq"], 3), round(fA["freq"], 3), "아니오", "파형·예측 오차", "LSTM", "분리 불가", "0~5 Hz 격자 최소제곱"),
        ("전류 첨도(구간 평균 제거, 길이≥17)", round(fN["kurt"], 3), round(fA["kurt"], 3), "아니오", "간접(파형)", "-", "분리 불가", "순수 사인 1.5, 가우스 잡음 3"),
    ]
    cols = ["feature", "normal", "abnormal", "removed_by_matched", "v2_components_reacting", "v1_package_models_reacting", "interpretation", "note"]
    t = pd.DataFrame(rows, columns=cols)
    t["team_rule"] = "어떤 신호 차이도 고장의 인과 증거로 쓰지 않는다"
    return t


# ---------- R1 분할·블록 맥락 ----------
def split_context(raw, seg_n, t_n):
    n = raw["normal"]
    cur = n.AI2_Current.to_numpy(float)
    dm = demean(cur, seg_n)
    rows = []
    for sid in D.SPLITS:
        model = GuardModel.load(ART / f"guard_{sid}.json")
        masks = part_masks(seg_n, sid)
        z = np.abs((n[D.SENSORS[:2]].to_numpy(float) - model.mean[:2]) / model.scale[:2]).max(axis=1)
        vib_segmax = pd.Series(z).groupby(seg_n).max()
        q95 = float(vib_segmax[np.unique(seg_n[masks["train"]])].quantile(.95))
        cal_med = float(np.median(model.cal))
        for part, m in masks.items():
            smax = v2_segment_max(model, n[m])
            ids = np.unique(seg_n[m])
            rows.append(dict(split=sid, part=part, segments=len(ids), rows=int(m.sum()),
                             start=f"{t_n[m].min():%H:%M:%S}", end=f"{t_n[m].max():%H:%M:%S}",
                             AI0_sd=float(n.AI0_Vibration[m].std()), AI1_sd=float(n.AI1_Vibration[m].std()),
                             current_rms_demeaned=float(np.sqrt(np.mean(dm[m] ** 2))),
                             vib_segmax_gt_train_q95=int((vib_segmax[ids] > q95).sum()),
                             v2_segmax_median=float(np.median(smax)), cal_median=cal_med,
                             share_gt_cal_median=float((smax > cal_med).mean()),
                             mannwhitney_p_vs_cal=float(stats.mannwhitneyu(smax, model.cal).pvalue) if part == "test" else np.nan,
                             note="학습 구간은 적합에 쓴 자료(표본 내)" if part == "train" else ("보정 자신" if part == "cal" else "")))
    return pd.DataFrame(rows)


def block_context(raw, seg_n, t_n):
    n = raw["normal"]
    cur = n.AI2_Current.to_numpy(float)
    dm = demean(cur, seg_n)
    model = GuardModel.load(ART / "guard_A.json")
    z = np.abs((n[D.SENSORS[:2]].to_numpy(float) - model.mean[:2]) / model.scale[:2]).max(axis=1)
    vib_segmax = pd.Series(z).groupby(seg_n).max()
    q95 = float(vib_segmax[vib_segmax.index < 360].quantile(.95))
    smax = pd.Series(v2_segment_max(model, n), index=np.unique(seg_n))
    rolling = pd.read_csv(GUARD_OUT / "rolling.csv")
    roll = rolling[rolling.model.eq("guard_v2") & rolling.alpha.eq(.01)].set_index("split").normal_notified_segments
    cal_med = float(np.median(model.cal))
    rows = []
    for b in range(10):
        lo, hi = 60 * b, 60 * b + 59
        m = (seg_n >= lo) & (seg_n <= hi)
        ids = np.arange(lo, hi + 1)
        part_a = "train" if hi < 360 else ("cal" if hi < 480 else "test")
        part_b = "train" if hi < 300 else ("cal" if hi < 420 else "test")
        key = f"normal_{lo}_{hi}"
        rows.append(dict(block=f"{lo}~{hi}", start=f"{t_n[m].min():%H:%M:%S}", end=f"{t_n[m].max():%H:%M:%S}",
                         part_A=part_a, part_B=part_b, AI0_sd=float(n.AI0_Vibration[m].std()), AI1_sd=float(n.AI1_Vibration[m].std()),
                         current_rms_demeaned=float(np.sqrt(np.mean(dm[m] ** 2))),
                         vib_segmax_gt_Atrain_q95=int((vib_segmax[ids] > q95).sum()),
                         v2A_segmax_median=float(smax[ids].median()), v2A_share_gt_cal_median=float((smax[ids] > cal_med).mean()),
                         rolling_v2_alerts_alpha1=int(roll[key]) if key in roll.index else np.nan))
    t = pd.DataFrame(rows)
    t.attrs["note"] = "v2A 열은 동결 A 모델 기준. 0~359는 A의 학습 자료라 표본 내 값이다. rolling은 해당 60구간을 평가로 둔 별도 재적합 결과(train.py --rolling)"
    return t


# ---------- R10 AR(2) 진동자 ----------
def ar2_oscillator():
    rows = []
    pure = 2 * np.cos(2 * np.pi * .6 * D.DT)
    for sid in D.SPLITS:
        c, p1, p2 = GuardModel.load(ART / f"guard_{sid}.json").coef
        roots = np.roots([1, -p1, -p2])
        rows.append(dict(split=sid, const=c, phi1=p1, phi2=p2, discriminant=p1 ** 2 + 4 * p2, complex_roots=bool(np.iscomplex(roots).all()),
                         root_modulus=float(abs(roots[0])), implied_freq_hz=float(abs(np.angle(roots[0])) / (2 * np.pi * D.DT)),
                         equilibrium=float(c / (1 - p1 - p2)), pure_sine_0p6hz_phi1=pure, pure_sine_phi2=-1.0,
                         note="사인 성분 적합 주파수는 정상 기록 대부분 0.600 Hz(v1 diagnosis). 같은 0.6 Hz 신호 가설을 AR은 3관측, 사인은 6·8관측으로 쓴다. 0.6 Hz의 물리 원인은 미확인(60 Hz 앨리어싱은 가설)"))
    return pd.DataFrame(rows)


# ---------- R14 진폭 신뢰 제한 ----------
def amplitude_reliability(raw, seg_n):
    rows = []
    for sid in D.SPLITS:
        model = GuardModel.load(ART / f"guard_{sid}.json")
        masks = part_masks(seg_n, sid)
        q = {k: D.quantize(D.inputs_only(f), "matched") for k, f in
             (("train", raw["normal"][masks["train"]]), ("normal_test", raw["normal"][masks["test"]]), ("abnormal", raw["abnormal"]))}
        bounds = condition_bounds(segment_feature_table(q["train"], D.segments(q["train"]), model.mean, model.scale))
        for subset in ("normal_test", "abnormal"):
            f = segment_feature_table(q[subset], D.segments(q[subset]), model.mean, model.scale)
            wave = _wave(f, bounds)
            for w in ("sine-like", "broken", "unfittable(<10)"):
                m = wave == w
                rows.append(dict(split=sid, subset=subset, wave=w, segments=int(m.sum()),
                                 length_ge17=int((m & f.amp_reliable).sum()), length_lt17=int((m & ~f.amp_reliable).sum()),
                                 r2_low_bound=bounds["r2_low"],
                                 amp_interpretation={"sine-like": "길이≥17이면 사인 진폭으로 읽을 수 있다",
                                                     "broken": "사인이 아니므로 amp_proxy는 √2×평균 제거 RMS일 뿐 진폭이 아니다",
                                                     "unfittable(<10)": "파형 판정 불가. 진폭 해석 안 함"}[w]))
    t = pd.DataFrame(rows)
    t.attrs["note"] = f"press_guard/analyze.py의 amp_reliable은 길이≥{AMP_MIN_LEN}만 뜻한다. 파형 적합 조건은 이 표로 따로 보인다. 오류 조건표의 분모는 바꾸지 않는다"
    return t


# ---------- R18 성분 상보성, R19 보정 곡선 ----------
def predictions(raw, seg_n):
    out = {}
    for sid in D.SPLITS:
        model = GuardModel.load(ART / f"guard_{sid}.json")
        test = raw["normal"][part_masks(seg_n, sid)["test"]]
        out[sid] = dict(model=model, normal=model.predict(test, .01), abnormal=model.predict(raw["abnormal"], .01))
    return out


def component_complementarity(preds):
    combo_rows, corr_rows, first_rows = [], [], []
    for sid, p in preds.items():
        for subset in ("abnormal", "normal"):
            d = p[subset]
            al = d[d.alarm.eq(1)]
            combos = al.reason.fillna("").map(lambda r: "+".join(sorted(r.split("+"), key=COMP.index)) if r else "none")
            for combo, k in combos.value_counts().items():
                combo_rows.append(dict(split=sid, subset=subset, combination=combo, components=combo.count("+") + 1,
                                       alarm_rows=int(k), share=k / len(al)))
            g = d[["g_magnitude", "g_waveform", "g_dynamics"]].dropna()
            rho = g.corr(method="spearman")
            for i, x in enumerate(COMP):
                for y in COMP[i + 1:]:
                    corr_rows.append(dict(split=sid, subset=subset, pair=f"{x}~{y}", rows=len(g), spearman=float(rho.loc[f"g_{x}", f"g_{y}"])))
            if subset == "abnormal":
                first = al.groupby("record_id").head(1)
                for reason, k in first.reason.value_counts().items():
                    first_rows.append(dict(split=sid, first_alarm_reason=reason, records=int(k)))
    combo = pd.DataFrame(combo_rows)
    combo.attrs["note"] = ("행 분해는 고정 문턱에서 각 성분 p≤α 여부(모델 reason 열)다. 성분을 빼고 다시 보정한 절제(ablation_v2.csv)와 다르다. "
                           "첫 경보는 위치 0·1에서 크기만, 위치 2부터 예측 오차가 먼저 가능하다")
    return combo, pd.DataFrame(corr_rows), pd.DataFrame(first_rows)


def calibration_curve(preds):
    rows = []
    for sid, p in preds.items():
        n_cal = len(p["model"].cal)
        rec_min = p["normal"].groupby("record_id").p_value.min()
        for k in range(1, 13):
            alpha = k / (n_cal + 1)
            x, n = int((rec_min <= alpha + 1e-12).sum()), len(rec_min)
            rows.append(dict(split=sid, k=k, alpha=alpha, nominal=alpha, records=n, alerted_records=x, realized=x / n,
                             binom_upper95=float(stats.beta.ppf(.95, x + 1, n - x)), above_nominal=bool(x / n > alpha)))
    t = pd.DataFrame(rows)
    t.attrs["note"] = ("기록구간 단위 정상 평가의 실현 경보율(기록 최소 p ≤ α). 같은 날·교환가능성 가정 아래의 주변 보장 점검이며 새 날짜 보장이 아니다. "
                       "A 평가 구간은 보정보다 조용한 시간대라(R1) 실현율이 낮게 나오는 쪽으로 치우친다")
    return t


# ---------- R20 중복, R21 격자, R22 공백·구간 규칙 ----------
def duplicate_rows(raw, seg_n):
    n = raw["normal"]
    body = n.drop(columns=[n.columns[0]])
    dup = body[body.duplicated(keep=False)]
    model_b = GuardModel.load(ART / "guard_B.json")
    rows = []
    for i in dup.index:
        s = int(seg_n[i])
        length = int((seg_n == s).sum())
        cal_ids = np.unique(seg_n[part_masks(seg_n, "B")["cal"]])
        rank = None
        if s in cal_ids:
            value = model_b.cal[list(cal_ids).index(s)]
            rank = int((model_b.cal > value).sum()) + 1
        rows.append(dict(row=int(n.iloc[i, 0]), timestamp=n.TimeStamp[i], AI0=n.AI0_Vibration[i], AI1=n.AI1_Vibration[i], AI2=n.AI2_Current[i],
                         segment=s, segment_length=length, part_A="train" if s < 360 else ("cal" if s < 480 else "test"),
                         part_B="train" if s < 300 else ("cal" if s < 420 else "test"),
                         B_cal_rank_from_top=rank, B_cal_segments=len(model_b.cal)))
    t = pd.DataFrame(rows)
    t.attrs["note"] = ("모든 값이 같은 완전 중복 1쌍. 삭제하지 않고 유지한다. 같은 시각이 경계가 되어 앞 구간(길이 2)과 뒤 구간(길이 1)으로 갈린다. "
                       "두 구간 모두 A 학습·B 보정에 있고 B 보정 최대 점수 순위가 119·120/120(최하위권)이라 α=1·3·5% 문턱(보정 최대 점수 1·3·6위)에 영향 없음")
    return t


def current_grid(raw):
    rows = []
    for k, f in raw.items():
        x = f.AI2_Current.to_numpy(float)
        kk = np.round(x / GRID)
        nz = kk != 0
        ls = float(np.sum(x[nz] * kk[nz]) / np.sum(kk[nz] ** 2))
        for name, g in (("상수 1.1920929", GRID), ("최소제곱 추정", ls)):
            res = np.abs(x - np.round(x / g) * g)
            rows.append(dict(file=k, step_name=name, step=g, residual_max=float(res.max()), residual_median=float(np.median(res)),
                             share_tol_1e3=float((res / g < 1e-3).mean()), share_tol_1e6=float((res / g < 1e-6).mean())))
    t = pd.DataFrame(rows)
    t.attrs["note"] = ("허용 1e-6 엄격 규칙의 이상 7.7%는 격자 상수 1.1920929의 유효숫자 한계에서 생긴 값이다. 최소제곱 간격(1.19209304)을 쓰면 이상 전류의 최대 잔차가 약 5.5e-6으로 "
                       "float32 저장 정밀도(유효숫자 약 7자리) 수준이라 사실상 모두 격자 위에 있다. 엄격 규칙은 판별 의미가 없고, 격자 판정은 허용 1e-3 기준(정상 0.175%, 이상 100%)을 쓴다")
    return t


def gaps_and_rule(raw):
    gap_rows, tol_rows = [], []
    for k, f in raw.items():
        t = pd.to_datetime(f.TimeStamp)
        dt = t.diff().dt.total_seconds().to_numpy()[1:]
        gaps = dt[np.abs(dt - D.DT) > D.GAP_TOL]
        pos = gaps[gaps > 0]
        seg = D.segments(f)
        lens = pd.Series(seg).value_counts()
        starts = t.groupby(seg).min()
        gap_rows.append(dict(file=k, boundaries=int(len(gaps)), zero_gaps=int((gaps == 0).sum()), positive_gaps=int(len(pos)),
                             gap_min_s=float(pos.min()), gap_q25_s=float(np.quantile(pos, .25)), gap_median_s=float(np.median(pos)),
                             gap_q75_s=float(np.quantile(pos, .75)), gap_max_s=float(pos.max()),
                             gaps_near_0p1_multiple=float(np.mean(np.abs(pos / .1 - np.round(pos / .1)) * .1 < 1e-3)),
                             segments=int(len(lens)), segments_len50=int((lens == 50).sum()), segments_len_gt50=int((lens > 50).sum()),
                             start_phase_ms_unique=int(len(np.unique((starts.dt.microsecond // 1000) % 100)))))
        for tol in (1e-9, 1e-6, 1e-3, .01, .05, .099, .1, .5, 1.0, 1.4, 1.5, 1.7, 2.0):
            new = np.r_[False, np.abs(np.r_[dt] - D.DT) > tol]
            tol_rows.append(dict(file=k, tolerance_s=tol, segments=int(new.sum() + 1)))
    g, tt = pd.DataFrame(gap_rows), pd.DataFrame(tol_rows)
    tt.attrs["note"] = "현행 규칙 |Δt−0.1|>1e-6. 0.1초 초과 1.5초 미만의 간격이 없어 허용오차를 1e-9~0.099초 어디로 바꿔도 600/21구간이다"
    return g, tt


def main():
    for stream in (sys.stdout, sys.stderr):     # 한국어 Windows(CP949) 콘솔에서 못 쓰는 기호는 바꿔 쓴다
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    start = time.monotonic()
    normal, abnormal, report = D.load(BASE)
    raw = {"normal": normal, "abnormal": abnormal}
    text = {k: pd.read_csv(D.data_dir(BASE) / D.FILES[k], dtype=str, keep_default_na=False) for k in raw}
    seg_n, seg_a = D.segments(normal), D.segments(abnormal)
    t_n = pd.to_datetime(normal.TimeStamp)
    preds = predictions(raw, seg_n)
    combo, corr, first = component_complementarity(preds)
    gaps, tol = gaps_and_rule(raw)
    tables = {
        "variable_dictionary.csv": variable_dictionary(raw, text),
        "imbalance.csv": imbalance(seg_n),
        "outliers.csv": outliers(raw, seg_n, seg_a),
        "quality_index.csv": quality_index(raw),
        "class_differences.csv": class_differences(raw, text, seg_n, seg_a),
        "split_context.csv": split_context(raw, seg_n, t_n),
        "block_context.csv": block_context(raw, seg_n, t_n),
        "ar2_oscillator.csv": ar2_oscillator(),
        "amplitude_reliability.csv": amplitude_reliability(raw, seg_n),
        "component_combinations.csv": combo,
        "component_correlation.csv": corr,
        "first_alarm_reason.csv": first,
        "calibration_curve.csv": calibration_curve(preds),
        "duplicate_rows.csv": duplicate_rows(raw, seg_n),
        "current_grid.csv": current_grid(raw),
        "gaps.csv": gaps,
        "segment_rule_tolerance.csv": tol,
    }
    notes = {}
    for name, t in tables.items():
        t.to_csv(HERE / name, index=False)
        if t.attrs.get("note"):
            notes[name] = t.attrs["note"]
    try:
        from threadpoolctl import threadpool_info
        blas = [{k: v for k, v in i.items() if k in ("internal_api", "version", "num_threads")} for i in threadpool_info()]
    except ImportError:
        blas = None
    D.dump_json(dict(purpose="루브릭 검수 R1~R4·R10·R14·R18~R22 진단·근거 보강 표", input_hashes={k: v["sha256"] for k, v in report["files"].items()},
                     artifacts={p.name: D.sha256_file(p) for p in sorted(ART.glob("guard_*.json"))},
                     code_sha256={"build_tables.py": D.sha256_file(Path(__file__)), "press_guard/model.py": D.sha256_file(YEJUN / "press_guard" / "model.py"),
                                  "press_guard/analyze.py": D.sha256_file(YEJUN / "press_guard" / "analyze.py")},
                     sources={"press_guard/outputs/rolling.csv": D.sha256_file(GUARD_OUT / "rolling.csv")},
                     outputs={name: D.sha256_file(HERE / name) for name in tables}, table_notes=notes,
                     environment=dict(D.environment(), blas_runtime=blas), elapsed_s=time.monotonic() - start), HERE / "manifest.json")
    for name in ("imbalance.csv", "split_context.csv", "ar2_oscillator.csv", "calibration_curve.csv"):
        print(name); print(tables[name].to_string(index=False)[:3000])


if __name__ == "__main__":
    main()
