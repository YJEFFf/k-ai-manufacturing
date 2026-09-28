"""새 날짜·설비의 정상 CSV로 v2를 다시 적합·보정하고 수락 검사를 기록한다. 이상 라벨은 쓰지 않는다.

    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python yejun/press_guard/recalibrate.py \
        --normal new_normal.csv --out site_model.json --report site_report.json [--alpha 0.01] [--cal-units 120] [--holdout-units 60]
        [--outcomes cases_with_outcomes.csv] [--windows monitor_windows_with_outcomes.csv] [--target-alerts-per-8h 3]

절차. 보정·알림 단위는 기록구간 안의 50행 블록이다(model.alert_units). 대회처럼 간헐 수집이면 기록구간 하나가 한 단위다.
1) 시간 순서대로 학습 / 보정 / 수락 검사로 나눈다. 수락 검사는 맨 뒤 --holdout-units개, 보정은 그 앞 --cal-units개, 나머지가 학습이다.
2) α에서 경보가 나려면 보정 단위가 ⌈1/α⌉−1개 이상이어야 한다(최소 p값 1/(n+1)). α=1%면 99개다. 모자라면 중단한다.
3) GuardModel.fit으로 학습·보정한다.
4) 수락 검사
   (a) 수락 구간에서 알림이 난 단위 수가 보정 조건부 예측분포 Beta-Binomial(단위 수 m, l, n+1−l)의 95백분위 이하인가.
       l=⌊α(n+1)⌋. 문턱이 보정 n단위의 l번째 최댓값이면 새 정상 단위의 알림 확률은 Beta(l, n+1−l)을 따른다(교환가능성).
       이항분포(명목 비율 고정)는 보정 표본의 흔들림을 빼서 정상 보정도 5%보다 자주 거부한다(α=5%·수락 60단위: 6.0%).
       보고서에는 실제 알림률이 명목의 2·3배일 때 이 검사가 거부할 확률(검정력)도 적는다.
   (b) 수락 구간 중 30행 이상 단위에 10행째부터 전류 잡음 0.2σ, 전류 오프셋 0.4×진폭, 진동 잡음 4σ를 더했을 때 2초(20행) 안 탐지율이 각각 90% 이상인가.
       주입 세기는 보완 실험 E1에서 동결 모델이 두 분할 모두 95% 이상 잡은 세기다(결과를 본 뒤 정한 운영 기준, analysis/press_supplement).
   (c) 운전 범위 점검(경고만, 수락 여부는 바꾸지 않는다). 17행 이상 단위의 전류 RMS(단위 평균 제거)·진동 SD 가운데 보정 단위의
       최솟값~최댓값 밖에 놓인 수락 단위 수가 교환가능 한도(세 특징을 합쳐 5%)를 넘으면 경고한다. 보정 자료가 어떤 운전 상태(예: 부하)를
       덮지 못하면 그 상태에서 문턱이 맞지 않을 수 있다. 교환가능하면 새 단위 하나가 보정 범위 밖일 확률은 2/(n+1)이다.
5) 모두 통과하면 모델을 저장한다. 실패하면 저장하지 않고 종료 코드 1을 돌려준다(--save-failed면 저장하되 보고서에 실패를 남긴다).
이 검사는 새 자료의 정상 알림 수준과 인공 이상 반응을 확인할 뿐이며, 실제 고장 탐지 성능을 보장하지 않는다.
정상 자료만 쓰므로 라벨 확률 보정기는 만들지 않는다. 저장 모델의 확률·우도비 열 4개는 비고 사전 비율 π는 쓰이지 않는다.

--outcomes: 점검 결과를 기록한 대기열 CSV(콘솔 내보내기). "정상 확인"으로 닫히지 않은 건의 의심 시간창은 재보정 자료에서 뺀다
(확인된 정상 구간만 정상 기준으로 쓴다, monitor.exclude_unconfirmed).
--windows: monitor.py의 창별 CSV에 outcome 열을 더한 파일. 조치 대상 창(재보정 검토·설비 점검 요청)은 outcome이
"정상 확인"일 때만 남긴다. 변경 기록이 있어도 확인을 대신하지 않는다. 결과가 비거나 열이 없으면 미확인으로 보고 기간 전체를 뺀다.
--target-alerts-per-8h: 교대(8시간)당 1단계 알림 예산. 입력 자료의 단위 밀도로 명목·보정 95% 알림 수를 환산하고, 예산을 맞추려면
필요한 α·보정 단위·정상 수집 시간을 보고서에 적는다(analyze.py의 alert_budget_design_v2.csv와 같은 식). 수락 여부는 바꾸지 않는다.
"""
from pathlib import Path
import argparse
from fractions import Fraction
import json
import math
import sys

