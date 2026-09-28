"""검증 0: redA2_common의 기본 설정이 팀 API(GuardModel.fit/predict)와 같은 결과를 내는지 행 단위로 대조한다.

대조 분할: A, B, 팀 시간순 5창, 시간 역순 2개, 격자 임의 3개. 대조 항목: 보정값 배열, 행 점수, α 1·3·5% 경보.
또 커밋된 press_guard/outputs/metrics.csv·rolling.csv의 TP/FP/FN·정상 알림과 대조한다(읽기만).
"""
import json
import time

import numpy as np
import pandas as pd

import redA2_common as C

started = time.monotonic()
data = C.Data()
GuardModel = C.M.GuardModel
rec = np.arange(600)
cases = {
    "A": (rec[:360], rec[360:480], rec[480:]),
    "B": (rec[:300], rec[300:420], rec[420:]),
    **{f"roll_{e + 120}_{e + 179}": (rec[:e], rec[e:e + 120], rec[e + 120:e + 180]) for e in (180, 240, 300, 360, 420)},
    "rev_A": (rec[240:], rec[120:240], rec[:120]),          # 뒤 360 학습, 가운데 120 보정, 앞 120 평가
    "rev_B": (rec[300:], rec[180:300], rec[:180]),
    "grid_200_100": (rec[:200], rec[200:300], rec[300:]),
    "grid_150_150": (rec[:150], rec[150:300], rec[300:]),
    "grid_430_100": (rec[:430], rec[430:530], rec[530:]),
}
rows, all_ok = [], True
for name, (tr, ca, te) in cases.items():
    fit = C.Fitted(data, tr, ca, C.V2)
    team = GuardModel.fit(data.frame("n", np.isin(data.seg["n"], tr)), data.frame("n", np.isin(data.seg["n"], ca)), split=name)
    test_rows = np.isin(data.seg["n"], te)
    same_cal = bool(np.array_equal(np.sort(team.cal), np.sort(fit.cal)))
    same_coef = bool(np.array_equal(team.coef, fit.coef))
    ok = same_cal and same_coef
    detail = {}
    for alpha in C.ALPHAS:
        pn = team.predict(data.frame("n", test_rows), alpha)
        pa = team.predict(data.frame("a", np.ones(len(data.seg["a"]), bool)), alpha)
        mine_n, mine_a = fit.alarm("n", alpha)[test_rows], fit.alarm("a", alpha)
        e_n = bool(np.array_equal(pn.alarm.to_numpy(bool), mine_n))
        e_a = bool(np.array_equal(pa.alarm.to_numpy(bool), mine_a))
        s_n = bool(np.array_equal(np.nan_to_num(pn.score.to_numpy(), nan=-9), np.nan_to_num(fit.score["n"][test_rows], nan=-9)))
        s_a = bool(np.array_equal(np.nan_to_num(pa.score.to_numpy(), nan=-9), np.nan_to_num(fit.score["a"], nan=-9)))
        # 2단계(건의 경보 행 2개 이상)와 사건 묶음도 팀 출력과 대조
        lvl2_team = int(pn.groupby("record_id").alarm.sum().ge(2).sum())
        s, _, n = C.summarize(fit, alpha, te)
        inc_team = int(pn.incident_notification.sum()), int(pn.incident_escalation.sum())
        inc = C.incident_counts(data.time["n"][test_rows].to_numpy(), data.seg["n"][test_rows], fit.units("n")[test_rows], mine_n)
        inc_mine = (len(inc), sum(i["level"] == 2 for i in inc))
        good = e_n and e_a and s_n and s_a and lvl2_team == s["normal_level2_records"] and inc_team == inc_mine
        ok &= good
        detail[alpha] = dict(alarm_normal_equal=e_n, alarm_abnormal_equal=e_a, score_normal_equal=s_n, score_abnormal_equal=s_a,
                             tp=s["tp"], fp=s["fp"], fn=s["fn"], normal_alerted=s["normal_alerted"], abnormal_detected=s["abnormal_detected"],
                             level2_team=lvl2_team, level2_mine=s["normal_level2_records"], incidents_team=inc_team, incidents_mine=inc_mine)
        rows.append(dict(split=name, alpha=alpha, **detail[alpha], cal_equal=same_cal, coef_equal=same_coef, all_equal=good and same_cal and same_coef))
    all_ok &= ok
    print(f"[{time.monotonic() - started:6.1f}s] {name}: {'일치' if ok else '불일치'}", flush=True)

table = pd.DataFrame(rows)
table.to_csv(C.HERE / "redA2_00_validate.csv", index=False)

# 커밋된 표와 대조(저장소 파일은 읽기만 한다)
REPO_OUT = C.REPO / "yejun" / "press_guard" / "outputs"
committed = pd.concat([pd.read_csv(REPO_OUT / "metrics.csv"), pd.read_csv(REPO_OUT / "rolling.csv")], ignore_index=True)
committed = committed[committed.model.eq("guard_v2")]
name_map = {"A": "A", "B": "B", **{f"roll_{e + 120}_{e + 179}": f"normal_{e + 120}_{e + 179}" for e in (180, 240, 300, 360, 420)}}
cmp = []
for r in table.itertuples():
    if r.split not in name_map:
        continue
    c = committed[committed.split.eq(name_map[r.split]) & np.isclose(committed.alpha, r.alpha)].iloc[0]
    same = (r.tp, r.fp, r.fn, r.normal_alerted, r.abnormal_detected) == (c.tp, c.fp, c.fn, c.normal_notified_segments, c.abnormal_notified_segments)
    cmp.append(dict(split=r.split, alpha=r.alpha, matches_committed=bool(same)))
    all_ok &= bool(same)
summary = dict(all_equal_team_api=bool(table.all_equal.all()), committed_matches=f"{sum(c['matches_committed'] for c in cmp)}/{len(cmp)}",
               splits=list(cases), elapsed_s=round(time.monotonic() - started, 1), ok=bool(all_ok))
(C.HERE / "redA2_00_validate.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False))
print(table[["split", "alpha", "tp", "fp", "fn", "normal_alerted", "abnormal_detected", "level2_mine", "incidents_mine", "all_equal"]].to_string(index=False))
