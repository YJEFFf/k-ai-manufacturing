"""redC: 4회차 새 기능의 반례 시험. 임시 사본(git archive cc1aac2 + 원본 CSV + 같은 SHA-256의 저장 모델)의 모듈만 부른다.

    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python redC_counterexamples.py --root <임시 사본>/yejun

저장소 작업 사본의 파일은 읽지도 쓰지도 않는다. 결과는 이 스크립트 옆 redC_counterexamples.json에 남긴다.
"""
import argparse
import hashlib
import json
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("--root", type=Path, required=True)
ap.add_argument("--only", default="")
args = ap.parse_args()
GUARD = args.root / "press_guard"
sys.path.insert(0, str(GUARD))
import model as M  # noqa: E402
import simulate  # noqa: E402
import monitor  # noqa: E402
import recalibrate  # noqa: E402
from probability import ProbabilityCalibrator  # noqa: E402

D = M.D
assert Path(M.__file__).resolve().parent == GUARD.resolve(), "임시 사본의 모듈이 아니다"
RESULT, T0 = {}, time.time()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def section(name):
    def wrap(fn):
        if args.only and name not in args.only.split(","):
            return fn
        t = time.time()
        try:
            RESULT[name] = fn()
        except Exception as exc:  # 시험 자체의 오류도 기록한다
            RESULT[name] = dict(error=repr(exc), trace=traceback.format_exc()[-1500:])
        RESULT[name]["seconds"] = round(time.time() - t, 1)
        print(f"[{name}] {RESULT[name]['seconds']}초", json.dumps(RESULT[name], ensure_ascii=False, default=str)[:3000], flush=True)
        return fn
    return wrap


normal, abnormal, _ = D.load()
models = {s: M.load_bundle(GUARD / "artifacts" / f"guard_{s}.json") for s in "AB"}
split_b = D.split_normal(normal, D.segments(normal), "B")
test_b = D.inputs_only(split_b["test"]).reset_index(drop=True)
rec_b = M.layout(test_b)[1]
ABN = D.inputs_only(abnormal).reset_index(drop=True)


def record(k):
    return test_b[rec_b == k].reset_index(drop=True)


def at(frame, start):
    out = frame.copy().reset_index(drop=True)
    out[D.TIME] = (pd.Timestamp(start) + pd.to_timedelta(np.arange(len(out)) * D.DT, unit="s")).astype(str)
    return out


def chain(frames, gaps, start="2022-07-12 00:00:00"):
    """frames를 차례로 잇는다. gaps[i]는 i번째 기록의 끝 행과 i+1번째 기록의 첫 행 사이의 시간(초)."""
    parts, t = [], pd.Timestamp(start)
    for i, f in enumerate(frames):
        parts.append(at(f, t))
        if i < len(gaps):
            t = t + pd.Timedelta(seconds=(len(f) - 1) * D.DT) + pd.Timedelta(seconds=gaps[i])
    return pd.concat(parts, ignore_index=True)


def stream(model, frame, chunk, alpha=.01):
    det = M.StreamDetector(model, alpha)
    return pd.concat([det.push(frame.iloc[i:i + chunk]) for i in range(0, len(frame), chunk)], ignore_index=True)


def same(a, b):
    try:
        pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True), rtol=1e-11, atol=1e-11)
        return True, ""
    except AssertionError as exc:
        return False, str(exc).replace("\n", " ")[:400]


def stream_equal(model, frame, chunks=(1, 7, 128), alpha=.01):
    batch = model.predict(frame, alpha)
    out = {}
    for c in chunks:
        ok, why = same(stream(model, frame, c, alpha), batch)
        out[str(c)] = True if ok else why
    return batch, out


