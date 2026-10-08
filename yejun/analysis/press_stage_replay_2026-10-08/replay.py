"""과제 1: 두 단계 경보 스트림(yejun/press_guard/stages.py)이 제출 예측 파일을 행마다 그대로 재현하는지 확인한다.

분할 A·B마다
1. 공식 tvt/01_scores와 같은 정상 학습·검증 구간으로 v2를 학습·보정하고 r2_ref를 정한다(StageState.fit). r2_ref를 공식 meta와 대조한다.
2. 기준값: 01_scores의 v2 행 표(성분 점수·검증 정상 기록 최대 점수 보정·성분 p·lib.prefix_r2)를 같은 함수로 다시 만들고
   evalcore._streams(05_test_predictions와 같은 계산)를 돌려 모든 행(검증+시험)의 v2·1단계·2단계 경보를 얻는다.
3. 같은 흐름(정상: 검증 정상 → 시험 정상 한 흐름, 이상: 21기록 전체 시간순)을 스트림에 (a) 한 행씩 push_row(행마다 지연 측정),
   (b) 무작위 묶음(1~512행), (c) 한 번에 넣어 세 결과가 모든 열에서 같은지 보고, 1·2단계·v2 경보를 기준값(모든 행)과
   제출 예측 파일(시험 행)에 행마다 대조한다. 시험 정상만 따로 흘린 결과(검증 흐름의 R1 상태 없이)도 대조한다.
4. (선택) --official-cache에 공식 실행의 cache/rows_{A,B}.pkl이 있으면 점수·p값·prefix R²를 그 값과도 비교한다.
출력: outputs/replay_summary.json, outputs/replay_counts.csv
실행: PYTHONDONTWRITEBYTECODE=1 python yejun/analysis/press_stage_replay_2026-10-08/replay.py [--data <원본 폴더>] [--official-cache <폴더>]
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import common as C

C.setup()

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import model as guard  # noqa: E402
import stages  # noqa: E402
from model import D, conformal_p  # noqa: E402

CANDS = {"v2": ("v2", "v2", False, False, False, 3), "stage1": ("v2+H1", "v2", True, False, False, 4),
         "stage2": ("v2+H1+H2", "v2", True, True, False, 5)}          # evalcore 후보 형식(이름, 기반, R1, R2, 기록 전용, 복잡도)
STREAM_COL = {"v2": "v2_alarm", "stage1": "stage1", "stage2": "stage2"}
PRED_COL = {"v2": "v2_realtime", "stage1": "locked_v2_R1_realtime", "stage2": "final_v2_R1_R2_realtime"}
SCORE_COLS = {"score": "v2|score", "p_value": "v2|p_full", "p_magnitude": "v2|cp_full|magnitude",
              "p_waveform": "v2|cp_full|waveform", "p_dynamics": "v2|cp_full|dynamics", "prefix_r2": "prefix_r2"}
CHUNK_MAX = 512


def reference_table(lib, model, valid_n, test_n, abnormal):
    """01_scores.build_split의 v2 부분(행 표, 검증 정상 기록 최대 점수 보정, 성분 p, prefix R²)을 같은 함수로 다시 만든다."""
    parts, comps = [], []
    for F, part, subset in ((valid_n, "valid", "normal"), (test_n, "test", "normal"), (abnormal, "abn", "abnormal")):
        status, seg = guard.layout(F)
        assert (status == "ok").all(), f"{part}/{subset}: 수집 상태 오류 행"
        q = D.quantize(D.inputs_only(F), "matched")
        pos, _ = D.segment_positions(seg)
        rows = pd.DataFrame(dict(part=part, subset=subset, seg=seg, pos=pos, label=int(subset == "abnormal"),
                                 ts=pd.to_datetime(F[D.TIME]).astype("datetime64[ns]").to_numpy()))
        if subset == "abnormal":
            rows["part"] = np.where(rows.seg < C.ABN_VALID_RECORDS, "valid", "test")
        rows["rec"] = [f"{p}:{subset}:{s}" for p, s in zip(rows.part, rows.seg)]
        rows["prefix_r2"] = lib.prefix_r2(q[D.SENSORS[2]].to_numpy(float), seg)
        parts.append(rows)
        comps.append(model.components(q, seg))
    table = pd.concat(parts, ignore_index=True)
    sv = comps[0]["score"]
    cal = pd.Series(np.where(np.isfinite(sv), sv, -np.inf)).groupby(parts[0].seg.to_numpy()).max().to_numpy()
    assert np.array_equal(np.sort(cal), np.sort(model.cal)), "보정값이 GuardModel과 다르다"
    table["v2|score"] = np.concatenate([c["score"] for c in comps])
    table["v2|p_full"] = conformal_p(cal, table["v2|score"].to_numpy())
    table["v2|p_loo"] = np.nan
    for name in stages.COMPONENTS:
        g = np.concatenate([c[f"g_{name}"] for c in comps])
        table[f"v2|cp_full|{name}"] = conformal_p(cal, g)
        table[f"v2|cp_loo|{name}"] = np.nan
    return table


def reference_alarms(evalcore, table, r2_ref):
    """evalcore._streams(시험 체제: 검증 → 시험 한 흐름)로 흐름별 모든 행의 v2·1단계·2단계 경보."""
    out = {}
    for key, cand in CANDS.items():
        for sub, rt, _, keep in evalcore._streams(table, cand, stages.ALPHA, "test", r2_ref):
            subset = sub.subset.iloc[0]
            out.setdefault(subset, {"rows": sub.reset_index(drop=True), "keep": keep})[key] = np.asarray(rt, bool)
    return out


def replay_rows(state, frame):
    """한 행씩 push_row. 반환 (결과 표, 행별 지연 ns, 상태 크기 최대 바이트, prefix R² 버퍼 최대 행 수)."""
    stream = stages.TwoStageStream(state)
    rows, lat, max_bytes, max_buffer = [], np.empty(len(frame), "int64"), 0, 0
    for i, r in enumerate(frame[[D.TIME] + D.SENSORS].itertuples(index=False, name=None)):
        t0 = time.perf_counter_ns()
        rows.append(stream.push_row(*r))
        lat[i] = time.perf_counter_ns() - t0
        max_bytes = max(max_bytes, stream.state_bytes())
        max_buffer = max(max_buffer, len(stream._current))
    return pd.DataFrame(rows, columns=stages.COLUMNS), lat, max_bytes, max_buffer


def score_diff(a: np.ndarray, b: np.ndarray) -> dict:
    a, b = np.asarray(a, float), np.asarray(b, float)
    fin = np.isfinite(a) & np.isfinite(b)
    return dict(nan_pattern_equal=bool(np.array_equal(np.isfinite(a), np.isfinite(b))),
                max_abs_diff=float(np.max(np.abs(a[fin] - b[fin]))) if fin.any() else 0.0, finite_rows=int(fin.sum()),
                bitwise_equal=bool(np.array_equal(a[fin], b[fin])))


def flow_counts(out: pd.DataFrame) -> dict:
    return dict(rows=int(len(out)), records=int(out.record.nunique()), v2_alarm_rows=int(out.v2_alarm.sum()),
                stage1_rows=int(out.stage1.sum()), stage2_rows=int(out.stage2.sum()),
                stage1_inherited_rows=int(out.inherited1.sum()), stage2_inherited_rows=int(out.inherited2.sum()),
                stage1_release_rows=int(out.released1.sum()), stage2_release_rows=int(out.released2.sum()),
                r2_hold_rows=int(out.r2_hold.sum()), insufficient_rows=int(out.insufficient.sum()),
                stage1_events=int(out.event1_start.sum()), stage2_events=int(out.event2_start.sum()))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=C.DATA_DEFAULT, help="대회 원본 CSV 2개가 든 폴더(하위 폴더 검색, 해시 확인)")
    ap.add_argument("--official-cache", type=Path, help="공식 실행의 tvt cache 폴더(rows_A.pkl·rows_B.pkl). 주면 점수도 대조")
    ap.add_argument("--seed", type=int, default=20261008)
    args = ap.parse_args()
    lib, evalcore = C.tvt_modules()
    normal, abnormal = C.load_data(args.data)
    meta = C.official_meta()
    summary = dict(environment=C.environment(), alpha=stages.ALPHA, splits={})
    count_rows = []
    rng = np.random.default_rng(args.seed)
    all_lat = []
    for sid in C.SPLITS:
        t_fit = time.perf_counter()
        sp = D.split_normal(normal, D.segments(normal), sid)
        state = stages.StageState.fit(sp["train"], sp["cal"], split=sid)
        fit_s = time.perf_counter() - t_fit
        info = state.summary()
        info["r2_ref_official"] = meta[sid]["r2_ref"]
        info["r2_ref_equal"] = bool(state.r2_ref == meta[sid]["r2_ref"])
        info["fit_seconds"] = round(fit_s, 2)
        info["frozen_model_json_bytes"] = len(json.dumps(D.to_jsonable(state.model.state), ensure_ascii=False))
        table = reference_table(lib, state.model, sp["cal"], sp["test"], abnormal)
        ref = reference_alarms(evalcore, table, state.r2_ref)
        pred = C.official_predictions(sid)
        cache = pd.read_pickle(args.official_cache / f"rows_{sid}.pkl") if args.official_cache else None
        flows = {"normal": pd.concat([sp["cal"], sp["test"]], ignore_index=True), "abnormal": abnormal.reset_index(drop=True)}
        res = {}
        for subset, frame in flows.items():
            print(f"{sid} {subset}: {len(frame)}행 한 행씩 …", flush=True)
            by_row, lat, max_bytes, max_buffer = replay_rows(state, frame)
            all_lat.append(lat)
            sizes = rng.integers(1, CHUNK_MAX + 1, size=len(frame))
            by_chunk = stages.replay(state, frame, chunk=sizes)
            used = int(np.searchsorted(np.cumsum(sizes), len(frame)) + 1)
            at_once = stages.replay(state, frame)
            r = ref[subset]
            rows_ref = r["rows"]
            assert len(rows_ref) == len(by_row)
            test = (rows_ref.part == "test").to_numpy()
            p = pred[pred.subset.eq(subset)].reset_index(drop=True)
            assert len(p) == int(test.sum())
            ts_match = bool((by_row.timestamp[test].str.slice(0, 23).to_numpy() == p.ts.str.slice(0, 23).to_numpy()).all())
            pos_match = bool(np.array_equal(by_row.position.to_numpy(), rows_ref.pos.to_numpy()))
            rec_match = bool(len(pd.unique(by_row.record)) == rows_ref.rec.nunique()
                             and np.array_equal(pd.factorize(by_row.record)[0], pd.factorize(rows_ref.rec)[0]))
            eq = {}
            for key in CANDS:
                mine = by_row[STREAM_COL[key]].to_numpy(bool)
                want = C.as_bool(p[PRED_COL[key]])
                eq[key] = dict(all_rows_equal_reference=int((mine == r[key]).sum()), all_rows=int(len(mine)),
                               test_rows_equal_prediction_file=int((mine[test] == want).sum()), test_rows=int(test.sum()),
                               alarm_rows_stream_test=int(mine[test].sum()), alarm_rows_prediction_file=int(want.sum()))
            sub_tab = table[(table.subset == subset).to_numpy()].reset_index(drop=True)
            scores = {k: score_diff(by_row[k], sub_tab[v]) for k, v in SCORE_COLS.items()}
            cache_cmp = None
            if cache is not None:
                cs = cache[cache.subset.eq(subset)].reset_index(drop=True)
                cache_cmp = {k: score_diff(by_row[k], cs[v]) for k, v in SCORE_COLS.items()}
            res[subset] = dict(rows=int(len(frame)), records=int(by_row.record.nunique()),
                               test_rows=int(test.sum()), timestamps_match_prediction_file=ts_match,
                               positions_match_reference=pos_match, records_match_reference=rec_match,
                               row_by_row_equals_random_chunks=bool(by_row.equals(by_chunk)),
                               row_by_row_equals_one_shot=bool(by_row.equals(at_once)), random_chunks_used=used,
                               random_chunk_size_range=[1, CHUNK_MAX],
                               alarms=eq, scores_vs_reference=scores, scores_vs_official_cache=cache_cmp,
                               latency_ms=dict(median=float(np.median(lat) / 1e6), p99=float(np.percentile(lat, 99) / 1e6),
                                               max=float(lat.max() / 1e6), mean=float(lat.mean() / 1e6)),
                               mutable_state_max_bytes=int(max_bytes), r2_buffer_max_rows=int(max_buffer),
                               counts=flow_counts(by_row), counts_test=flow_counts(by_row[test]))
            count_rows.append(dict(split=sid, flow=subset, **{f"{k}": v for k, v in flow_counts(by_row).items()}))
            if subset == "normal":
                # 콘솔처럼 시험 정상만 따로 흘리면(검증 흐름의 R1 상태 없음) 제출 파일과 같은가
                alone = stages.replay(state, sp["test"])
                res[subset]["test_only_flow"] = {key: int((alone[STREAM_COL[key]].to_numpy(bool) == C.as_bool(p[PRED_COL[key]])).sum())
                                                 for key in CANDS}
        info["flows"] = res
        summary["splits"][sid] = info
        print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk in ("alarms", "latency_ms", "row_by_row_equals_random_chunks")}
                          for k, v in res.items()}, ensure_ascii=False, indent=1, default=str), flush=True)
    lat = np.concatenate(all_lat) / 1e6
    summary["latency_ms_all_rows"] = dict(rows=int(len(lat)), median=float(np.median(lat)), p99=float(np.percentile(lat, 99)),
                                          max=float(lat.max()), mean=float(lat.mean()))
    ok = all(f["alarms"][k]["all_rows_equal_reference"] == f["alarms"][k]["all_rows"]
             and f["alarms"][k]["test_rows_equal_prediction_file"] == f["alarms"][k]["test_rows"]
             and f["row_by_row_equals_random_chunks"] and f["row_by_row_equals_one_shot"]
             for s in summary["splits"].values() for f in s["flows"].values() for k in CANDS)
    summary["all_equal"] = bool(ok and all(s["r2_ref_equal"] for s in summary["splits"].values()))
    C.dump(summary, C.OUT / "replay_summary.json")
    pd.DataFrame(count_rows).to_csv(C.OUT / "replay_counts.csv", index=False)
    print("all_equal:", summary["all_equal"], "| latency ms", summary["latency_ms_all_rows"])
    if not summary["all_equal"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