import numpy as np
import pandas as pd
from scipy import stats

from model import GuardModel, D, ALPHAS, ALERT_UNIT_ROWS, TIME_TOL_S, SHORT_RECORD_WARN, alert_units, layout
from monitor import alert_limit, exclude_unconfirmed, exclude_unconfirmed_windows, budget_design
import runtime

MIN_TRAIN_UNITS = 15          # 보완 실험 E3에서 확인한 가장 작은 학습 단위 수
COVERAGE_MIN_ROWS = 17        # 운전 범위 점검에 쓰는 단위의 최소 길이(0.6 Hz 한 주기 이상, 운전 상태 판정과 같은 길이)
COVERAGE_FAMILY_ALPHA = .05   # 세 특징을 합친 오경고 확률(본페로니)
MIN_INJECTION_UNITS = 10      # 주입 탐지율을 판정할 최소 단위 수
INJECTION = (("cur_noise", .2), ("cur_offset", .4), ("vib_noise", 4.0))
T0, WINDOW, MIN_UNIT_ROWS, DETECT_RATE = 10, 20, 30, .9


def min_cal_units(alpha):
    return math.ceil(1 / alpha - 1e-9) - 1


def split_units(frame, n_cal, n_holdout):
    status, seg = layout(frame)
    bad = int((status != "ok").sum())
    if bad:
        raise ValueError(f"정상 CSV에 수집 오류 행 {bad}개가 있다. 학습·보정에는 유효한 정상 입력만 쓴다")
    units = alert_units(seg, D.segment_positions(seg)[0])
    total = int(units.max()) + 1 if len(units) else 0
    n_train = total - n_cal - n_holdout
    if n_train < MIN_TRAIN_UNITS:
        raise ValueError(f"단위가 부족하다: 전체 {total}개 = 학습 {n_train} + 보정 {n_cal} + 수락 검사 {n_holdout}. 학습은 {MIN_TRAIN_UNITS}개 이상이어야 한다")
    parts = {"train": units < n_train, "cal": (units >= n_train) & (units < n_train + n_cal), "holdout": units >= n_train + n_cal}
    return {k: frame[m].reset_index(drop=True) for k, m in parts.items()}, total, n_train


def usage(frame):
    t = pd.to_datetime(frame[D.TIME], format="mixed")
    return dict(rows=len(frame), sensor_minutes=len(frame) * D.DT / 60, elapsed_minutes=(t.max() - t.min()).total_seconds() / 60)