def summarize(pred, model_frame=None):
    q = M.cases(pred)
    inc = M.incidents(q, pred) if len(q) else pd.DataFrame()
    inc0 = M.incidents(q) if len(q) else pd.DataFrame()
    return dict(rows=len(pred), status=pred.status.value_counts().to_dict(), records=int(pred.record_id.nunique()), alarm_rows=int(pred.alarm.sum()),
                incident_starts=int(pred.incident_notification.sum()), incident_escalations=int(pred.incident_escalation.sum()),
                cases=len(q), case_alarm_rows=q.alarm_rows.tolist() if len(q) else [], case_levels=q.level.tolist() if len(q) else [],
                incidents=len(inc), incident_levels=inc.level.tolist() if len(inc) else [],
                incident_alarm_rows=inc.alarm_rows.tolist() if len(inc) else [],
                escalation_rows=[None if pd.isna(v) else int(v) for v in inc.escalation_row] if len(inc) else [],
                escalation_rows_without_predictions=[None if pd.isna(v) else int(v) for v in inc0.escalation_row] if len(inc0) else [],
                suspect=[(a, b, int(o)) for a, b, o in zip(inc.suspect_from, inc.suspect_to, inc.suspect_open)] if len(inc) else [],
                negative_suspect_seconds=int((q.suspect_seconds < 0).sum()) if len(q) else 0,
                warning=M.timing_warning(pred))


@section("0_setup")
def _setup():
    return dict(artifact_sha256={p.name: sha(p) for p in sorted((GUARD / "artifacts").glob("*.json"))},
                model_py_sha256=sha(GUARD / "model.py"), b_test_rows=len(test_b), b_test_records=int(rec_b.max() + 1),
                b_false_alarm_records=M.cases(models["B"].predict(test_b)).record_id.tolist())


# ------------------------------------------------------------------ 1. 사건 단계
@section("1a_two_single_alarm_records_gap")
def _gap():
    model, out = models["B"], {}
    for gap in (0.3, 2.0, 59.9, 60.0, 60.1, 61.0, 600.0):
        frame = chain([record(3), record(41)], [gap])
        pred, eq = stream_equal(model, frame)
        s = summarize(pred)
        log = simulate.run(frame, model, .01, chunk=7)
        out[str(gap)] = dict(records=s["records"], case_alarm_rows=s["case_alarm_rows"], incidents=s["incidents"], incident_levels=s["incident_levels"],
                             escalation_rows=s["escalation_rows"], escalation_rows_without_predictions=s["escalation_rows_without_predictions"],
                             simulate_kinds=log[log.notify.eq(1)].kind.tolist(), stream_equals_batch=eq)
    return out


@section("1b_three_or_more_cases")
def _three():
    model = models["B"]
    out = {}
    frame = chain([record(3), record(41), record(150)], [2.0, 2.0])
    pred, eq = stream_equal(model, frame)
    out["3+41+150 (2초 간격)"] = {**summarize(pred), "stream_equals_batch": eq, "simulate": simulate.run(frame, model, .01, chunk=1).query("notify == 1").kind.tolist()}
    frame = chain([record(3), record(41), record(150), record(3), record(41)], [2.0, 70.0, 2.0, 2.0])
    pred, eq = stream_equal(model, frame)
    out["3+41 | 70초 | 150+3+41"] = {**summarize(pred), "stream_equals_batch": eq}
    return out


