"""검증 3: 초모수 민감도. 분할 A·B는 그대로 두고 v2의 설계값을 바꿔 다시 적합·보정한다.

한 번에 하나(OAT): 주 창 5~10, 초반 창 없음·4~7, 전환 위치 7~50, AR 차수 없음·1~4, 꼬리 분위 0.90~0.99, 결합 fmax·Fisher·합, 알림 단위 10~50행.
전체 격자(factorial): 주 창 × 초반 창 × AR 차수 × 분위 × 결합(전환 위치 = 주 창이 처음 차는 위치, 단위 50행).
출력: redA2_02_hyper_oat.csv, redA2_02_hyper_grid.csv, redA2_02_hyper_records.npz(설정별 이상 기록 미탐·정상 알림)
"""
import itertools
import json
import time
from dataclasses import asdict

import numpy as np
import pandas as pd

import redA2_common as C

started = time.monotonic()
data = C.Data()
rec = np.arange(600)
PARTS = {sid: (rec[:t], rec[t:c], rec[c:e]) for sid, (t, c, e) in C.SPLITS.items()}


def evaluate(cfg, alphas=C.ALPHAS):
    out, per = [], {}
    for sid, (tr, ca, te) in PARTS.items():
        fit = C.Fitted(data, tr, ca, cfg)
        for alpha in alphas:
            s, a, n = C.summarize(fit, alpha, te)
            out.append(dict(config=cfg.label(), **{k: ("none" if v is None else v) for k, v in asdict(cfg).items()}, switch_pos=cfg.switch_pos,
                            split=sid, alpha=alpha, tails_ok=fit.ok, **s))
            per[(sid, alpha)] = dict(fn_by_record=a["fn_by_record"], detected=a["detected_by_record"], normal_alerted=n["normal_alerted"], fp=n["fp"])
    return out, per


# ---------------- 한 번에 하나
oat = []
variants = [("v2", C.V2), ("v1(초반 창·AR 없음)", C.V1)]
variants += [(f"w_late={w}", C.replace(C.V2, w_late=w, w_early=min(6, w - 1) if w > 6 else (w - 1 if w > 4 else None))) for w in (5, 6, 7, 9, 10)]
variants += [(f"w_late={w}(초반 6 유지)", C.replace(C.V2, w_late=w)) for w in (7, 9, 10, 12)]
variants += [(f"w_early={w}", C.replace(C.V2, w_early=w)) for w in (None, 4, 5, 7)]
variants += [(f"switch={s}", C.replace(C.V2, switch=s)) for s in (8, 9, 10, 12, 15, 20, 50)]
variants += [(f"ar_order={p}", C.replace(C.V2, ar_order=p)) for p in (None, 1, 3, 4)]
variants += [(f"q={q}", C.replace(C.V2, q=q)) for q in (.80, .90, .975, .99)]
variants += [(f"rule={r}", C.replace(C.V2, rule=r)) for r in ("fisher", "sum")]
variants += [(f"unit_rows={u}", C.replace(C.V2, unit_rows=u)) for u in (10, 20, 25, 40)]
for w in (4, 5, 6, 7, 9, 10, 12):
    data.sine("n", w); data.sine("a", w)
print(f"[{time.monotonic() - started:6.1f}s] 사인 점수 준비", flush=True)
for name, cfg in variants:
    rows, _ = evaluate(cfg)
    for r in rows:
        r["variant"] = name
    oat += rows
oat = pd.DataFrame(oat)
oat.to_csv(C.HERE / "redA2_02_hyper_oat.csv", index=False)
print(f"[{time.monotonic() - started:6.1f}s] OAT {len(variants)}개", flush=True)

# ---------------- 전체 격자
grid_rows, records = [], {}
configs = []
for wl, we, p, q, rule in itertools.product((5, 6, 7, 8, 9, 10), (None, 4, 5, 6, 7), (None, 1, 2, 3, 4), (.90, .95, .975, .99), ("fmax", "fisher", "sum")):
    if we is not None and we >= wl:
        continue
    configs.append(C.Config(w_late=wl, w_early=we, ar_order=p, q=q, rule=rule))
for i, cfg in enumerate(configs):
    rows, per = evaluate(cfg)
    grid_rows += rows
    for (sid, alpha), v in per.items():
        records[f"{cfg.label()}|{sid}|{alpha}|fn"] = v["fn_by_record"]
        records[f"{cfg.label()}|{sid}|{alpha}|det"] = v["detected"]
    if (i + 1) % 200 == 0:
        print(f"[{time.monotonic() - started:6.1f}s] 격자 {i + 1}/{len(configs)}", flush=True)
grid = pd.DataFrame(grid_rows)
grid.to_csv(C.HERE / "redA2_02_hyper_grid.csv", index=False)
np.savez_compressed(C.HERE / "redA2_02_hyper_records.npz", **records)
(C.HERE / "redA2_02_hyper_meta.json").write_text(json.dumps(dict(oat_variants=len(variants), grid_configs=len(configs),
                                                                 elapsed_s=round(time.monotonic() - started, 1)), ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[{time.monotonic() - started:6.1f}s] 격자 {len(configs)}개 완료", flush=True)
show = oat[np.isclose(oat.alpha, .01)].pivot_table(index="variant", columns="split", values=["fn", "normal_alerted", "abnormal_detected", "delay_max_s", "f1"], sort=False)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
print(show.to_string())