def unit_layout(frame):
    _, seg = layout(frame)
    pos = D.segment_positions(seg)[0]
    units = alert_units(seg, pos)
    in_unit = pos - (pos // ALERT_UNIT_ROWS) * ALERT_UNIT_ROWS
    size = pd.Series(units).map(pd.Series(units).value_counts()).to_numpy()
    return units, in_unit, size


def unit_features(frame):
    """단위별 운전 특징: 전류 RMS(단위 평균 제거, ddof 0)와 두 진동 SD(ddof 0). COVERAGE_MIN_ROWS 미만 단위는 뺀다."""
    units, _, _ = unit_layout(frame)
    x = D.inputs_only(frame)[D.SENSORS].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    rows = []
    for u in np.unique(units):
        v = x[units == u]
        if len(v) >= COVERAGE_MIN_ROWS:
            rows.append(dict(current_rms=float(np.sqrt(np.mean((v[:, 2] - v[:, 2].mean()) ** 2))), vib0_sd=float(v[:, 0].std()), vib1_sd=float(v[:, 1].std())))
    return pd.DataFrame(rows, columns=["current_rms", "vib0_sd", "vib1_sd"])


def outside_pmf(n, m):
    """교환가능하면(보정 n·수락 m단위의 모든 배열이 같은 확률) 보정 최솟값~최댓값 밖에 놓이는 수락 단위 수 T의 분포.
    앞쪽 a개·뒤쪽 t−a개가 수락 단위인 배열 수를 세면 P(T=t) = (t+1)·C(n+m−t−2, n−2) / C(n+m, n)이다(n ≥ 2)."""
    total = math.comb(n + m, n)
    return [Fraction((t + 1) * math.comb(n + m - t - 2, n - 2), total) for t in range(m + 1)]


def outside_limit(n, m, q):
    """T의 q분위(가장 작은 t로 P(T ≤ t) ≥ q). 배열 수를 정수로 누적해 작은 t에서 멈춘다(보정 단위가 수천 개여도 빠르다)."""
    target, cum = Fraction(q) * math.comb(n + m, n), 0
    for t in range(m + 1):
        cum += (t + 1) * math.comb(n + m - t - 2, n - 2)
        if cum >= target:
            return t
    return m


def coverage(cal, holdout):
    """보정 자료가 수락 구간의 운전 범위를 덮는가(경고용, 수락 여부와 무관)."""
    fc, fh = unit_features(cal), unit_features(holdout)
    n, m = len(fc), len(fh)
    out = dict(min_rows=COVERAGE_MIN_ROWS, cal_units=n, holdout_units=m, family_alpha=COVERAGE_FAMILY_ALPHA, features={}, flagged=[])
    if n < 2 or m < 1:
        out["note"] = f"{COVERAGE_MIN_ROWS}행 이상 단위가 모자라 판정하지 않음"
        return out
    limit = outside_limit(n, m, 1 - COVERAGE_FAMILY_ALPHA / len(fc.columns))
    out["expected_outside"] = 2 * m / (n + 1)
    for c in fc.columns:
        lo, hi = float(fc[c].min()), float(fc[c].max())
        below, above = int((fh[c] < lo).sum()), int((fh[c] > hi).sum())
        out["features"][c] = dict(cal_min=lo, cal_max=hi, holdout_below=below, holdout_above=above, limit=limit, flagged=below + above > limit)
    out["flagged"] = [c for c, v in out["features"].items() if v["flagged"]]
    return out


def inject(frame, model, family, level, mask, rng):
    out = D.inputs_only(frame).copy()
    for c in D.SENSORS:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    n = int(mask.sum())
    if family == "cur_noise":
        out.loc[mask, D.SENSORS[2]] += level * model.scale[2] * rng.standard_normal(n)
    elif family == "cur_offset":
        out.loc[mask, D.SENSORS[2]] += level * np.sqrt(2) * model.scale[2]
    elif family == "vib_noise":
        for k, c in enumerate(D.SENSORS[:2]):
            out.loc[mask, c] += level * model.scale[k] * rng.standard_normal(n)
    return out


def _beta_params(alpha, n_cal):
    l = math.floor(alpha * (n_cal + 1) + 1e-9)
    return l, n_cal + 1 - l


def acceptance(model, holdout, alpha, n_cal):
    checks = []
    pred = model.predict(holdout, alpha)
    units, in_unit, size = unit_layout(holdout)
    per_unit = pd.Series(pred.alarm.to_numpy()).groupby(units).max()
    m = int(len(per_unit))
    nominal = math.floor(alpha * (n_cal + 1) + 1e-9) / (n_cal + 1)
    limit = alert_limit(alpha, n_cal, m)
    power = {f"{k}x": float(stats.binom.sf(limit, m, min(1.0, k * nominal))) for k in (2, 3)}
    checks.append(dict(name="정상 알림 단위 수가 보정 조건부 Beta-Binomial 95백분위 이하", value=int(per_unit.sum()), units=m,
                       nominal_rate=nominal, limit=limit, ok=bool(per_unit.sum() <= limit),
                       false_reject_rate=float(stats.betabinom.sf(limit, m, *_beta_params(alpha, n_cal))),
                       power_if_rate_multiplied=power,
                       note=f"한도 {limit} · 정상에서 거부할 확률 {float(stats.betabinom.sf(limit, m, *_beta_params(alpha, n_cal))):.1%} · "
                            f"실제 알림률이 명목의 2·3배일 때 거부할 확률(검정력) {power['2x']:.0%}·{power['3x']:.0%}"))
    eligible = size >= MIN_UNIT_ROWS
    mask = eligible & (in_unit >= T0)
    n_eligible = int(pd.Series(units[eligible]).nunique())
    rng = np.random.default_rng(0)
    for family, level in INJECTION:
        p = model.predict(inject(holdout, model, family, level, mask, rng), alpha)
        in_window = (p.alarm.to_numpy() == 1) & (in_unit >= T0) & (in_unit < T0 + WINDOW)
        hit = pd.Series(in_window[eligible]).groupby(units[eligible]).any()   # 30행 이상 단위마다 2초 안 경보 여부
        rate = float(hit.mean()) if len(hit) else float("nan")
        enough = n_eligible >= MIN_INJECTION_UNITS
        checks.append(dict(name=f"고장 주입 {family} {level:g} 2초 안 탐지율 ≥ {DETECT_RATE:.0%}", value=rate, units=n_eligible,
                           limit=DETECT_RATE, ok=bool(enough and rate >= DETECT_RATE),
                           note="" if enough else f"30행 이상 단위가 {n_eligible}개라 판정 불가(최소 {MIN_INJECTION_UNITS}개). 기록이 짧으면 수집 시각 간격을 확인한다"))
    return checks


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--normal", type=Path, required=True, help="새 날짜·설비의 정상 운전 CSV(TimeStamp, AI0_Vibration, AI1_Vibration, AI2_Current)")
    ap.add_argument("--out", type=Path, required=True, help="저장할 모델 JSON")
    ap.add_argument("--report", type=Path, help="수락 검사 보고서 JSON(기본: 모델 이름 + _report.json)")
    ap.add_argument("--alpha", type=float, choices=ALPHAS, default=.01)
    ap.add_argument("--cal-units", type=int, default=120)
    ap.add_argument("--holdout-units", type=int, default=60)
    ap.add_argument("--name", default="recalibrated", help="모델 split 이름(model_id에 붙는다)")
    ap.add_argument("--save-failed", action="store_true", help="수락 검사에 실패해도 모델을 저장한다(보고서에 실패가 남는다)")
    ap.add_argument("--outcomes", type=Path, help="점검 결과가 기록된 대기열 CSV. 정상 확인으로 닫히지 않은 건의 의심 시간창은 뺀다")
    ap.add_argument("--windows", type=Path, help="monitor.py 창별 CSV(outcome 열). 조치 대상 창은 정상 확인일 때만 남긴다")
    ap.add_argument("--target-alerts-per-8h", type=float, help="교대 8시간당 1단계 알림 예산(보고서의 설계 환산용)")
    args = ap.parse_args(argv)
    runtime.setup()
    report_path = args.report or args.out.with_name(args.out.stem + "_report.json")
    need = min_cal_units(args.alpha)
    try:
        if args.cal_units < need:
            raise ValueError(f"α={args.alpha:g}에서 경보가 나려면 보정 단위가 {need}개 이상이어야 한다(요청 {args.cal_units}개)")
        frame = pd.read_csv(args.normal)
        excluded = None
        if args.outcomes:
            frame, excluded = exclude_unconfirmed(frame, pd.read_csv(args.outcomes))
        excluded_windows = None
        if args.windows:
            frame, excluded_windows = exclude_unconfirmed_windows(frame, pd.read_csv(args.windows))
        status, seg0 = layout(frame)
        ok_rows = int((status == "ok").sum())
        mean_len = ok_rows / max(len(np.unique(seg0[status == "ok"])), 1)
        timing = (f" 수집 시각 간격 확인: 평균 기록 길이 {mean_len:.1f}행(0.1초 ± {TIME_TOL_S * 1000:.0f} ms 밖의 간격은 기록 경계가 된다)"
                  if ok_rows >= 50 and mean_len < SHORT_RECORD_WARN else "")
        if timing:
            print("경고:" + timing, file=sys.stderr)
        try:
            parts, total, n_train = split_units(frame, args.cal_units, args.holdout_units)
        except ValueError as exc:
            raise ValueError(str(exc) + timing) from None
    except (ValueError, KeyError, OSError, pd.errors.ParserError) as exc:
        print(f"재보정 중단: {exc}", file=sys.stderr)
        return 2
    model = GuardModel.fit(parts["train"], parts["cal"], split=args.name, input_hashes={"normal_csv": D.sha256_file(args.normal)})
    checks = acceptance(model, parts["holdout"], args.alpha, len(model.cal))
    passed = all(c["ok"] for c in checks)
    cover = coverage(parts["cal"], parts["holdout"])
    saved = passed or args.save_failed
    if saved:
        model.save(args.out)
    report = dict(input=str(args.normal), input_sha256=D.sha256_file(args.normal), alpha=args.alpha, alert_unit_max_rows=ALERT_UNIT_ROWS,
                  units=dict(total=total, train=n_train, cal=args.cal_units, holdout=args.holdout_units, min_cal_for_alpha=need),
                  usage={k: usage(v) for k, v in parts.items()}, calibration_units=len(model.cal),
                  checks=checks, passed=passed, coverage=cover, model_saved=bool(saved), model_path=str(args.out) if saved else None,
                  excluded_by_outcomes=excluded,
                  excluded_by_windows=excluded_windows,
                  budget=budget_design(frame, args.alpha, len(model.cal), args.target_alerts_per_8h),
                  note="같은 자료 안의 정상 알림 수준과 인공 이상 반응 확인이다. 실제 고장 탐지 성능·다른 날짜의 오경보율을 보장하지 않는다.")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(D.to_jsonable(report), ensure_ascii=False, indent=2), encoding="utf-8")
    for c in checks:
        print(("통과 " if c["ok"] else "실패 ") + f"{c['name']}: {c['value']}" + (f" ({c['note']})" if c.get("note") else ""))
    for c in cover["flagged"]:
        f = cover["features"][c]
        print(f"경고: 보정 자료가 수락 구간의 운전 범위를 덮지 않는다 — {c} 보정 범위 {f['cal_min']:.4g}~{f['cal_max']:.4g} 밖 수락 단위 "
              f"{f['holdout_below'] + f['holdout_above']}/{cover['holdout_units']}개(교환가능 한도 {f['limit']}). 그 상태를 포함한 정상 자료로 다시 보정한다")
    b = report["budget"]
    print(f"교대 8시간 1단계 알림: 명목 {b['nominal_alerts_per_8h']:.1f}건 · 보정 95% {b['calibrated95_alerts_per_8h']:.1f}건"
          + (f" · 예산 {b['target_alerts_per_8h']:g}건 {'충족' if b['within_budget'] else '초과 → ' + b['advice']}" if b.get("target_alerts_per_8h") else ""))
    print(f"{'수락' if passed else '거부'} · 모델 {'저장 ' + str(args.out) if saved else '저장 안 함'} · 보고서 {report_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
