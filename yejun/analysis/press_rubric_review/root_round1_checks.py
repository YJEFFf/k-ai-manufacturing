"""총괄(root) 재확인: 1차 평가관 02·03·06 지적이 저장 산출물·코드와 맞는지 독립 확인한다. 읽기 전용."""
from pathlib import Path
import json
import re

import numpy as np
import pandas as pd

YEJUN = Path(__file__).resolve().parents[2]
SUP = YEJUN / "analysis" / "press_supplement"
out = {}

# M1/P1-E3: 사전 안정 규칙 결과와 README 표현
stab = pd.read_csv(SUP / "e3_stability.csv")
readme = (SUP / "README.md").read_text()
out["M1_E3_prereg"] = dict(settings=len(stab), stable_true=int(stab.stable.sum()),
                           readme_says_not_applicable=bool(re.search("적용할 수 없었", readme)))

# P2-E3: '전류 주입 탐지는 모든 설정에서 100%' 문장
curve = pd.read_csv(SUP / "e3_curve.csv")
low = curve[curve.inject_cur_offset < 1]
small = curve[(curve.alpha == .01) & (curve.n_train == 15) & (curve.n_cal == 99)]
out["P2_E3_current_100pct"] = dict(fits=len(curve), cur_noise_min=float(curve.inject_cur_noise.min()),
                                   cur_offset_min=float(curve.inject_cur_offset.min()), cur_offset_below_1=len(low),
                                   small_15_99_cur_min=float(small[["inject_cur_noise", "inject_cur_offset"]].min().min()),
                                   readme_sentence_present="전류 주입 탐지는 모든 설정에서 100%" in readme)

# M2/P2-E1: 그림의 '주입 없음' 기준선(두 분할 최솟값)과 분할별 실제 값
s = pd.read_csv(SUP / "e1_summary.csv")
none = s[(s.family == "none") & (s.alpha == .01) & (s.t0 == 10) & (s["shape"] == "step") & (s.model == "guard_v2")]
out["M2_fig_none_baseline"] = dict(by_split={r.split: dict(records=int(r.records), rate=float(r.detect_rate_2s)) for r in none.itertuples()},
                                   figure_uses_min=float(none.detect_rate_2s.min()))

# M3: '관측 이상은 하한보다 약 5배'의 근거 산식·유효 n
ref = pd.read_csv(SUP / "e1_reference_segments.csv")
a, n = ref[ref.source == "abnormal"], ref[ref.source == "normal_test_A"]
coef = (1.83308321, -0.97486193)   # guard_A AR(2) 기울기(동결 artifact와 같은 값)
scale = 127.354406                  # guard_A 전류 척도
k = np.sqrt(1 + coef[0] ** 2 + coef[1] ** 2)
equiv = np.sqrt(np.maximum(a.ar_resid_std ** 2 - n.ar_resid_std.median() ** 2, 0)) / (scale * k)
out["M3_five_times"] = dict(valid_resid_segments=int(a.ar_resid_std.notna().sum()), abnormal_segments=len(a),
                            equiv_s_median=float(equiv.median()), equiv_s_min=float(equiv.min()), equiv_s_max=float(equiv.max()),
                            ratio_to_floor_0p1=float(equiv.median() / .1),
                            offset_abs_median_over_A=float(a.cur_mean_over_A.abs().median()),
                            offset_ratio_to_floor_0p4=float(a.cur_mean_over_A.abs().median() / .4))

# P2-AMP: 진폭 신뢰 제한 정의
analyze = (YEJUN / "press_guard" / "analyze.py").read_text()
out["P2_AMP_definition"] = dict(amp_reliable_length_only=bool(re.search(r"amp_reliable=bool\(len\(idx\) >= AMP_MIN_LEN\)", analyze)))

# R6-1/R6-3: 보완 실험 manifest 계약
man = {e: json.loads((SUP / f"{e}_manifest.json").read_text()) for e in ("e1", "e2", "e3")}
out["R6_manifests"] = {e: dict(keys=sorted(m), has_output_hashes=any("output" in k for k in m),
                               has_artifact_hashes="artifacts" in m, blas=m["environment"].get("blas"))
                       for e, m in man.items()}

# R6-2: E2 캐시 키
uci = (SUP / "uci_v2.py").read_text()
out["R6_2_cache_key"] = dict(cache_checks_only_zip_sha='if str(c["sha"]) == sha:' in uci)

print(json.dumps(out, ensure_ascii=False, indent=1))
(Path(__file__).with_suffix(".json")).write_text(json.dumps(out, ensure_ascii=False, indent=1))