@section("1c_quiet_or_bad_unit_between_alarms")
def _between():
    """경보 1행 기록 둘 사이에 경보 없는 기록·오류 행 하나가 끼면 60초 안이어도 사건이 갈라지는가."""
    model, out = models["B"], {}
    quiet = record(0)
    frame = chain([record(3), quiet, record(41)], [2.0, 2.0])
    pred, eq = stream_equal(model, frame)
    t = pd.to_datetime(pred.timestamp, format="mixed", utc=True)
    alarms = pred.index[pred.alarm.eq(1)].tolist()
    out["경보 없는 정상 기록 1개가 낌"] = {**summarize(pred), "seconds_between_alarm_rows": float((t[alarms[-1]] - t[alarms[0]]).total_seconds()), "stream_equals_batch": eq}
    # 오류 행 하나(센서 결측)만 끼는 경우. 두 기록 사이 공백은 2초 그대로다.
    a, b = record(3), record(41)
    bad = a.iloc[[0]].copy()
    bad[D.SENSORS[0]] = np.nan
    frame = chain([a, bad, b], [1.0, 1.0])
    pred, eq = stream_equal(model, frame)
    t = pd.to_datetime(pred.timestamp, format="mixed", utc=True)
    alarms = pred.index[pred.alarm.eq(1)].tolist()
    out["결측 센서 값 1행이 낌(총 공백 2초)"] = {**summarize(pred), "seconds_between_alarm_rows": float((t[alarms[-1]] - t[alarms[0]]).total_seconds()), "stream_equals_batch": eq}
    frame = chain([a, b], [2.0])
    frame.loc[len(a), D.TIME] = "bad"      # 둘째 기록 첫 행의 시각만 결측
    pred, eq = stream_equal(model, frame)
    out["둘째 기록 첫 행 시각 결측"] = {**summarize(pred), "stream_equals_batch": eq}
    return out


@section("1d_record_boundary_and_long_record")
def _boundary():
    """기록 경계에 걸친 경우: 이상 기록을 끊김 없이 이어 50행 블록 경계를 넘기고, 경계 바로 앞뒤에 경보가 있는 입력."""
    model, out = models["B"], {}
    seg = D.segments(abnormal)
    parts = [ABN[seg == k] for k in range(4)]
    frame = at(pd.concat(parts, ignore_index=True), "2022-07-12 00:00:00")       # 끊김 없는 한 기록(50행 초과)
    pred, eq = stream_equal(model, frame)
    out["이상 4기록을 끊김 없이 이음"] = {**summarize(pred), "max_position": int(pred.position.max()), "alert_units": int(pred.alert_unit.nunique()), "stream_equals_batch": eq}
    # 경보 1행 기록의 경보 행이 기록 끝에 오도록 자르고, 다음 기록은 경보 행으로 시작하게 자른다.
    a, b = record(3), record(41)
    pa, pb = model.predict(a), model.predict(b)
    ia, ib = int(pa.index[pa.alarm.eq(1)][0]), int(pb.index[pb.alarm.eq(1)][0])
    out["원 기록의 경보 위치"] = dict(record3=ia, record41=ib, len3=len(a), len41=len(b))
    for gap in (0.1, 0.12, 0.13, 2.0):
        frame = chain([a, b], [gap])
        pred, eq = stream_equal(model, frame)
        out[f"끝-첫 행 간격 {gap}초"] = {**summarize(pred), "stream_equals_batch": eq}
    return out


# ------------------------------------------------------------------ 2. 시각 이상
@section("2a_single_future_timestamp_blinds_detector")
def _future():
    """미래 시각 1행(수집 PC 시각 튐) 뒤의 실제 이상 600행이 어떻게 처리되는가."""
    model, out = models["B"], {}
    base = model.predict(ABN)
    out["기준(원본 이상 600행)"] = dict(alarm_rows=int(base.alarm.sum()), detected_records=int(base.groupby("record_id").alarm.max().sum()), records=int(base.record_id.nunique()))
    for label, shift in (("+1시간", pd.Timedelta(hours=1)), ("+1일", pd.Timedelta(days=1)), ("+10초", pd.Timedelta(seconds=10))):
        glitch = record(0).iloc[[0]].copy()
        first = pd.to_datetime(ABN[D.TIME].iloc[0])
        glitch[D.TIME] = str(first + shift)
        frame = pd.concat([glitch, ABN], ignore_index=True)
        pred, eq = stream_equal(model, frame)
        s = summarize(pred)
        log = simulate.run(frame, model, .01, chunk=1)
        out[label] = dict(status=s["status"], alarm_rows=s["alarm_rows"], incident_starts=s["incident_starts"], incident_escalations=s["incident_escalations"],
                          abnormal_rows_withheld=int(pred.status.iloc[1:].eq("bad_time_order").sum()),
                          simulate_notifications=log[log.notify.eq(1)].kind.tolist(), warning=s["warning"], stream_equals_batch=eq)
    return out


