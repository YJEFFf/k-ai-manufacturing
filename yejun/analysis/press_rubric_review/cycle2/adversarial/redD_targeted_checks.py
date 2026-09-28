"""적대적 검수자 D — 남은 표적 확인(읽기 전용).

1) 표의 파일:행 인용 중 수동 확인하지 않은 것을 실제 행으로 대조
2) README '크기 성분 문턱 |z| 4.49·3.77'이 v2 크기 성분의 실제 발화 경계인지(행 단위 예측으로)
3) A 보정 최대 점수가 어느 기록에서 나왔는지(저장 모델 JSON)
4) README:107 '이상 행 A 555/600·B 568/600이 상한 0.55' 재계산
산출: redD_targeted_checks.log
실행: OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python redD_targeted_checks.py
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from redD_lib import GUARD, HERE, OUT, SEL, SPL, YEJUN

log = []


def p(*a):
    s = " ".join(str(x) for x in a)
    log.append(s)
    print(s)


def rows(path, lines, cols=None):
    """파일의 물리 행 번호(머리글=1)로 읽는다."""
    df = pd.read_csv(path)
    out = []
    for ln in lines:
        r = df.iloc[ln - 2]
        out.append((ln, r if cols is None else r[cols]))
    return out


# 1) 인용 대조 --------------------------------------------------------------
p("== 1) 파일:행 인용 대조")
for ln, r in rows(SEL / "fp_mitigation_injection_v2.csv", [9, 10, 39, 40]):
    p(f"fp_mitigation_injection_v2.csv:{ln}", dict(r[[c for c in r.index if c in ("split", "alpha", "family", "level", "variant", "model", "detect_rate_2s_v2", "detect_rate_2s_variant")]]) or r.to_dict())
for ln, r in rows(OUT / "robustness_v2.csv", [3, 15, 39, 51], ["split", "model", "input_variant", "alpha", "normal_notified_segments", "normal_segments"]):
    p(f"robustness_v2.csv:{ln}", r.to_dict())
for ln, r in rows(OUT / "uncertainty_v2.csv", [23, 24, 25, 65, 66, 67], ["split", "model", "alpha", "statistic", "block_length", "observed", "boot_p2_5", "boot_p97_5", "degenerate_all_zero"]):
    p(f"uncertainty_v2.csv:{ln}", r.to_dict())
fe = pd.read_csv(OUT / "fp_events_v2.csv")
for ln in [3, 12, 18, 22, 28, 41, 42]:
    r = fe.iloc[ln - 2]
    p(f"fp_events_v2.csv:{ln}", r[["model", "alpha", "record", "alarm_rows", "reasons", "magnitude_sensor"]].to_dict())
cs = pd.read_csv(YEJUN / "analysis/press_dayshift/v2_current_scale.csv")
p("v2_current_scale.csv 열:", list(cs.columns)[:14])
for ln in [110, 167, 182, 221]:
    r = cs.iloc[ln - 2]
    p(f"v2_current_scale.csv:{ln}", {k: r[k] for k in r.index[:10]})
for f, ln in [("e2_uci_metrics.csv", 2), ("e3_stability.csv", 2)]:
    r = pd.read_csv(SPL / f).iloc[ln - 2]
    p(f"{f}:{ln}", {k: r[k] for k in r.index[:12]})
q = pd.read_csv(OUT / "queue_injection_ranks_v2.csv")
cited = [35, 55, 63, 71, 83, 91, 95, 111, 115]
sub = q.iloc[[c - 2 for c in cited]][["split", "alpha", "family", "level_value", "key", "injected_cases", "injected_below_best_false_alarm", "injected_incidents_below_best_false_alarm"]]
p("queue_injection_ranks_v2.csv 인용 9행:\n" + sub.to_string())
keys = q.key.unique().tolist()
adopted = q[q.injected_below_best_false_alarm > 0].groupby("key").size().to_dict()
p("키별 '뒤처진 조건' 수:", adopted, "| 키 목록:", keys)

# 2) 크기 성분 |z| 경계 ---------------------------------------------------------
p("\n== 2) v2 크기 성분의 실제 발화 경계(행 단위 예측)")
for split in ("A", "B"):
    t = pd.read_csv(OUT / f"test_predictions_{split}.csv", usecols=["reason", "magnitude", "g_magnitude", "alarm", "score"])
    fired = t.reason.fillna("").str.split("+").apply(lambda x: "magnitude" in x)
    thr = float(json.loads((GUARD / "artifacts" / f"guard_{split}.json").read_text()).get("threshold", {}).get("0.01", np.nan)) \
        if isinstance(json.loads((GUARD / "artifacts" / f"guard_{split}.json").read_text()).get("threshold"), dict) else np.nan
    p(f"{split}: 크기 발화 행 {int(fired.sum())}개, 발화 행 |z| 최소 {t.magnitude[fired].min():.3f}, "
      f"비발화 행 |z| 최대 {t.magnitude[~fired].max():.3f}, 발화 행 g 최소 {t.g_magnitude[fired].min():.3f}, 결합 점수 경보 최소 {t.score[t.alarm == 1].min():.3f}")

# 3) 보정 최대 점수의 출처 -------------------------------------------------------
p("\n== 3) 저장 모델의 보정 정보")
for split in ("A", "B"):
    g = json.loads((GUARD / "artifacts" / f"guard_{split}.json").read_text())

    def walk(o, path=""):
        if isinstance(o, dict):
            for k, v in o.items():
                yield from walk(v, f"{path}.{k}" if path else k)
        elif isinstance(o, list) and 100 <= len(o) <= 130 and all(isinstance(x, (int, float)) for x in o):
            yield path, o
    for path, arr in walk(g):
        a = np.asarray(arr, float)
        top = np.argsort(-a)[:3]
        p(f"{split} {path}: 길이 {len(a)}, 상위 3 값 {np.round(a[top], 3).tolist()} (위치 {top.tolist()})")
    for k in ("split", "calibration", "calibration_segments", "calibration_records", "cal_records", "n_calibration"):
        if k in g:
            v = g[k]
            p(f"{split} {k}: {str(v)[:160]}")

# 4) 상한 값 개수 -----------------------------------------------------------
p("\n== 4) π 1% 확률 상한(0.55) 행 수")
for split in ("A", "B"):
    t = pd.read_csv(OUT / f"test_predictions_{split}.csv", usecols=["label", "alarm", "anomaly_probability", "likelihood_ratio"])
    cap = np.isclose(t.anomaly_probability, 0.55)
    p(f"{split}: 이상 행 중 상한 {int((cap & (t.label == 1)).sum())}/600, 정상 경보 행 중 상한 {int((cap & (t.label == 0) & (t.alarm == 1)).sum())}/{int(((t.label == 0) & (t.alarm == 1)).sum())}")

(HERE / "redD_targeted_checks.log").write_text("\n".join(log) + "\n", encoding="utf-8")
sys.exit(0)
