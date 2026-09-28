"""검증 2·5: 초모수 격자 안에서의 중첩 선택. 팀 선택 규칙(정상 알림 ≤ v1, 학습에 쓴 이상 기록 전부 탐지, 두 분할 미탐 합 최소)을
격자 1,440개 설정에 적용한다. 이상 기록을 빼는 방식: 1개씩(21겹), 시간순 3개 묶음(7겹), 앞 절반/뒤 절반(2겹).
동률인 설정은 모두 뽑힌 것으로 보고 뺀 기록의 미탐을 평균한다.
입력: redA2_02_hyper_grid_wide.csv, redA2_02_hyper_records.npz   출력: redA2_03_nested_hyper.csv/.json
"""
import json

import numpy as np
import pandas as pd

from pathlib import Path
HERE = Path(__file__).resolve().parent
wide = pd.read_csv(HERE / "redA2_02_hyper_grid_wide.csv")
rec = np.load(HERE / "redA2_02_hyper_records.npz")
ALPHA = 0.01
N = 21
names = wide.config.tolist()
FN = {s: np.stack([rec[f"{c}|{s}|{ALPHA}|fn"] for c in names]) for s in "AB"}       # (설정, 기록)
DET = {s: np.stack([rec[f"{c}|{s}|{ALPHA}|det"] for c in names]) for s in "AB"}
normal_ok = ((wide.normal_alerted_A <= 0) & (wide.normal_alerted_B <= 3)).to_numpy()
is_v2 = (wide.config == "wl8_we6_sw7_ar2_q0.95_fmax_u50").to_numpy()
assert is_v2.sum() == 1 and FN["A"][is_v2].sum() == 44 and FN["B"][is_v2].sum() == 31
pools = {"전체 격자(fmax·Fisher·합)": np.ones(len(wide), bool), "fmax만": wide.rule.eq("fmax").to_numpy(),
         "fmax·q0.95만(창·AR만 고름)": (wide.rule.eq("fmax") & np.isclose(wide.q, .95)).to_numpy()}
schemes = {"이상 기록 1개 빼기(21겹)": [[j] for j in range(N)],
           "시간순 3개 묶음 빼기(7겹)": [list(range(j, j + 3)) for j in range(0, N, 3)],
           "앞 10개로 고르고 뒤 11개 평가 + 반대(2겹)": [list(range(10, 21)), list(range(0, 10))]}
rows = []
for pool_name, pool in pools.items():
    ok = pool & normal_ok
    total = FN["A"] + FN["B"]
    apparent = total[ok & DET["A"].all(1) & DET["B"].all(1)].sum(1)
    for scheme, folds in schemes.items():
        nested = {s: 0.0 for s in "AB"}
        v2_pick, picks, chosen_rules = 0.0, [], {}
        for held in folds:
            keep = np.ones(N, bool); keep[held] = False
            cand = ok & DET["A"][:, keep].all(1) & DET["B"][:, keep].all(1)
            score = np.where(cand, total[:, keep].sum(1), np.inf)
            best = np.flatnonzero(score == score.min())
            picks.append(len(best))
            v2_pick += float(is_v2[best].mean())
            for s in "AB":
                nested[s] += float(FN[s][best][:, held].sum(1).mean())
            for r in wide.rule.to_numpy()[best]:
                chosen_rules[r] = chosen_rules.get(r, 0) + 1 / len(best)
        held_total = sum(len(h) for h in folds)
        rows.append(dict(pool=pool_name, pool_configs=int(pool.sum()), eligible_normal=int(ok.sum()), scheme=scheme, folds=len(folds),
                         apparent_best_fn_sum=float(apparent.min()), v2_fn_sum=75,
                         nested_fn_A=round(nested["A"], 2), nested_fn_B=round(nested["B"], 2), nested_fn_sum=round(nested["A"] + nested["B"], 2),
                         optimism_vs_apparent_best=round(nested["A"] + nested["B"] - float(apparent.min()), 2),
                         nested_minus_v2=round(nested["A"] + nested["B"] - 75, 2), v2_share_of_picks=round(v2_pick / len(folds), 3),
                         mean_tied_configs=round(float(np.mean(picks)), 1), chosen_rules=json.dumps({k: round(v, 2) for k, v in chosen_rules.items()}, ensure_ascii=False),
                         held_records_total=held_total))
out = pd.DataFrame(rows)
out.to_csv(HERE / "redA2_03_nested_hyper.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60)
print(out.drop(columns=["chosen_rules"]).to_string(index=False))
print(out[["pool", "scheme", "chosen_rules"]].to_string(index=False))

# v2의 기록별 미탐과, 기록 하나가 선택을 뒤집을 수 있는 크기
v2_fn = FN["A"][is_v2][0] + FN["B"][is_v2][0]
summary = dict(v2_fn_by_record_A=FN["A"][is_v2][0].tolist(), v2_fn_by_record_B=FN["B"][is_v2][0].tolist(),
               normal_alert_patterns=wide.groupby(["normal_alerted_A", "normal_alerted_B"]).size().reset_index(name="configs").to_dict("records"))
(HERE / "redA2_03_nested_hyper.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(wide.groupby(["normal_alerted_A", "normal_alerted_B"]).size())