@section("2b_duplicates_missing_gaps")
def _messy():
    model, out = models["B"], {}
    rng = np.random.default_rng(20260928)
    # (1) 모든 행이 두 번씩 들어온 입력(시각 중복)
    dup = ABN.loc[ABN.index.repeat(2)].reset_index(drop=True)
    pred, eq = stream_equal(model, dup)
    out["모든 행 중복"] = {**{k: v for k, v in summarize(pred).items() if k not in ("suspect",)}, "stream_equals_batch": eq}
    # (2) 시각 5% 결측
    miss = ABN.copy()
    miss.loc[rng.random(len(miss)) < .05, D.TIME] = ""
    pred, eq = stream_equal(model, miss)
    out["시각 5% 결측"] = {**{k: v for k, v in summarize(pred).items() if k not in ("suspect",)}, "stream_equals_batch": eq}
    # (3) 정상 → 큰 공백(2시간) → 이상 → 큰 공백 → 정상
    frame = pd.concat([at(record(0), "2022-07-12 00:00:00"), at(ABN.iloc[:150], "2022-07-12 02:00:00"), at(record(1), "2022-07-12 04:00:00")], ignore_index=True)
    pred, eq = stream_equal(model, frame)
    out["2시간 공백 사이의 이상"] = {**summarize(pred), "stream_equals_batch": eq}
    # (4) 역순·중복·결측·공백을 섞은 입력
    mixed = pd.concat([at(record(0), "2022-07-12 00:00:00"), at(record(3), "2022-07-12 00:00:07"), at(record(41), "2022-07-12 00:00:05"),
                       at(ABN.iloc[:100], "2022-07-12 00:00:20"), at(record(1), "2022-07-12 00:03:00")], ignore_index=True)
    mixed.loc[[60, 61, 170], D.TIME] = ["", "bad", mixed[D.TIME].iloc[169]]
    mixed.loc[175, D.SENSORS[2]] = np.inf
    pred, eq = stream_equal(model, mixed)
    out["섞은 입력"] = {**summarize(pred), "stream_equals_batch": eq}
    prefix_bad = []
    for stop in (1, 30, 50, 51, 57, 60, 62, 95, 100, 101, 140, 171, 176, 177, 250, len(mixed)):
        ok, why = same(model.predict(mixed.iloc[:stop]), pred.iloc[:stop])
        if not ok:
            prefix_bad.append((stop, why))
    out["섞은 입력: 접두부 예측 = 전체 예측의 접두부"] = prefix_bad or True
    # (5) 파일 전체가 시각 내림차순
    rev = ABN.iloc[::-1].reset_index(drop=True)
    pred, eq = stream_equal(model, rev)
    out["전체 내림차순"] = {**{k: v for k, v in summarize(pred).items() if k not in ("suspect",)}, "stream_equals_batch": eq}
    return out


