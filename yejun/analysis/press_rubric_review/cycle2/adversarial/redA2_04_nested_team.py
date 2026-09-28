"""검증 2: 팀의 후보 목록·중첩 선택을 임시 사본에서 다시 계산하고, 중첩 선택이 뒤집힐 수 있었는지 본다.

- 임시 사본의 analysis/press_selection/run.py에서 candidate_universe·nested_selection 함수만 불러 쓴다(파일을 쓰지 않는다).
  run.py는 import할 때 동결 모델을 읽지 않는다(Context를 만들 때만 읽는다).
- 커밋된 candidate_universe.csv·nested_selection.csv와 대조한다.
- 선택 여유: v2와 차점 후보의 미탐 합 차이, 기록 하나·묶음을 뺐을 때 가능한 최대 변화.
- 팀 규칙을 사후 대안(Fisher·5NN·지속성 등, 커밋 표)까지 넣은 후보 집합에 적용하면 무엇이 뽑히는가.
출력: redA2_04_nested_team.json
"""
import importlib.util
import json
import sys

import numpy as np
import pandas as pd

import redA2_common as C

SEL = C.REPO / "yejun" / "analysis" / "press_selection"
spec = importlib.util.spec_from_file_location("team_selection_run", SEL / "run.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)
D = R.D
normal, abnormal, _ = D.load()
universe, stats_, sig, pattern_of = R.candidate_universe(normal, abnormal, D.segments(normal))
nested, meta = R.nested_selection(stats_, sig)
committed_u = pd.read_csv(SEL / "candidate_universe.csv")
committed_n = pd.read_csv(SEL / "nested_selection.csv")
out = dict(universe_rows=len(universe), universe_equals_committed=bool(universe.reset_index(drop=True)[["split_id", "candidate", "normal_alerted", "fp", "fn", "abnormal_detected"]]
                                                                     .equals(committed_u[["split_id", "candidate", "normal_alerted", "fp", "fn", "abnormal_detected"]])),
           nested_equals_committed=bool(nested.reset_index(drop=True).equals(committed_n)),
           nested_all_v2=bool(nested.chosen_is_v2.all()), alarm_patterns=len(sig), eligible_patterns=len(meta["eligible"]))

# 중첩 선택 코드가 뺀 기록을 선택에 쓰지 않는지: 뺀 기록의 미탐을 임의로 바꿔도 선택이 같아야 한다
import copy
rng = np.random.default_rng(0)
same = True
for j in range(21):
    s2 = copy.deepcopy(stats_)
    for key in s2:
        s2[key]["fn_by_rec"] = s2[key]["fn_by_rec"].copy(); s2[key]["det_by_rec"] = s2[key]["det_by_rec"].copy()
        s2[key]["fn_by_rec"][j] = rng.integers(0, 50)   # 뺀 기록의 미탐만 바꾼다(탐지 여부를 바꾸면 다른 겹의 후보가 모두 탈락해 비교가 안 된다)
    n2, _ = R.nested_selection(s2, sig)
    same &= bool(n2.chosen.iloc[j] == nested.chosen.iloc[j])
out["held_out_record_not_used_in_selection"] = same

# 선택 여유
elig = meta["eligible"]
tot = {u: sum(int(stats_[(s, u)]["fn_by_rec"].sum()) for s in "AB") for u in elig}
order = sorted(tot.items(), key=lambda kv: kv[1])
v2 = meta["v2_rep"]
runner = next(u for u, _ in order if u != v2)
diff = sum(stats_[(s, runner)]["fn_by_rec"] - stats_[(s, v2)]["fn_by_rec"] for s in "AB")     # 기록별(차점 − v2) 미탐 차이
out["eligible_ranking"] = [dict(candidate=u, aliases=meta["aliases"].get(u, []), fn_sum=t) for u, t in order[:8]]
out["margin"] = dict(v2_fn_sum=tot[v2], runner_up=runner, runner_up_fn_sum=tot[runner], gap=tot[runner] - tot[v2],
                     per_record_gap=diff.tolist(), max_single_record_gap=int(diff.max()),
                     records_where_runner_up_better=int((diff < 0).sum()),
                     max_records_removable_without_flip=int(np.searchsorted(np.cumsum(np.sort(diff)[::-1]), tot[runner] - tot[v2])),
                     note="기록 k개를 빼서 선택이 뒤집히려면 뺀 기록의 (차점 − v2) 차이 합이 전체 차이 이상이어야 한다")
# 정상 알림 조건에서 탈락한 후보 가운데 v2보다 미탐이 적은 것
uniq = sorted(g[0] for g in sig.values())
lim = meta["v1_limit"]
excluded = []
for u in uniq:
    if u in elig:
        continue
    t = sum(int(stats_[(s, u)]["fn_by_rec"].sum()) for s in "AB")
    if t <= tot[v2] + 10:
        excluded.append(dict(candidate=u, fn_sum=t, normal_alerted_A=stats_[("A", u)]["normal_alerted"], normal_alerted_B=stats_[("B", u)]["normal_alerted"]))
out["excluded_by_normal_alert_constraint_near_v2"] = excluded

# 팀 규칙을 사후 대안까지 넣은 집합에 적용(커밋 표 값 사용, α=1%)
alt = pd.read_csv(SEL / "same_feature_alternatives.csv")
rules = pd.read_csv(SEL / "combination_rules.csv")
mit = pd.read_csv(SEL / "fp_mitigation_v2.csv")
pool = []
for name, t, col in (("same_feature", alt, "candidate"), ("rule", rules, "rule"), ("mitigation", mit[mit.source.str.startswith("v2")], "variant")):
    t = t[np.isclose(t.alpha, .01)]
    fn_col = "fn" if "fn" in t else "fn_rows"
    for cand, g in t.groupby(col):
        g = g.set_index("split_id")
        if not {"A", "B"} <= set(g.index):
            continue
        pool.append(dict(source=name, candidate=cand, fn_A=int(g.loc["A", fn_col]), fn_B=int(g.loc["B", fn_col]),
                         normal_A=int(g.loc["A", "normal_alerted"]), normal_B=int(g.loc["B", "normal_alerted"]),
                         det_A=int(g.loc["A", "abnormal_detected"]), det_B=int(g.loc["B", "abnormal_detected"])))
pool = pd.DataFrame(pool)
pool["fn_sum"] = pool.fn_A + pool.fn_B
pool["eligible"] = (pool.normal_A <= lim["A"]) & (pool.normal_B <= lim["B"]) & (pool.det_A == 21) & (pool.det_B == 21)
pool = pool.sort_values(["eligible", "fn_sum"], ascending=[False, True])
out["team_rule_on_posthoc_pool"] = pool.to_dict("records")
out["team_rule_on_posthoc_pool_winner"] = pool[pool.eligible].iloc[0].to_dict()
(C.HERE / "redA2_04_nested_team.json").write_text(json.dumps(C.D.to_jsonable(out), ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(C.D.to_jsonable({k: v for k, v in out.items() if k != "team_rule_on_posthoc_pool"}), ensure_ascii=False, indent=1))
pd.set_option("display.width", 250)
print(pool.to_string(index=False))
