"""검증 1: 분할 선택 민감도. v2 설정(초반 6→8, AR(2), q95, fmax, 단위 50행)은 그대로 두고 정상 분할만 바꾼다.

격자
  forward  학습 [0,t) · 보정 [t,t+c) · 평가 [t+c,600)      t = 150,160,…  c ∈ {100,120,150}, 평가 ≥ 60기록
  reverse  학습 [600−t,600) · 보정 [600−t−c,600−t) · 평가 [0,600−t−c)   (시간 역순: 뒤로 학습, 앞을 평가)
  window   forward·c=120의 평가를 60기록 창으로 나눈 것(팀 시간순 5창과 같은 방식의 조밀한 판)
  random   기록 단위 무작위 분할 300/120/180, 360/120/120 각 200회(교환가능할 때의 참고 분포, 시드 0~199)
출력: redA2_01_split_grid.csv(분할×α 지표), redA2_01_fp_records.csv(오경보 기록·경보 행 수), redA2_01_summary.json
"""
import json
import time

import numpy as np
import pandas as pd

import redA2_common as C

started = time.monotonic()
data = C.Data()
rec = np.arange(600)
rows, fp_rows = [], []


def run(kind, name, tr, ca, te, extra=None):
    fit = C.Fitted(data, tr, ca, C.V2)
    for alpha in C.ALPHAS:
        s, a, n = C.summarize(fit, alpha, te)
        test_rows = np.isin(data.seg["n"], te)
        inc = C.incident_counts(data.time["n"][test_rows].to_numpy(), data.seg["n"][test_rows], fit.units("n")[test_rows],
                                fit.alarm("n", alpha)[test_rows])
        rows.append(dict(kind=kind, split=name, n_train=len(tr), n_test=len(te), test_from=int(te.min()) if kind != "random" else -1,
                         test_to=int(te.max()) if kind != "random" else -1, alpha=alpha, **s,
                         incidents=len(inc), incidents_level2=sum(i["level"] == 2 for i in inc),
                         incident_multi_record=sum(len(i["records"]) > 1 for i in inc), **(extra or {})))
        for r, k in zip(n["alerted_records"], n["alerted_rows"]):
            fp_rows.append(dict(kind=kind, split=name, alpha=alpha, record=int(r), alarm_rows=int(k), record_rows=int(data.len["n"][data.seg["n"] == r][0])))
    return fit


for c in (100, 120, 150):
    for t in range(150, 600 - c - 60 + 1, 10):
        fit = run("forward", f"f_t{t}_c{c}", rec[:t], rec[t:t + c], rec[t + c:], dict(t=t, c=c))
        run("reverse", f"r_t{t}_c{c}", rec[600 - t:], rec[600 - t - c:600 - t], rec[:600 - t - c], dict(t=t, c=c))
        if c == 120:
            for start in range(t + c, 600 - 60 + 1, 60):
                te = rec[start:start + 60]
                for alpha in C.ALPHAS:
                    s, a, n = C.summarize(fit, alpha, te)
                    rows.append(dict(kind="window60", split=f"f_t{t}_c{c}_w{start}", n_train=t, n_test=60, test_from=start, test_to=start + 59,
                                     alpha=alpha, **s, t=t, c=c))
    print(f"[{time.monotonic() - started:6.1f}s] c={c} 완료", flush=True)

for sizes in ((300, 120, 180), (360, 120, 120)):
    for seed in range(200):
        perm = np.random.default_rng(seed).permutation(600)
        tr, ca, te = np.sort(perm[:sizes[0]]), np.sort(perm[sizes[0]:sizes[0] + sizes[1]]), np.sort(perm[sizes[0] + sizes[1]:])
        run("random", f"rand_{sizes[0]}_{sizes[1]}_{seed}", tr, ca, te, dict(t=sizes[0], c=sizes[1]))
    print(f"[{time.monotonic() - started:6.1f}s] random {sizes} 완료", flush=True)

table = pd.DataFrame(rows)
table.to_csv(C.HERE / "redA2_01_split_grid.csv", index=False)
pd.DataFrame(fp_rows).to_csv(C.HERE / "redA2_01_fp_records.csv", index=False)


def pct_rank(values, x, higher_is_better):
    """x보다 나쁜 분할의 비율과 같거나 나쁜 분할의 비율(백분위 범위)."""
    v = np.asarray(values, float)
    worse = (v < x).mean() if higher_is_better else (v > x).mean()
    tie = (v == x).mean()
    return dict(share_worse=round(float(worse), 4), share_equal=round(float(tie), 4), share_better=round(float(1 - worse - tie), 4))


summary = {}
for alpha in C.ALPHAS:
    fwd = table[table.kind.eq("forward") & np.isclose(table.alpha, alpha)]
    for label, pool in (("forward_all", fwd), ("forward_c120", fwd[fwd.c.eq(120)]),
                        ("reverse_all", table[table.kind.eq("reverse") & np.isclose(table.alpha, alpha)]),
                        ("window60", table[table.kind.eq("window60") & np.isclose(table.alpha, alpha)]),
                        ("random", table[table.kind.eq("random") & np.isclose(table.alpha, alpha)])):
        d = {}
        for col in ("normal_alert_rate", "fn", "f1", "abnormal_detected", "delay_max_s", "normal_level2_records", "incidents_level2", "fp"):
            if col not in pool or pool[col].isna().all():
                continue
            v = pool[col].to_numpy(float)
            d[col] = dict(n=int(len(v)), min=float(np.min(v)), q25=float(np.quantile(v, .25)), median=float(np.median(v)), q75=float(np.quantile(v, .75)),
                          max=float(np.max(v)), mean=float(np.mean(v)))
        d["share_zero_normal_alert"] = float((pool.normal_units_alerted == 0).mean())
        d["share_all_21_detected"] = float((pool.abnormal_detected == 21).mean())
        summary[f"alpha{alpha}_{label}"] = d
    for sid, (t, c) in (("A", (360, 120)), ("B", (300, 120))):
        me = fwd[fwd.t.eq(t) & fwd.c.eq(c)].iloc[0]
        for label, pool in (("forward_all", fwd), ("forward_c120", fwd[fwd.c.eq(120)])):
            summary[f"alpha{alpha}_{sid}_in_{label}"] = dict(
                value=dict(normal_alert_rate=float(me.normal_alert_rate), fn=int(me.fn), f1=float(me.f1), abnormal_detected=int(me.abnormal_detected)),
                normal_alert_rate=pct_rank(pool.normal_alert_rate, me.normal_alert_rate, False), fn=pct_rank(pool.fn, me.fn, False),
                f1=pct_rank(pool.f1, me.f1, True))
summary["elapsed_s"] = round(time.monotonic() - started, 1)
(C.HERE / "redA2_01_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in summary.items() if "_in_" in k}, ensure_ascii=False, indent=1))
