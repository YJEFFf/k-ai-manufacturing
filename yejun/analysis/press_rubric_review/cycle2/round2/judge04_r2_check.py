"""평가관 04(현장 활용방안) cycle2 round2 검증. 저장소 코드·산출물은 읽기만 한다.

실행(yejun/에서):
  OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python \
      analysis/press_rubric_review/cycle2/round2/judge04_r2_check.py 2>&1 | tee analysis/press_rubric_review/cycle2/round2/judge04_r2_check.log
쓰는 파일: 이 폴더의 judge04_r2_check.json 하나. 재학습·재보정·모의 운용 산출물은 시스템 임시 폴더(judge04_c2r2_*)에만 쓴다.
콘솔 서버(serve.py)는 127.0.0.1의 빈 포트(OS 배정)에 띄우고 끝나면 종료한다.

[사후] 이상 라벨을 본 관찰(성능 근거 아님). [가정] 현장 자료가 없어 평가관이 둔 값.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[3]
REPO = YEJUN.parent
GUARD = YEJUN / "press_guard"
OUTP = GUARD / "outputs"
sys.path.insert(0, str(GUARD))
from model import (GuardModel, StreamDetector, cases, action_for, load_bundle, D, DECISION_TABLE, ACTIONS,  # noqa: E402
                   ALPHAS, ESCALATION_ALARM_ROWS, SUSPECT_MAX_GAP_S)
from monitor import Reference, gain_scenarios, monitor_windows  # noqa: E402

OUT = HERE / "judge04_r2_check.json"
TMP = Path(tempfile.mkdtemp(prefix="judge04_c2r2_"))
PY = sys.executable
ENV = dict(os.environ, OMP_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
res: dict = dict(tmp_dir=str(TMP))
T0 = time.time()


def sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout.strip()


def log(msg):
    print(f"[{time.time() - T0:6.1f}s] {msg}", flush=True)


def close(a, b, tol=1e-9):
    if (a is None or (isinstance(a, float) and math.isnan(a))) and (b is None or (isinstance(b, float) and math.isnan(b))):
        return True
    try:
        return bool(np.isclose(float(a), float(b), rtol=tol, atol=tol))
    except (TypeError, ValueError):
        return a == b


def jsonable(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return str(o)


# ============================================================ 0. 출처
def pycache_dirs():
    return sorted(subprocess.run(["find", str(YEJUN), "-name", "__pycache__", "-o", "-name", ".pytest_cache"], capture_output=True, text=True).stdout.split())


res["provenance"] = dict(head=git("rev-parse", "HEAD"), status_before=git("status", "--porcelain", "--", "yejun"),
                         python=sys.version.split()[0], omp=os.environ.get("OMP_NUM_THREADS"), cache_dirs_before=pycache_dirs())
log(f"HEAD {res['provenance']['head']} · status_before={res['provenance']['status_before']!r}")

# ============================================================ 1. 원본 재학습(임시 폴더) → manifest·커밋 산출물과 대조
t = time.time()
run = subprocess.run([PY, str(GUARD / "train.py"), "--out", str(TMP / "out"), "--artifacts", str(TMP / "art"), "--rolling"],
                     cwd=YEJUN, env=ENV, capture_output=True, text=True)
manifest = json.loads((OUTP / "manifest.json").read_text(encoding="utf-8"))
new_manifest = json.loads((TMP / "out" / "manifest.json").read_text(encoding="utf-8")) if (TMP / "out" / "manifest.json").exists() else {}
retrain = dict(returncode=run.returncode, seconds=round(time.time() - t, 1), stderr_tail=run.stderr[-400:])
retrain["artifacts_eq_manifest"] = {k: new_manifest.get("artifacts", {}).get(k) == v for k, v in manifest["artifacts"].items()}
retrain["local_artifacts_eq_manifest"] = {k: (GUARD / "artifacts" / k).exists() and sha(GUARD / "artifacts" / k) == v for k, v in manifest["artifacts"].items()}
retrain["outputs_eq_manifest"] = {k: new_manifest.get("outputs", {}).get(k) == v for k, v in manifest["outputs"].items()}
retrain["committed_eq_manifest"] = {k: (OUTP / k).exists() and sha(OUTP / k) == v for k, v in manifest["outputs"].items()}
res["retrain_from_raw"] = retrain
log(f"재학습 {retrain['returncode']} {retrain['seconds']}s · artifacts {retrain['artifacts_eq_manifest']} · outputs 모두 일치 {all(retrain['outputs_eq_manifest'].values())}")

models = {s: load_bundle(TMP / "art" / f"guard_{s}.json") for s in ("A", "B")}
normal, abnormal, _ = D.load()
seg_all = D.segments(normal)
splits = {s: D.split_normal(normal, seg_all, s) for s in ("A", "B")}


def rolling_fits():
    fits = {}
    for end in (180, 240, 300, 360, 420):
        tr = normal[seg_all < end]
        ca = normal[(seg_all >= end) & (seg_all < end + 120)]
        fits[f"rolling_test_{end + 120}_{end + 179}"] = (GuardModel.fit(tr, ca, split=f"train_to_{end}"), end + 120, end + 180)
    return fits


FITS = {"frozen_A": (models["A"], 480, 600), "frozen_B": (models["B"], 420, 600), **rolling_fits()}

# ============================================================ 2. U1: 단계별 알림·업무량·지연 재계산(독립 구현) → alert_levels_v2.csv
lv_csv = pd.read_csv(OUTP / "alert_levels_v2.csv")
lv_rows, mism = [], []
pred_cache = {}
for name, (m, lo, hi) in FITS.items():
    test = normal[(seg_all >= lo) & (seg_all < hi)]
    tt = pd.to_datetime(test[D.TIME])
    elapsed_h = (tt.max() - tt.min()).total_seconds() / 3600
    for a in ALPHAS:
        pn, pa = m.predict(test, a), m.predict(abnormal, a)
        pred_cache[(name, a)] = (pn, pa)
        for level in (1, 2):
            # 기록구간 단위: 1단계 = 경보 행 존재, 2단계 = 단계 2 행 존재(대회 자료는 기록구간 = 알림 단위)
            hit_n = pn.groupby("record_id").alert_level.max() >= level
            hit_a = pa.groupby("record_id").alert_level.max() >= level
            k, n = int(hit_n.sum()), int(len(hit_n))
            firstpos = pa[pa.alert_level >= level].groupby("record_id").position.min() * D.DT
            l1pos = pa[pa.alert_level >= 1].groupby("record_id").position.min() * D.DT
            lag = (firstpos - l1pos.reindex(firstpos.index)).dropna() if level == 2 else pd.Series(dtype=float)
            nominal = (math.floor(a * (len(m.cal) + 1) + 1e-9) / (len(m.cal) + 1)) * n / elapsed_h * 8 if level == 1 else float("nan")
            row = dict(model=name, alpha=a, level=level, normal_alerted=k, normal_units=n, units_per_h=n / elapsed_h,
                       nominal_8h=nominal, observed_8h=k / elapsed_h * 8, upper95_8h=float(stats.beta.ppf(.95, k + 1, n - k)) * n / elapsed_h * 8,
                       abnormal_detected=int(hit_a.sum()), abnormal_units=int(len(hit_a)),
                       delay_median_s=float(firstpos.median()), delay_max_s=float(firstpos.max()),
                       esc_after_first_median_s=float(lag.median()) if len(lag) else float("nan"),
                       esc_after_first_max_s=float(lag.max()) if len(lag) else float("nan"))
            c = lv_csv[(lv_csv.model == name) & np.isclose(lv_csv.alpha, a) & (lv_csv.level == level)].iloc[0]
            ok = (k == c.normal_alerted_segments and n == c.normal_segments and row["abnormal_detected"] == c.abnormal_detected_segments
                  and close(row["nominal_8h"], c.nominal_alerts_per_8h_elapsed) and close(row["observed_8h"], c.alerts_per_8h_elapsed)
                  and close(row["upper95_8h"], c.upper95_alerts_per_8h_elapsed) and close(row["delay_median_s"], c.delay_median_s)
                  and close(row["delay_max_s"], c.delay_max_s)
                  and (level == 1 or (close(row["esc_after_first_median_s"], c.escalation_after_first_median_s)
                                      and close(row["esc_after_first_max_s"], c.escalation_after_first_max_s))))
            row["match_csv"] = bool(ok)
            if not ok:
                mism.append(row)
            lv_rows.append(row)
lv = pd.DataFrame(lv_rows)
indep = ["rolling_test_300_359", "rolling_test_360_419", "rolling_test_540_599"]
l1l2 = {}
for a in ALPHAS:
    g = lv[lv.model.isin(indep) & np.isclose(lv.alpha, a)]
    l1l2[f"alpha_{a}"] = dict(level1=int(g[g.level == 1].normal_alerted.sum()), level2=int(g[g.level == 2].normal_alerted.sum()),
                              units=int(g[g.level == 1].normal_units.sum()))
res["U1_alert_levels"] = dict(rows_checked=len(lv), all_match=bool(lv.match_csv.all()), mismatches=mism[:5],
                             frozen_B_a1=lv[(lv.model == "frozen_B") & np.isclose(lv.alpha, .01)].to_dict("records"),
                             independent_folds_L1_to_L2=l1l2,
                             note="독립 폴드(동결 모델과 보정값이 다른 300~359·360~419·540~599)에서 1단계 → 2단계 정상 알림 수. 2단계 규칙 선택 때 보지 않은 자료")
log(f"U1 단계표 {len(lv)}행 재계산 일치={bool(lv.match_csv.all())} · 독립 폴드 L1→L2 {l1l2}")

# 2단계 알림률의 명목·상한은 표본 크기에 묶인다: 0/n의 단측 95% 상한을 교대 환산
uph = float(lv[(lv.model.isin(["frozen_A", "frozen_B"])) & (lv.level == 1) & np.isclose(lv.alpha, .01)].units_per_h.mean())
res["U1_level2_bound_by_sample"] = {f"zero_of_{n}": dict(upper95_rate=1 - .05 ** (1 / n), per_8h=(1 - .05 ** (1 / n)) * uph * 8)
                                     for n in (120, 180, 300, 600)}

# 알림 예산 설계표(alert_budget_design_v2.csv) 식 재계산
bd = pd.read_csv(OUTP / "alert_budget_design_v2.csv")
work = pd.read_csv(OUTP / "workload_v2.csv")
uph_w = float(work[work.model.eq("guard_v2")].units_per_elapsed_hour.mean())
bd_ok = []
for r in bd.itertuples():
    u = uph_w if r.collection.startswith("간헐") else 3600 / (50 * D.DT)
    a = r.target_alerts_per_8h / (u * 8)
    n_req = math.ceil(1 / a - 1e-9) - 1
    bd_ok.append(close(a, r.alpha_required) and n_req == r.calibration_units_required and close(n_req / u, r.normal_collection_hours))
res["U1_budget_design"] = dict(rows=len(bd), all_match=bool(all(bd_ok)), units_per_elapsed_hour=uph_w,
                               target3=bd[bd.target_alerts_per_8h.eq(3)].to_dict("records"),
                               model_alpha_choices=list(ALPHAS),
                               note="설계표의 α(예: 3건 → 0.084%)는 모델이 받는 α 선택지(1·3·5%) 밖이다(recalibrate.budget_design advice에 명시)")
log(f"U1 예산 설계표 식 일치={all(bd_ok)} · 간헐 밀도 {uph_w:.1f}/h")

# ============================================================ 3. U2·U5: 혼합 대기열·품질 시간창(독립 계산) → queue_mixed_ranks·quality_windows·cases
def mixed(model, test, alpha):
    pn, pa = model.predict(test, alpha), model.predict(abnormal, alpha)
    sh = pa.copy()
    off = int(pn.record_id.max()) + 1
    sh["record_id"] += off
    sh["row_id"] += len(pn)
    p = pd.concat([pn, sh], ignore_index=True)
    return p, off


qw_csv = pd.read_csv(OUTP / "quality_windows_v2.csv")
qm_csv = pd.read_csv(OUTP / "queue_mixed_ranks_v2.csv")
u2 = {}
for s in ("A", "B"):
    test = splits[s]["test"]
    for a in ALPHAS:
        p, off = mixed(models[s], test, a)
        pn_part = p[p.record_id < off]
        tt = pd.to_datetime(pn_part.timestamp, format="mixed")
        starts, ends = tt.groupby(pn_part.record_id).min(), tt.groupby(pn_part.record_id).max()
        q = cases(p)
        src = np.where(q.record_id >= off, "abnormal", "normal")
        fa = q[src == "normal"]
        # 독립 계산: 오경보 기록 r의 창 = (앞의 경보 없는 기록 끝) ~ (뒤의 경보 없는 기록 시작). 대회 자료는 오경보가 고립돼 있다.
        alarmed = p[p.record_id < off].groupby("record_id").alarm.max()
        win = []
        for r in fa.itertuples():
            prev = [x for x in range(r.record_id - 1, -1, -1) if not alarmed.get(x, 0)]
            nxt = [x for x in range(r.record_id + 1, off) if not alarmed.get(x, 0)]
            lo_t = ends[prev[0]] if prev else pd.NaT
            hi_t = starts[nxt[0]] if nxt else pd.NaT
            if pd.notna(lo_t) and (starts[r.record_id] - lo_t).total_seconds() > SUSPECT_MAX_GAP_S:
                lo_t = pd.NaT
            if pd.notna(hi_t) and (hi_t - ends[r.record_id]).total_seconds() > SUSPECT_MAX_GAP_S:
                hi_t = pd.NaT
            win.append((hi_t - lo_t).total_seconds() if pd.notna(lo_t) and pd.notna(hi_t) else float("nan"))
        fa_ranks = sorted(fa.priority_rank.tolist())
        ab = q[src == "abnormal"]
        csv_fa = qw_csv[(qw_csv.split == s) & np.isclose(qw_csv.alpha, a) & (qw_csv.source == "normal")].sort_values("record_id")
        csv_m = qm_csv[(qm_csv.split == s) & np.isclose(qm_csv.alpha, a)]
        u2[f"{s}_a{a}"] = dict(cases=len(q), false_alarm_records=fa.record_id.tolist(), fa_levels=fa.level.tolist(), fa_ranks=fa_ranks,
                               fa_window_s_independent=[round(w, 3) for w in win], fa_window_s_code=[round(w, 3) for w in fa.suspect_seconds],
                               abnormal_open=int(ab.suspect_open.sum()), abnormal_cases=len(ab), abnormal_level2=int(ab.level.eq(2).sum()),
                               matches_quality_csv=bool(np.allclose(np.sort(fa.suspect_seconds.to_numpy(float)), np.sort(csv_fa.suspect_seconds.to_numpy(float)))
                                                        if len(fa) else len(csv_fa) == 0),
                               independent_eq_code=bool(np.allclose(np.asarray(win, float), fa.suspect_seconds.to_numpy(float), equal_nan=True)) if len(fa) else True,
                               matches_mixed_rank_csv=bool(sorted(csv_m[csv_m.source == "normal"].rank_level_evidence_share_peak.tolist()) == fa_ranks),
                               spm20_60_pieces=[(round(w * 20 / 60, 2), round(w, 2)) for w in fa.suspect_seconds])
cb = pd.read_csv(OUTP / "cases_B.csv")
res["U2_U5_queue_quality"] = dict(by_split_alpha=u2, cases_B_rows=len(cb), cases_B_rank_unique=bool(cb.priority_rank.is_unique),
                                  cases_B_ranks_are_1_to_n=bool(sorted(cb.priority_rank) == list(range(1, len(cb) + 1))))
log(f"U2·U5 B α1% 오경보 순위 {u2['B_a0.01']['fa_ranks']} 창 {u2['B_a0.01']['fa_window_s_independent']} · 이상 창 열림 {u2['B_a0.01']['abnormal_open']}/21")

# 대기열 한계 문장(README:133 "B α 3·5%") 대조: 주입 고장 대 최선 오경보 순위
qi = pd.read_csv(OUTP / "queue_injection_ranks_v2.csv")
k0 = qi[qi.key.eq("level_evidence_share_peak") & qi.injected_below_best_false_alarm.gt(0)]
res["U5_injection_below_fa"] = k0[["split", "alpha", "family", "level_value", "injected_cases", "injected_below_best_false_alarm"]].to_dict("records")
res["U5_key_selection"] = pd.read_csv(OUTP / "queue_key_selection_v2.csv").to_dict("records")

# ============================================================ 4. 경보 폭주: 대회 자료의 지속 이상(21기록·약 3분)이 내는 알림 수와 사건 묶음 시 알림 수
def incidents(p, gap_s=SUSPECT_MAX_GAP_S):
    t = pd.to_datetime(p.timestamp, format="mixed", utc=True, errors="coerce")
    u = (p.assign(t=t).groupby(["record_id", "alert_unit"], sort=False)
         .agg(start=("t", "min"), end=("t", "max"), alarm=("alarm", "max"), l2=("alert_level", "max")).reset_index())
    inc, prev_alarm, prev_end = [], False, None
    for r in u.itertuples():
        if r.alarm:
            if prev_alarm and (r.start - prev_end).total_seconds() <= gap_s:
                inc[-1]["units"] += 1
                inc[-1]["l2"] = inc[-1]["l2"] or r.l2 >= 2
                inc[-1]["end"] = r.end
            else:
                inc.append(dict(start=r.start, end=r.end, units=1, l2=bool(r.l2 >= 2)))
        prev_alarm, prev_end = bool(r.alarm), r.end
    return inc


flood = {}
for s in ("A", "B"):
    for a in ALPHAS:
        p, off = mixed(models[s], splits[s]["test"], a)
        pa_part, pn_part = p[p.record_id >= off], p[p.record_id < off]
        ta = pd.to_datetime(pa_part.timestamp)
        inc_a, inc_n = incidents(pa_part), incidents(pn_part)
        flood[f"{s}_a{a}"] = dict(abnormal_minutes=round((ta.max() - ta.min()).total_seconds() / 60, 2),
                                  abnormal_notifications_now=int(pa_part.notification.sum() + pa_part.escalation.sum()),
                                  abnormal_cases_now=int(len(cases(pa_part))),
                                  abnormal_incidents_if_grouped=len(inc_a), abnormal_notifications_if_grouped=int(len(inc_a) + sum(i["l2"] for i in inc_a)),
                                  normal_notifications_now=int(pn_part.notification.sum() + pn_part.escalation.sum()),
                                  normal_incidents_if_grouped=len(inc_n), normal_notifications_if_grouped=int(len(inc_n) + sum(i["l2"] for i in inc_n)))
res["alert_flood"] = dict(by_split_alpha=flood, rule="[평가관 가정] 경보 단위가 이어지고 단위 사이 공백 ≤ 60초(SUSPECT_MAX_GAP_S)면 한 사건으로 묶고, 사건마다 1단계 1회·2단계 1회만 알림")
log(f"경보 폭주 B α1%: {flood['B_a0.01']}")

# ============================================================ 5. 연속 입력(R7) S1·S2 재현 + 한 기록 안 여러 건(콘솔 식별 결함)
pt = models["B"].predict(D.inputs_only(splits["B"]["test"]), .01)
per = pt.groupby("record_id").agg(n=("alarm", "size"), a=("alarm", "sum"))
clean = int(per[(per.n == 50) & (per.a == 0)].index[0])
fa_rec = int(per[(per.n == 50) & (per.a > 0)].index[0])
testB = D.inputs_only(splits["B"]["test"])
ab = D.inputs_only(abnormal)


def restamp(frame, start="2026-09-27 08:00:00"):
    g = frame.copy().reset_index(drop=True)
    g[D.TIME] = (pd.Timestamp(start) + pd.to_timedelta(np.arange(len(g)) * D.DT, unit="s")).strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3]
    return g


def stream(frame, chunk=128):
    sd = StreamDetector(models["B"], .01)
    return pd.concat([sd.push(frame.iloc[i:i + chunk]) for i in range(0, len(frame), chunk)], ignore_index=True)


s_res = {}
for name, lead_rec in (("S1_clean_lead", clean), ("S2_false_alarm_lead", fa_rec)):
    lead = testB[pt.record_id.to_numpy() == lead_rec]
    f = restamp(pd.concat([lead, ab], ignore_index=True))
    p = stream(f)
    p1 = stream(f, chunk=1)
    n0 = len(lead)
    s_res[name] = dict(lead_record=lead_rec, lead_rows=n0, records=int(p.record_id.nunique()),
                       first_alerts=p.index[p.notification == 1].tolist(), escalations=p.index[p.escalation == 1].tolist(),
                       escalation_rows_after_onset=[i - n0 for i in p.index[p.escalation == 1] if i >= n0],
                       level2_rows_after_onset=int((p.alert_level.iloc[n0:] == 2).sum()),
                       chunk1_same=bool(p1.notification.tolist() == p.notification.tolist() and p1.escalation.tolist() == p.escalation.tolist()),
                       batch_same=bool(models["B"].predict(f, .01).escalation.tolist() == p.escalation.tolist()))
big = restamp(pd.concat([testB, ab], ignore_index=True))
pb = stream(big)
qb = cases(pb)
s_res["S3_one_continuous_record"] = dict(rows=len(big), records=int(pb.record_id.nunique()), cases=len(qb),
                                         distinct_case_record_ids=int(qb.record_id.nunique()),
                                         cases_sharing_a_record_id=int(qb.record_id.duplicated(keep=False).sum()),
                                         note="콘솔(app.js)은 건을 record_id로 찾으므로(selectCase·결과 저장) 같은 record_id의 둘째 건부터는 상세·결과 기록에 닿지 않는다")
big.to_csv(TMP / "continuous_B_plus_abnormal.csv", index=False)
res["stream"] = s_res
log(f"S2 격상(이상 시작 기준 행) {s_res['S2_false_alarm_lead']['escalation_rows_after_onset']} · S3 건 {len(qb)}개 중 서로 다른 record_id {qb.record_id.nunique()}")

# ============================================================ 6. U6: 감시 규칙(전류 배율) 재계산 → monitor_gain_v2.csv
mg_csv = pd.read_csv(OUTP / "monitor_gain_v2.csv")
spB = splits["B"]
refB = Reference.from_frame(pd.concat([spB["train"], spB["cal"]], ignore_index=True))
g = gain_scenarios(models["B"], refB, spB["test"], .01)
cmp = mg_csv[(mg_csv.split == "B") & np.isclose(mg_csv.alpha, .01)].set_index("gain")
mg_ok = all(r.alerted_by_window == cmp.loc[r.gain, "alerted_by_window"] and bool(r.recalibration_review) == bool(cmp.loc[r.gain, "recalibration_review"])
            for r in g.itertuples())
w0 = monitor_windows(models["B"].predict(spB["test"], .01), spB["test"], .01, len(models["B"].cal), refB)
res["U6_monitor"] = dict(B_a1_match_csv=bool(mg_ok), gains=g[["gain", "alerted_by_window", "windows_exceed", "windows_exceed99", "windows_drift_up",
                                                               "windows_low_load", "recalibration_review"]].to_dict("records"),
                         nominal_windows=w0[["window", "units", "alerted_units", "limit95", "limit99", "current_ratio", "band_low", "band_high",
                                             "low_load", "level1_notifications", "level2_escalations"]].to_dict("records"),
                         has_cli=bool(re.search(r"__main__", (GUARD / "monitor.py").read_text(encoding="utf-8"))))
log(f"U6 감시 재계산 일치={mg_ok} · 무변화 B 창별 저부하 {w0.low_load.tolist()} · monitor.py CLI {res['U6_monitor']['has_cli']}")

# ============================================================ 7. U6: recalibrate.py(예산·결과 기록 반영·거부)
seg_ok = seg_all < 480
site_csv = TMP / "normal_0_479.csv"
D.inputs_only(normal[seg_ok]).to_csv(site_csv, index=False)
rc = {}
r1 = subprocess.run([PY, str(GUARD / "recalibrate.py"), "--normal", str(site_csv), "--out", str(TMP / "site.json"), "--target-alerts-per-8h", "3"],
                    cwd=YEJUN, env=ENV, capture_output=True, text=True)
rep = json.loads((TMP / "site_report.json").read_text(encoding="utf-8"))
rc["target3"] = dict(returncode=r1.returncode, passed=rep["passed"], saved=rep["model_saved"], units=rep["units"],
                     checks=[(c["name"], c["value"], c.get("limit"), c["ok"]) for c in rep["checks"]],
                     power=rep["checks"][0].get("power_if_rate_multiplied"), false_reject=rep["checks"][0].get("false_reject_rate"),
                     budget={k: rep["budget"].get(k) for k in ("nominal_alerts_per_8h", "calibrated95_alerts_per_8h", "target_alerts_per_8h",
                                                                "alpha_required", "calibration_units_required", "within_budget", "advice")},
                     stdout_tail=r1.stdout[-600:])
# 결과 기록 반영: 같은 자료를 동결 B 모델 α5%로 분석한 대기열 중 절반만 "정상 확인"으로 닫은 콘솔 내보내기 모양의 CSV
pp = models["B"].predict(pd.read_csv(site_csv), .05)
qq = cases(pp)
qq["outcome"] = np.where(np.arange(len(qq)) % 2 == 0, "정상 확인", "")
qq.to_csv(TMP / "outcomes.csv", index=False)
tt = pd.to_datetime(pd.read_csv(site_csv)[D.TIME], format="mixed", utc=True)
drop = np.zeros(len(tt), bool)
for r in qq[qq.outcome.ne("정상 확인")].itertuples():
    # 콘솔 내보내기 CSV를 다시 읽으면 빈 칸은 결측이다: 열린 쪽은 자료 처음·끝까지(monitor.exclude_unconfirmed 문서)
    lo_t = pd.to_datetime(r.suspect_from, format="mixed", utc=True) if isinstance(r.suspect_from, str) and r.suspect_from else pd.NaT
    hi_t = pd.to_datetime(r.suspect_to, format="mixed", utc=True) if isinstance(r.suspect_to, str) and r.suspect_to else pd.NaT
    drop |= ((tt >= lo_t).to_numpy() if pd.notna(lo_t) else True) & ((tt <= hi_t).to_numpy() if pd.notna(hi_t) else True)
r2 = subprocess.run([PY, str(GUARD / "recalibrate.py"), "--normal", str(site_csv), "--out", str(TMP / "site2.json"), "--outcomes", str(TMP / "outcomes.csv")],
                    cwd=YEJUN, env=ENV, capture_output=True, text=True)
rep2 = json.loads((TMP / "site2_report.json").read_text(encoding="utf-8"))
rc["outcomes"] = dict(returncode=r2.returncode, cases=len(qq), unconfirmed=int(qq.outcome.ne("정상 확인").sum()), excluded=rep2["excluded_by_outcomes"],
                      rows_removed_independent=int(drop.sum()), passed=rep2["passed"])
r3 = subprocess.run([PY, str(GUARD / "recalibrate.py"), "--normal", str(site_csv), "--out", str(TMP / "site3.json"), "--cal-units", "50"],
                    cwd=YEJUN, env=ENV, capture_output=True, text=True)
rc["refuse_cal50"] = dict(returncode=r3.returncode, model_exists=(TMP / "site3.json").exists(), stderr=r3.stderr.strip()[-200:])
res["U6_recalibrate"] = rc
log(f"U6 재보정 예산3: rc={r1.returncode} 통과={rep['passed']} · 결과 반영 제외 {rep2['excluded_by_outcomes']} (독립 {int(drop.sum())}) · cal50 rc={r3.returncode}")

# ============================================================ 8. U7: simulate.py CLI = 일괄 분석
sim_csv = TMP / "sim.csv"
segA = D.segments(abnormal)
part = pd.concat([normal[(seg_all >= 421) & (seg_all <= 424)], abnormal[segA < 5]], ignore_index=True)
D.inputs_only(part).to_csv(sim_csv, index=False)
t = time.time()
r4 = subprocess.run([PY, str(GUARD / "simulate.py"), "--csv", str(sim_csv), "--split", "B", "--model", str(TMP / "art" / "guard_B.json"),
                     "--speed", "0", "--chunk", "1", "--log", str(TMP / "sim_log.csv")], cwd=YEJUN, env=ENV, capture_output=True, text=True)
sim_s = time.time() - t
slog = pd.read_csv(TMP / "sim_log.csv")
batch = models["B"].predict(pd.read_csv(sim_csv), .01)
res["U7_simulate"] = dict(returncode=r4.returncode, seconds=round(sim_s, 1), rows=len(part),
                          first_alert_rows_eq_batch=slog[slog.kind.eq("첫 알림")].row_id.tolist() == batch.index[batch.notification.eq(1)].tolist(),
                          escalation_rows_eq_batch=slog[slog.kind.eq("격상")].row_id.tolist() == batch.index[batch.escalation.eq(1)].tolist(),
                          events=slog.kind.value_counts().to_dict(), compute_ms_p95=float(slog.compute_ms.quantile(.95)),
                          stderr_tail=r4.stderr.strip()[-200:],
                          docstring_figure_path_exists=(GUARD / "outputs" / "fig_architecture_v2.png").exists())
log(f"U7 모의 운용 {res['U7_simulate']}")

# ============================================================ 9. U4: 기대효과 식 재계산 + 0 점검 부담 행
ee = pd.read_csv(OUTP / "expected_effect_v2.csv")
ee_ok = []
for r in ee.itertuples():
    l2 = 0.0 if pd.isna(r.level2_per_8h) else r.level2_per_8h
    h = ((r.level1_per_8h * r.assume_minutes_level1 if r.policy == "전건 확인" else 0) + l2 * r.assume_minutes_level2) / 60
    inspect_y = h * r.assume_shifts_per_day * r.assume_days_per_year
    avoided = r.assume_failures_per_year * r.source_detect_probability * r.assume_avoided_fraction * r.source_downtime_days * r.assume_shifts_per_day * 8
    ee_ok.append(close(h, r.inspection_hours_per_shift) and close(inspect_y, r.inspection_hours_per_year) and close(avoided, r.downtime_hours_avoided_per_year)
                 and close(inspect_y / avoided, r.breakeven_loss_ratio))
zero = ee[ee.inspection_hours_per_shift.eq(0)]
res["U4_expected_effect"] = dict(rows=len(ee), formula_all_match=bool(all(ee_ok)),
                                 zero_burden_rows=zero[["alert_scenario", "policy", "case", "level2_per_8h", "breakeven_loss_ratio"]].to_dict("records"),
                                 upper_L2_only=ee[(ee.alert_scenario == "관측 95% 상한") & (ee.policy == "2단계만 출동")][
                                     ["case", "level2_per_8h", "inspection_hours_per_shift", "shift_share", "breakeven_loss_ratio"]].to_dict("records"),
                                 detect_basis_for_all_policies=sorted(ee.source_detect_basis.unique().tolist()))
log(f"U4 기대효과 식 일치={all(ee_ok)} · 점검 0시간 행 {len(zero)}")

# ============================================================ 10. U8: 판단표 = 조치 규칙 원천, 점검 항목·FM·가이드북 쪽
dt = pd.read_csv(OUTP / "decision_table_v2.csv")
dt_eq = dt.fillna("").to_dict("records") == [{k: v for k, v in r.items()} for r in DECISION_TABLE]
produced = {action_for(v, c, sh) for v in (False, True) for c in (False, True) for sh in (False, True)}
fm = pd.read_csv(YEJUN / "analysis" / "press_evidence" / "failure_mode_map.csv")
fm_ids = set(fm.fm_id)
fm_used = {x for r in DECISION_TABLE for x in r["failure_modes"].split("·")}
pdf = next((REPO / "데이터셋" / "프레스_유압펌프_예지보전").glob("Guidebook_*.pdf"), None)
pages = {}
if pdf is not None:
    for pg in (7, 8):     # PDF 쪽 → 인쇄 쪽 6, 7
        txt = subprocess.run(["pdftotext", "-f", str(pg), "-l", str(pg), "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
        flat = re.sub(r"\s+", "", txt)
        pages[f"pdf{pg}"] = dict(printed_page=re.findall(r"^\s*(\d+)\s*$", txt, re.M)[-1:] or None, gear_type="기어형" in flat,
                                 gear_wear="기어마모" in flat, output_pressure="출력유압이약해" in flat, defect="불량품" in flat,
                                 downtime_2_3_days="2~3일" in flat, noise_by_operator="작동소음" in flat)
res["U8_decision_table"] = dict(csv_eq_source=bool(dt_eq), actions_all_in_table=bool(produced <= set(dt.action)) and ACTIONS["invalid"] in set(dt.action),
                                checklist_nonempty=bool(dt.checklist.fillna("").str.len().gt(0).all()), fm_ids_exist=bool(fm_used <= fm_ids),
                                guidebook=pages)
log(f"U8 판단표 원천 일치={dt_eq} · 조치 포함={res['U8_decision_table']['actions_all_in_table']} · 가이드북 {pages}")

# ============================================================ 11. U3: OPERATIONS.md 참조 파일·명령 존재
ops = (GUARD / "OPERATIONS.md").read_text(encoding="utf-8")
refs = set(re.findall(r"\]\(([^)#\s]+)\)", ops)) | set(re.findall(r"`([\w./-]+\.(?:py|csv|png|json))`", ops))
exist = {r: (GUARD / r).exists() or (GUARD / "outputs" / r).exists() for r in sorted(refs)}
res["U3_operations_refs"] = dict(refs=exist, all_exist=all(exist.values()),
                                 figures={p: sha(GUARD / p) for p in ("docs/fig_operation_flow.png", "docs/fig_architecture.png")},
                                 console_capture=json.loads((OUTP / "console" / "capture.json").read_text(encoding="utf-8"))["shots"],
                                 capture_hash_ok={n: sha(OUTP / "console" / n) == v["sha256"] for n, v in
                                                  json.loads((OUTP / "console" / "capture.json").read_text(encoding="utf-8"))["shots"].items()},
                                 capture_web_code_current={n: sha(GUARD / "web" / n) == v for n, v in
                                                           json.loads((OUTP / "console" / "capture.json").read_text(encoding="utf-8"))["web_code_sha256"].items()})
log(f"U3 OPERATIONS 참조 {exist}")

# ============================================================ 12. 콘솔 서버(임시 포트) API 직접 호출
def free_port():
    with socket.socket() as sck:
        sck.bind(("127.0.0.1", 0))
        return sck.getsockname()[1]


port = free_port()
srv = subprocess.Popen([PY, str(GUARD / "serve.py"), "--port", str(port)], cwd=GUARD, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
base = f"http://127.0.0.1:{port}"
api = dict(port=port)


def call(path, body=None, timeout=120):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return r.status, raw


try:
    for _ in range(240):
        try:
            call("/api/overview", timeout=5)
            break
        except OSError:
            time.sleep(.5)
    st, html = call("/")
    api["index"] = dict(status=st, has_levels=("2단계" in html.decode()), has_outcome_form=("점검 결과 기록" in html.decode()),
                        has_simulate=("모의 운용" in html.decode()), method_note_upper=("95% 상한" in html.decode()))
    st, raw = call("/api/overview")
    ov = json.loads(raw)
    api["overview"] = dict(status=st, keys=sorted(ov), levels_rows=len(ov["levels"]), quality_windows_rows=len(ov["quality_windows"]),
                           monitor_gain_rows=len(ov["monitor_gain"]), expected_effect_rows=len(ov["expected_effect"]),
                           decision_checklist=all(r.get("checklist") for r in ov["decision_table"]), outcome_columns=ov["outcome_columns"],
                           audit_all_ok=ov["audit"].get("all_ok"))
    for s in ("A", "B"):
        t = time.time()
        st, raw = call("/api/analyze", dict(split=s, alpha=.01, prior=.01, dataset="mixed"))
        r_ = json.loads(raw)
        cs = pd.DataFrame(r_["cases"])
        fa_c = cs[cs.reference_label.eq(0)] if len(cs) else cs
        api[f"mixed_{s}"] = dict(status=st, seconds=round(time.time() - t, 2), level_counts=r_["level_counts"], cases=len(cs),
                                 notifications=r_["stats"]["notifications"],
                                 fa_ranks=sorted(fa_c.priority_rank.tolist()) if len(fa_c) else [],
                                 fa_max_probability=fa_c.max_probability.round(4).tolist() if len(fa_c) else [],
                                 abnormal_max_probability=sorted(set(cs[cs.reference_label.eq(1)].max_probability.round(4))) if len(cs) else [],
                                 abnormal_suspect_open=int(cs[cs.reference_label.eq(1)].suspect_open.sum()) if len(cs) else 0,
                                 fa_suspect_seconds=fa_c.suspect_seconds.round(3).tolist() if len(fa_c) else [])
    # 사전 비율 π 0.1%에서 같은 건의 이상 확률(경보는 불변)
    st, raw = call("/api/analyze", dict(split="B", alpha=.01, prior=.001, dataset="mixed"))
    r_ = json.loads(raw)
    cs = pd.DataFrame(r_["cases"])
    api["mixed_B_prior0.001"] = dict(level_counts=r_["level_counts"], fa_max_probability=cs[cs.reference_label.eq(0)].max_probability.round(4).tolist(),
                                     abnormal_max_probability=sorted(set(cs[cs.reference_label.eq(1)].max_probability.round(4))))
    # 끊김 없는 연속 CSV 업로드: 한 기록 안의 여러 건
    csv_text = (TMP / "continuous_B_plus_abnormal.csv").read_text(encoding="utf-8")
    st, raw = call("/api/analyze", dict(split="B", alpha=.01, prior=.01, dataset="upload", csv=csv_text))
    r_ = json.loads(raw)
    cs = pd.DataFrame(r_["cases"])
    api["upload_continuous"] = dict(status=st, rows=r_["stats"]["rows"], segments=r_["stats"]["segments"], cases=len(cs),
                                    distinct_record_ids=int(cs.record_id.nunique()) if len(cs) else 0,
                                    level_counts=r_["level_counts"],
                                    cases_first_rows=cs.first_row.tolist() if len(cs) else [],
                                    cases_alarm_rows=cs.alarm_rows.tolist() if len(cs) else [])
finally:
    srv.terminate()
    try:
        srv.wait(timeout=10)
    except subprocess.TimeoutExpired:
        srv.kill()
        srv.wait()
    stopped = True
    try:
        call("/api/overview", timeout=2)
        stopped = False
    except OSError:
        pass
    api["server_stopped"] = stopped and srv.returncode is not None
res["console_api"] = api
log(f"콘솔 API {json.dumps(api, ensure_ascii=False, default=jsonable)[:1500]}")

# ============================================================ 13. 끝
res["provenance"]["status_after"] = git("status", "--porcelain", "--", "yejun")
res["provenance"]["cache_dirs_new"] = sorted(set(pycache_dirs()) - set(res["provenance"]["cache_dirs_before"]))
res["elapsed_s"] = round(time.time() - T0, 1)
OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=jsonable), encoding="utf-8")
log(f"끝 · {res['elapsed_s']}s · status_after={res['provenance']['status_after']!r} · 새 캐시 폴더={res['provenance']['cache_dirs_new']}")
