"""평가관 04 cycle2 round3: 대기열 한계(queue_injection_ranks_v2.csv, 건 단위)를 콘솔이 쓰는 사건 단위로 다시 센다. 읽기 전용.

실행(yejun/에서):
  OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python \
      analysis/press_rubric_review/cycle2/round3/judge04_queue_incident.py 2>&1 | tee analysis/press_rubric_review/cycle2/round3/judge04_queue_incident.log
방법: 팀 queue_rankings와 같은 주입(길이 30행 이상 단위의 10행째부터, seed 0)과 같은 정렬 키(level→evidence_count→alarm_share→peak_score).
  건 단위: 팀 표와 같은지 먼저 확인한다. 사건 단위: 주입 자료(시간 순서 그대로)의 사건 중 주입 기록을 포함한 사건과, 주입 없는 정상 평가의 사건(오경보)을
  한 목록으로 순위를 매겨, 가장 앞선 오경보 사건보다 뒤에 오는 주입 사건 수를 센다. [주입] 인공 신호.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[3]
GUARD = YEJUN / "press_guard"
sys.path.insert(0, str(GUARD))
from model import D, ALPHAS, cases, incidents, priority_ranks, load_bundle  # noqa: E402
from recalibrate import inject, unit_layout  # noqa: E402

T0 = time.time()
models = {s: load_bundle(GUARD / "artifacts" / f"guard_{s}.json") for s in ("A", "B")}
normal, abnormal, _ = D.load()
qi = pd.read_csv(GUARD / "outputs" / "queue_injection_ranks_v2.csv")
qi = qi[qi.key.eq("level_evidence_share_peak")]
INJ = (("cur_noise", .1), ("cur_noise", .2), ("cur_offset", .4), ("vib_noise", 2.0), ("vib_noise", 4.0))
rows = []
for sid, model in models.items():
    test = D.inputs_only(D.split_normal(normal, D.segments(normal), sid)["test"])
    units, in_unit, size = unit_layout(test)
    mask = (size >= 30) & (in_unit >= 10)
    for alpha in ALPHAS:
        pn = model.predict(test, alpha)
        qn = cases(pn)
        fa_inc = incidents(qn, pn) if len(qn) else pd.DataFrame()
        for fam, lv in INJ:
            frame = inject(test, model, fam, lv, mask, np.random.default_rng(0))
            pi = model.predict(frame, alpha)
            inj_recs = set(np.unique(pi.record_id[mask]))
            # 건 단위(팀 방법 재현): 정상 평가 건 + 주입 기록 건
            keep = np.isin(pi.record_id, list(inj_recs))
            sub = pi[keep].copy(); sub["record_id"] += int(pn.record_id.max()) + 1; sub["row_id"] += len(pn)
            q2 = cases(pd.concat([pn, sub], ignore_index=True))
            injected = q2.record_id > pn.record_id.max()
            r2 = priority_ranks(q2)
            best = r2[~injected].min() if (~injected).any() else np.inf
            case_below = int((r2[injected] > best).sum()) if np.isfinite(best) else 0
            team = qi[(qi.split == sid) & np.isclose(qi.alpha, alpha) & (qi.family == fam) & np.isclose(qi.level_value, lv)]
            # 사건 단위: 주입 자료 자체의 사건(시간 순서 그대로) 중 주입 기록을 포함한 사건 + 정상 평가의 오경보 사건
            qa = cases(pi)
            ia = incidents(qa, pi) if len(qa) else pd.DataFrame()
            inc_inj = ia[ia.records.map(lambda s: bool(set(int(x) for x in str(s).split("+")) & inj_recs))] if len(ia) else ia
            both = pd.concat([fa_inc.assign(src="fa"), inc_inj.assign(src="inj")], ignore_index=True)
            if len(both):
                both["rank"] = priority_ranks(both)
                best_i = both[both.src.eq("fa")]["rank"].min() if both.src.eq("fa").any() else np.inf
                inc_below = int((both[both.src.eq("inj")]["rank"] > best_i).sum()) if np.isfinite(best_i) else 0
                inj_level1 = int((both.src.eq("inj") & both.level.eq(1)).sum())
            else:
                inc_below, inj_level1 = 0, 0
            rows.append(dict(split=sid, alpha=alpha, family=fam, level=lv, injected_cases=int(injected.sum()), fa_cases=int((~injected).sum()),
                             case_below_best_fa=case_below, team_case_below=int(team.injected_below_best_false_alarm.iloc[0]) if len(team) else None,
                             injected_incidents=int(len(inc_inj)), fa_incidents=int(len(fa_inc)), incident_below_best_fa=inc_below,
                             injected_incidents_level1=inj_level1,
                             injected_records_per_incident=round(len(inj_recs) / max(len(inc_inj), 1), 2)))
out = pd.DataFrame(rows)
out["case_eq_team"] = out.case_below_best_fa == out.team_case_below
summary = dict(case_level_eq_team_all=bool(out.case_eq_team.all()),
               case_level_total=int(out.case_below_best_fa.sum()), incident_level_total=int(out.incident_below_best_fa.sum()),
               conditions_case_positive=int((out.case_below_best_fa > 0).sum()), conditions_incident_positive=int((out.incident_below_best_fa > 0).sum()),
               elapsed_s=round(time.time() - T0, 1))
(HERE / "judge04_queue_incident.json").write_text(json.dumps(dict(summary=summary, rows=out.to_dict("records")), ensure_ascii=False, indent=1,
                                                             default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")
print(out.to_string(index=False))
print(summary)
