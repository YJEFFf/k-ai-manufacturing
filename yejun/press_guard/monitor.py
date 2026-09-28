"""운영 중 감시와 점검 결과 기록 규칙. 이상 라벨을 쓰지 않는다.

1) 알림 수 한계: 한 감시 창(교대 또는 정한 단위 수)에서 알림이 난 단위 수를, 보정 조건부 예측분포
   Beta-Binomial(m, l, n+1−l)의 95·99백분위와 비교한다. m=창의 알림 단위 수, n=보정 단위 수, l=⌊α(n+1)⌋.
   문턱이 보정 n단위 점수의 l번째 최댓값이면, 같은 조건의 새 정상 단위가 알림을 낼 확률은 Beta(l, n+1−l)을 따른다(교환가능성).
   2단계(점검 요청)는 1단계 알림 단위의 부분집합이라 같은 한계 안에 있다.
2) 전류 수준 이동: 창에 든 기록구간 전류 진폭(√2×평균 제거 RMS)의 중앙값을 정상 기준 자료의 중앙값으로 나눈다.
   정상 기준 자료를 60구간 블록으로 나눈 블록 중앙값 비의 범위 위로 벗어나면 "상승 이동"이다. 대회 정상 하루 안에서도
   10분 블록 전류가 0.85~1.29배 오르내리므로 좁은 한계를 두지 않는다. 그래서 몇 % 수준의 이동은 잡지 못한다.
   범위 아래(저부하)는 참고로만 적는다. 대회에서 가장 조용한 시간대(A 평가 구간)는 알림이 늘지 않았다.
3) 조치 분기: 한 창이 99백분위를 넘거나, 95백분위 초과 또는 상승 이동이 연속 2개 창에서 나면 조치 대상이다.
   - 운전 조건 변경 기록(작업자 입력: 금형·가압력·생산품 변경)이 그 창에 있거나 전류 수준이 상승 이동했으면 "재보정 검토"
     (정상 운전변화일 가능성).
   - 변경 기록도 수준 이동도 없으면 "설비 점검 요청(열화 의심)". 점검 결과가 "정상 확인"일 때만 그 기간을 재보정 자료로 쓴다.
   자동으로 재보정하지 않는다. 창의 알림 근거 구성(진동 크기·전류 성분 경보 행 비율)을 함께 적는다.
4) 결과 기록: 대기열에 확인 시각·담당·결과·조치·상태 열을 둔다. 결과가 "정상 확인"인 건만 정상으로 닫힌다.
   재보정(recalibrate.py --outcomes)은 정상 확인으로 닫히지 않은 건의 의심 시간창을 자료에서 뺀다.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats

from model import D, ALERT_UNIT_ROWS, alert_units, layout

OUTCOME_COLUMNS = ("confirmed_at", "owner", "outcome", "measure", "status")   # 확인 시각, 담당, 결과, 조치, 상태
OUTCOME_LABELS = dict(confirmed_at="확인 시각", owner="담당", outcome="결과", measure="조치", status="상태")
OUTCOMES = ("정상 확인", "이상 확인", "보류")
STATUSES = ("열림", "닫힘")
CONSECUTIVE = 2          # 재보정 검토로 넘기는 연속 창 수
BLOCK_RECORDS = 60       # 전류 수준 기준 범위를 잴 블록 크기(기록구간 수)
MIN_AMP_ROWS = 10        # 진폭을 잴 최소 기록 길이


def beta_params(alpha, n_cal):
    l = math.floor(alpha * (n_cal + 1) + 1e-9)
    return l, n_cal + 1 - l


def alert_limit(alpha, n_cal, units, level=.95):
    """m개 알림 단위에서 허용하는 알림 단위 수(보정 조건부 Beta-Binomial 백분위)."""
    if units <= 0:
        return 0
    return int(stats.betabinom.ppf(level, int(units), *beta_params(alpha, n_cal)))


def record_amplitude(frame):
    """기록구간별 전류 진폭 √2×(평균 제거 RMS). 짧은 기록(MIN_AMP_ROWS 미만)과 수집 오류 행은 뺀다."""
    status, seg = layout(frame)
    cur = pd.to_numeric(frame[D.SENSORS[2]], errors="coerce").to_numpy(float)
    ok = status == "ok"
    s = pd.DataFrame(dict(seg=seg[ok], x=cur[ok]))
    g = s.groupby("seg").x
    amp = np.sqrt(2) * g.std(ddof=0)
    return amp[g.size() >= MIN_AMP_ROWS]


class Reference:
    """정상 기준 자료(학습+보정)의 전류 진폭 기준."""

    def __init__(self, median, band_low, band_high, blocks):
        self.median, self.band_low, self.band_high, self.blocks = float(median), float(band_low), float(band_high), int(blocks)

    @classmethod
    def from_frame(cls, normal):
        amp = record_amplitude(normal)
        med = float(amp.median())
        block = np.arange(len(amp)) // BLOCK_RECORDS
        ratios = amp.groupby(block).median() / med
        return cls(med, ratios.min(), ratios.max(), len(ratios))

    def as_dict(self):
        return dict(median=self.median, band_low=self.band_low, band_high=self.band_high, blocks=self.blocks)


ACTION_RECALIBRATE = "재보정 검토(운전 조건 변경·수준 이동)"
ACTION_INSPECT = "설비 점검 요청(열화 의심)"


def monitor_windows(predictions, frame, alpha, n_cal, reference, window_units=60, operating_changes=()):
    """감시 창별 알림 단위 수·한계·초과, 1·2단계 알림 수, 근거 구성, 전류 수준 비·이동, 권장 조치.
    operating_changes: 운전 조건 변경 시각 목록(작업자 입력). 창의 시간 범위에 있으면 그 창의 초과를 운전변화로 본다."""
    p = predictions
    block = p.alert_unit.to_numpy() if "alert_unit" in p else p.position.to_numpy() // ALERT_UNIT_ROWS
    unit = alert_units(p.record_id.to_numpy(), np.asarray(block) * ALERT_UNIT_ROWS)
    reason = p.reason.astype(str) if "reason" in p else pd.Series("", index=p.index)
    alarm_rows = p.alarm.to_numpy() == 1
    per_unit = pd.DataFrame(dict(unit=unit, record=p.record_id.to_numpy(), alarm=p.alarm.to_numpy(), note=p.notification.to_numpy(),
                                 esc=p.escalation.to_numpy() if "escalation" in p else 0,
                                 t=pd.to_datetime(p.timestamp, format="mixed", utc=True, errors="coerce"),
                                 mag=alarm_rows & reason.str.contains("magnitude").to_numpy(),
                                 cur=alarm_rows & reason.str.contains("waveform|dynamics").to_numpy(), arows=alarm_rows)).groupby("unit").agg(
        record=("record", "first"), alarm=("alarm", "max"), note=("note", "sum"), esc=("esc", "sum"), t0=("t", "min"), t1=("t", "max"),
        mag=("mag", "sum"), cur=("cur", "sum"), arows=("arows", "sum"))
    changes = pd.to_datetime(pd.Series(list(operating_changes), dtype=object), format="mixed", utc=True, errors="coerce").dropna()
    per_unit["window"] = np.arange(len(per_unit)) // window_units
    amp = record_amplitude(frame)
    rows, run_exceed, run_drift = [], 0, 0
    for w, g in per_unit.groupby("window"):
        m = len(g)
        limit95, limit99 = alert_limit(alpha, n_cal, m), alert_limit(alpha, n_cal, m, .99)
        a = amp.reindex(g.record.unique()).dropna()
        ratio = float(a.median() / reference.median) if len(a) else np.nan
        k = int(g.alarm.sum())
        exceed, exceed99 = k > limit95, k > limit99
        drift_up = bool(np.isfinite(ratio) and ratio > reference.band_high)
        run_exceed = run_exceed + 1 if exceed else 0
        run_drift = run_drift + 1 if drift_up else 0
        review = exceed99 or run_exceed >= CONSECUTIVE or run_drift >= CONSECUTIVE
        changed = bool(((changes >= g.t0.min()) & (changes <= g.t1.max())).any()) if len(changes) else False
        action = "관측 지속" if not review else (ACTION_RECALIBRATE if (changed or run_drift >= 1) else ACTION_INSPECT)
        n_alarm = int(g.arows.sum())
        rows.append(dict(window=int(w), start=str(g.t0.min()), end=str(g.t1.max()), units=m, alerted_units=k, limit95=limit95, limit99=limit99,
                         exceed=bool(exceed), exceed99=bool(exceed99), operating_change=changed,
                         alarm_rows=n_alarm, share_magnitude=float(g.mag.sum() / n_alarm) if n_alarm else np.nan,
                         share_current=float(g.cur.sum() / n_alarm) if n_alarm else np.nan, recommended_action=action,
                         recalibration_data="점검 '정상 확인' 뒤에만 재보정 자료" if action == ACTION_INSPECT else "",
                         level1_notifications=int(g.note.sum()), level2_escalations=int(g.esc.sum()),
                         current_ratio=ratio, band_low=reference.band_low, band_high=reference.band_high, drift_up=drift_up,
                         low_load=bool(np.isfinite(ratio) and ratio < reference.band_low), recalibration_review=bool(review),
                         reason="+".join(n for n, yes in (("99백분위 초과", exceed99), ("95백분위 연속 초과", run_exceed >= CONSECUTIVE),
                                                          ("전류 상승 이동 연속", run_drift >= CONSECUTIVE)) if yes)))
    return pd.DataFrame(rows)


def gain_scenarios(model, reference, frame, alpha, gains=(1.0, 1.05, 1.1, 1.2, 1.3, 1.5), window_units=60, operating_changes=()):
    """정상 운전변화 모의: 전류 전체에 배율 k를 곱한 정상 평가 자료에서 감시 규칙이 무엇을 내는지(analysis/press_dayshift와 같은 배율)."""
    rows = []
    for k in gains:
        f = D.inputs_only(frame).copy()
        f[D.SENSORS[2]] = pd.to_numeric(f[D.SENSORS[2]], errors="coerce") * k
        win = monitor_windows(model.predict(f, alpha), f, alpha, len(model.cal), reference, window_units, operating_changes)
        rows.append(dict(gain=k, windows=len(win), alerted_units=int(win.alerted_units.sum()), units=int(win.units.sum()),
                         alerted_by_window="/".join(map(str, win.alerted_units)), limit95=int(win.limit95.iloc[0]), limit99=int(win.limit99.iloc[0]),
                         windows_exceed=int(win.exceed.sum()), windows_exceed99=int(win.exceed99.sum()), windows_drift_up=int(win.drift_up.sum()),
                         windows_low_load=int(win.low_load.sum()),
                         max_current_ratio=float(win.current_ratio.max()), recalibration_review=bool(win.recalibration_review.any()),
                         first_review_window=int(win.window[win.recalibration_review].min()) if win.recalibration_review.any() else -1))
    return pd.DataFrame(rows)


def exclude_unconfirmed(frame, outcomes):
    """결과가 "정상 확인"이 아닌 건(빈 결과 포함)의 의심 시간창 행을 뺀다. 창이 열려 있으면 자료 끝(또는 처음)까지 뺀다."""
    t = pd.to_datetime(frame[D.TIME], format="mixed", utc=True, errors="coerce")
    o = outcomes.copy()
    o["outcome"] = o.get("outcome", pd.Series("", index=o.index)).fillna("").astype(str)
    open_cases = o[o.outcome.ne("정상 확인")]
    drop = np.zeros(len(frame), bool)
    for r in open_cases.itertuples():
        lo = pd.to_datetime(getattr(r, "suspect_from", "") or getattr(r, "first_timestamp", ""), format="mixed", utc=True, errors="coerce")
        hi = pd.to_datetime(getattr(r, "suspect_to", "") or "", format="mixed", utc=True, errors="coerce")
        drop |= ((t >= lo) if pd.notna(lo) else True) & ((t <= hi) if pd.notna(hi) else True)
    kept = frame[~drop].reset_index(drop=True)
    return kept, dict(cases=int(len(o)), unconfirmed_cases=int(len(open_cases)), rows_removed=int(drop.sum()), rows_kept=int(len(kept)))


def budget_design(frame, alpha, n_cal, target=None):
    """교대 8시간 1단계 알림: 입력 자료의 단위 밀도로 명목·보정 95% 환산. 예산을 주면 필요한 α·보정 단위·정상 수집 시간."""
    status, seg = layout(frame)
    units = alert_units(seg, D.segment_positions(seg)[0])
    t = pd.to_datetime(frame[D.TIME], format="mixed", utc=True, errors="coerce")
    hours = (t.max() - t.min()).total_seconds() / 3600
    uph = (int(units.max()) + 1) / hours if hours > 0 and len(units) else float("nan")
    l, b = beta_params(alpha, n_cal)
    out = dict(units_per_elapsed_hour=uph, nominal_rate=l / (n_cal + 1), calibrated95_rate=float(stats.beta.ppf(.95, l, b)),
               nominal_alerts_per_8h=l / (n_cal + 1) * uph * 8, calibrated95_alerts_per_8h=float(stats.beta.ppf(.95, l, b)) * uph * 8,
               note="같은 운전 조건·수집 밀도의 정상(교환가능성) 가정. 2단계는 명목값이 없고 관측값만 있다")
    if target:
        a = target / (uph * 8)
        n_req = math.ceil(1 / a - 1e-9) - 1
        out.update(target_alerts_per_8h=float(target), alpha_required=a, calibration_units_required=n_req,
                   normal_collection_hours_required=n_req / uph, within_budget=bool(out["nominal_alerts_per_8h"] <= target),
                   advice=(f"1단계는 화면 기록만 하고 출동은 2단계(점검 요청)로 한정하거나, α≈{a:.3%}에 맞춰 보정 단위 {n_req}개"
                           f"(정상 수집 약 {n_req / uph:.1f}시간)를 모은다. 현재 구현의 α 선택지는 1·3·5%다"))
    return out


def main(argv=None):
    """교대 감시 명령: 한 교대(또는 임의 기간)의 CSV를 저장 모델로 추론해 창별 표를 쓴다."""
    import argparse
    import sys
    from pathlib import Path
    from model import load_bundle, HERE, ALPHAS, timing_warning
    import runtime
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, required=True, help="감시할 기간의 CSV(TimeStamp, AI0_Vibration, AI1_Vibration, AI2_Current)")
    ap.add_argument("--split", choices=tuple(D.SPLITS), default="B")
    ap.add_argument("--model", type=Path, help="모델 JSON(기본 artifacts/guard_<split>.json, 재보정 모델도 가능)")
    ap.add_argument("--reference", type=Path, help="정상 기준 CSV(학습+보정). 기본은 대회 정상 자료의 해당 분할 학습+보정")
    ap.add_argument("--alpha", type=float, choices=ALPHAS, default=.01)
    ap.add_argument("--window", type=int, default=60, help="감시 창의 알림 단위 수")
    ap.add_argument("--changes", type=Path, help="운전 조건 변경 기록 CSV(열 time)")
    ap.add_argument("--out", type=Path, help="창별 표 CSV")
    args = ap.parse_args(argv)
    runtime.setup()
    model = load_bundle(args.model or HERE / "artifacts" / f"guard_{args.split}.json")
    if args.reference:
        reference = Reference.from_frame(pd.read_csv(args.reference))
    else:
        normal, _, _ = D.load()
        sp = D.split_normal(normal, D.segments(normal), args.split)
        reference = Reference.from_frame(pd.concat([sp["train"], sp["cal"]], ignore_index=True))
    frame = pd.read_csv(args.csv)
    pred = model.predict(frame, args.alpha)
    changes = pd.read_csv(args.changes).time.tolist() if args.changes else ()
    win = monitor_windows(pred, frame, args.alpha, len(model.cal), reference, args.window, changes)
    if args.out:
        win.to_csv(args.out, index=False)
    warn = timing_warning(pred)
    if warn:
        print(warn, file=sys.stderr)
    cols = ["window", "units", "alerted_units", "limit95", "limit99", "level1_notifications", "level2_escalations", "current_ratio", "recommended_action"]
    print(win[cols].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
