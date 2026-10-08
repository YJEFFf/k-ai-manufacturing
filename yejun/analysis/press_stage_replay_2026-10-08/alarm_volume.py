"""과제 2: 정상 자료만으로 1·2단계 경보량(60초 묶음 사건)을 시간당·교대(8시간)당으로 추정하고, 1단계 '되풀이' 기준 횟수를 정한다.

평가 집합(모두 정상 기록만 쓴다. 이상 파일은 읽지 않는다)
- E3 시간순 5창(tvt/04 v3_splits·13 folds와 같은 분할): 창마다 정상 기록 < end로 다시 학습하고 end~end+119로 다시 보정해
  end+120~end+179를 평가한다(end = 180·240·300·360·420). 평가 흐름은 창마다 새 상태로 시작한다(04 Final.rows와 같다).
  다섯 평가 구간(정상 기록 300~599)은 서로 겹치지 않아 합친다. 스트림(stages.py) 결과를 04의 Final.rows·Final.alarms(공식 코드)와
  행마다 대조하고, 기록 단위 경보 수를 13의 r2_oos_alpha.json(A_per_fold, α 1%)과 대조한다.
- 제출 분할 A·B의 시험 정상: 제출 예측 파일의 locked_v2_R1_realtime(1단계)·final_v2_R1_R2_realtime(2단계)·v2_realtime 열
  (검증 → 시험 한 흐름). E3 평가 구간과 같은 기록이므로(A 480~599, B 420~599) 따로 적고 E3와 합치지 않는다.
사건: 단계별로 경보 행을 시간순으로 놓고 직전 경보 행과 60초를 넘게 떨어지면 새 사건(보고서 4.2절의 60초 묶음).
노출 시간: 평가 집합의 달력 시간(첫 행 ~ 마지막 행 + 0.1초, 수집 공백 포함). 운전 상태별 노출은 기록 시작부터 다음 기록 시작까지를
  그 기록의 상태(domain/06 state)에 준다(마지막 기록은 기록 길이). 사건은 첫 경보 행이 든 기록의 상태로 센다.
구간: 포아송 정확(Garwood) 양측 95%와 단측 95% 상한(보고서 2.5절과 같은 계산). 교대 = 시간당 × 8.
비교 기준: ISA-18.2(exida 백서 Table 1) 운전원당 시간당 약 6건 이하 "very likely acceptable".
되풀이 기준: E3 5창 합친 1단계 사건률 λ로 교대 사건 수 N ~ Poisson(8λ)일 때 P(N ≥ c) ≤ 5%인 가장 작은 c.
  민감도: λ의 단측 95% 상한, α 1% 설계 사건률(기록당 1/121), A·B 시험 정상 사건률, 5% 대신 1%, 1시간 창.
출력: outputs/alarm_volume.json, alarm_volume_sets.csv, alarm_volume_states.csv, alarm_events.csv, repeat_criterion.csv
실행: PYTHONDONTWRITEBYTECODE=1 python yejun/analysis/press_stage_replay_2026-10-08/alarm_volume.py [--data <원본 폴더>]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import common as C

C.setup()

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import chi2, poisson  # noqa: E402

import model as guard  # noqa: E402
import stages  # noqa: E402
from model import D, conformal_p  # noqa: E402

STAGES = {"v2": ("v2_alarm", "v2_realtime"), "stage1": ("stage1", "locked_v2_R1_realtime"),
          "stage2": ("stage2", "final_v2_R1_R2_realtime")}
STAGE_LABEL = {"v2": "v2(규칙 없음, 참고)", "stage1": "1단계 주의(v2+R1)", "stage2": "2단계 점검 요청(v2+R2→R1)"}
REPEAT_TAIL = 0.05


def load_v04(lib):
    """준용 tvt/04_validation.py를 모듈로 읽는다(Final.rows·Final.alarms·fit_split을 기준 계산에 쓴다)."""
    spec = importlib.util.spec_from_file_location("tvt_v04_stage_replay", C.TVT / "04_validation.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def records_frame(frame: pd.DataFrame, first_record: int) -> pd.DataFrame:
    """평가 집합의 기록별 시작·끝 시각과 전역 정상 기록 번호, 노출 시간(다음 기록 시작까지)."""
    _, seg = guard.layout(frame)
    ts = pd.to_datetime(frame[D.TIME]).astype("datetime64[ns]").astype("int64").to_numpy()
    g = pd.DataFrame(dict(seg=seg, ts=ts)).groupby("seg").ts.agg(["min", "max", "size"]).reset_index()
    g["record"] = first_record + np.arange(len(g))
    nxt = np.r_[g["min"].to_numpy()[1:], g["max"].to_numpy()[-1] + int(D.DT * 1e9)]
    g["exposure_s"] = (nxt - g["min"].to_numpy()) / 1e9
    return g.rename(columns={"min": "start_ns", "max": "end_ns", "size": "rows"})


def summarize_set(name, ts_ns, rec_local, pos, alarms: dict, recs: pd.DataFrame, states: pd.Series, extra: dict | None = None):
    """평가 집합 하나: 단계별 경보 행·기록·사건, 노출, 사건 목록과 상태별 집계."""
    exposure_h = float((ts_ns.max() - ts_ns.min()) / 1e9 + D.DT) / 3600
    assert abs(recs.exposure_s.sum() / 3600 - exposure_h) < 1e-9
    rec_global = recs.record.to_numpy()[rec_local]
    rows, events, by_state = [], [], []
    rec_state = states.reindex(recs.record).to_numpy()
    for stage, alarm in alarms.items():
        alarm = np.asarray(alarm, bool)
        ev = C.event_ids(ts_ns, alarm)
        n_ev = int(ev.max()) if len(ev) else 0
        first_rows = np.array([np.flatnonzero(ev == e)[0] for e in range(1, n_ev + 1)], int)
        for e in range(1, n_ev + 1):
            m = ev == e
            first = first_rows[e - 1]
            row = dict(set=name, stage=stage, event=e, start=str(pd.Timestamp(int(ts_ns[first]))), end=str(pd.Timestamp(int(ts_ns[m][-1]))),
                       alarm_rows=int(m.sum()), records="+".join(map(str, pd.unique(rec_global[m]))),
                       first_record=int(rec_global[first]), first_position=int(pos[first]),
                       state=str(states.get(int(rec_global[first]), "")))
            if extra is not None:
                for key, values in extra.items():
                    row[key] = values(m, first)
            events.append(row)
        lo, hi = C.poisson_ci(n_ev, exposure_h)
        up = C.poisson_upper(n_ev, exposure_h)
        alarmed_records = int(pd.Series(alarm).groupby(rec_local).max().sum())
        rows.append(dict(set=name, stage=stage, records=int(len(recs)), rows=int(len(ts_ns)), exposure_h=exposure_h,
                         exposure_min=exposure_h * 60, alarm_rows=int(alarm.sum()), alarm_records=alarmed_records, events=n_ev,
                         rate_h=n_ev / exposure_h, ci95_lo_h=lo, ci95_hi_h=hi, upper95_h=up,
                         per_shift=C.SHIFT_HOURS * n_ev / exposure_h, ci95_lo_shift=C.SHIFT_HOURS * lo, ci95_hi_shift=C.SHIFT_HOURS * hi,
                         upper95_shift=C.SHIFT_HOURS * up, benchmark_per_hour=C.BENCHMARK_PER_HOUR,
                         point_within_benchmark=bool(n_ev / exposure_h <= C.BENCHMARK_PER_HOUR),
                         upper95_within_benchmark=bool(up <= C.BENCHMARK_PER_HOUR)))
        ev_state = pd.Series(rec_state[rec_local[first_rows]]).value_counts() if n_ev else pd.Series(dtype=int)
        exp_state = pd.Series(recs.exposure_s.to_numpy(), index=rec_state).groupby(level=0).sum() / 3600
        rec_count = pd.Series(1, index=rec_state).groupby(level=0).sum()
        for st in C.STATE_LABELS:
            e_h = float(exp_state.get(st, 0.0))
            k = int(ev_state.get(st, 0))
            lo_s, hi_s = C.poisson_ci(k, e_h) if e_h > 0 else (np.nan, np.nan)
            by_state.append(dict(set=name, stage=stage, state=st, state_label=C.STATE_LABELS[st], records=int(rec_count.get(st, 0)),
                                 exposure_h=e_h, events=k, rate_h=k / e_h if e_h > 0 else np.nan, ci95_lo_h=lo_s, ci95_hi_h=hi_s,
                                 upper95_h=C.poisson_upper(k, e_h) if e_h > 0 else np.nan,
                                 per_shift=C.SHIFT_HOURS * k / e_h if e_h > 0 else np.nan))
    return rows, events, by_state


def repeat_threshold(rate_h: float, hours: float = C.SHIFT_HOURS, tail: float = REPEAT_TAIL) -> dict:
    """N ~ Poisson(rate·hours)에서 P(N ≥ c) ≤ tail인 가장 작은 c와 그 꼬리 확률."""
    mu = rate_h * hours
    c = int(poisson.ppf(1 - tail, mu)) + 1 if mu > 0 else 1
    return dict(rate_h=rate_h, hours=hours, tail=tail, mean=mu, threshold=c, p_at_threshold=float(poisson.sf(c - 1, mu)),
                p_at_threshold_minus_1=float(poisson.sf(c - 2, mu)) if c >= 2 else 1.0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=C.DATA_DEFAULT)
    args = ap.parse_args()
    lib, _ = C.tvt_modules()
    v04 = load_v04(lib)
    M = dict(D=D, guard=guard, conformal_p=conformal_p)
    (normal,) = C.load_data(args.data, keys=("normal",))     # 이상 파일은 열지 않는다(정상 전용)
    regime = pd.read_csv(C.DOMAIN_STATES).set_index("rec")
    states = regime.state
    seg_all = D.segments(normal)
    assert len(regime) == len(np.unique(seg_all)) == 600
    official13 = json.loads((C.TVT / "outputs" / "r2_oos_alpha.json").read_text(encoding="utf-8"))
    per_fold13 = {r["fold"]: r for r in official13["A_per_fold"] if abs(r["alpha"] - 0.01) < 1e-12}

    set_rows, event_rows, state_rows, checks = [], [], [], []
    pooled = {k: [] for k in ("ts", "rec", "alarms", "recs")}
    offset = 0
    for end in C.E3_ENDS:
        name = f"E3 평가{end + 120}~{end + 179}"
        tr, ca, te = seg_all < end, (seg_all >= end) & (seg_all < end + 120), (seg_all >= end + 120) & (seg_all < end + 180)
        train, cal, ev = (normal[m].reset_index(drop=True) for m in (tr, ca, te))
        state = stages.StageState.fit(train, cal, split=f"E3_{end}")
        fin = v04.fit_split(M, train, cal)                     # 공식 04 코드의 같은 적합(기준 계산)
        assert fin.r2_ref == state.r2_ref and np.array_equal(np.sort(fin.model.cal), np.sort(state.model.cal))
        out = stages.replay(state, ev)                        # 스트림(묶음 크기와 무관함은 replay.py·시험이 확인)
        r = fin.rows(ev)
        ref1, _ = v04.Final.alarms(r, "v2+R1")
        ref2, _ = v04.Final.alarms(r, "v2+R1+R2")
        eq = dict(fold=name, rows=int(len(ev)), v2_equal=int((out.v2_alarm.to_numpy() == r["v2"]).sum()),
                  stage1_equal=int((out.stage1.to_numpy() == ref1).sum()), stage2_equal=int((out.stage2.to_numpy() == ref2).sum()))
        rec_local = out.record.to_numpy()
        f13 = per_fold13.get(f"rolling 평가{end + 120}~{end + 179}")
        if f13 is not None:
            for key, col in (("v2", "v2_alarm"), ("v2+R1", "stage1"), ("v2+R1+R2", "stage2")):
                eq[f"records_{key}"] = int(out.groupby("record")[col].max().sum())
                eq[f"records_{key}_official13"] = int(f13[f"all|{key}"])
        checks.append(eq)
        recs = records_frame(ev, end + 120)
        ts_ns = pd.to_datetime(ev[D.TIME]).astype("datetime64[ns]").astype("int64").to_numpy()
        alarms = {k: out[v[0]].to_numpy(bool) for k, v in STAGES.items()}
        extra = dict(evidence=lambda m, f, o=out: "+".join(sorted(set("+".join(o.evidence[m]).split("+")) - {""})),
                     r2_hold_rows=lambda m, f, o=out: int(o.r2_hold[m].sum()),
                     inherited_rows=lambda m, f, o=out: int(o.inherited1[m].sum()))
        s, e, b = summarize_set(name, ts_ns, rec_local, out.position.to_numpy(), alarms, recs, states, extra)
        set_rows += s; event_rows += e; state_rows += b
        pooled["ts"].append(ts_ns); pooled["rec"].append(rec_local + offset); pooled["alarms"].append(alarms); pooled["recs"].append(recs)
        offset += len(recs)
        print(name, eq, {x["stage"]: x["events"] for x in s}, flush=True)

    # E3 5창 합침: 창 사이 공백은 노출에 넣지 않는다(창마다 첫 행~마지막 행)
    pooled_rows = []
    for stage in STAGES:
        sub = [x for x in set_rows if x["set"].startswith("E3") and x["stage"] == stage]
        k, T = sum(x["events"] for x in sub), sum(x["exposure_h"] for x in sub)
        lo, hi = C.poisson_ci(k, T)
        up = C.poisson_upper(k, T)
        ks, Ts = np.array([x["events"] for x in sub]), np.array([x["exposure_h"] for x in sub])
        lam = k / T
        disp = float(((ks - lam * Ts) ** 2 / (lam * Ts)).sum()) if lam > 0 else np.nan     # 창 사이 과산포(포아송 지수) 검정
        pooled_rows.append(dict(set="E3 5창 합침", stage=stage, records=int(sum(x["records"] for x in sub)),
                                rows=int(sum(x["rows"] for x in sub)), exposure_h=T, exposure_min=T * 60,
                                alarm_rows=int(sum(x["alarm_rows"] for x in sub)), alarm_records=int(sum(x["alarm_records"] for x in sub)),
                                events=k, rate_h=lam, ci95_lo_h=lo, ci95_hi_h=hi, upper95_h=up, per_shift=C.SHIFT_HOURS * lam,
                                ci95_lo_shift=C.SHIFT_HOURS * lo, ci95_hi_shift=C.SHIFT_HOURS * hi, upper95_shift=C.SHIFT_HOURS * up,
                                benchmark_per_hour=C.BENCHMARK_PER_HOUR, point_within_benchmark=bool(lam <= C.BENCHMARK_PER_HOUR),
                                upper95_within_benchmark=bool(up <= C.BENCHMARK_PER_HOUR),
                                window_events="/".join(map(str, ks)), dispersion_chi2=disp,
                                dispersion_p=float(chi2.sf(disp, len(ks) - 1)) if np.isfinite(disp) else np.nan))
    set_rows += pooled_rows
    recs_all = pd.concat(pooled["recs"], ignore_index=True)
    for stage in STAGES:
        sub = [x for x in state_rows if x["set"].startswith("E3") and x["stage"] == stage]
        for st in C.STATE_LABELS:
            cell = [x for x in sub if x["state"] == st]
            k, T = sum(x["events"] for x in cell), sum(x["exposure_h"] for x in cell)
            lo, hi = C.poisson_ci(k, T) if T > 0 else (np.nan, np.nan)
            state_rows.append(dict(set="E3 5창 합침", stage=stage, state=st, state_label=C.STATE_LABELS[st],
                                   records=int(sum(x["records"] for x in cell)), exposure_h=T, events=k, rate_h=k / T if T > 0 else np.nan,
                                   ci95_lo_h=lo, ci95_hi_h=hi, upper95_h=C.poisson_upper(k, T) if T > 0 else np.nan,
                                   per_shift=C.SHIFT_HOURS * k / T if T > 0 else np.nan))

    # 제출 분할 A·B의 시험 정상(제출 예측 파일 열)
    for sid in C.SPLITS:
        pred = C.official_predictions(sid)
        p = pred[pred.subset.eq("normal")].reset_index(drop=True)
        first = D.SPLITS[sid][2]
        sp = D.split_normal(normal, seg_all, sid)
        test = sp["test"]
        assert len(test) == len(p) and (test[D.TIME].astype(str).str.slice(0, 23).to_numpy() == p.ts.str.slice(0, 23).to_numpy()).all()
        recs = records_frame(test, first)
        rec_local = p.rec.str.split(":").str[-1].astype(int).to_numpy()
        ts_ns = pd.to_datetime(p.ts).astype("datetime64[ns]").astype("int64").to_numpy()
        alarms = {k: C.as_bool(p[v[1]]) for k, v in STAGES.items()}
        # 사건 근거(켜진 성분·R2 보류·R1 이어받음)는 같은 흐름(검증 → 시험)의 스트림 결과에서 붙인다. 경보는 예측 파일과 행마다 같아야 한다.
        state = stages.StageState.fit(sp["train"], sp["cal"], split=sid)
        out = stages.replay(state, pd.concat([sp["cal"], test], ignore_index=True)).iloc[len(sp["cal"]):].reset_index(drop=True)
        assert all(np.array_equal(out[v[0]].to_numpy(bool), alarms[k]) for k, v in STAGES.items())
        extra = dict(evidence=lambda m, f, o=out: "+".join(sorted(set("+".join(o.evidence[m]).split("+")) - {""})),
                     r2_hold_rows=lambda m, f, o=out: int(o.r2_hold[m].sum()),
                     inherited_rows=lambda m, f, o=out: int(o.inherited1[m].sum()))
        s, e, b = summarize_set(f"제출 {sid} 시험 정상", ts_ns, rec_local, p.pos.to_numpy(), alarms, recs, states, extra)
        set_rows += s; event_rows += e; state_rows += b
        print(sid, {x["stage"]: (x["events"], round(x["exposure_min"], 2)) for x in s}, flush=True)

    sets = pd.DataFrame(set_rows)
    by_state = pd.DataFrame(state_rows)
    events = pd.DataFrame(event_rows)

    # 되풀이 기준(1단계, 정상 자료만)
    e3 = sets[(sets.set == "E3 5창 합침")].set_index("stage")
    lam1, up1 = float(e3.loc["stage1", "rate_h"]), float(e3.loc["stage1", "upper95_h"])
    rec_per_h = float(e3.loc["stage1", "records"] / e3.loc["stage1", "exposure_h"])
    design = rec_per_h / 121                                         # α 1%·보정 120기록: 기록당 1/121(R1·60초 묶음 전)
    crit = [dict(basis="E3 5창 합친 1단계 사건률(주 기준)", **repeat_threshold(lam1)),
            dict(basis="E3 사건률의 단측 95% 상한", **repeat_threshold(up1)),
            dict(basis="α 1% 설계(기록당 1/121 × E3 기록 밀도)", **repeat_threshold(design))]
    for sid in C.SPLITS:
        row = sets[(sets.set == f"제출 {sid} 시험 정상") & (sets.stage == "stage1")].iloc[0]
        crit.append(dict(basis=f"제출 {sid} 시험 정상 1단계 사건률", **repeat_threshold(float(row.rate_h))))
    crit.append(dict(basis="E3 사건률, 꼬리 1%", **repeat_threshold(lam1, tail=0.01)))
    crit.append(dict(basis="E3 사건률, 1시간 창", **repeat_threshold(lam1, hours=1.0)))
    crit = pd.DataFrame(crit)

    C.OUT.mkdir(parents=True, exist_ok=True)
    sets.to_csv(C.OUT / "alarm_volume_sets.csv", index=False)
    by_state.to_csv(C.OUT / "alarm_volume_states.csv", index=False)
    events.to_csv(C.OUT / "alarm_events.csv", index=False)
    crit.to_csv(C.OUT / "repeat_criterion.csv", index=False)
    main_crit = crit.iloc[0].to_dict()
    summary = dict(
        definition=dict(event_gap_s=stages.EVENT_GAP_S, shift_hours=C.SHIFT_HOURS, benchmark_per_hour=C.BENCHMARK_PER_HOUR,
                        exposure="평가 집합의 첫 행~마지막 행 + 0.1초(수집 공백 포함 달력 시간)", ci="포아송 정확 양측 95%, 단측 95% 상한",
                        states="claude/code/press/domain/outputs/06_operating_regime_records.csv state"),
        checks=dict(e3_stream_vs_official04=checks,
                    all_equal=bool(all(c["v2_equal"] == c["rows"] and c["stage1_equal"] == c["rows"] and c["stage2_equal"] == c["rows"]
                                       for c in checks)),
                    records_match_official13=bool(all(c.get(f"records_{k}") == c.get(f"records_{k}_official13")
                                                      for c in checks for k in ("v2", "v2+R1", "v2+R1+R2")))),
        sets=sets.to_dict("records"),
        states=by_state[~by_state.set.str.startswith("E3 평가")].to_dict("records"),
        events=events.to_dict("records"),
        repeat_criterion=dict(primary=main_crit, all=crit.to_dict("records"), records_per_hour_e3=rec_per_h, design_rate_h=design,
                              statement=f"정상 운전에서 교대(8시간) 1단계 사건이 {int(main_crit['threshold'])}건 이상일 확률은 "
                                        f"{main_crit['p_at_threshold'] * 100:.1f}%(≤5%)다. 이 수 이상이면 '되풀이'로 본다."))
    C.dump(summary, C.OUT / "alarm_volume.json")
    pd.set_option("display.width", 250)
    print(sets[["set", "stage", "exposure_min", "alarm_rows", "events", "rate_h", "ci95_lo_h", "ci95_hi_h", "upper95_h", "per_shift"]].round(3).to_string(index=False))
    print(crit.round(4).to_string(index=False))
    print("checks:", summary["checks"]["all_equal"], summary["checks"]["records_match_official13"])
    if not summary["checks"]["all_equal"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