# ------------------------------------------------------------------ 3. 운전 상태
@section("3a_state_causal_and_chunk_invariant")
def _state():
    model, out = models["B"], {}
    frame = pd.concat([test_b.iloc[:1500], ABN.iloc[:200]], ignore_index=True)
    frame.loc[[40, 41, 700], D.SENSORS[2]] = [np.nan, "x", np.inf]
    frame.loc[900, D.TIME] = ""
    pred, eq = stream_equal(model, frame)
    out["stream_equals_batch"] = eq
    cols = ["record_current_rms", "operating_state", "record_id", "position", "status"]
    bad = []
    for stop in list(range(1, 120)) + [500, 701, 702, 901, 1499, 1500, 1501, 1517, 1700]:
        p = model.predict(frame.iloc[:stop])
        ok, why = same(p[cols], pred[cols].iloc[:stop])
        if not ok:
            bad.append((stop, why))
    out["prefix_state_mismatch"] = bad or "없음(접두부 128개)"
    # 상태 열 직접 재계산: 같은 기록의 그 행까지 원 전류의 평균 제거 RMS
    raw = pd.to_numeric(frame[D.SENSORS[2]], errors="coerce").where(pred.status.eq("ok")).to_numpy(float)
    worst = 0.0
    for r, g in pred.groupby("record_id"):
        x = raw[g.index]
        for i in range(len(x)):
            seen = x[:i + 1]
            seen = seen[np.isfinite(seen)]
            want = np.std(seen) if np.isfinite(x[i]) and len(seen) else np.nan
            got = g.record_current_rms.iloc[i]
            if np.isnan(want) != np.isnan(got):
                worst = np.inf
            elif np.isfinite(want):
                worst = max(worst, abs(want - got))
    out["max_abs_diff_vs_direct_std"] = worst
    return out


@section("3b_state_stability_within_record")
def _flip():
    """인과 누적 RMS 상태가 기록 안에서 바뀌는가(17행 이후의 중간 표시가 기록 끝 상태와 다른 기록 수)."""
    out = {}
    for sid, frame in (("normal_all", D.inputs_only(normal)), ("abnormal", ABN)):
        pred = models["B"].predict(frame)
        g = pred[pred.position >= M.STATE_MIN_ROWS - 1].groupby("record_id")
        final = g.operating_state.last()
        flips = g.operating_state.nunique().gt(1)
        first17 = g.operating_state.first()
        rms_final = g.record_current_rms.last()
        out[sid] = dict(records_ge17=int(len(final)), final_state=final.value_counts().to_dict(), records_with_state_change=int(flips.sum()),
                        state_at_row17_differs_from_final=int((first17 != final).sum()),
                        of_which_final_load=int(((first17 != final) & final.eq("load")).sum()),
                        final_rms_within_5_of_threshold=int(rms_final.sub(M.LOAD_STATE_RMS).abs().lt(5).sum()),
                        min_gap_to_threshold=float(rms_final.sub(M.LOAD_STATE_RMS).abs().min()))
    pred = models["B"].predict(test_b)
    q = M.cases(pred)
    out["B 오경보 3건"] = q[["record_id", "first_alarm_position", "first_alarm_operating_state", "operating_state", "record_current_rms"]].to_dict("records")
    for r in q.itertuples():
        x = pred[pred.record_id.eq(r.record_id)]
        out[f"record {r.record_id} 인과 RMS 경과"] = dict(rms_at_17=float(x.record_current_rms.iloc[16]), rms_min_after17=float(x.record_current_rms.iloc[16:].min()),
                                                        rms_final=float(x.record_current_rms.iloc[-1]), states_after17=x.operating_state.iloc[16:].value_counts().to_dict())
    return out


