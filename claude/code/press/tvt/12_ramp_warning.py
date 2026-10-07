"""12단계(사후, test 채점 이후): 합성 열화(점점 커지는 고장)에서 경보 단계별 첫 경보가 열화 완성보다 얼마나 앞서는지 잰다(보고서 4.3절 †).

실제 이상은 처음부터 이상 상태라 '고장 전 경보'를 잴 수 없다(2.1절). 그래서 test 정상 흐름의 한 시점 t0부터 T분(2·5·10분)에 걸쳐
04와 같은 주입(예준 v3 Generator)의 강도를 기록마다 0에서 최대 강도까지 선형으로 키우고, 완성 뒤 1분은 최대 강도를 유지한다.
- 주입: 전류 파형(current_residual, 최대 강도 1), 진동 대역 잡음(band_noise, 상·하부, 1), 진동 감쇠 충격(damped_impulse, 상·하부, 4)
- 시작 시점: test 정상 흐름에서 열화 구간이 들어갈 수 있는 곳 4개(고르게), seed 11·29·47
- 모델: 2단계 판정 v2+R1+R2, 1단계(사전 잠금 모델) v2+R1, 기반 모델 v2(α 1%). 흐름은 t0 직전 기록부터 열화 끝 + 1분까지 시간순으로 이어 돌린다(R1 상태 포함)
- 지표: 열화 완성 전에 경보가 났는지, 선행 시간(완성 시각 − 첫 경보 시각, 분), 첫 경보 때의 강도 비율(0~1)
- 대조: 같은 구간을 주입 없이 돌려 열화 구간 안에서 경보가 난 비율(우연한 경보)
선택·잠금·최종 선정에는 쓰지 않는다. 출력: outputs/ramp_warning.csv, outputs/ramp_summary.json
실행: python code/press/tvt/12_ramp_warning.py --repo <팀 레포>
"""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

from lib import OUT, SPLITS, repo_arg, setup, v3_records

_spec = importlib.util.spec_from_file_location("tvt_v04", Path(__file__).with_name("04_validation.py"))
V04 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(V04)

RAMPS_MIN = (2, 5, 10)
HOLD_MIN = 1.0
N_STARTS = 4
FAMILIES = (("current_residual", 2, 1.0), ("band_noise", 0, 1.0), ("band_noise", 1, 1.0),
            ("damped_impulse", 0, 4.0), ("damped_impulse", 1, 4.0))
MODELS = ("v2+R1+R2", "v2+R1", "v2")


def run_split(M, normal, sid):
    D, v3 = M["D"], M["v3"]
    sp = D.split_normal(normal, D.segments(normal), sid)
    fin = V04.fit_split(M, sp["train"], sp["cal"])
    q_tr = D.quantize(D.inputs_only(sp["train"]), "matched")
    gen = v3.Generator(v3.features(v3_records(M, q_tr, "train")), sid)
    test = sp["test"].reset_index(drop=True)
    recs = V04.records_of(test, M)
    S = D.SENSORS
    X = test[S].to_numpy(float)
    ts = pd.to_datetime(test.TimeStamp).astype("datetime64[ns]").to_numpy()
    rec_t0 = np.array([ts[r[0]] for r in recs])
    minutes = lambda a, b: (a - b) / np.timedelta64(1, "s") / 60
    f_test = v3.features([V04.v3_record(M, X[idx], k) for k, idx in enumerate(recs)])
    scales = {}
    for fam, target, _ in FAMILIES:
        axis = f"v{target}_rms" if target < 2 else "i_residual"
        scales[(fam, target)] = gen.scales(f_test, axis)
    span = minutes(rec_t0[-1], rec_t0[0])
    rows = []
    for T in RAMPS_MIN:
        need = T + HOLD_MIN
        if span <= need:
            continue
        # 열화가 흐름 안에 들어가는 시작 기록 후보(첫 기록 다음부터) 가운데 고르게 4개
        cand = [k for k in range(1, len(recs)) if minutes(rec_t0[-1], rec_t0[k]) >= need]
        starts = [cand[int(i)] for i in np.linspace(0, len(cand) - 1, N_STARTS)]
        for k0 in starts:
            t0 = rec_t0[k0]
            win = [k for k in range(k0 - 1, len(recs)) if minutes(rec_t0[k], t0) <= need]
            idx_all = np.concatenate([recs[k] for k in win])
            for fam, target, smax in FAMILIES + (("none", -1, 0.0),):
                for seed in (V04.SEEDS if fam != "none" else V04.SEEDS[:1]):
                    sub = test.iloc[idx_all].reset_index(drop=True).copy()
                    frac_row = np.zeros(len(sub))
                    pos = 0
                    for k in win:
                        n = len(recs[k])
                        frac = float(np.clip(minutes(rec_t0[k], t0) / T, 0, 1)) if k >= k0 else 0.0
                        if fam != "none" and frac > 0:
                            rec, info = gen.inject(V04.v3_record(M, X[recs[k]], k), fam, target, smax * frac, seed, scales[(fam, target)][k])
                            if info["valid"]:
                                sub.loc[pos:pos + n - 1, S] = rec.x
                        frac_row[pos:pos + n] = frac if k >= k0 else -1
                        pos += n
                    r = fin.rows(sub)
                    rts = r["ts"]
                    in_ramp = frac_row >= 0
                    for m in MODELS:
                        a, _ = V04.Final.alarms(r, m)
                        hit = np.flatnonzero(a & in_ramp)
                        if len(hit):
                            i = hit[0]
                            first_min = float(minutes(rts[i], t0))
                            rows.append(dict(split=sid, ramp_min=T, start_rec=k0, family=fam, target=target, seed=seed, model=m,
                                             alarmed=True, first_min=first_min, lead_min=T - first_min, frac_at_alarm=float(frac_row[i]),
                                             before_complete=first_min < T))
                        else:
                            rows.append(dict(split=sid, ramp_min=T, start_rec=k0, family=fam, target=target, seed=seed, model=m,
                                             alarmed=False, first_min=np.nan, lead_min=np.nan, frac_at_alarm=np.nan, before_complete=False))
    return pd.DataFrame(rows)


def main():
    repo = repo_arg()
    M = setup(repo)
    normal, _, _ = M["D"].load(repo / "yejun/press_submission")
    t = pd.concat([run_split(M, normal, s) for s in SPLITS], ignore_index=True)
    t.to_csv(OUT / "ramp_warning.csv", index=False)
    t["kind"] = np.select([t.family == "current_residual", t.family == "none"], ["전류 파형", "대조(주입 없음)"], "진동")
    summ = {}
    for (kind, T, m), g in t.groupby(["kind", "ramp_min", "model"]):
        hit = g[g.alarmed]
        summ[f"{kind}|{T}분|{m}"] = dict(n=int(len(g)), alarm_rate=round(float(g.alarmed.mean()), 4),
                                        before_complete_rate=round(float(g.before_complete.mean()), 4),
                                        lead_median_min=round(float(hit.lead_min.median()), 2) if len(hit) else None,
                                        frac_at_alarm_median=round(float(hit.frac_at_alarm.median()), 3) if len(hit) else None)
    (OUT / "ramp_summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summ, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
