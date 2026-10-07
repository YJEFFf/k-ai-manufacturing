"""6단계: 02~05 산출물에서 주 표와 사전 등록 교체 검토 조건(PROTOCOL.md 7절)의 판정을 그대로 뽑는다.

README에 옮길 수치는 이 출력(outputs/06_summary.md·.json)에서만 가져온다(손으로 옮겨 적지 않는다).
실행: PYTHONDONTWRITEBYTECODE=1 python 06_summary.py
"""
from __future__ import annotations

import json
import sys

sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import lx_harness as H  # noqa: E402

LBL = {"L": "보완 LSTM (새 시드 3·4·5 앙상블)", "L+R1": "보완 LSTM + R1 (새 시드 앙상블)"}


def load(name):
    p = H.OUT / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def f(x, n=3):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else (f"{x:.{n}f}" if isinstance(x, float) else str(x))


def main():
    sel, comp, cond = load("02_selection.json"), load("03_comparison.json"), load("04_conditions.json")
    rob = load("05_robustness.json")
    L, out = [], {}
    w = L.append

    # ---------------- 선택 경로
    s1, s2a = load("02_stage1_selection.json"), load("02_stage2a_selection.json")
    w("## 선택 경로 (valid만, 시드 0·1·2 앙상블)")
    for name, s in (("1단계", s1["track_L"]), ("2a", s2a["chosen"]), ("최종(잠금)", sel["track_L"])):
        w(f"- {name}: `{s['cfg']}` · `{s['scoring']}` — valid 평균 {f(s['metric'], 4)} (단일 시드 평균 {f(s['single_mean'], 4)}, 표준편차 {f(s['single_sd'], 4)})")
    w(f"- 트랙 L+R1 주 결과: 최종 변형 + R1 — valid 평균 {f(sel['track_LR1']['metric'], 4)}")
    e = sel["exploratory_LR1"]
    w(f"- 트랙 L+R1 탐색 최고(낙관, 보조): `{e['cfg']}` · `{e['scoring']}` — valid 평균 {f(e['metric'], 4)}")
    w("")

    # ---------------- 주 비교
    def pick(rows, key):
        return next((r for r in rows if r.get("variant", r.get("model", "")).endswith(key)), None)

    def refrow(name):
        return next(r for r in comp["refs"] if r["model"] == name)

    lst = comp["track_L"]
    e345, e012 = pick(lst, ":e345"), pick(lst, ":e012")
    singles = [r for r in lst if r["variant"].split(":")[-1].startswith("s")]
    lr1 = comp["track_LR1"]
    lr1_e345, lr1_e012 = pick(lr1, ":e345"), pick(lr1, ":e012")
    start = [r for r in comp["start_point"] if r["variant"].endswith(":e012")]
    rows = [("가이드북 LSTM 출발점 (이 PC 시드 0·1·2 앙상블)", start[0] if start else None),
            ("lstm20 (준용 행 표와 같은 시드 0 모델)", refrow("lstm20")),
            ("보완 LSTM — 새 시드 앙상블 e345 (주 값)", e345), ("보완 LSTM — 선택 시드 앙상블 e012", e012),
            ("v2", refrow("v2")),
            ("보완 LSTM + R1 — e345 (주 값)", lr1_e345), ("보완 LSTM + R1 — e012", lr1_e012),
            ("v2 + R1 (잠금 선택)", refrow("v2+H1")), ("v2 + R1 + R2 (최종, 참고)", refrow("v2+H1+H2"))]
    w("## 주 비교 (α 1%, 실시간 행 F1)")
    w("")
    w("| 모델 | valid A / B (평균) | test A / B | test 미탐 행 A / B | test 오경보 행 A / B | test 기록 판정 F1 A / B | test부터 따로(R1) A / B |")
    w("|---|---|---|---|---|---|---|")
    table = []
    for name, r in rows:
        if r is None:
            continue
        va = f"{f(r.get('valid_A'))} / {f(r.get('valid_B'))} ({f(r.get('valid_mean', (r.get('valid_A', np.nan) + r.get('valid_B', np.nan)) / 2))})"
        w(f"| {name} | {va} | {f(r.get('test_A'))} / {f(r.get('test_B'))} | {f(r.get('test_fn_A'))} / {f(r.get('test_fn_B'))} | "
          f"{f(r.get('test_fp_A'))} / {f(r.get('test_fp_B'))} | {f(r.get('test_record_A'))} / {f(r.get('test_record_B'))} | "
          f"{f(r.get('test_only_A'))} / {f(r.get('test_only_B'))} |")
        table.append(dict(name=name, **r))
    out["main_table"] = table
    if singles:
        sv = pd.DataFrame(singles)
        sv["valid_mean"] = (sv.valid_A + sv.valid_B) / 2
        sv["test_mean"] = (sv.test_A + sv.test_B) / 2
        w("")
        w(f"- 단일 시드 6개(s0~s5) valid 평균 {f(sv.valid_mean.mean(), 4)} (범위 {f(sv.valid_mean.min(), 4)}~{f(sv.valid_mean.max(), 4)}), "
          f"test 평균 {f(sv.test_mean.mean(), 4)} (범위 {f(sv.test_mean.min(), 4)}~{f(sv.test_mean.max(), 4)})")
        out["singles"] = sv.round(6).to_dict("records")
    w("")

    # ---------------- α 민감도 (PROTOCOL.md 6절)
    t3, r3 = pd.read_csv(H.OUT / "03_test.csv"), pd.read_csv(H.OUT / "03_test_refs.csv")
    lv = f"lx:{sel['track_L']['cfg']}:{sel['track_L']['scoring']}:e345"
    sens = []
    for a in H.ALPHAS:
        for name, df, col, key, rule in (("보완 LSTM e345", t3, "variant", lv, "none"), ("보완 LSTM+R1 e345", t3, "variant", lv, "R1"),
                                         ("v2", r3, "model", "v2", None), ("v2+R1", r3, "model", "v2+H1", None),
                                         ("v2+R1+R2", r3, "model", "v2+H1+H2", None)):
            q = df[(df[col] == key) & (df.alpha == a) & (df["mode"] == "realtime")]
            if rule is not None:
                q = q[q.rule == rule]
            d = dict(alpha=a, model=name)
            for reg in ("valid", "test"):
                for s in H.SPLITS:
                    x = q[(q.regime == reg) & (q.split == s)].iloc[0]
                    d[f"{reg}_{s}"] = float(x.f1)
                    if reg == "test":
                        d[f"test_fp_{s}"], d[f"test_fn_{s}"] = int(x.fp), int(x.fn)
            d["valid_mean"] = (d["valid_A"] + d["valid_B"]) / 2
            sens.append(d)
    sens = pd.DataFrame(sens)
    out["alpha_sensitivity"] = sens.round(4).to_dict("records")
    w("## α 민감도 (실시간 행 F1, test 오경보·미탐 행)")
    w("")
    w("| α | 모델 | valid 평균 | test A / B | test 오경보 행 A / B | test 미탐 행 A / B |")
    w("|---|---|---|---|---|---|")
    for r in sens.to_dict("records"):
        w(f"| {int(r['alpha'] * 100)}% | {r['model']} | {f(r['valid_mean'])} | {f(r['test_A'])} / {f(r['test_B'])} | "
          f"{r['test_fp_A']} / {r['test_fp_B']} | {r['test_fn_A']} / {r['test_fn_B']} |")
    w("")
    # 보고서(준용 PC)의 lstm20 값
    tv, tt = pd.read_csv(H.TVT / "outputs/tvt_valid.csv"), pd.read_csv(H.TVT / "outputs/tvt_test.csv")
    rep = {nm: df[(df.model == "lstm20") & (df.alpha == H.PRIMARY_ALPHA) & (df["mode"] == "realtime")].set_index("split").f1.round(3).to_dict()
           for nm, df in (("valid", tv), ("test", tt))}
    out["lstm20_report_values"] = rep
    w(f"- 보고서(준용 PC)의 lstm20: valid {rep['valid']['A']} / {rep['valid']['B']}, test {rep['test']['A']} / {rep['test']['B']}")
    w("")

    # ---------------- 운전 상태별 오경보 (분할 B valid+test 정상 300기록)
    st = pd.read_csv(H.OUT / "04_states.csv")
    w("## 운전 상태별 오경보 기록 수 (분할 B, valid+test 정상 300기록, 경보가 1행이라도 난 기록)")
    models = ["start:e012", "L:e345", "L:e012", "v2", "L+R1:e345", "v2+R1", "v2+R1+R2"]
    for a in H.ALPHAS:
        q = st[(st.split == "B") & (st.alpha == a) & (st.part == "valid+test") & st.model.isin(models)]
        pv = q.pivot(index="state", columns="model", values="fa_records").reindex(["quiet", "busy_low", "busy_mid", "busy_high", "busy_short", "all"])
        n = q[q.model == "v2"].set_index("state").records
        pv.insert(0, "기록 수", n)
        w(f"\nα {int(a * 100)}%\n")
        w(pv[[c for c in ["기록 수"] + models if c in pv.columns]].to_markdown())
        out[f"states_B_alpha{int(a * 100)}"] = pv.reset_index().to_dict("records")
    # 오경보 구조: 분할 B test 정상 기록에서 경보 기록 수와 경보 행 수(LSTM 오경보가 한 기록에 몰리는지)
    w("\n분할 B test 정상 180기록의 경보 기록 수 / 경보 행 수 (α 1·3·5%)\n")
    for m in ("L:e345", "v2", "L+R1:e345", "v2+R1"):
        recs = st[(st.split == "B") & (st.part == "test") & (st.state == "all") & (st.model == m)].set_index("alpha").fa_records
        rowsfp = sens[sens.model == {"L:e345": "보완 LSTM e345", "v2": "v2", "L+R1:e345": "보완 LSTM+R1 e345", "v2+R1": "v2+R1"}[m]].set_index("alpha").test_fp_B
        w(f"- {m}: " + ", ".join(f"α {int(a * 100)}% {int(recs[a])}기록·{int(rowsfp[a])}행" for a in H.ALPHAS))
    w("")

    # ---------------- 미탐 위치 (test, A+B)
    mp_ = pd.read_csv(H.OUT / "04_miss_position.csv")
    q = mp_[(mp_.part == "test") & mp_.model.isin(["start:e012", "L:e345", "v2"])].groupby(["model", "pos_bin"]).missed.sum().unstack()
    w("## test 미탐 행의 기록 안 위치 (분할 A+B 합)")
    w(q[[c for c in ["0", "1", "2~7", "8~19", "20+"] if c in q.columns]].to_markdown())
    w("")

    # ---------------- 강건성
    if rob:
        pod = pd.read_csv(H.OUT / "05_v1_pod.csv")
        cols = [c for c in pod.columns if c.endswith("|detected")]
        w("## 강건성: 인공 주입 탐지율 (test 정상 기록, α 1%)")
        show = pod[pod.strength > 0].copy()
        show.columns = [c.replace("|detected", "") for c in show.columns]
        w(show.round(3).to_markdown(index=False))
        loss = pd.read_csv(H.OUT / "05_v2_loss.csv")
        lp = loss.groupby(["split", "target", "multiplier"])[[c for c in loss.columns if c.endswith("|detected")]].mean().reset_index()
        lp.columns = [c.replace("|detected", "") for c in lp.columns]
        w("\n## 강건성: 진폭 감소(V2) 탐지율\n")
        w(lp.round(3).to_markdown(index=False))
        v5 = pd.read_csv(H.OUT / "05_v5.csv")
        w("\n## 강건성: V5 교락 시험 (경보 기록 비율)\n")
        w(v5.pivot_table(index=["split", "test", "level"], columns="model", values="rate").round(4).to_markdown())
        out["v5"] = v5.to_dict("records")
        out["determinism"] = rob.get("determinism")
        out["v2_matches_tvt_validation"] = rob.get("v2_matches_tvt_validation")
    w("")

    # ---------------- 교체 검토 조건 (PROTOCOL.md 7절)
    def checks(lstm_label, ref_label, lrow, rrow, v1ref):
        res = {}
        res["1_valid_mean"] = dict(lstm=lrow["valid_mean"], ref=rrow["valid_mean"], ok=bool(lrow["valid_mean"] >= rrow["valid_mean"] - 0.002))
        res["2_test_AB"] = dict(lstm=[lrow["test_A"], lrow["test_B"]], ref=[rrow["test_A"], rrow["test_B"]],
                                ok=bool(lrow["test_A"] >= rrow["test_A"] - 0.01 and lrow["test_B"] >= rrow["test_B"] - 0.01))
        b5 = st[(st.split == "B") & (st.alpha == 0.05) & (st.part == "valid+test") & (st.state == "all")].set_index("model").fa_records
        res["3_fa_B_alpha5"] = dict(lstm=int(b5[lstm_label]), ref=int(b5[ref_label]), ok=bool(b5[lstm_label] <= b5[ref_label]))
        if rob:
            d3 = pod[pod.family == "current_residual"]
            diff = d3[f"{v1ref[0]}|detected"] - d3[f"{v1ref[1]}|detected"]
            res["4_v1_current"] = dict(min_diff_pp=round(float(diff.min() * 100), 2), ok=bool((diff >= -0.05).all()))
            mr = v5[(v5.test == "abnormal_mean_removal") & (v5.level != "none") & (v5.model == v1ref[0])]
            jt = v5[(v5.test == "jitter_60.6Hz") & (v5.level.astype(str) == "0.1")].pivot(index="split", columns="model", values="rate")
            res["5_v5"] = dict(mean_removal_detected=mr[["split", "level", "alerted"]].to_dict("records"),
                               jitter01=jt[[v1ref[0], v1ref[2]]].round(4).to_dict("index"),
                               ok=bool((mr.alerted >= 20).all() and (jt[v1ref[0]] <= jt[v1ref[2]]).all()))
        res["all_ok"] = all(v["ok"] for v in res.values() if isinstance(v, dict) and "ok" in v)
        return res

    rl = {**e345, "valid_mean": (e345["valid_A"] + e345["valid_B"]) / 2}
    rv2 = {**refrow("v2"), "valid_mean": (refrow("v2")["valid_A"] + refrow("v2")["valid_B"]) / 2}
    out["checklist_L_vs_v2"] = checks("L:e345", "v2", rl, rv2, ("L:e345", "v2", "v2"))
    rlr = {**lr1_e345, "valid_mean": (lr1_e345["valid_A"] + lr1_e345["valid_B"]) / 2}
    rv2r = {**refrow("v2+H1"), "valid_mean": (refrow("v2+H1")["valid_A"] + refrow("v2+H1")["valid_B"]) / 2}
    out["checklist_LR1_vs_v2R1"] = checks("L+R1:e345", "v2+R1", rlr, rv2r, ("L:e345+R1", "v2+R1", "v2+R1"))
    w("## 교체 검토 조건 (PROTOCOL.md 7절, 실행 전 고정)")
    for k, title in (("checklist_L_vs_v2", "보완 LSTM(e345) ↔ v2"), ("checklist_LR1_vs_v2R1", "보완 LSTM+R1(e345) ↔ v2+R1")):
        w(f"\n### {title}\n")
        for item, v in out[k].items():
            if item == "all_ok":
                w(f"- **모두 충족: {v}**")
            else:
                w(f"- {item}: {'충족' if v['ok'] else '미충족'} — {json.dumps({kk: vv for kk, vv in v.items() if kk != 'ok'}, ensure_ascii=False, default=str)}")
    w("")
    w("## 사후 낙관 상한 (test 최고 e012 변형, 선택에 쓰지 않음)")
    for r, lst_ in comp["post_hoc_best_test_e012"].items():
        w(f"- {r}: " + "; ".join(f"`{x['variant']}` {x['f1']}" for x in lst_[:3]))
    (H.OUT / "06_summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    H.dump(out, H.OUT / "06_summary.json")
    print("\n".join(L))


if __name__ == "__main__":
    main()