# ------------------------------------------------------------------ 4. 감시 분기·재보정 자료 필터
@section("4a_monitor_four_branches")
def _monitor():
    model, out = models["B"], {}
    ref = monitor.Reference.from_frame(pd.concat([split_b["train"], split_b["cal"]], ignore_index=True))
    out["reference"] = ref.as_dict()

    def windows(frame, changes=()):
        pred = model.predict(frame, .01)
        return monitor.monitor_windows(pred, frame, .01, len(model.cal), ref, 60, changes)

    cols = ["window", "alerted_units", "limit95", "limit99", "exceed", "exceed99", "operating_change", "current_ratio", "drift_up", "recalibration_review", "recommended_action", "reason"]
    vib = recalibrate.inject(test_b, model, "vib_noise", 2.0, np.ones(len(test_b), bool), np.random.default_rng(0))
    w0 = windows(vib)
    out["진동 2σ·변경 기록 없음"] = w0[cols].to_dict("records")
    w1 = windows(vib, [w0.start.iloc[0], w0.start.iloc[1], w0.start.iloc[2]])
    out["진동 2σ·변경 기록 있음(모든 창)"] = w1[cols].to_dict("records")
    kept, info = monitor.exclude_unconfirmed_windows(vib, w1)
    out["진동 2σ·변경 기록 있음 → 재보정 자료 필터"] = info
    kept0, info0 = monitor.exclude_unconfirmed_windows(vib, w0)
    out["진동 2σ·변경 기록 없음 → 재보정 자료 필터"] = info0
    cur = test_b.copy()
    cur[D.SENSORS[2]] = pd.to_numeric(cur[D.SENSORS[2]]) * 1.5
    w2 = windows(cur)
    out["전류 ×1.5·변경 기록 없음"] = w2[cols].to_dict("records")
    # 전류 ×1.5와 진동 2σ가 함께: 전류 수준 이동 갈래가 열화 갈래를 가린다
    both = vib.copy()
    both[D.SENSORS[2]] = pd.to_numeric(both[D.SENSORS[2]]) * 1.5
    out["전류 ×1.5 + 진동 2σ·변경 기록 없음"] = windows(both)[cols].to_dict("records")
    # 실제 이상 자료에 변경 기록이 있을 때
    wa = monitor.monitor_windows(model.predict(ABN, .01), ABN, .01, len(model.cal), ref, 5, [ABN[D.TIME].iloc[0]])
    out["대회 이상 600행·창 5단위·첫 행에 변경 기록"] = wa[cols].to_dict("records")
    keptA, infoA = monitor.exclude_unconfirmed_windows(ABN, wa)
    out["대회 이상 600행 → 재보정 자료 필터"] = infoA
    return out


@section("4b_windows_filter_edge_cases")
def _filter():
    out = {}
    frame = test_b.iloc[:2000].reset_index(drop=True)
    t = frame[D.TIME]

    def run(rows):
        try:
            kept, info = monitor.exclude_unconfirmed_windows(frame, pd.DataFrame(rows))
            return info
        except Exception as exc:
            return f"{type(exc).__name__}: {exc}"

    base = dict(start=t.iloc[100], end=t.iloc[199], recommended_action=monitor.ACTION_INSPECT)
    for label, outcome in (("정상 확인", "정상 확인"), ("앞뒤 공백", "  정상 확인 "), ("붙여 씀", "정상확인"), ("영문", "normal"), ("빈칸", ""), ("결측", np.nan), ("이상 확인", "이상 확인")):
        out[f"outcome={label}"] = run([{**base, "outcome": outcome}])
    out["outcome 열 없음"] = run([base])
    out["3회차 문구의 조치(재보정 검토(운전 조건 변경·수준 이동))·결과 없음"] = run([{**base, "recommended_action": "재보정 검토(운전 조건 변경·수준 이동)", "outcome": ""}])
    out["조치 앞에 공백"] = run([{**base, "recommended_action": " " + monitor.ACTION_INSPECT, "outcome": ""}])
    out["조치 결측"] = run([{**base, "recommended_action": np.nan, "outcome": ""}])
    out["recommended_action 열 없음"] = run([dict(start=t.iloc[100], end=t.iloc[199], outcome="")])
    out["start>end"] = run([{**base, "start": t.iloc[199], "end": t.iloc[100], "outcome": ""}])
    out["시간대 표기(+09:00)로 적은 같은 창"] = run([{**base, "start": str(pd.Timestamp(t.iloc[100]).tz_localize("UTC").tz_convert("Asia/Seoul")),
                                                  "end": str(pd.Timestamp(t.iloc[199]).tz_localize("UTC").tz_convert("Asia/Seoul")), "outcome": ""}])
    out["겹치는 두 창(하나만 정상 확인)"] = run([{**base, "outcome": "정상 확인"}, {**base, "start": t.iloc[150], "end": t.iloc[249], "outcome": ""}])
    return out


