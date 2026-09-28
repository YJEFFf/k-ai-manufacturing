"""평가관 04(현장 활용방안) cycle2 round3 검증. 저장소 코드·산출물은 읽기만 한다.

실행(yejun/에서):
  OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python \
      analysis/press_rubric_review/cycle2/round3/judge04_r3_check.py 2>&1 | tee analysis/press_rubric_review/cycle2/round3/judge04_r3_check.log
  --skip-retrain: 원본 재학습을 건너뛰고 로컬 모델(해시를 manifest와 대조)을 쓴다(개발용).
쓰는 파일: 이 폴더의 judge04_r3_check.json 하나. 재학습·재보정·모의 운용·명령 산출물은 시스템 임시 폴더(judge04_c2r3_*)에만 쓴다.

[사후] 이상 라벨을 본 관찰(성능 근거 아님). [가정] 현장 자료가 없어 평가관이 둔 값. [주입] 인공 신호.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
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
from model import (GuardModel, StreamDetector, cases, incidents, timing_warning, load_bundle, D, ALPHAS,  # noqa: E402
                   INCIDENT_MAX_GAP_S, TIME_TOL_S, QUALITY_ACTIONS)
from monitor import (Reference, monitor_windows, gain_scenarios, exclude_unconfirmed,  # noqa: E402
                     ACTION_RECALIBRATE, ACTION_INSPECT)
from recalibrate import inject  # noqa: E402
import simulate  # noqa: E402

SKIP_RETRAIN = "--skip-retrain" in sys.argv
OUT = HERE / "judge04_r3_check.json"
TMP = Path(tempfile.mkdtemp(prefix="judge04_c2r3_"))
PY = sys.executable
ENV = dict(os.environ, OMP_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
res: dict = dict(tmp_dir=str(TMP), skip_retrain=SKIP_RETRAIN)
T0 = time.time()


def sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout.strip()


def log(msg):
    print(f"[{time.time() - T0:6.1f}s] {msg}", flush=True)


def close(a, b, tol=1e-9):
    try:
        fa, fb = float(a), float(b)
    except (TypeError, ValueError):
        return a == b
    if math.isnan(fa) and math.isnan(fb):
        return True
    return bool(np.isclose(fa, fb, rtol=tol, atol=tol))


def jsonable(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return str(o)


def pycache_dirs():
    return sorted(subprocess.run(["find", str(YEJUN), "-name", "__pycache__", "-o", "-name", ".pytest_cache"],
                                 capture_output=True, text=True).stdout.split())


# ============================================================ 0. 출처
res["provenance"] = dict(head=git("rev-parse", "HEAD"), status_before=git("status", "--porcelain", "--", "yejun"),
                         python=sys.version.split()[0], omp=os.environ.get("OMP_NUM_THREADS"), cache_dirs_before=pycache_dirs())
log(f"HEAD {res['provenance']['head']} · status_before={res['provenance']['status_before']!r}")

# ============================================================ 1. 원본 재학습(임시 폴더) → manifest·커밋 산출물 대조
manifest = json.loads((OUTP / "manifest.json").read_text(encoding="utf-8"))
local_ok = {k: (GUARD / "artifacts" / k).exists() and sha(GUARD / "artifacts" / k) == v for k, v in manifest["artifacts"].items()}
committed_ok = {k: (OUTP / k).exists() and sha(OUTP / k) == v for k, v in manifest["outputs"].items() if (OUTP / k).exists()}
analysis_ok = {k: (OUTP / k).exists() and sha(OUTP / k) == v for k, v in manifest["analysis"]["outputs"].items()}
retrain = dict(local_artifacts_eq_manifest=local_ok, committed_outputs_eq_manifest=committed_ok,
               committed_analysis_outputs_eq_manifest_all=bool(all(analysis_ok.values())),
               analysis_mismatch=[k for k, v in analysis_ok.items() if not v])
ART = GUARD / "artifacts"
if not SKIP_RETRAIN:
    t = time.time()
    run = subprocess.run([PY, str(GUARD / "train.py"), "--out", str(TMP / "out"), "--artifacts", str(TMP / "art"), "--rolling"],
                         cwd=YEJUN, env=ENV, capture_output=True, text=True)
    newm = json.loads((TMP / "out" / "manifest.json").read_text(encoding="utf-8")) if (TMP / "out" / "manifest.json").exists() else {}
    retrain.update(returncode=run.returncode, seconds=round(time.time() - t, 1), stderr_tail=run.stderr[-300:],
                   artifacts_eq_manifest={k: newm.get("artifacts", {}).get(k) == v for k, v in manifest["artifacts"].items()},
                   outputs_eq_manifest={k: newm.get("outputs", {}).get(k) == v for k, v in manifest["outputs"].items()})
    ART = TMP / "art"
res["retrain_from_raw"] = retrain
log(f"재학습: {retrain.get('returncode')} {retrain.get('seconds')}s · 로컬 모델=manifest {all(local_ok.values())} · "
    f"커밋 산출물=manifest {all(committed_ok.values())} · 분석 산출물=manifest {retrain['committed_analysis_outputs_eq_manifest_all']}")

models = {s: load_bundle(ART / f"guard_{s}.json") for s in ("A", "B")}
normal, abnormal, _ = D.load()
seg_all = D.segments(normal)
splits = {s: D.split_normal(normal, seg_all, s) for s in ("A", "B")}


# ============================================================ 2. 사건 층(R2-03): 독립 구현과 대조
def my_incidents(p, gap_s=INCIDENT_MAX_GAP_S):
    """평가관 독립 구현. 알림 단위(기록구간×50행 블록) 순서대로: 경보 단위가 '바로 앞 단위도 경보 + 공백 ≤ gap_s'면 같은 사건.
    사건 안 경보 1행째 = 사건 알림, 2행째 = 격상, 이후 새 근거 성분 = 갱신(사건에 이미 성분이 있을 때)."""
    t = pd.to_datetime(p.timestamp, format="mixed", utc=True, errors="coerce").ffill()
    rec, blk = p.record_id.to_numpy(), p.alert_unit.to_numpy()
    alarm = p.alarm.to_numpy().astype(bool)
    why = p.reason.astype(str).to_numpy()
    n = len(p)
    out = np.zeros((n, 4), dtype=int)
    change = np.r_[True, (rec[1:] != rec[:-1]) | (blk[1:] != blk[:-1])]
    starts = np.flatnonzero(change)
    ends = np.r_[starts[1:], n]
    inc, count, comps = 0, 0, set()
    prev_alarm, prev_end = False, None
    tv = t.to_numpy()
    for s, e in zip(starts, ends):
        rows = np.arange(s, e)
        a_rows = rows[alarm[s:e]]
        if len(a_rows):
            gap = (pd.Timestamp(tv[s]) - pd.Timestamp(prev_end)).total_seconds() if prev_end is not None else np.inf
            if not (prev_alarm and gap <= gap_s):
                inc += 1; count = 0; comps = set()
            for i in a_rows:
                count += 1
                new = set(filter(None, why[i].split("+"))) - comps
                out[i] = (inc, int(count == 1), int(count == 2), int(bool(new) and count > 1 and bool(comps)))
                comps |= new
        prev_alarm, prev_end = bool(len(a_rows)), tv[e - 1]
    return out


def inc_cols(p):
    return p[["incident_id", "incident_notification", "incident_escalation", "incident_update"]].to_numpy(int)


# 2a. 분할×α×(정상 평가·이상) 12조합 + incident_summary_v2.csv 재계산
isum = pd.read_csv(OUTP / "incident_summary_v2.csv")
rows, eq_all = [], True
pred_cache = {}
for s in ("A", "B"):
    for a in ALPHAS:
        for subset, frame in (("normal_test", splits[s]["test"]), ("abnormal", abnormal)):
            p = models[s].predict(frame, a)
            pred_cache[(s, a, subset)] = p
            mine = my_incidents(p)
            same = bool((mine == inc_cols(p)).all())
            eq_all &= same
            r = dict(split=s, alpha=a, subset=subset, records=int(p.record_id.nunique()), case_notifications=int(p.notification.sum()),
                     case_escalations=int(p.escalation.sum()), incidents=int(mine[:, 0].max()), incident_level2=int(mine[:, 2].sum()),
                     incident_notifications=int(mine[:, 1].sum() + mine[:, 2].sum()), incident_updates=int(mine[:, 3].sum()), code_eq_mine=same)
            c = isum[(isum.split == s) & np.isclose(isum.alpha, a) & (isum.subset == subset)].iloc[0]
            r["csv_eq"] = all(int(c[k]) == r[k] for k in ("records", "case_notifications", "case_escalations", "incidents", "incident_level2",
                                                           "incident_notifications", "incident_updates"))
            rows.append(r)
isr = pd.DataFrame(rows)
res["R2_03_incident_summary"] = dict(rows=len(isr), code_eq_independent_all=bool(eq_all), csv_eq_all=bool(isr.csv_eq.all()),
                                     table=isr.to_dict("records"))
log(f"사건 요약 12행: 코드=독립 구현 {eq_all} · CSV 일치 {bool(isr.csv_eq.all())} · B α1% 이상 {isr[(isr.split=='B')&(isr.alpha==.01)&(isr.subset=='abnormal')].iloc[0][['incidents','incident_notifications']].tolist()}")


# 2b. 스트림 = 일괄(사건 열). 콘솔 혼합 자료(정상 평가 + 이상 원 시각), 이어 붙인 연속 기록(한 기록구간)
def stream(frame, model, alpha=.01, chunk=128):
    sd = StreamDetector(model, alpha)
    return pd.concat([sd.push(frame.iloc[i:i + chunk]) for i in range(0, len(frame), chunk)], ignore_index=True)


def restamp(frame, start="2026-09-27 08:00:00"):
    g = D.inputs_only(frame).reset_index(drop=True)
    g[D.TIME] = (pd.Timestamp(start) + pd.to_timedelta(np.arange(len(g)) * D.DT, unit="s")).strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3]
    return g


mixB = D.inputs_only(pd.concat([splits["B"]["test"], abnormal], ignore_index=True))
contB = restamp(pd.concat([splits["B"]["test"], abnormal], ignore_index=True))
sb = {}
for name, frame, chunks in (("mixed_B_original_time", mixB, (7, 128)), ("continuous_B_one_record", contB, (7, 128))):
    batch = models["B"].predict(frame, .01)
    mine = my_incidents(batch)
    d = dict(rows=len(frame), batch_eq_independent=bool((mine == inc_cols(batch)).all()),
             incidents=int(batch.incident_id.max()), incident_notifications=int(batch.incident_notification.sum() + batch.incident_escalation.sum()),
             case_notifications=int(batch.notification.sum() + batch.escalation.sum()))
    for ch in chunks:
        st = stream(frame, models["B"], .01, ch)
        d[f"chunk{ch}_incident_eq_batch"] = bool((inc_cols(st) == inc_cols(batch)).all())
        d[f"chunk{ch}_case_cols_eq_batch"] = bool((st[["notification", "escalation", "alert_level"]].to_numpy() ==
                                                   batch[["notification", "escalation", "alert_level"]].to_numpy()).all())
    sb[name] = d
# 한 행씩(chunk 1): 오경보 구간 앞뒤 + 이상 앞 5구간(시험과 다른 조합: 오경보 461·570 포함)
a_seg = D.segments(abnormal)
small = D.inputs_only(pd.concat([normal[(seg_all >= 459) & (seg_all <= 462)], normal[(seg_all >= 569) & (seg_all <= 571)],
                                 abnormal[a_seg < 5]], ignore_index=True))
b1, s1 = models["B"].predict(small, .01), stream(small, models["B"], .01, 1)
sim_small = simulate.run(small, models["B"], .01, chunk=1)
sb["chunk1_small"] = dict(rows=len(small), incident_eq_batch=bool((inc_cols(s1) == inc_cols(b1)).all()),
                          batch_eq_independent=bool((my_incidents(b1) == inc_cols(b1)).all()),
                          simulate_notify_rows=sim_small[sim_small.notify.eq(1)].row_id.tolist(),
                          batch_notify_rows=sorted(b1.index[b1.incident_notification.eq(1) | b1.incident_escalation.eq(1)].tolist()),
                          simulate_kinds=sim_small[sim_small.notify.eq(1)].kind.tolist())
res["R2_03_stream_batch"] = sb
log(f"스트림=일괄: { {k: {kk: vv for kk, vv in v.items() if 'eq' in kk} for k, v in sb.items()} }")

# 2c. 사건 격상과 사건 대기열 단계의 불일치: 경보 1행 오경보 기록 두 개가 60초 안에 이어질 때
pB = pred_cache[("B", .01, "normal_test")]
fa_recs = pB[pB.alarm.eq(1)].groupby("record_id").alarm.sum()
testB = splits["B"]["test"].reset_index(drop=True)
rel = pB.record_id.to_numpy()


def rec_frame(r):
    return D.inputs_only(testB[rel == r]).reset_index(drop=True)


def shift_to(frame, start):
    g = frame.copy()
    t = pd.to_datetime(g[D.TIME], format="mixed")
    g[D.TIME] = (t - t.iloc[0] + pd.Timestamp(start)).dt.strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3]
    return g


clean = [r for r, g in pB.groupby("record_id") if len(g) == 50 and g.alarm.sum() == 0][:2]
parts, tcur = [], pd.Timestamp("2026-09-27 09:00:00")
for r in (clean[0], int(fa_recs.index[0]), int(fa_recs.index[1]), clean[1]):
    f = shift_to(rec_frame(r), tcur)
    parts.append(f)
    tcur = pd.to_datetime(f[D.TIME]).iloc[-1] + pd.Timedelta(seconds=2)
merged = pd.concat(parts, ignore_index=True)
merged.to_csv(TMP / "two_single_row_false_alarms_2s_apart.csv", index=False)
pm = models["B"].predict(merged, .01)
qm = cases(pm)
im = incidents(qm, pm)
sim_m = simulate.run(merged, models["B"], .01, chunk=1)
res["new_incident_level_mismatch"] = dict(
    records=[clean[0], int(fa_recs.index[0]), int(fa_recs.index[1]), clean[1]], alarm_rows_per_fa=fa_recs.iloc[:2].tolist(),
    predict_incident_escalations=int(pm.incident_escalation.sum()), predict_incidents=int(pm.incident_id.max()),
    simulate_events=sim_m[["row_id", "kind", "notify", "level", "level_name"]].to_dict("records"),
    cases_levels=qm.level.tolist(), incident_table=im[["incident_id", "cases", "level", "level_name", "escalation_row", "quality_action"]].to_dict("records"),
    note="사건 격상(predict·simulate: 2단계 '점검 요청' 알림)이 났는데 사건 대기열(model.incidents, 콘솔·incidents_*.csv)은 건 단계 최댓값으로 1단계 '주의'·1단계 품질 조치")
log(f"사건 단계 불일치: simulate {sim_m[['kind','level']].values.tolist()} · 사건 대기열 단계 {im.level.tolist()} escalation_row {im.escalation_row.tolist()}")


# 2d. [주입] 지속 약한 이상: B 평가 21연속 기록 전체 행에 주입 → 건·사건·알림 수, 단계 불일치
def sustained(model, family, level, start, n=21, alpha=.01, seed=0):
    test = D.inputs_only(testB)
    mask = (rel >= start) & (rel < start + n)
    f = test if family == "none" else inject(test, model, family, level, mask, np.random.default_rng(seed))
    p = model.predict(f, alpha)
    win = p[(p.record_id >= start) & (p.record_id < start + n)]
    q = cases(p)
    q = q[(q.record_id >= start) & (q.record_id < start + n)] if len(q) else q
    ev = win[win.incident_id > 0]
    iq = incidents(cases(p), p)
    iq = iq[iq.incident_id.isin(ev.incident_id.unique())] if len(iq) else iq
    esc_inc = set(win[win.incident_escalation.eq(1)].incident_id)
    mismatch = int(sum(1 for r in iq.itertuples() if (r.incident_id in esc_inc) and r.level == 1)) if len(iq) else 0
    return dict(records_alarmed=int(win.groupby("record_id").alarm.max().sum()), cases=int(len(q)),
                case_alerts=int(win.notification.sum() + win.escalation.sum()), incidents=int(ev.incident_id.nunique()),
                incident_alerts=int(win.incident_notification.sum() + win.incident_escalation.sum()),
                incidents_escalated=len(esc_inc), incidents_level1_but_escalated=mismatch)


fams = (("cur_noise", .1), ("cur_noise", .2), ("cur_offset", .2), ("cur_offset", .4), ("vib_noise", 2.0), ("vib_noise", 4.0))
starts_rel = (10, 50, 90, 120, 155)   # 오경보 기록(상대 3·41·150)을 피한 21연속 창
sus = []
for fam, lv in fams:
    for st in starts_rel:
        sus.append(dict(family=fam, level=lv, start=st, **sustained(models["B"], fam, lv, st)))
sus = pd.DataFrame(sus)
agg = sus.groupby(["family", "level"]).agg(records_alarmed=("records_alarmed", "mean"), case_alerts=("case_alerts", "mean"),
                                           incidents=("incidents", "mean"), incident_alerts=("incident_alerts", "mean"),
                                           max_incidents=("incidents", "max"), mismatch_total=("incidents_level1_but_escalated", "sum")).reset_index()
res["new_sustained_weak_fault"] = dict(windows=list(starts_rel), per_window=sus.to_dict("records"), summary=agg.to_dict("records"),
                                       reference_contest_anomaly="대회 이상 21기록: 사건 1개·알림 2건(incident_summary_v2.csv)",
                                       note="[주입] 21연속 기록(약 2.5~3분)의 모든 행. 경보 없는 기록이 끼면 사건이 닫혀 새 사건·새 알림이 된다")
log("지속 약한 이상(5창 평균):\n" + agg.to_string(index=False))

# ============================================================ 3. R2-02 비사후 2단계 추정 재계산 + 민감도
lv_csv = pd.read_csv(OUTP / "alert_levels_v2.csv")


def rolling_fits():
    fits = {}
    for end in (180, 240, 300, 360, 420):
        tr = normal[seg_all < end]
        ca = normal[(seg_all >= end) & (seg_all < end + 120)]
        fits[f"rolling_test_{end + 120}_{end + 179}"] = (GuardModel.fit(tr, ca, split=f"train_to_{end}"), end + 120, end + 180)
    return fits


FITS = {"frozen_A": (models["A"], 480, 600), "frozen_B": (models["B"], 420, 600), **rolling_fits()}
lvl, alerted = [], {}
for name, (m, lo, hi) in FITS.items():
    test = normal[(seg_all >= lo) & (seg_all < hi)]
    for a in ALPHAS:
        pn = m.predict(test, a)
        g = pn.groupby("record_id").agg(l1=("alarm", "max"), l2=("escalation", "max"), rows=("alarm", "sum"))
        for level, col in ((1, "l1"), (2, "l2")):
            k = int(g[col].sum())
            c = lv_csv[(lv_csv.model == name) & np.isclose(lv_csv.alpha, a) & (lv_csv.level == level)].iloc[0]
            lvl.append(dict(model=name, alpha=a, level=level, k=k, n=len(g), csv_eq=bool(k == c.normal_alerted_segments and len(g) == c.normal_segments)))
        alerted[(name, a)] = {int(r + lo): int(g.loc[r, "rows"]) for r in g.index[g.l1 == 1]}
lvl = pd.DataFrame(lvl)
indep = ["rolling_test_300_359", "rolling_test_360_419", "rolling_test_540_599"]


def ratio(models_, a):
    g = lvl[lvl.model.isin(models_) & np.isclose(lvl.alpha, a)]
    k1, k2 = int(g[g.level == 1].k.sum()), int(g[g.level == 2].k.sum())
    return k1, k2


nominal = float(lv_csv[(lv_csv.model == "frozen_B") & np.isclose(lv_csv.alpha, .01) & (lv_csv.level == 1)].nominal_alerts_per_8h_elapsed.iloc[0])
sens = []
for label, mods, a in (("독립 폴드 α5%(팀 채택)", indep, .05), ("독립 폴드 α3%", indep, .03), ("동결 B α3%", ["frozen_B"], .03),
                       ("동결 B α5%", ["frozen_B"], .05), ("동결 A α5%", ["frozen_A"], .05)):
    k1, k2 = ratio(mods, a)
    r = k2 / k1 if k1 else float("nan")
    hi = float(stats.beta.ppf(.95, k2 + 1, k1 - k2)) if k1 else float("nan")
    sens.append(dict(basis=label, level1=k1, level2=k2, ratio=r, ratio_hi95=hi, level2_per_8h=nominal * r, level2_per_8h_hi95=nominal * hi))
ee = pd.read_csv(OUTP / "expected_effect_v2.csv")
ee_np = ee[ee.alert_scenario.str.startswith("비사후")]
seen_570 = {name: alerted[(name, .05)].get(570) for name in indep}
res["R2_02_level2_estimate"] = dict(
    levels_recomputed_rows=len(lvl), levels_csv_eq_all=bool(lvl.csv_eq.all()), nominal_level1_per_8h=nominal,
    sensitivity=sens, csv_nonposthoc_level2=sorted(set(ee_np.level2_per_8h.round(6))),
    independent_alpha5_alerted_records_absolute={name: alerted[(name, .05)] for name in indep},
    seen_false_alarm_570_in_independent_fold=seen_570,
    note="팀 채택 비는 독립 폴드 α5% 1/9. 동결 B의 α3·5% 오경보(규칙을 유리하게 고른 자료가 아님)는 2/5·3/7로 더 높다")
log("2단계 비 민감도:\n" + pd.DataFrame(sens).to_string(index=False) + f"\n독립 폴드 α5% 경보 기록(절대 번호:경보 행) {res['R2_02_level2_estimate']['independent_alpha5_alerted_records_absolute']}")

# 기대효과 27행 식 재계산
inj = pd.read_csv(OUTP / "alert_levels_injection_v2.csv")
det_min = float(inj[(inj.split == "B") & np.isclose(inj.alpha, .01) & (inj.family != "none")].level2_detect_2s.min())
lvB = lv_csv[(lv_csv.model == "frozen_B") & np.isclose(lv_csv.alpha, .01)].set_index("level")
k1, k2 = ratio(indep, .05)
rt, rhi = k2 / k1, float(stats.beta.ppf(.95, k2 + 1, k1 - k2))
AL = {"명목": (nominal, np.nan), "비사후 추정(독립 폴드 2/1단계 비)": (nominal, nominal * rt), "비사후 추정 95% 상한": (nominal, nominal * rhi),
      "관측": (lvB.loc[1, "alerts_per_8h_elapsed"], lvB.loc[2, "alerts_per_8h_elapsed"]),
      "관측 95% 상한": (lvB.loc[1, "upper95_alerts_per_8h_elapsed"], lvB.loc[2, "upper95_alerts_per_8h_elapsed"])}
M1, M2, SH, DY, FY, AF = (1, 2, 3), (10, 20, 30), (1, 2, 3), (250, 250, 300), (0.5, 1, 2), (0.3, 0.5, 0.8)
DET = (det_min, .05 ** (1 / 21), 1.0)
ok_rows = []
for r in ee.itertuples():
    k = ("비관", "중간", "낙관").index(r.case)
    a1, a2 = AL[r.alert_scenario]
    m1, m2 = M1[2 - k], M2[2 - k]
    a2u = 0.0 if not np.isfinite(a2) else a2
    hps = ((a1 * m1 if r.policy == "전건 확인" else 0.0) + a2u * m2) / 60
    ih = hps * SH[k] * DY[k]
    av = FY[k] * DET[k] * AF[k] * (2 if k == 0 else 3) * SH[k] * 8
    be = ih / av if av > 0 else np.inf
    ok_rows.append(close(hps, r.inspection_hours_per_shift, 1e-9) and close(ih, r.inspection_hours_per_year, 1e-9)
                   and close(av, r.downtime_hours_avoided_per_year, 1e-9) and close(be, r.breakeven_loss_ratio, 1e-9)
                   and (bool(r.post_hoc) == (r.alert_scenario.startswith("관측") and r.policy == "2단계만 출동")))
mid = ee[(ee.case == "중간") & (ee.policy == "2단계만 출동")][["alert_scenario", "post_hoc", "level2_per_8h", "inspection_hours_per_shift", "breakeven_loss_ratio"]]
res["R2_02_expected_effect"] = dict(rows=len(ee), formula_eq_all=bool(all(ok_rows)), ratio=rt, ratio_hi95=rhi,
                                    level2_per_8h=nominal * rt, level2_per_8h_hi95=nominal * rhi, mid_level2_only=mid.to_dict("records"))
log(f"기대효과 {len(ee)}행 식 일치 {all(ok_rows)} · 비 {rt:.4f}(상한 {rhi:.4f}) → 교대 {nominal*rt:.2f}건(상한 {nominal*rhi:.2f})")

# ============================================================ 4. R2-01 감시 조치 분기·재보정 자료 규칙, R2-07 명령행
spB = splits["B"]
refB = Reference.from_frame(pd.concat([spB["train"], spB["cal"]], ignore_index=True))
tB = D.inputs_only(spB["test"])
ncal = len(models["B"].cal)


def windows(frame, changes=()):
    w = monitor_windows(models["B"].predict(frame, .01), frame, .01, ncal, refB, 60, changes)
    return w[["window", "alerted_units", "limit95", "limit99", "operating_change", "current_ratio", "drift_up",
              "share_magnitude", "share_current", "recommended_action", "recalibration_data"]].to_dict("records")


def gain(k):
    g = tB.copy(); g["AI2_Current"] = pd.to_numeric(g.AI2_Current) * k
    return g


last = D.segments(tB) >= 120
scen = {
    "x1.3_with_change": windows(gain(1.3), [tB.TimeStamp.iloc[5]]),
    "x1.3_no_change": windows(gain(1.3)),
    "x1.5_no_change": windows(gain(1.5)),
    "vib1sigma_last_window_no_change": windows(inject(tB, models["B"], "vib_noise", 1.0, last, np.random.default_rng(0))),
    "vib1sigma_last_window_with_change": windows(inject(tB, models["B"], "vib_noise", 1.0, last, np.random.default_rng(0)),
                                                 [tB.TimeStamp[last].iloc[10]]),
    "cur_offset0.2_last_window_no_change": windows(inject(tB, models["B"], "cur_offset", .2, last, np.random.default_rng(0))),
}
res["R2_01_monitor_branch"] = {k: [dict(w=x["window"], units=x["alerted_units"], lim=(x["limit95"], x["limit99"]), change=x["operating_change"],
                                        ratio=round(x["current_ratio"], 3), drift=x["drift_up"], mag=x["share_magnitude"], cur=x["share_current"],
                                        action=x["recommended_action"], data=x["recalibration_data"]) for x in v] for k, v in scen.items()}
for k, v in res["R2_01_monitor_branch"].items():
    log(f"감시 {k}: " + " | ".join(f"창{x['w']} {x['units']}단위 비{x['ratio']} → {x['action']}" for x in v))

# 재보정 자료 규칙: 콘솔 사건 내보내기 형식(사건 대기열 + 결과 열)을 exclude_unconfirmed에 넣는다(정상 0~479, 동결 B, α1%)
n479 = normal[seg_all < 480].reset_index(drop=True)
p479 = models["B"].predict(n479, .01)
q479 = cases(p479)
i479 = incidents(q479, p479)
exp_cols = ["priority_rank", "incident_id", "level", "level_name", "first_timestamp", "last_case_timestamp", "cases", "case_uids", "records", "evidence",
            "alarm_rows", "observed_rows", "alarm_share", "peak_score", "action", "suspect_from", "suspect_to", "suspect_open", "quality_action",
            "max_probability", "max_likelihood_ratio"]
export = i479[exp_cols].copy()
for c in ("confirmed_at", "owner", "outcome", "measure", "status"):
    export[c] = ""
export.to_csv(TMP / "incident_export_unconfirmed.csv", index=False)
kept_inc, info_inc = exclude_unconfirmed(n479, pd.read_csv(TMP / "incident_export_unconfirmed.csv"))
q479.assign(outcome="").to_csv(TMP / "case_export_unconfirmed.csv", index=False)
kept_case, info_case = exclude_unconfirmed(n479, pd.read_csv(TMP / "case_export_unconfirmed.csv"))
res["R2_01_recalibration_rule"] = dict(incidents=len(i479), cases=len(q479), incident_export=info_inc, case_export=info_case,
                                       same_rows_removed=bool(info_inc["rows_removed"] == info_case["rows_removed"]),
                                       inspect_window_exclusion_in_code=False,
                                       note="'설비 점검 요청' 창 기간을 재보정 자료에서 빼는 규칙은 OPERATIONS 9단계 문장뿐이고 recalibrate.py에 입력이 없다(수작업)")
log(f"재보정 자료: 사건 내보내기 {info_inc} · 건 내보내기 {info_case}")

# 명령행(R2-07): 대회 B 평가 자료 → 2/0/1, 변경 기록 입력
csvB = TMP / "shift_B.csv"; tB.to_csv(csvB, index=False)
chg = TMP / "changes.csv"; pd.DataFrame(dict(time=[tB.TimeStamp.iloc[5]])).to_csv(chg, index=False)
t = time.time()
mon = subprocess.run([PY, str(GUARD / "monitor.py"), "--csv", str(csvB), "--split", "B", "--changes", str(chg), "--out", str(TMP / "win.csv")],
                     cwd=YEJUN, env=ENV, capture_output=True, text=True)
wcli = pd.read_csv(TMP / "win.csv") if (TMP / "win.csv").exists() else pd.DataFrame()
res["R2_07_monitor_cli"] = dict(returncode=mon.returncode, seconds=round(time.time() - t, 1),
                                alerted_by_window="/".join(map(str, wcli.alerted_units)) if len(wcli) else None,
                                actions=wcli.recommended_action.tolist() if len(wcli) else None, stdout_tail=mon.stdout[-400:],
                                simulate_doc_path_exists=(GUARD / "docs" / "fig_architecture.png").exists()
                                and "docs/fig_architecture.png" in (GUARD / "simulate.py").read_text(encoding="utf-8"))
log(f"monitor 명령: rc {mon.returncode} · 창별 {res['R2_07_monitor_cli']['alerted_by_window']}")

# ============================================================ 5. R2-05 시각 흔들림
def jitter(frame, ms, seed=0):
    g = D.inputs_only(frame).reset_index(drop=True)
    t = pd.to_datetime(g[D.TIME], format="mixed")
    g[D.TIME] = (t + pd.to_timedelta(np.random.default_rng(seed).uniform(-ms, ms, len(t)) / 1000, unit="s")).dt.strftime("%Y-%m-%d %H:%M:%S.%f")
    return g


jit = {}
base_n, base_a = models["B"].predict(tB, .01), models["B"].predict(D.inputs_only(abnormal), .01)
for ms in (0, 1, 2, 10, 20, 50):
    pn, pa = models["B"].predict(jitter(tB, ms), .01), models["B"].predict(jitter(abnormal, ms), .01)
    jit[f"{ms}ms"] = dict(normal_records=int(pn.record_id.nunique()), normal_alarm_same=bool((pn.alarm.to_numpy() == base_n.alarm.to_numpy()).all()),
                          normal_alerted_records=int(pn.groupby("record_id").alarm.max().sum()),
                          abnormal_records=int(pa.record_id.nunique()), abnormal_misses=int((pa.alarm == 0).sum()),
                          abnormal_alarm_same=bool((pa.alarm.to_numpy() == base_a.alarm.to_numpy()).all()),
                          warning=timing_warning(pn) or timing_warning(pa) or "")
res["R2_05_jitter_predict"] = jit
log("흔들림: " + " · ".join(f"{k} 기록 {v['normal_records']}/{v['abnormal_records']} 미탐 {v['abnormal_misses']} 경고 {'있음' if v['warning'] else '없음'}"
                           for k, v in jit.items()))

# 재보정(정상 0~479, 흔들림 0·2·50 ms)
rc = {}
for ms in (0, 2, 50):
    f = n479 if ms == 0 else jitter(n479, ms)
    csv = TMP / f"normal479_{ms}ms.csv"
    D.inputs_only(f).to_csv(csv, index=False)
    t = time.time()
    r = subprocess.run([PY, str(GUARD / "recalibrate.py"), "--normal", str(csv), "--out", str(TMP / f"site_{ms}.json"),
                        "--report", str(TMP / f"site_{ms}_report.json")], cwd=YEJUN, env=ENV, capture_output=True, text=True)
    rep = json.loads((TMP / f"site_{ms}_report.json").read_text(encoding="utf-8")) if (TMP / f"site_{ms}_report.json").exists() else {}
    rc[f"{ms}ms"] = dict(returncode=r.returncode, seconds=round(time.time() - t, 1), saved=(TMP / f"site_{ms}.json").exists(),
                         stderr=r.stderr.strip()[-400:], stdout=r.stdout.strip()[-400:], units=rep.get("units"), passed=rep.get("passed"),
                         checks=[(c.get("name"), c.get("value"), c.get("ok")) for c in rep.get("checks", [])],
                         timing_warning_shown="수집 시각 간격" in (r.stdout + r.stderr))
res["R2_05_recalibrate_jitter"] = rc
log("재보정 흔들림: " + " · ".join(f"{k} rc {v['returncode']} 저장 {v['saved']} 단위 {v['units']}" for k, v in rc.items()))
if rc["0ms"]["checks"] and rc["2ms"]["checks"]:
    res["R2_05_recalibrate_jitter"]["checks_2ms_eq_0ms"] = rc["0ms"]["checks"] == rc["2ms"]["checks"]

# 명령별 경고(±50 ms): predict·simulate·monitor
j50 = TMP / "abnormal_50ms.csv"; jitter(abnormal, 50).to_csv(j50, index=False)
jB50 = TMP / "shift_B_50ms.csv"; jitter(tB, 50).to_csv(jB50, index=False)
cmds = {"predict": [PY, str(GUARD / "predict.py"), "--input", str(j50), "--out", str(TMP / "pred50.csv"), "--model", str(ART / "guard_B.json")],
        "simulate": [PY, str(GUARD / "simulate.py"), "--csv", str(j50), "--split", "B", "--speed", "0", "--log", str(TMP / "sim50.csv")],
        "monitor": [PY, str(GUARD / "monitor.py"), "--csv", str(jB50), "--split", "B", "--out", str(TMP / "win50.csv")]}
warn = {}
for k, c in cmds.items():
    r = subprocess.run(c, cwd=YEJUN, env=ENV, capture_output=True, text=True)
    txt = r.stdout + r.stderr
    warn[k] = dict(returncode=r.returncode, warned="수집 시각 간격" in txt, tail=txt.strip()[-300:])
res["R2_05_command_warnings_50ms"] = warn
log("±50 ms 경고: " + " · ".join(f"{k} rc {v['returncode']} 경고 {v['warned']}" for k, v in warn.items()))

# ============================================================ 6. 정적 대조(R2-02 문구, R2-06, R2-08, R2-09)
readme = (GUARD / "README.md").read_text(encoding="utf-8").splitlines()
ops = (GUARD / "OPERATIONS.md").read_text(encoding="utf-8").splitlines()
idx = (GUARD / "web" / "index.html").read_text(encoding="utf-8")
app = (GUARD / "web" / "app.js").read_text(encoding="utf-8")
qi = pd.read_csv(OUTP / "queue_injection_ranks_v2.csv")
pos = qi[qi.key.eq("level_evidence_share_peak") & qi.injected_below_best_false_alarm.gt(0)]
cited = [int(x) for x in re.search(r"queue_injection_ranks_v2\.csv\)?:([\d,]+)", "\n".join(readme)).group(1).split(",")]
res["static"] = dict(
    ops_level2_row=next(l for l in ops if l.startswith("| 2단계(점검 요청)")),
    ops_budget_row=next(l for l in ops if l.startswith("| 목표 k건")),
    readme_level2_line=next(l for l in readme if l.startswith("- **2단계:**")),
    index_method_note_level2=re.search(r"2단계\(점검 요청\)는[^.]*\.", idx).group(0) if re.search(r"2단계\(점검 요청\)는[^.]*\.", idx) else None,
    index_mentions_nonposthoc=("3.3" in idx) or ("비사후" in idx), app_highlight_rule="startsWith('비사후')" in app,
    queue_rows_positive=[int(i) + 2 for i in pos.index], readme_cited_rows=cited, queue_rows_match=[int(i) + 2 for i in pos.index] == cited,
    queue_rows=pos[["split", "alpha", "family", "level_value", "injected_cases", "false_alarm_cases", "injected_below_best_false_alarm"]].to_dict("records"),
    probability_cap_text="≥" in app and "(상한)" in app)
log(f"README 대기열 인용 {cited} = CSV 양수 행 {res['static']['queue_rows_positive']} → {res['static']['queue_rows_match']}")

# 구간 단위 지표 불변(R2-03 완료 기준): 2회차 기준 커밋의 metrics.csv와 현재·재학습 결과
prev_metrics = git("show", "f5679ca:yejun/press_guard/outputs/metrics.csv")
cur_metrics = (OUTP / "metrics.csv").read_text(encoding="utf-8").strip()
mt = pd.read_csv(OUTP / "metrics.csv")
res["R2_03_segment_metrics_unchanged"] = dict(
    metrics_csv_eq_round2_commit=prev_metrics.strip() == cur_metrics,
    retrained_metrics_eq_committed=((TMP / "out" / "metrics.csv").read_text(encoding="utf-8").strip() == cur_metrics) if (TMP / "out" / "metrics.csv").exists() else None,
    main=mt[mt.columns.intersection(["split_id", "model", "alpha", "f1_all_rows", "fn", "fp", "normal_notified_segments", "abnormal_notified_segments"])]
    .query("alpha == 0.01").to_dict("records") if "alpha" in mt else None)
# 감시 표의 1·2단계 알림 수 단위: 대회 이상 21기록(B, α1%)
wa = monitor_windows(pred_cache[("B", .01, "abnormal")], abnormal, .01, ncal, refB, 60)
res["monitor_alert_count_unit"] = dict(level1_notifications=int(wa.level1_notifications.sum()), level2_escalations=int(wa.level2_escalations.sum()),
                                       incident_alerts=int(pred_cache[("B", .01, "abnormal")].incident_notification.sum()
                                                           + pred_cache[("B", .01, "abnormal")].incident_escalation.sum()),
                                       note="monitor_windows의 level1_notifications·level2_escalations는 건(기록구간) 단위 열(notification·escalation)을 센다")
# 커밋된 사건 대기열의 격상 행
res["incidents_csv_escalation_row"] = {s: pd.read_csv(OUTP / f"incidents_{s}.csv").escalation_row.isna().all() for s in ("A", "B")}
log(f"구간 지표 불변 {res['R2_03_segment_metrics_unchanged']['metrics_csv_eq_round2_commit']} · 감시 알림 수 {res['monitor_alert_count_unit']} · "
    f"incidents_*.csv 격상 행 모두 비어 있음 {res['incidents_csv_escalation_row']}")

res["provenance"]["status_after"] = git("status", "--porcelain", "--", "yejun")
res["provenance"]["cache_dirs_after"] = pycache_dirs()
res["elapsed_s"] = round(time.time() - T0, 1)
OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=jsonable), encoding="utf-8")
log(f"끝 · {res['elapsed_s']}초 · {OUT.name}")
