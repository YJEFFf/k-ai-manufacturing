"""두 단계 경보 콘솔: 제출 체계(1단계 "주의" = v2 + R1, 2단계 "점검 요청" = v2 → R2 → R1)로 기록 재생·CSV 분석을 보인다.

    PYTHONDONTWRITEBYTECODE=1 python yejun/press_guard/stage_console.py [--port 8766] [--data-root <원본 CSV 폴더>] [--artifacts <모델 폴더>]

- 기존 콘솔(serve.py, web/index.html·app.js·style.css)은 v2 경보와 '사건 안 2행' 격상 규칙의 프로토타입이며 그대로 둔다. 그 파일들은
  outputs/manifest.json의 코드 해시(contracts.CODE_FILES)에 묶여 있어 고치면 v2 실행 검증 기록이 깨진다. 그래서 이 모듈이 serve.Console을
  상속해 /api/analyze 결과에 두 단계 경보(stages.TwoStageStream)를 붙이고, 새 화면(web/stage.html·stage.js·stage.css)을 낸다.
  v2 경보·이상 확률·운전 상태는 기존 콘솔과 같은 계산(StreamDetector)이고, 두 계산의 v2 경보가 다르면 stats.v2_mismatch_rows로 보인다.
- 행마다: 1·2단계 경보, 켜진 v2 성분, R1 이어받음·해제, R2 보류, 관측 부족(기록 첫 7행·수집 오류: 파형 판단 전이라 R2가 보류하지 못하고
  R1이 해제되지 못함). 사건 = 60초 안에 이어지는 1단계 경보 행의 묶음(보고서 4.2절). 사건 안에 2단계 경보 행이 있으면 점검 요청, 없으면 주의.
- 운영 α는 1%(제출 체계)이고 다른 α는 비교용이다. r2_ref는 각 분할의 정상 학습 구간으로 정한다(stages.fit_r2_ref).
- 정상 자료 경보량·되풀이 기준·재생 대조는 analysis/press_stage_replay_2026-10-08/outputs의 결과를 읽어 성능 검증 탭에 보인다.
- 실제 설비 제어/정지 명령을 보내지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import pandas as pd

import runtime
import serve
import stages
from model import D, HERE, LEVEL_NAMES, QUALITY_ACTIONS, SUSPECT_MAX_GAP_S, action_for, load_bundle, priority_ranks

REPLAY_OUT = HERE.parent / "analysis" / "press_stage_replay_2026-10-08" / "outputs"
WEB = {"/": ("stage.html", "text/html"), "/stage.js": ("stage.js", "text/javascript"), "/stage.css": ("stage.css", "text/css"),
       "/style.css": ("style.css", "text/css")}
FLAGS = ("stage1", "stage2", "own1", "own2", "inherited1", "inherited2", "released1", "released2", "r2_hold", "insufficient",
         "wave_judgeable", "v2_alarm")
BASE_KEYS = ("split", "alpha", "dataset", "source_name", "calibration_segments", "threshold", "min_p_attainable", "alert_unit_rows",
             "prior", "decision_actions", "quality_actions", "suspect_max_gap_s", "probability_available", "lr_cap", "warnings")
NO_EVIDENCE_ACTION = "직전 사건 이어받음(R1): 직전 기록의 근거·점검 항목을 따른다"


def read_inputs(root):
    """root 아래에서 대회 원본 두 CSV를 찾아 SHA-256을 확인하고 읽는다(press_submission/data에 두지 않은 경우)."""
    frames = {}
    for key, name in D.FILES.items():
        hits = [p for p in sorted(Path(root).rglob(name)) if p.is_file()]
        good = [p for p in hits if hashlib.sha256(p.read_bytes()).hexdigest() == D.EXPECTED_SHA256[key]]
        if not good:
            raise SystemExit(f"{root}: SHA-256이 대회 원본과 같은 {name}이 없다")
        frames[key] = pd.read_csv(good[0])
    return frames["normal"], frames["abnormal"]


def _num(v):
    v = float(v)
    return v if np.isfinite(v) else None


def _peak(values, fn):
    v = np.asarray(values, float)
    v = v[np.isfinite(v)]
    return float(fn(v)) if len(v) else None


def _evidence(rows: pd.DataFrame):
    return sorted(set("+".join(rows.evidence.astype(str)).split("+")) - {""})


def _action(evidence, sensors):
    if not evidence:
        return NO_EVIDENCE_ACTION
    current = D.SENSORS[2]
    return action_for(any(s != current for s in sensors), current in sensors, bool({"waveform", "dynamics"} & set(evidence)))


def stage_tables(out: pd.DataFrame, points: pd.DataFrame, truth=None):
    """(사건 표, 건 표). 사건 = 1단계 60초 묶음(stages의 event1), 건 = 사건이 걸친 기록 하나. 모두 행마다 낸 인과적 표시로만 집계한다."""
    o = out.reset_index(drop=True)
    times = pd.to_datetime(points.timestamp, format="mixed", utc=True, errors="coerce")
    rec = o.record.to_numpy()
    recs = pd.DataFrame(dict(rec=rec, t=times, s1=o.stage1.to_numpy(), valid=points.status.eq("ok").to_numpy())).groupby("rec").agg(
        start=("t", "min"), end=("t", "max"), s1=("s1", "any"), valid=("valid", "all"))
    ev_all = o.event1.to_numpy()
    incidents, cases = [], []
    for ev in pd.unique(ev_all[ev_all > 0]):
        rows = np.flatnonzero(ev_all == ev)
        g = o.iloc[rows]
        members = pd.unique(rec[rows])
        span = np.flatnonzero(np.isin(rec, members))
        s = o.iloc[span]
        level = 2 if g.stage2.any() else 1
        esc = int(rows[g.stage2.to_numpy()][0]) if level == 2 else None
        own = g[g.own1]
        evidence = _evidence(own)
        mag = own.index[own.evidence.str.split("+").map(lambda e: "magnitude" in e).astype(bool)]
        sensors = sorted(set(points.magnitude_sensor.iloc[mag].astype(str)) - {"", "nan", "None"})
        before = recs[(recs.index < members[0]) & ~recs.s1 & recs.valid]
        after = recs[(recs.index > members[-1]) & ~recs.s1 & recs.valid]
        t0, t1 = recs.start[members[0]], recs.end[members[-1]]
        start = before.end.iloc[-1] if len(before) else pd.NaT
        end = after.start.iloc[0] if len(after) else pd.NaT
        if pd.notna(start) and not 0 <= (t0 - start).total_seconds() <= SUSPECT_MAX_GAP_S:
            start = pd.NaT
        if pd.notna(end) and not 0 <= (end - t1).total_seconds() <= SUSPECT_MAX_GAP_S:
            end = pd.NaT
        release = span[s.released1.to_numpy()]
        case_uids = []
        for r in members:
            idx = np.flatnonzero(rec == r)
            gr = o.iloc[idx]
            mine = idx[np.isin(idx, rows)]
            first = int(mine[0]) if len(mine) else int(idx[0])
            ga = o.iloc[mine]
            ev_c = _evidence(ga[ga.own1])
            mag_c = ga.index[(ga.own1 & ga.evidence.str.contains("magnitude")).to_numpy()]
            sens_c = sorted(set(points.magnitude_sensor.iloc[mag_c].astype(str)) - {"", "nan", "None"})
            rel = idx[gr.released1.to_numpy()]
            case_uids.append(first)
            cases.append(dict(
                case_uid=first, incident_id=int(ev), record_id=int(r), row_from=int(idx[0]), row_to=int(idx[-1]), first_row=first,
                first_timestamp=str(points.timestamp.iloc[first]), first_alarm_position=int(o.position[first]),
                detection_delay_s=float(o.position[first] * D.DT), alarm_rows=int(len(mine)), stage2_rows=int(ga.stage2.sum()),
                own_rows=int(ga.own1.sum()), observed_rows=int(len(idx)), alarm_share=float(len(mine) / len(idx)),
                r1_rows=int(ga.inherited1.sum()), r1_only_rows=int((ga.inherited1 & ~ga.own1).sum()),
                release_row=int(rel[0]) if len(rel) else None, release_position=int(o.position[rel[0]]) if len(rel) else None,
                r2_hold_rows=int(ga.r2_hold.sum()), insufficient_rows=int(ga.insufficient.sum()),
                level=2 if ga.stage2.any() else 1, level_name=LEVEL_NAMES[2 if ga.stage2.any() else 1],
                evidence="+".join(ev_c), evidence_count=len(ev_c), magnitude_sensors="+".join(sens_c), action=_action(ev_c, sens_c),
                peak_score=_peak(points.score.iloc[mine], np.max), min_p=_peak(points.p_value.iloc[mine], np.min),
                operating_state=str(points.operating_state.iloc[idx[-1]]), record_current_rms=_num(points.record_current_rms.iloc[idx[-1]]),
                first_alarm_operating_state=str(points.operating_state.iloc[first]),
                max_probability=_peak(points.anomaly_probability.iloc[mine], np.max),
                max_likelihood_ratio=_peak(points.likelihood_ratio.iloc[mine], np.max),
                reference_label=int(truth[idx].max()) if truth is not None else None))
        incidents.append(dict(
            incident_id=int(ev), first_row=int(rows[0]), last_row=int(rows[-1]), first_timestamp=str(points.timestamp.iloc[rows[0]]),
            last_timestamp=str(points.timestamp.iloc[rows[-1]]), last_case_timestamp=str(points.timestamp.iloc[case_uids[-1]]),
            level=level, level_name=LEVEL_NAMES[level], escalation_row=esc,
            escalation_after_first_s=float((times[esc] - times[rows[0]]).total_seconds()) if esc is not None else None,
            cases=int(len(members)), case_uids="+".join(map(str, case_uids)), records="+".join(map(str, members)),
            alarm_rows=int(len(rows)), stage2_rows=int(g.stage2.sum()), own_rows=int(g.own1.sum()), observed_rows=int(len(span)),
            alarm_share=float(len(rows) / len(span)), r1_rows=int(g.inherited1.sum()), r1_only_rows=int((g.inherited1 & ~g.own1).sum()),
            release_rows=int(len(release)), release_row=int(release[0]) if len(release) else None,
            r2_hold_rows=int(g.r2_hold.sum()), insufficient_rows=int(g.insufficient.sum()),
            evidence="+".join(evidence), evidence_count=len(evidence), magnitude_sensors="+".join(sensors), action=_action(evidence, sensors),
            peak_score=_peak(points.score.iloc[rows], np.max), min_p=_peak(points.p_value.iloc[rows], np.min),
            max_probability=_peak(points.anomaly_probability.iloc[rows], np.max),
            max_likelihood_ratio=_peak(points.likelihood_ratio.iloc[rows], np.max),
            operating_state="+".join(dict.fromkeys(str(points.operating_state.iloc[np.flatnonzero(rec == r)[-1]]) for r in members)),
            first_alarm_operating_state=str(points.operating_state.iloc[rows[0]]),
            suspect_from=start.isoformat() if pd.notna(start) else "", suspect_to=end.isoformat() if pd.notna(end) else "",
            suspect_seconds=float((end - start).total_seconds()) if pd.notna(start) and pd.notna(end) else None,
            suspect_open=int(pd.isna(start) or pd.isna(end)), quality_action=QUALITY_ACTIONS[level],
            reference_label=int(truth[span].max()) if truth is not None else None))
    queue = pd.DataFrame(incidents)
    if len(queue):
        queue["priority_rank"] = priority_ranks(queue.assign(peak_score=queue.peak_score.astype(float)))
        case_frame = pd.DataFrame(cases)
        case_frame["priority_rank"] = priority_ranks(case_frame.assign(peak_score=case_frame.peak_score.astype(float)))
    else:
        case_frame = pd.DataFrame(cases)
    return queue, case_frame


def _records(frame: pd.DataFrame):
    return json.loads(frame.to_json(orient="records", double_precision=12)) if len(frame) else []


def stage_result(base: dict, out: pd.DataFrame, truth, state: stages.StageState, elapsed: float) -> dict:
    """기존 /api/analyze 결과(v2 행·확률·운전 상태)에 두 단계 경보 행 표시를 붙이고, 사건·건·통계를 두 단계 기준으로 바꾼다."""
    points = pd.DataFrame(base["points"])
    o = out.reset_index(drop=True)
    if len(points) != len(o):
        raise ValueError("v2 결과와 두 단계 스트림의 행 수가 다르다")
    ok = points.status.eq("ok").to_numpy()
    mismatch = int(((points.alarm.to_numpy() == 1) != o.v2_alarm.to_numpy())[ok].sum())
    pts = points.copy()
    for c in FLAGS:
        pts[c] = o[c].astype(int).to_numpy()
    pts["stage_level"] = o.level.to_numpy()
    pts["stage_record"] = o.record.to_numpy()
    pts["stage_position"] = o.position.to_numpy()
    pts["prefix_r2"] = o.prefix_r2.to_numpy()
    pts["stage_evidence"] = o.evidence.to_numpy()
    pts["incident_id"] = o.event1.to_numpy()
    pts["stage2_event"] = o.event2.to_numpy()
    pts["incident_notification"] = o.event1_start.astype(int).to_numpy()      # 1단계 사건 시작(주의 알림)
    esc = np.zeros(len(o), int)                                               # 사건 안 첫 2단계 행(점검 요청 승격)
    for ev in pd.unique(o.event1[o.event1 > 0]):
        rows = np.flatnonzero((o.event1 == ev).to_numpy() & o.stage2.to_numpy())
        if len(rows):
            esc[rows[0]] = 1
    pts["incident_escalation"] = esc
    pts["alert_level"] = o.level.to_numpy()
    incidents, cases = stage_tables(o, pts, truth)
    n2 = int(incidents.level.eq(2).sum()) if len(incidents) else 0
    stats = dict(rows=int(len(o)), segments=int(o.record.nunique()), scored=int(points.score.notna().sum()), invalid=int((~ok).sum()),
                 alarm_rows=int(o.stage1.sum()), stage1_rows=int(o.stage1.sum()), stage2_rows=int(o.stage2.sum()),
                 v2_alarm_rows=int(o.v2_alarm.sum()), r1_rows=int(o.inherited1.sum()), r1_only_rows=int((o.inherited1 & ~o.own1).sum()),
                 r1_release_rows=int(o.released1.sum()), r2_hold_rows=int(o.r2_hold.sum()), insufficient_rows=int(o.insufficient.sum()),
                 stage1_events=int(len(incidents)), stage2_events=int(o.event2_start.sum()), level2_incidents=n2,
                 level1_incidents=int(len(incidents)) - n2, v2_mismatch_rows=mismatch,
                 elapsed_s=float(base["stats"].get("elapsed_s", 0.0)) + elapsed, stage_elapsed_s=elapsed)
    info = dict(state.summary(), official_alpha=stages.ALPHA, event_gap_s=stages.EVENT_GAP_S,
                rule=dict(stage1="v2 + R1(사건 지속)", stage2="v2 → R2(교차 확인) → R1", event="60초 안에 이어지는 1단계 경보 행 = 한 사건"))
    result = {k: base[k] for k in BASE_KEYS if k in base}
    result.update(stage=info, stats=stats, level_counts={LEVEL_NAMES[2]: n2, LEVEL_NAMES[1]: int(len(incidents)) - n2},
                  incidents=_records(incidents), cases=_records(cases), points=_records(pts))
    return result


class StageConsole(serve.Console):
    """serve.Console의 v2 분석에 두 단계 경보를 붙인다. 원본·모델 위치를 인자로 받을 수 있다(기본은 기존 콘솔과 같다)."""

    def __init__(self, data_root=None, artifacts=None, replay_out=REPLAY_OUT):
        if data_root is None:
            self.normal, self.abnormal, _ = D.load()
        else:
            self.normal, self.abnormal = read_inputs(data_root)
        self.artifacts = Path(artifacts) if artifacts else HERE / "artifacts"
        self.models = {s: load_bundle(self.artifacts / f"guard_{s}.json") for s in D.SPLITS}
        seg = D.segments(self.normal)
        self.r2_ref = {s: stages.fit_r2_ref(D.split_normal(self.normal, seg, s)["train"]) for s in D.SPLITS}
        self.cache, self.stage_cache = {}, {}
        self.lock = threading.Lock()
        self.replay_out = Path(replay_out)

    def frame_for(self, request):
        kind = request.get("dataset", "mixed")
        if kind == "upload":
            return pd.read_csv(io.StringIO(request.get("csv", ""))), None
        sp = D.split_normal(self.normal, D.segments(self.normal), str(request.get("split", "A")))
        frame = {"normal": sp["test"], "abnormal": self.abnormal, "mixed": pd.concat([sp["test"], self.abnormal], ignore_index=True)}[kind]
        return frame, frame[D.LABEL].astype(int).to_numpy()

    def analyze(self, request):
        base = super().analyze(request)          # 입력 검사·v2 경보·이상 확률·운전 상태(기존 콘솔과 같은 계산과 캐시)
        key = (base["split"], base["alpha"], base["dataset"], base["prior"])
        if base["dataset"] != "upload" and key in self.stage_cache:
            return self.stage_cache[key]
        frame, truth = self.frame_for(request)
        state = stages.StageState(self.models[base["split"]], self.r2_ref[base["split"]], base["alpha"])
        start = time.perf_counter()
        out = stages.replay(state, frame, chunk=128)
        result = stage_result(base, out, truth, state, time.perf_counter() - start)
        if base["dataset"] != "upload":
            self.stage_cache[key] = result
        return result

    def stage_overview(self):
        """성능 검증 탭의 두 단계 경보량·되풀이 기준·재생 대조(analysis/press_stage_replay_2026-10-08 결과, 없으면 빈 값)."""
        def read(name):
            path = self.replay_out / name
            return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
        vol, rep = read("alarm_volume.json"), read("replay_summary.json")
        volume = None
        if vol:
            keep = ("E3 5창 합침", "제출 A 시험 정상", "제출 B 시험 정상")
            volume = dict(sets=[r for r in vol["sets"] if r["set"] in keep and r["stage"] in ("stage1", "stage2")],
                          states=[r for r in vol["states"] if r["set"] == "E3 5창 합침" and r["stage"] in ("stage1", "stage2")],
                          repeat=vol["repeat_criterion"], definition=vol["definition"], checks=dict(all_equal=vol["checks"]["all_equal"],
                          records_match_official13=vol["checks"]["records_match_official13"]))
        replay = None
        if rep:
            replay = dict(all_equal=rep["all_equal"], latency_ms=rep["latency_ms_all_rows"], cpu=rep["environment"].get("cpu"),
                          splits={sid: dict(r2_ref_equal=s["r2_ref_equal"],
                                            flows={f: dict(rows=v["rows"], test_rows=v["test_rows"],
                                                           alarms={k: dict(equal=a["test_rows_equal_prediction_file"], rows=a["test_rows"],
                                                                           all_equal=a["all_rows_equal_reference"], all_rows=a["all_rows"])
                                                                   for k, a in v["alarms"].items()},
                                                           score_max_abs_diff=v["scores_vs_reference"]["score"]["max_abs_diff"],
                                                           chunks_equal=v["row_by_row_equals_random_chunks"])
                                                   for f, v in s["flows"].items()})
                                  for sid, s in rep["splits"].items()})
        return dict(level_names=LEVEL_NAMES, official_alpha=stages.ALPHA, event_gap_s=stages.EVENT_GAP_S, r2_ref=self.r2_ref,
                    constants=dict(GAP_S=stages.GAP_S, CONFIRM_ROWS=stages.CONFIRM_ROWS, R2_Q=stages.R2_Q, R2_MIN_LEN=stages.R2_MIN_LEN),
                    volume=volume, replay=replay)

    def overview(self):
        o = super().overview()
        o["stage"] = self.stage_overview()
        return o


def handler(console):
    """serve.handler의 응답·POST 처리를 그대로 쓰고, 화면 파일만 두 단계 콘솔 것으로 바꾼다."""
    base = serve.handler(console)

    class Handler(base):
        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/overview":
                self.response(console.overview())
                return
            if path not in WEB:
                self.response({"error": "찾을 수 없음"}, 404)
                return
            name, mime = WEB[path]
            self.response((HERE / "web" / name).read_bytes(), mime=mime + "; charset=utf-8")
    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--data-root", type=Path, help="대회 원본 CSV 두 개가 든 폴더(기본: press_submission/data)")
    ap.add_argument("--artifacts", type=Path, help="guard_*.json·probability_*.json 폴더(기본: press_guard/artifacts)")
    args = ap.parse_args()
    runtime.setup()
    console = StageConsole(args.data_root, args.artifacts)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(console))
    print(f"Press Guard 두 단계 경보 콘솔: http://127.0.0.1:{args.port} (Ctrl+C 종료)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