# ------------------------------------------------------------------ 5. 확률 층 단조성
@section("5_probability_monotone")
def _prob():
    out = {}
    for sid, model in models.items():
        cal = model.probability
        grid = np.unique(np.r_[np.linspace(-50, 500, 200001), cal.x, cal.x - 1e-12, cal.x + 1e-12, np.nextafter(cal.x, np.inf), np.nextafter(cal.x, -np.inf),
                               [-1e300, 1e300, 0.0]])
        lr = cal.likelihood_ratio(grid)
        drops = np.diff(lr) < 0
        observed = np.r_[models[sid].predict(ABN).score.to_numpy(), models[sid].predict(D.inputs_only(normal)).score.to_numpy()]
        observed = np.sort(observed[np.isfinite(observed)])
        lo = cal.likelihood_ratio(observed)
        out[sid] = dict(grid=len(grid), lr_min=float(lr.min()), lr_max=float(lr.max()), lr_floor=cal.lr_floor, lr_cap=cal.lr_cap,
                        decreasing_steps_on_grid=int(drops.sum()), decreasing_steps_on_observed_scores=int((np.diff(lo) < 0).sum()),
                        nan_inputs=cal.likelihood_ratio([np.nan, np.inf, -np.inf]).tolist(),
                        p_prior_monotone=bool(np.all(np.diff(cal.probability(grid, .001)) >= 0) and np.all(np.diff(cal.probability(grid, .1)) >= 0)),
                        knots=len(cal.x), jump_to_cap=dict(score_low=float(cal.x[-3]), p_low=float(cal.y[-3]), score_high=float(cal.x[-2]), p_high=float(cal.y[-2])),
                        lr_at_alarm_threshold=float(cal.likelihood_ratio([float(np.sort(model.cal)[-1])])[0]), alarm_threshold_alpha1=float(np.sort(model.cal)[-1]))
    rng = np.random.default_rng(7)
    fails, fits = [], 0
    for trial in range(400):
        n0, n1 = int(rng.integers(3, 400)), int(rng.integers(1, 200))
        kind = trial % 4
        s0 = rng.exponential(1, n0) if kind != 3 else rng.integers(0, 5, n0).astype(float)
        s1 = rng.exponential(1, n1) * rng.uniform(.5, 8) + (rng.uniform(0, 3) if kind == 1 else 0)
        if kind == 2:
            s1 = np.r_[s1, s0[: max(1, n0 // 3)]]          # 동률
        if kind == 3:
            s1 = rng.integers(0, 8, n1).astype(float)
        try:
            cal = ProbabilityCalibrator.fit(s0, s1, calibration_units=int(rng.integers(20, 300)))
        except Exception as exc:
            fails.append(dict(trial=trial, fit_error=repr(exc)[:200]))
            continue
        fits += 1
        grid = np.unique(np.r_[np.linspace(min(s0.min(), s1.min()) - 2, max(s0.max(), s1.max()) + 2, 4001), cal.x, np.nextafter(cal.x, np.inf), np.nextafter(cal.x, -np.inf)])
        lr = cal.likelihood_ratio(grid)
        if np.any(np.diff(lr) < 0) or lr.min() < cal.lr_floor - 1e-15 or lr.max() > cal.lr_cap + 1e-12 or not np.isfinite(lr).all():
            fails.append(dict(trial=trial, kind=kind, drops=int((np.diff(lr) < 0).sum()), lr_min=float(np.nanmin(lr)), lr_max=float(np.nanmax(lr))))
    out["synthetic"] = dict(trials=400, fitted=fits, failures=fails[:10], failure_count=len(fails))
    return out


RESULT["total_seconds"] = round(time.time() - T0, 1)
name = "redC_counterexamples.json" if not args.only else f"redC_counterexamples_{args.only.replace(',', '_')}.json"
Path(__file__).with_name(name).write_text(json.dumps(RESULT, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
print("저장:", name, RESULT["total_seconds"], "초")
