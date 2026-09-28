"""검토 6(문서 수치 대조): 커밋 0b34a6b의 문서 수치를 커밋된 결과 파일(또는 그 파일로부터의 재계산)과 한 줄씩 대조한다.

실행(시스템 임시 폴더의 사본에서만):
    git -C <저장소> archive 0b34a6b yejun | tar -x -C <사본>
    원본 CSV 두 개를 <사본>/yejun/press_submission/data/3_소성가공_예지보전/ 에 복사
    # 행 단위 예측은 커밋되지 않으므로 동결 모델 사본(outputs/expected/guard_*.json·probability_*.json)을 artifacts/에 두고
    # predict.py --split A/B 로 다시 만든다. SHA-256이 outputs/expected/predictions_digest.json·manifest.json과 같아야 한다.
    # v1 행 예측은 press_submission/run_all.py --steps 2 로 다시 만들고 v1 manifest의 SHA-256과 대조한다.
    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review6_check.py <사본>/yejun <예측 폴더>

반올림: 문서 표기 자릿수로 사사오입(ROUND_HALF_UP)한 값이 문서 값과 같으면 일치로 본다. 은행가 반올림으로만 같으면 '반올림 차이'로 적는다.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(sys.argv[1]).resolve()
PRED = Path(sys.argv[2]).resolve()
G = ROOT / "press_guard" / "outputs"
EV = ROOT / "analysis" / "press_evidence"
SEL = ROOT / "analysis" / "press_selection"
SUP = ROOT / "analysis" / "press_supplement"
V1 = ROOT / "press_submission" / "outputs"
RAW = ROOT / "press_submission" / "data" / "3_소성가공_예지보전"

rows = []


def rnd(x, nd, mode=ROUND_HALF_UP):
    return Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-nd), rounding=mode)


def decimals(s):
    s = s.replace(",", "")
    return len(s.split(".")[1]) if "." in s else 0


def match_num(doc, value, pct=False):
    """doc: 문서 표기 문자열(예 '0.910082', '95.5%', '1,412', '2.9e-11'). value: 계산값(비율이면 pct=True로 100배)."""
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "계산 불가"
    v = float(value) * (100 if pct else 1)
    d = doc.strip().rstrip("%").replace("−", "-").replace("+", "")
    if "e" in d.lower():
        mant, exp = d.lower().split("e")
        nd = decimals(mant)
        got = f"{v:.{nd}e}".lower()
        gm, ge = got.split("e")
        return "일치" if (float(gm) == float(mant) and int(ge) == int(exp)) else f"불일치(계산 {got})"
    nd = decimals(d)
    up, even = rnd(v, nd), rnd(v, nd, ROUND_HALF_EVEN)
    target = Decimal(d.replace(",", ""))
    if up == target:
        return "일치"
    if even == target:
        return "반올림 차이(은행가 반올림으로만 같음)"
    return f"불일치(계산 {up})"


def add(cid, where, claim, doc, value, pct=False, note=""):
    norm = lambda x: x.replace("−", "-")
    status = match_num(doc, value, pct) if not isinstance(value, str) else ("일치" if norm(value) == norm(doc) else f"불일치(계산 {value})")
    shown = value if isinstance(value, str) else (f"{float(value) * (100 if pct else 1):.6g}" + ("%" if pct else ""))
    rows.append(dict(id=cid, where=where, claim=claim, doc=doc, computed=shown, status=status, note=note))


def add_bool(cid, where, claim, ok, computed, note=""):
    rows.append(dict(id=cid, where=where, claim=claim, doc="(주장)", computed=computed, status="일치" if ok else "불일치", note=note))


def csv(p):
    return pd.read_csv(p)


def one(df, **kw):
    m = np.ones(len(df), bool)
    for k, v in kw.items():
        m &= (df[k] == v).to_numpy()
    r = df[m]
    assert len(r) == 1, (kw, len(r))
    return r.iloc[0]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ---------------------------------------------------------------- 0. 재생성 예측의 동일성
digest = json.loads((G / "expected" / "predictions_digest.json").read_text(encoding="utf-8"))
for s in "AB":
    f = PRED / f"test_predictions_{s}.csv"
    add_bool(f"P0-{s}", "expected/predictions_digest.json", f"재생성 test_predictions_{s}.csv SHA-256 = 동결 digest",
             sha(f) == digest[f"test_predictions_{s}.csv"]["sha256"], sha(f)[:16])
v1m = json.loads((V1 / "expected" / "manifest.json").read_text(encoding="utf-8"))
v1out = v1m.get("outputs", v1m)
for s in "AB":
    f = V1 / f"predictions_{s}.csv"
    add_bool(f"P0-v1{s}", "press_submission/outputs/expected/manifest.json", f"재생성 v1 predictions_{s}.csv SHA-256 = v1 동결 manifest",
             sha(f) == v1out[f"predictions_{s}.csv"], sha(f)[:16])

tp = {s: csv(PRED / f"test_predictions_{s}.csv") for s in "AB"}
v1p = {s: csv(V1 / f"predictions_{s}.csv") for s in "AB"}
metrics = csv(G / "metrics.csv")
rolling = csv(G / "rolling.csv")
unit = csv(G / "unit_results_v2.csv")
RM = "press_guard/README.md"
OP = "press_guard/OPERATIONS.md"
EVR = "analysis/press_evidence/README.md"
SELR = "analysis/press_selection/README.md"
CYR = "analysis/press_rubric_review/cycle2/README.md"

# ---------------------------------------------------------------- 1. README 결과 표(:50-53)
for s, model, key, doc in (("A", "baseline_v1", "v1", ("0.910082", 99, "0/120", "0.7")), ("A", "guard_v2", "v2", ("0.961938", 44, "0/120", "0.5")),
                           ("B", "baseline_v1", "v1", ("0.920322", 86, "3/180", "0.7")), ("B", "guard_v2", "v2", ("0.970990", 31, "3/180", "0.5"))):
    r = one(metrics, split=s, model=model, alpha=0.01)
    line = {("A", "v1"): 50, ("A", "v2"): 51, ("B", "v1"): 52, ("B", "v2"): 53}[(s, key)]
    add(f"R-{s}{key}-f1", f"{RM}:{line}", f"{s} {key} 행 F1", doc[0], r.f1)
    add(f"R-{s}{key}-fn", f"{RM}:{line}", f"{s} {key} 미탐 행", str(doc[1]), r.fn)
    add(f"R-{s}{key}-nn", f"{RM}:{line}", f"{s} {key} 정상 알림", doc[2], f"{int(r.normal_notified_segments)}/{int(r.normal_segments)}")
    add(f"R-{s}{key}-ab", f"{RM}:{line}", f"{s} {key} 이상 탐지", "21/21", f"{int(r.abnormal_notified_segments)}/{int(r.abnormal_segments)}")
    add(f"R-{s}{key}-dl", f"{RM}:{line}", f"{s} {key} 최대 첫 경보 지연(초)", doc[3], r.delay_max_s)

# 파일만으로 F1(:77)
for s, doc in (("A", "0.961938"), ("B", "0.970990")):
    t = tp[s]
    y, a = t.label.to_numpy(int), t.alarm.to_numpy(int)
    tp_, fp_, fn_ = int(((y == 1) & (a == 1)).sum()), int(((y == 0) & (a == 1)).sum()), int(((y == 1) & (a == 0)).sum())
    add(f"R-file-f1-{s}", f"{RM}:77", f"test_predictions_{s} label·alarm로 F1", doc, 2 * tp_ / (2 * tp_ + fp_ + fn_))
add("R-file-rows-A", f"{RM}:77", "test_predictions_A 행 수", "4,690", len(tp["A"]))
add("R-file-rows-B", f"{RM}:77", "test_predictions_B 행 수", "6,697", len(tp["B"]))
add_bool("R-file-same-abn", f"{RM}:77", "이상 600행은 두 파일이 같다(입력 행·라벨)",
         tp["A"][tp["A"].label == 1][["timestamp", "record_id", "position"]].reset_index(drop=True).equals(
             tp["B"][tp["B"].label == 1][["timestamp", "record_id", "position"]].reset_index(drop=True)), "입력 행 동일(점수는 모델별)")
add("R-fileprior-A", f"{RM}:90", "A 파일 이상 비율", "0.128", tp["A"].file_prior.iloc[0])
add("R-fileprior-B", f"{RM}:90", "B 파일 이상 비율", "0.090", tp["B"].file_prior.iloc[0])
undoc = sorted(set(tp["A"].columns) - {"subset", "label", "row_id", "record_id", "position", "timestamp", "status", "score", "p_value", "alarm",
                                       "notification", "alert_level", "escalation", "incident_id", "incident_notification", "incident_escalation",
                                       "incident_update", "reason", "action", "magnitude", "current_residual", "g_magnitude", "g_waveform",
                                       "g_dynamics", "magnitude_sensor", "waveform_window", "likelihood_ratio", "anomaly_probability",
                                       "record_likelihood_ratio", "record_probability", "probability_prior", "probability_source",
                                       "record_current_rms", "operating_state", "file_prior", "anomaly_probability_file_prior",
                                       "anomaly_score", "criterion", "model_id", "protocol_version", "alert_unit", "beyond_calibration_length", "is_scored"})
add_bool("R-cols", f"{RM}:79-91", "열 표가 예측 파일의 모든 열을 설명", not undoc, "설명 없는 열: " + ",".join(undoc))

# ---------------------------------------------------------------- 2. 단위별 결과(:56-58)
u1 = unit[unit.alpha == 0.01]
for s in "AB":
    v2 = one(u1, split=s, model="v2(최종)"); v1 = one(u1, split=s, model="v1(기준)")
    add_bool(f"U-{s}-rec", f"{RM}:56", f"{s} α1% 기록 단위 v1=v2(이상 21/21, 정상 알림 기록 수)",
             (v2.abnormal_records_detected, v2.normal_records_alerted) == (v1.abnormal_records_detected, v1.normal_records_alerted),
             f"v2 {v2.abnormal_records_detected}/{v2.normal_records_alerted}, v1 {v1.abnormal_records_detected}/{v1.normal_records_alerted}")
    add(f"U-{s}-auc", f"{RM}:56", f"{s} 기록 최대 점수 AUROC", "1.0", v2.record_auroc)
add("U-A-amin", f"{RM}:56", "A 이상 기록 최소(기록 최대 점수)", "12.3", one(u1, split="A", model="v2(최종)").record_abnormal_min)
add("U-B-amin", f"{RM}:56", "B 이상 기록 최소", "12.8", one(u1, split="B", model="v2(최종)").record_abnormal_min)
add("U-A-nmax", f"{RM}:56", "A 정상 기록 최대", "3.8", one(u1, split="A", model="v2(최종)").record_normal_max)
add("U-B-nmax", f"{RM}:56", "B 정상 기록 최대", "4.6", one(u1, split="B", model="v2(최종)").record_normal_max)
# v1의 기록 최대 점수를 v1 예측 파일에서 직접
for s in "AB":
    p = v1p[s]
    rn = p[p.source == "normal_test"].groupby("record_id").combined_score.max(); ra = p[p.source == "abnormal"].groupby("record_id").combined_score.max()
    u = one(u1, split=s, model="v1(기준)")
    add_bool(f"U-{s}-v1rec", f"{RM}:56", f"{s} unit_results v1 기록 최대·최소 = v1 예측 파일", abs(rn.max() - u.record_normal_max) < 1e-9 and abs(ra.min() - u.record_abnormal_min) < 1e-9,
             f"v1 파일 정상 최대 {rn.max():.4f}, 이상 최소 {ra.min():.4f}")
# B v1 오경보 기록 번호(평가 상대 번호 → 절대 = 420 + 상대)
for s, base in (("B", 420),):
    p = v1p[s]; n = p[p.source == "normal_test"]
    rec_v1 = sorted(int(r) + base for r in n[n.alarm == 1].record_id.unique())
    t = tp[s]; n2 = t[(t.label == 0) & (t.alarm == 1)]
    rec_v2 = sorted(int(r) + base for r in n2.record_id.unique())
    add_bool("U-B-same", f"{RM}:56", "B α1% v1·v2 오경보 기록이 같은 423·461·570", rec_v1 == rec_v2 == [423, 461, 570], f"v1 {rec_v1}, v2 {rec_v2}")
diff = []
for s in "AB":
    for al in (0.03, 0.05):
        ua = unit[unit.alpha == al]
        diff.append(abs(int(one(ua, split=s, model="v2(최종)").normal_records_alerted) - int(one(ua, split=s, model="v1(기준)").normal_records_alerted)))
add("U-diff-35", f"{RM}:56", "α 3·5%에서 v1·v2 정상 알림 기록 수 차이(문서 '1~2개')", "1~2", f"{min(diff)}~{max(diff)}",
    note=f"A3%·A5%·B3%·B5% 차이 {diff}")
sr = {s: one(u1, split=s, model="단순 규칙(학습 없음, 사후)") for s in "AB"}
add("U-rule-A-f1", f"{RM}:57", "단순 규칙 A 행 F1", "0.890", sr["A"].f1_rows)
add("U-rule-B-f1", f"{RM}:57", "단순 규칙 B 행 F1", "0.900", sr["B"].f1_rows)
add("U-rule-nn", f"{RM}:57", "단순 규칙 정상 알림 A·B", "0/120·2/180", f"{sr['A'].normal_records_alerted}/120·{sr['B'].normal_records_alerted}/180")
add("U-rule-ab", f"{RM}:57", "단순 규칙 이상 기록", "21/21·21/21", f"{sr['A'].abnormal_records_detected}/21·{sr['B'].abnormal_records_detected}/21")
for s, d26, d7, d01 in (("A", 49, 6, 26), ("B", 51, 4, 20)):
    v2 = one(u1, split=s, model="v2(최종)"); v1 = one(u1, split=s, model="v1(기준)")
    add(f"U-{s}-55", f"{RM}:58", f"{s} v1 대비 미탐 감소", "55", v1.fn - v2.fn)
    add(f"U-{s}-26", f"{RM}:58", f"{s} 감소분 중 위치 2~6", str(d26), v1["missed_pos_2-6"] - v2["missed_pos_2-6"])
    add(f"U-{s}-7", f"{RM}:58", f"{s} 감소분 중 위치 7 이후", str(d7), v1["missed_pos_>=7"] - v2["missed_pos_>=7"])
    add_bool(f"U-{s}-01", f"{RM}:58", f"{s} 위치 0~1 미탐 {d01}행 v1=v2", v1["missed_pos_0-1"] == v2["missed_pos_0-1"] == d01, f"v1 {v1['missed_pos_0-1']}, v2 {v2['missed_pos_0-1']}")
for s in "AB":   # 한계 :247 단순 규칙과 v2의 차이는 위치 7 이후
    v2 = one(u1, split=s, model="v2(최종)"); ru = sr[s]
    add_bool(f"U-{s}-rule7", f"{RM}:247", f"{s} 단순 규칙−v2 미탐 차이가 주로 위치 7 이후",
             (ru["missed_pos_>=7"] - v2["missed_pos_>=7"]) > 0.9 * (ru.fn - v2.fn),
             f"전체 {ru.fn - v2.fn}, 0~1 {ru['missed_pos_0-1'] - v2['missed_pos_0-1']}, 2~6 {ru['missed_pos_2-6'] - v2['missed_pos_2-6']}, ≥7 {ru['missed_pos_>=7'] - v2['missed_pos_>=7']}")

# ---------------------------------------------------------------- 3. E1·하한(:59-60)
floor = csv(SUP / "e1_detection_floor.csv")
for fam, v2d, v1d in (("cur_noise", "0.1", "0.2"), ("cur_offset", "0.4", "0.8"), ("vib_noise", "4.0", "4.0")):
    add(f"E1-{fam}-v2", f"{RM}:59", f"E1 하한 {fam} v2", v2d, one(floor, family=fam, model="guard_v2").floor)
    add(f"E1-{fam}-v1", f"{RM}:59", f"E1 하한 {fam} v1", v1d, one(floor, family=fam, model="baseline_v1").floor)
e1 = csv(SUP / "e1_summary.csv")
grid_ok = True
for fam, fl in (("cur_noise", 0.1), ("cur_offset", 0.4), ("vib_noise", 4.0)):
    lv = sorted(e1[(e1.family == fam) & (e1.t0 == 10) & (e1["shape"] == "step")].level.unique())
    i = lv.index(fl); grid_ok &= abs(lv[i] / lv[i - 1] - 2) < 1e-9
add_bool("E1-grid", f"{RM}:59", "하한값 바로 아래 격자가 1/2(2배 간격)", grid_ok, "cur_noise 격자 " + str(sorted(e1[e1.family == "cur_noise"].level.unique())))
add("L-cp21", f"{RM}:60", "21/21 단측 95% 하한(Clopper–Pearson)", "0.867", 0.05 ** (1 / 21))
gaps = csv(EV / "gaps.csv")
add("L-gapmin", f"{RM}:60", "이상 기록 사이 공백 최소(초)", "1.8", one(gaps, file="abnormal").gap_min_s)
add("L-gapmax", f"{RM}:60", "이상 기록 사이 공백 최대(초)", "8.6", one(gaps, file="abnormal").gap_max_s)

# ---------------------------------------------------------------- 4. 단일 성분·AR 차수(:61-62)·press_selection §1·§5
sfa = csv(SEL / "same_feature_alternatives.csv")
s1 = sfa[sfa.alpha == 0.01]
for cand, rec, f1a, f1b, line in (("크기 단독", "18/21", "0.448", "0.491", 28), ("파형 단독", "18/21", "0.892", "0.891", 29), ("예측 오차(AR(2)) 단독", "20/21", "0.832", "0.840", 30)):
    a, b = one(s1, split_id="A", candidate=cand), one(s1, split_id="B", candidate=cand)
    add(f"S1-{cand}-recA", f"{SELR}:{line}; {RM}:61", f"{cand} 이상 기록 A", rec, f"{a.abnormal_detected}/{a.abnormal_records}")
    add(f"S1-{cand}-recB", f"{SELR}:{line}; {RM}:61", f"{cand} 이상 기록 B", rec, f"{b.abnormal_detected}/{b.abnormal_records}")
    add(f"S1-{cand}-f1A", f"{SELR}:{line}", f"{cand} 행 F1 A", f1a, a.f1_rows)
    add(f"S1-{cand}-f1B", f"{SELR}:{line}", f"{cand} 행 F1 B", f1b, b.f1_rows)
table1 = {"v2 (fmax, AR(2))": ((44, "0/120", "21/21", "0.962", 0), (31, "3/180", "21/21", "0.971", 0), 24),
          "5NN(v2 성분)": ((36, "0/120", "21/21", "0.969", 8), (29, "3/180", "21/21", "0.973", 2), 25),
          "IF(v2 성분)": ((120, "0/120", "20/21", "0.889", 3), (117, "0/180", "20/21", "0.892", 1), 26),
          "합(v2 성분)": ((40, "0/120", "21/21", "0.966", 4), (39, "2/180", "21/21", "0.965", 1), 27),
          "크기 단독": ((427, "0/120", "18/21", "0.448", 0), (404, "3/180", "18/21", "0.491", 0), 28),
          "파형 단독": ((117, "0/120", "18/21", "0.892", 0), (115, "4/180", "18/21", "0.891", 0), 29),
          "예측 오차(AR(2)) 단독": ((173, "0/120", "20/21", "0.832", 0), (165, "1/180", "20/21", "0.840", 0), 30),
          "early+AR(1)": ((78, "0/120", "21/21", "0.930", 0), (63, "3/180", "21/21", "0.942", 0), 31),
          "early+AR(3)": ((50, "0/120", "21/21", "0.957", 0), (40, "3/180", "21/21", "0.963", 0), 32),
          "early+AR(4)": ((57, "0/120", "21/21", "0.950", 0), (46, "4/180", "21/21", "0.957", 0), 33)}
for cand, (da, db, line) in table1.items():
    for s, d in (("A", da), ("B", db)):
        r = one(s1, split_id=s, candidate=cand)
        got = (int(r.fn), f"{int(r.normal_alerted)}/{int(r.normal_records)}", f"{int(r.abnormal_detected)}/{int(r.abnormal_records)}",
               str(rnd(r.f1_rows, 3)), int(r.no_evidence_alarms_abnormal))
        want = (d[0], d[1], d[2], d[3], d[4])
        add_bool(f"S1T-{cand}-{s}", f"{SELR}:{line}", f"§1 표 {cand} {s} 칸(미탐·정상 알림·이상 탐지·F1·근거 없는 경보)", got == want, str(got))
# '기록·행 모두 낫다'(§1 :38)
for s in "AB":
    v2 = one(s1, split_id=s, candidate="v2 (fmax, AR(2))")
    better_rec = all(v2.record_f1 >= one(s1, split_id=s, candidate=c).record_f1 for c in ("크기 단독", "파형 단독", "예측 오차(AR(2)) 단독"))
    better_row = all(v2.f1_rows >= one(s1, split_id=s, candidate=c).f1_rows for c in ("크기 단독", "파형 단독", "예측 오차(AR(2)) 단독"))
    ar = one(s1, split_id=s, candidate="예측 오차(AR(2)) 단독")
    add_bool(f"S1-better-{s}", f"{SELR}:38; same_feature_alternatives.csv remark", f"{s}: v2가 단일 성분보다 기록(기록 F1)·행 모두 낫다", better_rec and better_row,
             f"기록 F1 v2 {v2.record_f1:.3f} vs AR(2) 단독 {ar.record_f1:.3f}; 정상 알림 {v2.normal_alerted} vs {ar.normal_alerted}; 행 F1 {v2.f1_rows:.3f} vs {ar.f1_rows:.3f}")
add("S1-AR4-A", f"{RM}:62", "AR(4) 행 F1 A", "0.950", one(s1, split_id="A", candidate="early+AR(4)").f1_rows)
add("S1-AR4-B", f"{RM}:62", "AR(4) 행 F1 B", "0.957", one(s1, split_id="B", candidate="early+AR(4)").f1_rows)
uc = csv(SEL / "unified_comparison.csv")
print(uc.columns.tolist(), file=sys.stderr)

# ---------------------------------------------------------------- 5. A 문턱·보정 상위(:64)
cal = {s: np.asarray(json.loads((G / "expected" / f"guard_{s}.json").read_text())["state"]["calibration"], float) for s in "AB"}
start = {"A": 360, "B": 300}
order = {s: np.argsort(-cal[s]) for s in "AB"}
top = {s: [int(i) + start[s] for i in order[s][:6]] for s in "AB"}
add("T-A-1", f"{RM}:64", "A α1% 문턱(보정 최댓값)", "4.418", cal["A"][order["A"][0]])
add_bool("T-A-1r", f"{RM}:64", "A 보정 최댓값 기록 = 461, 둘째 = 423", top["A"][:2] == [461, 423], str(top["A"][:4]))
add("T-A-2", f"{RM}:64", "A 보정 둘째 값(423)", "4.049", cal["A"][order["A"][1]])
add("T-A-3", f"{RM}:64", "두 기록을 빼면 A 문턱(셋째 값)", "3.504", cal["A"][order["A"][2]])
ta = tp["A"]; na = ta[ta.label == 0]
rec_max = na.groupby("record_id").score.max()
over = sorted(int(r) + 480 for r in rec_max[rec_max > cal["A"][order["A"][2]]].index)
add_bool("T-A-570", f"{RM}:64", "문턱 3.504에서 A 평가 오경보 기록 = 570뿐", over == [570], str(over))
fpev = csv(G / "fp_events_v2.csv")
b3 = sorted(fpev[(fpev.model == "frozen_B") & (fpev.alpha == 0.03)].record.tolist())
add_bool("T-A-top4", f"{RM}:64", "A 보정 상위 4개 461·423·446·426이 모두 B α3% 오경보 기록", top["A"][:4] == [461, 423, 446, 426] and set(top["A"][:4]) <= set(b3),
         f"A 상위4 {top['A'][:4]}, B α3% 오경보 {b3}")
sc = csv(EV / "split_context.csv")
r = one(sc, split="A", part="test")
add("T-A-12", f"{RM}:64", "A 평가 중 보정 중앙값 초과 구간 수", "12", r.share_gt_cal_median * r.segments)
add("T-A-p", f"{RM}:64", "Mann–Whitney p", "2.9e-11", r.mannwhitney_p_vs_cal)

# ---------------------------------------------------------------- 6. 상태별 분모(:65)·시간순(:66)
nabs = csv(EV / "normal_alarms_by_state.csv")
add("S-A-load", f"{RM}:65", "A 평가 부하 기록 수", "21", one(nabs, group="동결 A", alpha=0.01, state="부하").records)
add("S-B-load", f"{RM}:65", "B 평가 부하 기록 수", "51", one(nabs, group="동결 B", alpha=0.01, state="부하").records)
ssc = csv(EV / "split_state_composition.csv")
for part, doc in (("A 평가", "78"), ("B 평가", "65"), ("A 보정", "35"), ("B 보정", "32")):
    add(f"S-{part}", f"{RM}:65", f"{part} 저수준 비율(%)", doc, one(ssc, part=part).low_share, pct=True)
rv = rolling[(rolling.model == "guard_v2") & (rolling.alpha == 0.01)]
add("RO-f1min", f"{RM}:66", "시간순 5창 F1 최소", "0.961938", rv.f1.min())
add("RO-f1max", f"{RM}:66", "시간순 5창 F1 최대", "0.971819", rv.f1.max())
add("RO-alerts", f"{RM}:66", "시간순 5창 정상 알림", "0·0·2·0·0", "·".join(str(int(x)) for x in rv.normal_notified_segments))

# ---------------------------------------------------------------- 7. 2단계·사건(:70-72, OPERATIONS §2)
al = csv(G / "alert_levels_v2.csv")
lv2 = al[(al.level == 2) & (al.alpha == 0.01)]
add_bool("L2-zero-1", f"{RM}:70", "2단계 정상 평가 0건(α 1%, A·B·시간순 5창)", (lv2.normal_alerted_segments == 0).all(), str(lv2.normal_alerted_segments.tolist()))
lv2all = al[(al.level == 2) & (al.normal_alerted_segments > 0)]
add_bool("L2-zero-all", f"{RM}:70", "2단계 정상 평가 '모두 0건'이 α 3·5%에도 성립", len(lv2all) == 0,
         "; ".join(f"{r.model} α{r.alpha:g} {r.normal_alerted_segments}건" for r in lv2all.itertuples()),
         note="같은 문장의 주 추정 1/7은 α 5% 폴드의 2단계 1건에서 나온다")
r = one(al, model="frozen_A", alpha=0.01, level=2)
add("L2-med", f"{RM}:70", "이상 격상 지연 중앙(초)", "0.2", r.delay_median_s)
add("L2-max", f"{RM}:70", "이상 격상 지연 최대(초)", "0.6", r.delay_max_s)
add("L2-after", f"{OP}:41", "첫 경보 뒤 격상(초) 중앙~최대", "0.1~0.2", f"{r.escalation_after_first_median_s:g}~{r.escalation_after_first_max_s:g}")
ee = csv(G / "expected_effect_v2.csv")
def ee1(sc_):
    return ee[ee.alert_scenario == sc_].iloc[0]
add("EE-main", f"{RM}:70; {OP}:40", "2단계 주추정(교대 8시간)", "4.2", ee1("비중첩 폴드 추정(주추정)").level2_per_8h)
add("EE-main-u", f"{RM}:70; {OP}:40", "주추정 95% 상한", "15.4", ee1("비중첩 폴드 추정 95% 상한").level2_per_8h)
add("EE-ratio", f"{RM}:70", "주추정 비", "1/7", f"{int(ee1('비중첩 폴드 추정(주추정)').ratio_numerator)}/{int(ee1('비중첩 폴드 추정(주추정)').ratio_denominator)}")
add("EE-19", f"{RM}:70; {OP}:40", "1/9 민감도", "3.3", ee1("민감도(겹치는 폴드 포함)").level2_per_8h)
add("EE-19u", f"{RM}:70; {OP}:40", "1/9 민감도 상한", "12.7", ee1("민감도(겹치는 폴드 포함) 95% 상한").level2_per_8h)
add("EE-25", f"{OP}:40", "동결 B α3% 2/5", "11.8", ee1("민감도(동결 B α3%)").level2_per_8h)
add("EE-37", f"{OP}:40", "동결 B α5% 3/7", "12.7", ee1("민감도(동결 B α5%)").level2_per_8h)
add("AL-A-u", f"{OP}:40", "A 정상 0/120의 2단계 95% 상한(교대)", "88", one(al, model="frozen_A", alpha=0.01, level=2).upper95_alerts_per_8h_elapsed)
add("AL-B-u", f"{OP}:40", "B 정상 0/180의 2단계 95% 상한(교대)", "59", one(al, model="frozen_B", alpha=0.01, level=2).upper95_alerts_per_8h_elapsed)
wl = csv(G / "workload_v2.csv")
wB = one(wl, split_id="B", model="guard_v2", alpha=0.01); wA = one(wl, split_id="A", model="guard_v2", alpha=0.01)
add("WL-nom", f"{OP}:39", "1단계 명목(교대)", "30", wB.nominal_alerts_per_8h_elapsed)
add("WL-obs", f"{OP}:39", "B 관측", "60", wB.observed_alerts_per_8h_elapsed)
add("WL-up", f"{OP}:39", "이항 95% 상한", "152", wB.upper95_alerts_per_8h_elapsed)
add("WL-postA", f"{OP}:39", "사후 95% A", "44", wA.posterior95_alerts_per_8h_elapsed)
add("WL-postB", f"{OP}:39", "사후 95% B", "92", wB.posterior95_alerts_per_8h_elapsed)
inc = csv(G / "incident_summary_v2.csv")
ab = one(inc, split="A", alpha=0.01, subset="abnormal")
add("INC-ab", f"{RM}:71", "이상 21기록 사건·알림", "1·2", f"{ab.incidents}·{ab.incident_notifications}")
add("INC-ab42", f"{RM}:71", "구간 단위 알림", "42", ab.case_notifications + ab.case_escalations)
for al_, doc in ((0.01, "3(3)"), (0.03, "5(7)"), (0.05, "7(10)")):
    r = one(inc, split="B", alpha=al_, subset="normal_test")
    add(f"INC-B-{al_}", f"{RM}:71", f"B 정상 α{al_:g} 사건(알림)", doc, f"{r.incidents}({r.incident_notifications})")
raw_ab = pd.read_csv(RAW / "outlier_data.csv")
tt = pd.to_datetime(raw_ab.TimeStamp)
add("INC-span", f"{RM}:71", "이상 21기록 경과(분)", "2.76", (tt.max() - tt.min()).total_seconds() / 60)
add_bool("INC-dow", f"{RM}:73", "07-17 일요일·07-12 화요일", (tt.min().day_name() == "Sunday") and pd.Timestamp("2022-07-12").day_name() == "Tuesday", tt.min().day_name())
for al_, v2d, v1d in ((0.03, 5, 4), (0.05, 7, 6)):
    add(f"ALR-{al_}", f"{RM}:72", f"B α{al_:g} 정상 알림 v2(v1)", f"{v2d}({v1d})",
        f"{int(one(metrics, split='B', model='guard_v2', alpha=al_).normal_notified_segments)}({int(one(metrics, split='B', model='baseline_v1', alpha=al_).normal_notified_segments)})")
rob = csv(G / "robustness_v2.csv")
add("ROB-coarse", f"{RM}:72; {RM}:179", "coarse B α1% v2(v1)", "5(4)",
    f"{int(one(rob, split_id='B', version='v2', input_variant='coarse', criterion='conformal', alpha=0.01).normal_notified_segments)}"
    f"({int(one(rob, split_id='B', version='v1', input_variant='coarse', criterion='conformal', alpha=0.01).normal_notified_segments)})")

# ---------------------------------------------------------------- 8. 확률(:104-138)
pe = csv(G / "probability_eval_v2.csv")
for s, meth, b, ll, ece in (("A", "calibrated_isotonic", "0.0072", "0.046", "0.0075"), ("A", "prevalence_only", "0.112", "0.382", None),
                            ("A", "naive_1_minus_p", "0.012", "0.110", "0.036"), ("B", "calibrated_isotonic", "0.0056", "0.037", "0.0066"),
                            ("B", "prevalence_only", "0.082", "0.302", None), ("B", "naive_1_minus_p", "0.023", "0.120", "0.078")):
    r = one(pe, split=s, cv="21fold", unit="rows", method=meth)
    add(f"PR-{s}-{meth}-b", f"{RM}:106-111", f"{s} {meth} Brier", b, r.brier)
    add(f"PR-{s}-{meth}-l", f"{RM}:106-111", f"{s} {meth} log-loss", ll, r.log_loss)
    if ece:
        add(f"PR-{s}-{meth}-e", f"{RM}:106-111", f"{s} {meth} ECE", ece, r.ece)
for s, meth, ece, b in (("A", "isotonic_uncapped", "0.0012", "0.0069"), ("B", "isotonic_uncapped", "0.0009", "0.0052"),
                        ("A", "platt_logistic", "0.0036", "0.0074"), ("B", "platt_logistic", "0.0022", "0.0055")):
    r = one(pe, split=s, cv="21fold", unit="rows", method=meth)
    add(f"PR-{s}-{meth}-e", f"{RM}:113", f"{s} {meth} ECE", ece, r.ece)
    add(f"PR-{s}-{meth}-b", f"{RM}:113", f"{s} {meth} Brier", b, r.brier)
add("PR-cap", f"{RM}:116", "π 1%·LR 121의 확률", "0.55", 0.01 * 121 / (0.01 * 121 + 0.99))
for s, doc in (("A", "555/600"), ("B", "568/600")):
    t = tp[s]; a = t[t.label == 1]
    add(f"PR-cap-{s}", f"{RM}:117", f"{s} 이상 행 중 LR 상한(121) 행", doc, f"{int((a.likelihood_ratio >= 121 - 1e-9).sum())}/{len(a)}")
fa = tp["B"][(tp["B"].label == 0) & (tp["B"].alarm == 1)]
add_bool("PR-cap-fa", f"{RM}:117; {RM}:125", "B 오경보 3행 모두 LR 121(π1% 0.55)", len(fa) == 3 and (fa.likelihood_ratio >= 121 - 1e-9).all(),
         f"{len(fa)}행 LR {fa.likelihood_ratio.round(3).tolist()}")


def losses(y, p, bins=10):
    y, p = np.asarray(y, float), np.asarray(p, float)
    edges = np.linspace(0, 1, bins + 1); e = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        k = (p >= lo) & ((p < hi) | (hi == 1))
        if k.any():
            e += k.mean() * abs(p[k].mean() - y[k].mean())
    return float(((p - y) ** 2).mean()), e


for s, bdoc, edoc, bfp, efp in (("A", "0.0321", "0.0615", "0.0072", "0.0075"), ("B", "0.0221", "0.0423", "0.0056", "0.0066")):
    t = tp[s]; ok = np.isfinite(t.anomaly_probability)
    b_, e_ = losses(t.label[ok], t.anomaly_probability[ok])
    add(f"PR-file-{s}-b", f"{RM}:118", f"{s} π1% 확률을 파일 라벨로 Brier", bdoc, b_)
    add(f"PR-file-{s}-e", f"{RM}:118", f"{s} π1% 확률을 파일 라벨로 ECE", edoc, e_)
    b2, e2 = losses(t.label[ok], t.anomaly_probability_file_prior[ok])
    add(f"PR-fp-{s}-b", f"{RM}:118", f"{s} 파일 비율 확률 Brier", bfp, b2)
    add(f"PR-fp-{s}-e", f"{RM}:118", f"{s} 파일 비율 확률 ECE", efp, e2)
pb = csv(G / "probability_baselines_v2.csv")
for s, cur, omp, alarm01, two in (("A", "0.0025", "0.0083", "0.0007", "0.0026"), ("B", "0.0026", "0.0217", "0.0010", "0.0026")):
    q = pb[(pb.split == s) & (pb.evaluation_prior == "1%")]
    add(f"PB-{s}-cur", f"{RM}:120", f"{s} 평가 1% 현재 층 Brier", cur, q[q.method.str.startswith("현재")].brier.iloc[0])
    add(f"PB-{s}-1mp", f"{RM}:120", f"{s} 평가 1% 1−p Brier", omp, q[q.method.str.startswith("1−p")].brier.iloc[0])
    add(f"PB-{s}-01", f"{RM}:120", f"{s} 평가 1% 경보 0/1 Brier", alarm01, q[q.method.str.startswith("경보")].brier.iloc[0])
    add(f"PB-{s}-two", f"{RM}:121", f"{s} 평가 1% 두 수준 Brier", two, q[q.method.str.startswith("두 수준")].brier.iloc[0])
    add_bool(f"PB-{s}-min", f"{RM}:120", f"{s} 평가 1%에서 Brier 최소 = 경보 0/1", q.sort_values("brier").method.iloc[0].startswith("경보"), q.sort_values("brier").method.iloc[0])
pc = csv(G / "probability_conversion_v2.csv")
pa, pbb = one(pc, split="A", prior=0.01), one(pc, split="B", prior=0.01)
add("PC-A-thr", f"{RM}:123", "A 문턱 확률(π1%)", "0.30", pa.p_at_threshold)
add("PC-B-thr", f"{RM}:123", "B 문턱 확률(π1%)", "0.007", pbb.p_at_threshold)
add("PC-B-l", f"{RM}:123", "B 계단 왼쪽", "2.896", pbb.iso_step_left)
add("PC-B-thrs", f"{RM}:123", "B 문턱 점수", "3.520", pbb.threshold_score)
add("PC-B-cnt", f"{RM}:123", "계단 안 정상 보정·이상 행", "9·1", f"{pbb.step_normal_cal_rows}·{pbb.step_abnormal_rows}")
add("PC-B-phat", f"{RM}:123", "계단 P̂", "0.10", pbb.step_p_hat)
pfit = json.loads((G / "expected" / "probability_B.json").read_text())["state"]["pi_fit"]
add("PC-B-pifit", f"{RM}:123", "적합 비율", "0.137", pfit)
add("PC-B-lr", f"{RM}:123", "문턱 LR", "0.70", pbb.lr_at_threshold)
add("PC-B-r", f"{RM}:123", "다음 계단 시작", "3.561", pbb.iso_step_right)
add("PC-A-min", f"{RM}:124", "A 경보 행 최소 LR", "108.9", pa.alarm_rows_min_lr)
add("PC-A-minp", f"{RM}:124", "A 최소 LR 확률(π1%)", "0.52", pa.alarm_rows_min_p)
add("PC-B-min", f"{RM}:124", "B 경보 행 최소 LR", "2.42", pbb.alarm_rows_min_lr)
add("PC-B-minp", f"{RM}:124", "B 최소 LR 확률", "0.024", pbb.alarm_rows_min_p)
for s, doc in (("A", "108.9"), ("B", "2.42")):
    t = tp[s]; al_rows = t[t.alarm == 1]
    add(f"PC-{s}-min-pred", f"{RM}:124", f"{s} 예측 파일에서 경보 행 최소 LR", doc, al_rows.likelihood_ratio.min())
    add(f"PC-{s}-lt1", f"{RM}:124", f"{s} 경보 행 중 LR<1", "0", int((al_rows.likelihood_ratio < 1).sum()))
lf = csv(G / "label_free_alert_probability_v2.csv")
q = lf[(lf.split == "A") & (lf.alpha == 0.01) & (lf.tpr_basis == "E1 cur_noise 0.1")]
add("LF-tpr", f"{RM}:134", "E1 전류 잡음 0.1σ 탐지율(%)", "95.5", q.tpr.iloc[0], pct=True)
add("LF-n-01", f"{RM}:134", "명목 FAR·π0.1%", "10.4", one(q, far_basis="nominal", prior=0.001).p_anomaly_given_alert, pct=True)
add("LF-n-1", f"{RM}:134", "명목 FAR·π1%", "53.8", one(q, far_basis="nominal", prior=0.01).p_anomaly_given_alert, pct=True)
add("LF-c-01", f"{RM}:135", "보정 95% FAR·π0.1%", "3.7", one(q, far_basis="calibrated95", prior=0.001).p_anomaly_given_alert, pct=True)
add("LF-c-1", f"{RM}:135", "보정 95% FAR·π1%", "28.1", one(q, far_basis="calibrated95", prior=0.01).p_anomaly_given_alert, pct=True)
r = one(q, far_basis="nominal", prior=0.01)
add_bool("LF-eq", f"{RM}:136", "α1%에서 nominal_lr_reference = min_rank_nominal_lr_reference", abs(r.nominal_lr_reference - r.min_rank_nominal_lr_reference) < 1e-9,
         f"{r.nominal_lr_reference:.4f} vs {r.min_rank_nominal_lr_reference:.4f}")
add("LF-sbb", f"{RM}:138", "SBB 우도비", "9.3", pa.sbb_reference_lr)
add("LF-sbbp", f"{RM}:138", "SBB π1% 확률(%)", "8.6", pa.sbb_reference_p, pct=True)

# ---------------------------------------------------------------- 9. 영향변수(:142-157)
si = csv(G / "sensor_importance_v2.csv")
def sir(method, s, variant, alpha=0.01):
    return one(si, method=method, split=s, variant=variant, alpha=alpha)
add("SI-cur-A", f"{RM}:143", "전류만 F1 A", "0.956", sir("refit_ablation", "A", "current_only").f1)
add("SI-cur-B", f"{RM}:143", "전류만 F1 B", "0.955", sir("refit_ablation", "B", "current_only").f1)
add("SI-cur-d", f"{RM}:143", "전류만 이상 탐지", "20/21·20/21", f"{int(sir('refit_ablation','A','current_only').abnormal_detected_segments)}/21·{int(sir('refit_ablation','B','current_only').abnormal_detected_segments)}/21")
add("SI-vib-A", f"{RM}:143", "진동만 F1 A", "0.448", sir("refit_ablation", "A", "vibration_only").f1)
add("SI-vib-B", f"{RM}:143", "진동만 F1 B", "0.491", sir("refit_ablation", "B", "vibration_only").f1)
add("SI-dAI0", f"{RM}:143", "AI0 제거 미탐 A·B", "49·47", f"{int(sir('refit_ablation','A','drop_AI0').fn)}·{int(sir('refit_ablation','B','drop_AI0').fn)}")
add("SI-dAI1", f"{RM}:143", "AI1 제거 미탐 A·B", "45·34", f"{int(sir('refit_ablation','A','drop_AI1').fn)}·{int(sir('refit_ablation','B','drop_AI1').fn)}")
add("SI-swap", f"{RM}:144", "채널 교체 미탐 AI2·AI0·AI1", "427·404, 61·51, 46·34",
    ", ".join(f"{int(one(si, method='channel_swap', split='A', variant=v).fn)}·{int(one(si, method='channel_swap', split='B', variant=v).fn)}"
              for v in ("swap_AI2_Current", "swap_AI0_Vibration", "swap_AI1_Vibration")))
for s, sensor, doc in (("A", "AI1_Vibration", "0.93"), ("B", "AI1_Vibration", "0.90"), ("A", "AI0_Vibration", "0.86"), ("B", "AI0_Vibration", "0.86"),
                       ("A", "AI2_Current", "0.44"), ("B", "AI2_Current", "0.38")):
    add(f"SI-auc-{s}-{sensor}", f"{RM}:147,150", f"구간 SD 단변량 AUROC {s} {sensor}", doc, one(si, method="univariate_segment_sd", split=s, variant=sensor).auroc)
abl = csv(G / "ablation_v2.csv")
def ab_(s, m):
    return one(abl, split_id=s, model=m, alpha=0.01, criterion="conformal", preprocess="matched")
for m, doc in (("no_waveform", "133·112"), ("no_dynamics", "86·71"), ("no_magnitude", "56·56"), ("no_early_switch", "46·33")):
    add(f"AB-{m}", f"{RM}:145", f"{m} 미탐 A·B", doc, f"{int(ab_('A', m).fn)}·{int(ab_('B', m).fn)}")
add("AB-nomag-det", f"{RM}:145", "크기 제거 이상 탐지 A·B", "20/21·20/21", f"{int(ab_('A','no_magnitude').abnormal_notified_segments)}/21·{int(ab_('B','no_magnitude').abnormal_notified_segments)}/21")
add("AB-nomag-fp", f"{RM}:145", "크기 제거 B 정상 오경보 3→", "1", ab_("B", "no_magnitude").normal_notified_segments)
cf = csv(G / "coupling_fit_v2.csv")
add("CP-rA", f"{RM}:153", "결합 r A", "0.95", one(cf, split="A").r)
add("CP-rB", f"{RM}:153", "결합 r B", "0.95", one(cf, split="B").r)
cr = csv(G / "coupling_records_v2.csv")
for s in "AB":
    add(f"CP-z-{s}", f"{RM}:153", f"이상 결합 잔차 z 중앙 {s}", "12.1", cr[(cr.split == s) & (cr.subset == "abnormal")].resid_z.median())
pvm = csv(G / "position_vibration_misses_v2.csv")
for s in "AB":
    r = one(pvm, split=s, position="0-1", vibration="vibration_normal_range")
    add(f"PV-{s}", f"{RM}:152,168", f"{s} 진동 정상 범위 × 위치 0~1 미탐", "6/6", f"{r.missed_rows}/{r.rows}")
fn = csv(G / "fn_intensity_v2.csv")
vA, vB = one(fn, split="A", family="vib_noise"), one(fn, split="B", family="vib_noise")
for k, d, v in (("dA", "0.407", vA.interaction_rho_difference), ("lA", "0.061", vA.interaction_ci_low), ("hA", "0.725", vA.interaction_ci_high),
                ("dB", "0.799", vB.interaction_rho_difference), ("lB", "0.551", vB.interaction_ci_low), ("hB", "1.023", vB.interaction_ci_high),
                ("q", "0.0146", vA.q_amp_bh), ("bon9", "0.0974", vA.p_amp_bonferroni), ("bon18", "0.1948", vA.p_amp_joint_bonferroni)):
    add(f"FN-{k}", f"{RM}:154", f"fn_intensity {k}", d, v)
add("FN-boot", f"{RM}:154", "재표집 횟수", "4000", vA.interaction_bootstrap_repeats)
add("FN-ntest", f"{RM}:154", "BH 검정 수(진폭·진동 SD까지)", "9·18", f"{int(vA.n_tests_amp)}·{int(vA.n_tests_amp_vib_sd)}")
fpi = csv(G / "fp_intensity_v2.csv")
r = one(fpi, alpha=0.05, condition="operating_state", value="load")
add("FP-load5", f"{RM}:155; {RM}:175", "5적합 합침 α5% 부하", "17/154", f"{r.false_alarms}/{r.denominator}")
add("FP-rest5", f"{RM}:155; {RM}:175", "저수준·짧은 기록", "0/326", f"{r.comparison_false_alarms}/{r.comparison_denominator}")
r = one(fpi, alpha=0.05, condition="amp_high_block_stratified", value="B 정상 학습 q75")
add("FP-or", f"{RM}:155", "MH OR", "9.96", r.mh_pooled_or)
add("FP-cmh", f"{RM}:155; {RM}:175", "CMH p", "2.9e-6", r.cmh_p)
add("FP-perm", f"{RM}:155", "순열 p", "5.0e-5", r.permutation_p_greater)
add("FP-perm-floor", f"{RM}:155", "순열 p 해상도 하한 1/(20000+1)", "5.0e-5", 1 / 20001)
r = one(fpi, alpha=0.05, condition="amp_within_load")
add("FP-within", f"{RM}:155", "부하 안 진폭 ≥ 중앙 / 미만", "12/77·5/77", f"{r.false_alarms}/{r.denominator}·{r.comparison_false_alarms}/{r.comparison_denominator}")
add("FP-thr", f"{RM}:155", "부하 안 진폭 중앙", "203.6", r.threshold)
add("FP-fisher", f"{RM}:155", "Fisher p", "0.060", r.fisher_p_greater)
add("FP-rho", f"{RM}:155", "Spearman ρ", "0.263", r.spearman_amp)
add("FP-rhop", f"{RM}:155", "Spearman p", "0.001", r.spearman_p)
r = one(fpi, alpha=0.01, condition="amp_high", value="전류 진폭 ≥ B 정상 학습 q75 (222.9)")
add("FP-high1", f"{RM}:175", "고부하 α1% (나머지)", "2/46 (1/254)", f"{r.false_alarms}/{r.denominator} ({r.comparison_false_alarms}/{r.comparison_denominator})")
r = one(fpi, alpha=0.05, condition="amp_high", value="전류 진폭 ≥ B 정상 학습 q75 (222.9)")
add("FP-high5", f"{RM}:175", "고부하 α5% (나머지)", "10/46 (4/254)", f"{r.false_alarms}/{r.denominator} ({r.comparison_false_alarms}/{r.comparison_denominator})")
add("FP-high5p", f"{RM}:175", "α5% 단측 p", "1.8e-6", r.fisher_p_greater)
add("FP-block", f"{RM}:175", "480~539 블록", "0/120", f"{one(fpi, alpha=0.01, condition='block', value='480~539').false_alarms}/{one(fpi, alpha=0.01, condition='block', value='480~539').denominator}")
for st, doc in (("load", "3/154"), ("low", "0/225"), ("short", "0/101")):
    r = one(fpi, alpha=0.01, condition="operating_state", value=st)
    add(f"FP-state-{st}", f"{OP}:18", f"5적합 합침 α1% {st}", doc, f"{r.false_alarms}/{r.denominator}")
add("FP-B-load", f"{RM}:156", "B α1% 부하·저수준", "3/51(0/94)",
    f"{one(nabs, group='동결 B', alpha=0.01, state='부하').alerted}/{one(nabs, group='동결 B', alpha=0.01, state='부하').records}"
    f"({one(nabs, group='동결 B', alpha=0.01, state='저수준').alerted}/{one(nabs, group='동결 B', alpha=0.01, state='저수준').records})")
ib = csv(G / "incidents_B.csv")
add("FP-rel", f"{RM}:157", "B 오경보 상대 기록 번호", "3·41·150", "·".join(str(int(x)) for x in ib[ib.source == "normal"].records))

# ---------------------------------------------------------------- 10. 오류 조건 표(:168-179)
es = csv(G / "error_condition_summary_v2.csv")
add("EC-rows", f"{RM}:161,201", "요약 행 수", "12", len(es))
r = es.iloc[2]
add("EC-off08", f"{RM}:170", "기록 시작부터 오프셋 0.8 탐지 A·B(%)", "3.3·28.8",
    f"{rnd(100 * (1 - r.errors_A / r.denominator_A), 1)}·{rnd(100 * (1 - r.errors_B / r.denominator_B), 1)}")
r = es.iloc[3]
add("EC-gain", f"{RM}:171", "×1.15 탐지 A·B(%)", "0·6.3", f"{rnd(100 * (1 - r.errors_A / r.denominator_A), 0)}·{rnd(100 * (1 - r.errors_B / r.denominator_B), 1)}")
fB = one(fn, split="B", family="cur_gain", level_value=1.15)
add("EC-gainQ", f"{RM}:171", "B 진폭 Q1·Q2 / Q4", "0/56, 6/28", f"{int(fB.detected_amp_Q1 + fB.detected_amp_Q2)}/{int(fB.units_amp_Q1 + fB.units_amp_Q2)}, {int(fB.detected_amp_Q4)}/{int(fB.units_amp_Q4)}")
add("EC-v2A", f"{RM}:172", "진동 2σ Q1→Q4 A", "0.711 → 0.806", f"{rnd(vA.detected_amp_Q1 / vA.units_amp_Q1, 3)} → {rnd(vA.detected_amp_Q4 / vA.units_amp_Q4, 3)}")
add("EC-v2B", f"{RM}:172", "진동 2σ Q1→Q4 B", "0.939 → 0.992", f"{rnd(vB.detected_amp_Q1 / vB.units_amp_Q1, 3)} → {rnd(vB.detected_amp_Q4 / vB.units_amp_Q4, 3)}")
add("EC-v2rho", f"{RM}:172", "Spearman A·B", "0.293·0.481", f"{rnd(vA.spearman_amp, 3)}·{rnd(vB.spearman_amp, 3)}")
add("EC-v2all", f"{RM}:172", "전체 A·B(%)", "72.3·95.0", f"{rnd(100 * vA.detect_mean, 1)}·{rnd(100 * vB.detect_mean, 1)}")
e1v = e1[(e1.family == "vib_noise") & (e1.level == 2.0) & (e1.t0 == 10) & (e1["shape"] == "step") & (e1.model == "guard_v2") & (e1.alpha == 0.01)]
add("EC-e1", f"{RM}:172", "E1 진동 2σ A·B(%)", "74.4·93.9", f"{rnd(100 * one(e1v, split='A').detect_rate_2s, 1)}·{rnd(100 * one(e1v, split='B').detect_rate_2s, 1)}")
oA, oB = one(fn, split="A", family="cur_offset"), one(fn, split="B", family="cur_offset")
add("EC-offQ4", f"{RM}:173", "오프셋 0.2 Q4 미탐 A·B", "13/19·20/28", f"{int(oA.units_amp_Q4 - oA.detected_amp_Q4)}/{int(oA.units_amp_Q4)}·{int(oB.units_amp_Q4 - oB.detected_amp_Q4)}/{int(oB.units_amp_Q4)}")
add("EC-offB", f"{RM}:173", "B 탐지 Q1→Q4(ρ)", "20/28 → 8/28(−0.32)", f"{int(oB.detected_amp_Q1)}/{int(oB.units_amp_Q1)} → {int(oB.detected_amp_Q4)}/{int(oB.units_amp_Q4)}({rnd(oB.spearman_amp, 2)})")
fmi = csv(SEL / "fp_mitigation_injection_v2.csv")
print(fmi.columns.tolist(), file=sys.stderr)
es8 = es.iloc[8]
add("EC-ai0", f"{RM}:176", "AI0 단발 α5% 사건 / 경보 1행", "15/17·13/17", f"{int(es8.errors_A)}/{es8.denominator_A}·{int(es8.errors_B)}/{es8.denominator_B}")
nmc = csv(G / "near_miss_corr_v2.csv")
add("EC-near", f"{RM}:177", "B 문턱 0.9배 이상", "7/180", f"{one(nmc, split='B', condition='vib_maxz').records_ge_0_9}/180")
add("EC-nearrho", f"{RM}:177", "Spearman 진동 max|z|·전류 진폭·시간", "0.61·0.50·-0.31",
    "·".join(str(rnd(one(nmc, split="B", condition=c).spearman, 2)) for c in ("vib_maxz", "current_amp", "time_order")))
es10 = es.iloc[10]
add("EC-gain15", f"{RM}:178", "×1.5 A·B", "0/120·17/180", f"{int(es10.errors_A)}/{es10.denominator_A}·{int(es10.errors_B)}/{es10.denominator_B}")
mg = csv(G / "monitor_gain_v2.csv")
first_act = mg[(mg.split == "B") & (mg.alpha == 0.01) & mg.recalibration_review].gain.min()
add("EC-mon13", f"{RM}:178", "감시 규칙 조치 시작 배율(B α1%)", "1.3", first_act)
add("EC-coarse", f"{RM}:179", "coarse A·B (matched)", "0/120·5/180 (0·3)",
    f"{int(one(rob, split_id='A', version='v2', input_variant='coarse', criterion='conformal', alpha=0.01).normal_notified_segments)}/120·"
    f"{int(one(rob, split_id='B', version='v2', input_variant='coarse', criterion='conformal', alpha=0.01).normal_notified_segments)}/180 "
    f"({int(one(rob, split_id='A', version='v2', input_variant='matched', criterion='conformal', alpha=0.01).normal_notified_segments)}·"
    f"{int(one(rob, split_id='B', version='v2', input_variant='matched', criterion='conformal', alpha=0.01).normal_notified_segments)})")

# ---------------------------------------------------------------- 11. 대기열(:193)
qi = csv(G / "queue_injection_ranks_v2.csv")
qk = qi[qi.key == "level_evidence_share_peak"]
pos = qk[qk.injected_below_best_false_alarm > 0]
lines = [int(i) + 2 for i in pos.index]
add("Q-lines", f"{RM}:193", "뒤처지는 조건의 파일 행", "35,55,63,71,83,91,95,111,115", ",".join(map(str, lines)))
listed = {("B", 0.01, "cur_noise"), ("B", 0.01, "cur_offset"), ("A", 0.03, "vib_noise"), ("A", 0.05, "vib_noise"), ("B", 0.03, "vib_noise"),
          ("B", 0.05, "vib_noise"), ("B", 0.05, "cur_offset")}
missing = [f"{r.split} α{r.alpha:g} {r.family} {r.level_value:g} {r.injected_below_best_false_alarm}건" for r in pos.itertuples() if (r.split, r.alpha, r.family) not in listed]
add_bool("Q-enum", f"{RM}:193", "본문 열거가 9개 조건을 모두 담는다", not missing, "본문에 없는 조건: " + "; ".join(missing))
mx = pos.sort_values("injected_below_best_false_alarm").iloc[-1]
add("Q-max", f"{RM}:193", "가장 큰 경우 B α5% 오프셋", "12/111", f"{mx.injected_below_best_false_alarm}/{mx.injected_cases}")
add("Q-inc", f"{RM}:193", "사건 단위 뒤처짐 조건·사건", "2·2", f"{int((qk.injected_incidents_below_best_false_alarm > 0).sum())}·{int(qk.injected_incidents_below_best_false_alarm.sum())}")
qks = csv(G / "queue_key_selection_v2.csv")
add("Q-keys", f"{RM}:193", "정렬 키 후보 수", "4", len(qks))

# ---------------------------------------------------------------- 12. 산출물·검증(:199-236)
mc = csv(G / "model_comparison_v2.csv")
add("OUT-14", f"{RM}:200", "모델 비교 모델 수", "14", mc.model.nunique())
add("OUT-44", f"{RM}:209", "expected 결과 CSV 수", "44", len(list((G / "expected").glob("*.csv"))))
audit = json.loads((G / "audit.json").read_text())
add("OUT-audit", f"{RM}:218", "audit 검증 수", "16", len(audit["checks"]))

# ---------------------------------------------------------------- 13. 한계(:240-246)
cd = csv(EV / "class_differences.csv").set_index("feature")
off = cd.loc[[k for k in cd.index if k.startswith("전류 구간 |평균| > 구간 SD")][0]]
add("LIM-off", f"{RM}:241; {OP}:18; {EVR}:62", "|평균| > SD 정상·이상", "0/530·9/17", f"{off.normal}·{off.abnormal}")
co = csv(EV / "current_offset.csv")
def co_(s, v, d):
    return one(co, split=s, variant=v, data=d)
add("LIM-dm", f"{RM}:241; {EVR}:72", "평균 제거 경보 행 A·B", "556→555·569→567",
    f"{co_('A','원자료','abnormal').alarm_rows}→{co_('A','전류 기록 평균 제거','abnormal').alarm_rows}·{co_('B','원자료','abnormal').alarm_rows}→{co_('B','전류 기록 평균 제거','abnormal').alarm_rows}")
add("LIM-272", f"{RM}:241; {EVR}:75; {CYR}:232", "+272 경보 기록 A·B", "114/120·179/180",
    f"{co_('A','전류 +272.4(이상 기록 |평균| 최댓값)','normal_test').records_alarmed}/120·{co_('B','전류 +272.4(이상 기록 |평균| 최댓값)','normal_test').records_alarmed}/180")
add("LIM-81", f"{EVR}:75; {CYR}:232", "+81.4 경보 기록 A·B", "0/120·8/180",
    f"{co_('A','전류 +81.4(이상 기록 |평균| 중앙값)','normal_test').records_alarmed}/120·{co_('B','전류 +81.4(이상 기록 |평균| 중앙값)','normal_test').records_alarmed}/180")
add("LIM-dmB", f"{EVR}:76", "평균 제거 B 정상 경보 구간", "3 → 4", f"{co_('B','원자료','normal_test').records_alarmed} → {co_('B','전류 기록 평균 제거','normal_test').records_alarmed}")
add_bool("LIM-dyn", f"{EVR}:75", "+272 경보 거의 모두 예측 오차", co_("A", "전류 +272.4(이상 기록 |평균| 최댓값)", "normal_test").dynamics_rows / 596 > 0.9
         and co_("B", "전류 +272.4(이상 기록 |평균| 최댓값)", "normal_test").dynamics_rows / 2675 > 0.9,
         f"A {co_('A','전류 +272.4(이상 기록 |평균| 최댓값)','normal_test').dynamics_rows}/596, B {co_('B','전류 +272.4(이상 기록 |평균| 최댓값)','normal_test').dynamics_rows}/2675")
add_bool("LIM-magcur", f"{EVR}:72", "이상 파일 크기 경보 중 전류 최댓값 0행", co_("A", "원자료", "abnormal").magnitude_current_rows == 0 and co_("B", "원자료", "abnormal").magnitude_current_rows == 0, "A·B 0")
js = csv(EV / "sampling_jitter_stress.csv")
def js_(s, f, sig):
    m = (js.split == s) & (js.jitter_rms_ms == sig) & ((js.source_frequency_hz == f) if f is not None else js.source_frequency_hz.isna())
    return js[m].iloc[0]
add("LIM-j01", f"{RM}:241; {OP}:14; {EVR}:286", "0.1 ms 경보 기록 A·B(%)", "8·31", f"{rnd(100 * js_('A', 60.6, 0.1).level1_rate, 0)}·{rnd(100 * js_('B', 60.6, 0.1).level1_rate, 0)}")
add("LIM-j02", f"{OP}:14", "0.2 ms A·B(%)", "71·90", f"{rnd(100 * js_('A', 60.6, 0.2).level1_rate, 0)}·{rnd(100 * js_('B', 60.6, 0.2).level1_rate, 0)}")
m = re.search(r"이상 ([0-9.]+)\(이상은", off.note)
add("LIM-lag2", f"{RM}:241", "이웃 기록 평균 상관(class_differences note)", "0.81", float(m.group(1)) if m else float("nan"))
add("LIM-022", f"{RM}:241; {EVR}:68", "이상 적합 주파수 중앙(Hz)", "0.22", float(cd.loc["전류 사인 적합 주파수 중앙값(Hz)"].abnormal))
alinj = csv(G / "alert_levels_injection_v2.csv")
def ai(s, fam, lvl):
    return one(alinj, split=s, family=fam, level_value=lvl, alpha=0.01)
add("LIM-l2", f"{RM}:243; {OP}:42", "진동 2σ 2단계 A~B(%)", "38~79", f"{rnd(100 * ai('A','vib_noise',2.0).level2_detect_2s, 0)}~{rnd(100 * ai('B','vib_noise',2.0).level2_detect_2s, 0)}")
add("OP-l1c", f"{OP}:42", "전류 잡음 0.1σ 1단계 A·B(%)", "97·97", f"{rnd(100 * ai('A','cur_noise',0.1).level1_detect_2s, 0)}·{rnd(100 * ai('B','cur_noise',0.1).level1_detect_2s, 0)}")
add("OP-l2c", f"{OP}:42", "전류 잡음 0.1σ 2단계 A~B(%)", "90~93", f"{rnd(100 * ai('A','cur_noise',0.1).level2_detect_2s, 0)}~{rnd(100 * ai('B','cur_noise',0.1).level2_detect_2s, 0)}")
add("OP-l1v", f"{OP}:42", "진동 2σ 1단계 A~B(%)", "77~95", f"{rnd(100 * ai('A','vib_noise',2.0).level1_detect_2s, 0)}~{rnd(100 * ai('B','vib_noise',2.0).level1_detect_2s, 0)}")
e2 = csv(SUP / "e2_uci_metrics.csv")
loc = e2[e2["mode"] == "local_normal_reference"].auroc
add("LIM-e2", f"{RM}:246; {EVR}:284", "E2 현지 기준 AUROC 범위", "0.43~0.55", f"{rnd(loc.min(), 2)}~{rnd(loc.max(), 2)}")

# ---------------------------------------------------------------- 14. OPERATIONS 기타
bd = csv(G / "alert_budget_design_v2.csv")
r = one(bd, target_alerts_per_8h=3, collection="간헐 수집(대회 밀도)")
add("OP-k3-a", f"{OP}:43", "3건/교대 α(%)", "0.08", r.alpha_required, pct=True)
add("OP-k3-n", f"{OP}:43", "보정 단위(약)", "1,200", round(r.calibration_units_required, -2))
add("OP-k3-h", f"{OP}:43", "정상 수집 시간", "2.7", r.normal_collection_hours)
add("OP-447", f"{OP}:14", "경과 1시간당 단위", "447", wB.units_per_elapsed_hour)
add("OP-23", f"{OP}:14", "174단위의 경과(분)", "23", 174 / wB.units_per_elapsed_hour * 60)
nrm = pd.read_csv(RAW / "press_data_normal.csv")
tn = pd.to_datetime(nrm.TimeStamp)
dtn = tn.diff().dt.total_seconds()
segn = np.r_[0, np.cumsum((dtn.sub(0.1).abs() > 1e-6).to_numpy()[1:])]
end479 = tn[segn <= 479].max()
add("OP-61", f"{OP}:14", "기록 0~479(480단위)의 실제 경과(분)", "61", (end479 - tn.min()).total_seconds() / 60,
    note="대회 밀도 447단위/시로 환산하면 480/447.5×60 = %.1f분" % (480 / wB.units_per_elapsed_hour * 60))
e3 = csv(SUP / "e3_curve.csv")
add_bool("OP-e3", f"{OP}:14", "E3 곡선에 학습 15·보정 99(α1%) 조건이 있다", ((e3.n_train == 15) & (e3.n_cal == 99) & (e3.alpha == 0.01)).any(), "있음")

# ---------------------------------------------------------------- 15. press_evidence R4·흔들림·FM 표
for feat, dn, da in (("AI0 진동 SD", "0.071", "0.448"), ("AI1 진동 SD", "0.119", "0.241")):
    add(f"R4-{feat}-n", f"{EVR}:58", f"{feat} 정상", dn, float(cd.loc[feat].normal)); add(f"R4-{feat}-a", f"{EVR}:58", f"{feat} 이상", da, float(cd.loc[feat].abnormal))
add("R4-ratio0", f"{EVR}:58; {EVR}:383", "AI0 SD 배율", "6.3", float(cd.loc["AI0 진동 SD"].abnormal) / float(cd.loc["AI0 진동 SD"].normal))
add("R4-ratio1", f"{EVR}:58", "AI1 SD 배율", "2.0", float(cd.loc["AI1 진동 SD"].abnormal) / float(cd.loc["AI1 진동 SD"].normal))
add("R4-corr", f"{EVR}:60", "상·하부 상관 정상·이상", "0.37·-0.38", f"{rnd(float(cd.loc['상·하부 진동 상관(합동)'].normal), 2)}·{rnd(float(cd.loc['상·하부 진동 상관(합동)'].abnormal), 2)}")
add("R4-mean", f"{EVR}:61", "전류 구간 평균 중앙값", "0.6·22.9", f"{rnd(float(cd.loc['전류 구간 평균 중앙값(길이≥17)'].normal), 1)}·{rnd(float(cd.loc['전류 구간 평균 중앙값(길이≥17)'].abnormal), 1)}")
add("R4-r2", f"{EVR}:63", "R² 중앙 정상·이상", "0.996·0.451", f"{rnd(float(cd.loc['전류 사인 적합 R² 중앙값(길이≥10)'].normal), 3)}·{rnd(float(cd.loc['전류 사인 적합 R² 중앙값(길이≥10)'].abnormal), 3)}")
add("R4-grid", f"{EVR}:57", "격자 일치율 정상(%)", "0.18", float(cd.loc["전류 격자 1.1920929 일치율(허용 1e-3)"].normal), pct=True)
# 50행 이상 기록 두 개와 0.22 Hz 위상 비율
segA = np.r_[0, np.cumsum((pd.to_datetime(raw_ab.TimeStamp).diff().dt.total_seconds().sub(0.1).abs() > 1e-6).to_numpy()[1:])]
g = pd.DataFrame(dict(seg=segA, cur=raw_ab.AI2_Current.to_numpy(float))).groupby("seg").cur
st = pd.DataFrame(dict(n=g.size(), mean=g.mean(), sd=g.std(ddof=1)))
s50 = st[(st.n == 50) & (st["mean"].abs() > st.sd)]
add("R4-50", f"{EVR}:69", "50행 치우친 기록 평균·SD", "155·232, 127·111",
    f"{'·'.join(str(int(rnd(v, 0))) for v in s50['mean'])}, {'·'.join(str(int(rnd(v, 0))) for v in s50.sd)}")
phi = np.linspace(0, 2 * np.pi, 200000, endpoint=False)
tt17 = np.arange(17) * 0.1
X = np.sin(2 * np.pi * 0.22 * tt17[None, :] + phi[:, None])
frac = float((np.abs(X.mean(axis=1)) > X.std(axis=1, ddof=1)).mean())
add("R4-57", f"{EVR}:68", "0.22 Hz 사인 17행에서 |평균|>SD인 위상 비율(%)", "57", frac, pct=True)
# 앨리어싱 R²↔흔들림
add("R4-24", f"{EVR}:78", "R² 0.451에 해당하는 60 Hz 흔들림 RMS(ms, R²≈exp(-(2πfσ)²))", "2.4", math.sqrt(-math.log(0.451)) / (2 * math.pi * 60) * 1000)
for (lab, s, f, sig, d1, d2) in (("none", "A", None, 0.0, "0", "0"), ("none", "B", None, 0.0, "2.1", "0"), ("0.05", "A", 60.6, 0.05, "0", "0"),
                                 ("0.05", "B", 60.6, 0.05, "3.7", "0.6"), ("0.1", "A", 60.6, 0.1, "7.7", "1.3"), ("0.1", "B", 60.6, 0.1, "31.3", "8.3"),
                                 ("0.2", "A", 60.6, 0.2, "71.0", "48.5"), ("0.2", "B", 60.6, 0.2, "89.5", "73.1"), ("0.5", "A", 60.6, 0.5, "100", "99.8"),
                                 ("0.5", "B", 60.6, 0.5, "100", "100"), ("2.4", "A", 60.6, 2.4, "100", "100"), ("2.4", "B", 60.6, 2.4, "100", "100"),
                                 ("50.6", "A", 50.6, 0.2, "51.5", "24.8"), ("50.6", "B", 50.6, 0.2, "76.6", "54.3"), ("0.6", "A", 0.6, 2.4, "0", "0"),
                                 ("0.6", "B", 0.6, 2.4, "2.3", "0")):
    r = js_(s, f, sig)
    add(f"J-{lab}-{s}-1", f"{EVR}:371-378", f"흔들림 {lab} {s} 경보 기록(%)", d1, r.level1_rate, pct=True)
    add(f"J-{lab}-{s}-2", f"{EVR}:371-378", f"흔들림 {lab} {s} 경보 2행 이상(%)", d2, r.level2_rate, pct=True)
for lab, f, sig, dr, dn in (("none", None, 0.0, ("0.995", "0.995"), ("100", "100")), ("0.05", 60.6, 0.05, ("0.995", "0.995"), ("100", "100")),
                            ("0.1", 60.6, 0.1, ("0.994", "0.994"), ("100", "100")), ("0.2", 60.6, 0.2, ("0.990", "0.991"), ("100", "100")),
                            ("0.5", 60.6, 0.5, ("0.964", "0.965"), ("100", "99.7")), ("2.4", 60.6, 2.4, ("0.480", "0.472"), ("83.1", "80.8")),
                            ("50.6", 50.6, 0.2, ("0.992", "0.992"), ("100", "100")), ("0.6", 0.6, 2.4, ("0.995", "0.995"), ("100", "100"))):
    for i, s in enumerate("AB"):
        r = js_(s, f, sig)
        add(f"J-{lab}-{s}-r2", f"{EVR}:371-378", f"흔들림 {lab} {s} R² 중앙", dr[i], r.sine_r2_median)
        add(f"J-{lab}-{s}-fr", f"{EVR}:371-378", f"흔들림 {lab} {s} 0.6±0.05 Hz 안(%)", dn[i], r.fit_frequency_near_06_share, pct=True)
add("J-8183", f"{EVR}:381; {CYR}:231", "2.4 ms에서 0.6 Hz 유지 비율 범위(%)", "81~83",
    f"{rnd(100 * js_('B', 60.6, 2.4).fit_frequency_near_06_share, 0)}~{rnd(100 * js_('A', 60.6, 2.4).fit_frequency_near_06_share, 0)}")
add("J-n", f"{EVR}:366", "평가 기록 수 A·B", "96·145", f"{int(js_('A', None, 0.0).records)}·{int(js_('B', None, 0.0).records)}")
fm = csv(EV / "failure_mode_map.csv").set_index("fm_id")
def e1r(s, fam, lvl, t0=10):
    return one(e1[(e1["shape"] == "step")], split=s, family=fam, level=lvl, t0=t0, model="guard_v2", alpha=0.01).detect_rate_2s
for cid, doc, vals in (("FM1", "74%·94%, 100%·100%", [e1r("A", "vib_noise", 2.0), e1r("B", "vib_noise", 2.0), e1r("A", "vib_noise", 4.0), e1r("B", "vib_noise", 4.0)]),
                       ("FM2", "95%·97%", [e1r("A", "cur_noise", 0.1), e1r("B", "cur_noise", 0.1)]),
                       ("FM4a", "100%·100%, 3%·29%, 0%·6%", [e1r("A", "cur_offset", 0.4), e1r("B", "cur_offset", 0.4), e1r("A", "cur_offset", 0.8, 0), e1r("B", "cur_offset", 0.8, 0),
                                                          e1r("A", "cur_gain", 1.15), e1r("B", "cur_gain", 1.15)]),
                       ("FM5", "95%·97%, 72%·83%", [e1r("A", "cur_noise", 0.1), e1r("B", "cur_noise", 0.1), e1r("A", "cur_gain", 1.5), e1r("B", "cur_gain", 1.5)])):
    got = [f"{rnd(100 * v, 0)}%" for v in vals]
    want = re.findall(r"\d+%", doc)
    add_bool(f"FMT-{cid}", f"{EVR}:281-285", f"고장 모드 표 {cid} 대리 주입 탐지율", got == want, "·".join(got))
ab_seg = csv(EV / "abnormal_segments.csv")
add("FM-18", f"{EVR}:281,383", "이상 구간 중 진동 q99 초과", "18/21", f"{int(ab_seg.vib_out.sum())}/{len(ab_seg)}")

# ---------------------------------------------------------------- 16. press_selection §5
def ucr(s, model_prefix):
    m = uc[(uc.split_id == s) & uc.model.astype(str).str.startswith(model_prefix)]
    assert len(m) == 1, (s, model_prefix, len(m))
    return m.iloc[0]
print(uc.model.unique().tolist(), file=sys.stderr)

for s_, v2d, v1d in (("A", ("0.978", "0.970", "0.962", "0.973", "1.000"), ("0.939", "0.913")), ("B", ("0.976", "0.966", "0.971", "0.971", "0.933"), ("0.934", "0.902"))):
    r = ucr(s_, "v2 최종"); q_ = ucr(s_, "v1 기준선")
    for k, d, v in (("auc", v2d[0], r.row_auroc), ("ap", v2d[1], r.row_ap), ("f1", v2d[2], r.f1_rows), ("oracle", v2d[3], r.oracle_f1_rows), ("recf1", v2d[4], r.record_f1),
                    ("v1auc", v1d[0], q_.row_auroc), ("v1ap", v1d[1], q_.row_ap)):
        add(f"S5-{s_}-{k}", f"{SELR}:186-187", f"§5 {s_} {k}", d, v)
    add_bool(f"S5-{s_}-recf1eq", f"{SELR}:184-187", f"§5 {s_} 기록구간 F1 v1 = v2", abs(r.record_f1 - q_.record_f1) < 1e-12, f"{r.record_f1:.4f} vs {q_.record_f1:.4f}")
    add_bool(f"S5-{s_}-recauc", f"{SELR}:189", f"§5 {s_} 기록구간 AUROC v1·v2 모두 1.0", r.record_auroc == 1.0 and q_.record_auroc == 1.0, f"{r.record_auroc}, {q_.record_auroc}")
for s_, doc in (("A", "0.915~0.973"), ("B", "0.972~0.974")):
    v = [ucr(s_, "지도학습 logistic(창+v2 성분)").f1_rows, ucr(s_, "지도학습 hgb(창+v2 성분)").f1_rows]
    add(f"S5-sup-{s_}", f"{SELR}:191", f"§5 지도학습(창+v2 성분) F1 범위 {s_}", doc, f"{rnd(min(v), 3)}~{rnd(max(v), 3)}",
        note=f"unified_comparison.csv 값 {[round(x, 6) for x in v]}")
gr = csv(ROOT / "analysis" / "press_supervised" / "grouped_records.csv")
g21 = gr[(gr.features == "window_plus_v2") & (gr.cv == "21fold") & (gr.threshold == "conformal") & (gr.split == "B")]
add("SUP-B-hgb", "analysis/press_supervised/README.md:32", "지도학습 B 창+v2 부스팅 F1 (미탐/정상 알림)", "0.974 (30 / 0)",
    f"{rnd(one(g21, model='hgb').f1, 3)} ({one(g21, model='hgb').fn} / {one(g21, model='hgb').normal_alerted_segments})")
add("SUP-B-log", "analysis/press_supervised/README.md:33", "지도학습 B 창+v2 로지스틱 F1 (미탐/정상 알림)", "0.972 (32 / 1)",
    f"{rnd(one(g21, model='logistic').f1, 3)} ({one(g21, model='logistic').fn} / {one(g21, model='logistic').normal_alerted_segments})")
allc = gr[(gr.features == "window_plus_v2") & (gr.cv == "21fold") & (gr.threshold == "conformal")].f1
add("SUP-all", "analysis/press_supervised/README.md:64", "창+v2 지도학습 F1 범위(클래스 가중 포함, 두 분할)", "0.830~0.974", f"{rnd(allc.min(), 3)}~{rnd(allc.max(), 3)}")
orc = gr[(gr.features == "window_plus_v2") & (gr.cv == "21fold") & (gr.threshold == "oracle")].f1
add("SUP-oracle", "analysis/press_supervised/README.md:40", "사후 최적 문턱 창+v2 지도학습 F1 범위", "0.970~0.975", f"{rnd(orc.min(), 3)}~{rnd(orc.max(), 3)}")
led = csv(SEL / "search_ledger.csv")
add("SEL-65", f"{RM}:44; {SELR}:164", "탐색 장부 규칙 수(선정 전·후)", "65(55·10)",
    f"{led.rules.sum()}({led[led.before_v2_selection == '예'].rules.sum()}·{led[led.before_v2_selection != '예'].rules.sum()})")
ns = csv(SEL / "nested_selection.csv")
add("SEL-21", f"{RM}:44; {SELR}:167", "중첩 선택 v2 선택 횟수", "21/21", f"{int(ns.chosen_is_v2.sum())}/{len(ns)}")
add("SEL-fn", f"{SELR}:167", "중첩 선택 뺀 기록 미탐 A·B", "44·31", f"{ns.held_out_fn_A.sum()}·{ns.held_out_fn_B.sum()}")
arc = json.loads((G / "expected" / "guard_A.json").read_text())["state"]["ar2"]
add("R4-ar2", f"{EVR}:74", "AR(2) 수준 이동 이득 1−φ1−φ2 (A)", "0.14", 1 - arc[1] - arc[2])
rc = (ROOT / "press_guard" / "recalibrate.py").read_text(encoding="utf-8")
mt = int(re.search(r"MIN_TRAIN_UNITS = (\d+)", rc).group(1)); ho = int(re.search(r'"--holdout-units", type=int, default=(\d+)', rc).group(1))
add("OP-174", f"{OP}:14", "α1% 최소 단위(학습·보정·수락)", "174(15·99·60)", f"{mt + 99 + ho}({mt}·{math.ceil(1 / .01 - 1e-9) - 1}·{ho})")
for s_ in "AB":
    jj = js[(js.split == s_) & (js.source_frequency_hz == 50.6) & (js.jitter_rms_ms == 0.1)].iloc[0]
    add_bool(f"J-506-{s_}", f"{RM}:241", f"'앨리어싱 가설 아래' 0.1 ms 수치(8%·31%)가 주파수 조건 없이 성립(50.6 Hz 가설과 비교, {s_}). OPERATIONS:14는 '상용 전원 대역'(=60.6 Hz 행)으로 조건을 적어 해당 없음",
             abs(jj.level1_rate - js_(s_, 60.6, 0.1).level1_rate) < 0.01, f"50.6 Hz 0.1 ms {100 * jj.level1_rate:.1f}% vs 60.6 Hz {100 * js_(s_, 60.6, 0.1).level1_rate:.1f}%")

out = pd.DataFrame(rows)
out.to_csv(PRED / "review6_claims.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 120); pd.set_option("display.max_rows", 2000)
print(out.to_string())
print()
print(out.status.value_counts().to_string())
